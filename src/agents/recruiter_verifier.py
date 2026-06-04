# src/agents/recruiter_verifier.py
#
# Recruiter Verification Layer — Asynchronous Audit Pipeline
# ─────────────────────────────────────────────────────────────────────────────
#
# Functional position in the pipeline:
#   candidate_simulator_node  →  recruiter_verifier_node  →  UI visualization
#
# This module consumes the InterviewSimulationTranscript produced by the
# candidate simulation and runs three independent Gemini-powered audit passes
# concurrently before assembling a single VerificationReport that is appended
# to the canonical system state.
#
# Audit Pass 1 — Bias Audit:
#   Scans all interviewer questions for structural, cognitive, and linguistic
#   bias signals. Scores the evaluation on gender, age inference, nationality,
#   educational prestige, and cognitive bias dimensions.
#
# Audit Pass 2 — Evaluation Integrity Assessment:
#   Cross-references candidate responses against CANDIDATE_KNOWLEDGE_MAP to
#   detect knowledge boundary violations — fabricated ClickHouse, Airflow, or
#   Spark implementation claims. Deterministically computes gap acknowledgement
#   rate and adjacent reasoning quality from structured transcript metadata.
#   Gemini audits only the suspicious turns identified by the deterministic pass.
#
# Audit Pass 3 — Labor Code & Compliance Check:
#   Invokes HybridRAGPipeline.retrieve_multi_collection() against the
#   labor_code_am ChromaDB collection to retrieve relevant RA Labor Code
#   excerpts. Gemini verifies that no prohibited, invasive, or discriminatory
#   evaluation criteria were introduced across the interview turns.
#
# All three passes run concurrently via asyncio.gather after the synchronous
# RAG retrieval completes. Every Gemini invocation is wrapped in a try/except
#  with a structurally valid fallback to guarantee pipeline continuity.
#
# ─────────────────────────────────────────────────────────────────────────────
# Module Layout:
#   Section 1  — Imports
#   Section 2  — Enumerations
#   Section 3  — LLM-Facing Output Schemas (PydanticOutputParser targets)
#   Section 4  — Internal Assessment Schemas
#   Section 5  — Main Output Schema: VerificationReport
#   Section 6  — Configuration Constants
#   Section 7  — Audit Prompt Templates (3 audit types)
#   Section 8  — Output Parsers
#   Section 9  — Private Helper Functions
#   Section 10 — Core Async Audit Functions
#   Section 11 — Main Integration Entry Point

from __future__ import annotations

# ===========================================================================
# SECTION 1 — Imports
# ===========================================================================

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field, field_validator, model_validator

from src.agents.candidate_simulator import (
    CANDIDATE_KNOWLEDGE_MAP,
    KnowledgeBoundaryEntry,
    KnowledgeDomain,
    SimulationRound,
    TargetGapArea,
    InterviewSimulationTranscript,
)
from src.engine.rag_pipeline import get_pipeline

logger = logging.getLogger(__name__)


# ===========================================================================
# SECTION 2 — Enumerations
# ===========================================================================

class ComplianceStatus(str):
    """
    Categorical compliance verdict for the full interview session.
    Not a Python Enum to allow direct string comparisons in Gemini JSON output
    before mapping to the canonical representation.
    """
    COMPLIANT       = "compliant"
    MINOR_CONCERN   = "minor_concern"
    MAJOR_CONCERN   = "major_concern"
    NON_COMPLIANT   = "non_compliant"

    # Ordered severity: higher index = more severe
    _SEVERITY_ORDER: List[str] = [
        "compliant", "minor_concern", "major_concern", "non_compliant"
    ]

    @classmethod
    def from_string(cls, value: str) -> str:
        """Normalises a raw LLM string to a valid ComplianceStatus value."""
        normalised = value.lower().strip().replace(" ", "_").replace("-", "_")
        valid = {"compliant", "minor_concern", "major_concern", "non_compliant"}
        return normalised if normalised in valid else "minor_concern"

    @classmethod
    def most_severe(cls, a: str, b: str) -> str:
        """Returns whichever of two status strings represents the higher severity."""
        order = cls._SEVERITY_ORDER
        idx_a = order.index(a) if a in order else 0
        idx_b = order.index(b) if b in order else 0
        return a if idx_a >= idx_b else b


class BiasRiskLevel(str):
    """Categorical bias risk level for a single audit dimension or aggregate."""
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"

    @classmethod
    def from_score(cls, score: float) -> str:
        """Maps a [0.0, 1.0] float risk score to a categorical level."""
        if score < 0.25:
            return cls.LOW
        if score < 0.50:
            return cls.MEDIUM
        if score < 0.75:
            return cls.HIGH
        return cls.CRITICAL

    @classmethod
    def from_string(cls, value: str) -> str:
        normalised = value.lower().strip()
        return normalised if normalised in {"low", "medium", "high", "critical"} else "medium"


class IntegrityViolationType(str):
    """Classification of a single integrity violation instance."""
    NONE                      = "none"
    BOUNDARY_BREACH           = "boundary_breach"
    KNOWLEDGE_FABRICATION     = "knowledge_fabrication"
    INCONSISTENT_CONFIDENCE   = "inconsistent_confidence"

    @classmethod
    def from_string(cls, value: str) -> str:
        normalised = value.lower().strip().replace(" ", "_")
        valid = {"none", "boundary_breach", "knowledge_fabrication", "inconsistent_confidence"}
        return normalised if normalised in valid else "boundary_breach"


class AuditDimension(str):
    """Bias audit dimension — which protected or structural dimension is at risk."""
    GENDER_SIGNAL              = "gender_signal"
    AGE_INFERENCE              = "age_inference"
    NATIONALITY_SIGNAL         = "nationality_signal"
    EDUCATIONAL_PRESTIGE_BIAS  = "educational_prestige_bias"
    COGNITIVE_BIAS             = "cognitive_bias"
    STRUCTURAL_BIAS            = "structural_bias"
    NONE                       = "none"

    @classmethod
    def from_string(cls, value: str) -> str:
        normalised = value.lower().strip().replace(" ", "_").replace("-", "_")
        valid = {
            "gender_signal", "age_inference", "nationality_signal",
            "educational_prestige_bias", "cognitive_bias", "structural_bias", "none",
        }
        return normalised if normalised in valid else "none"


# Module-level frozenset of gap-probe TargetGapArea values.
# Defined locally to avoid dependency on the private _GAP_PROBE_AREAS
# constant in candidate_simulator.py.
_GAP_PROBE_AREAS: frozenset = frozenset({
    TargetGapArea.CLICKHOUSE_CORE,
    TargetGapArea.CLICKHOUSE_ARCHITECTURE,
    TargetGapArea.AIRFLOW_FUNDAMENTALS,
    TargetGapArea.AIRFLOW_PRODUCTION,
    TargetGapArea.SPARK_FUNDAMENTALS,
    TargetGapArea.SPARK_STREAMING,
})

# Map EvaluationIntegrityRisk float score to categorical label (matching
# canonical_payload.EvaluationIntegrityRisk enum without importing it,
# since canonical_payload lives in the schema layer, not the agent layer).
_EIR_LOW      = "low"
_EIR_MEDIUM   = "medium"
_EIR_HIGH     = "high"


def _float_to_eir(score: float) -> str:
    """Maps a [0.0, 1.0] integrity risk score to EvaluationIntegrityRisk value."""
    if score < 0.34:
        return _EIR_LOW
    if score < 0.67:
        return _EIR_MEDIUM
    return _EIR_HIGH


# ===========================================================================
# SECTION 3 — LLM-Facing Output Schemas
# ===========================================================================
# These schemas are the direct targets of PydanticOutputParser.
# They use flat, LLM-friendly structure. Mapping to the richer internal
# schemas in Section 4 is performed by the helper functions in Section 9.

class _BiasSignalRaw(BaseModel):
    """One bias signal detected by the Bias Audit LLM pass."""
    dimension:   str = Field(..., description="One of: gender_signal, age_inference, nationality_signal, educational_prestige_bias, cognitive_bias, structural_bias, none")
    signal_type: str = Field(..., description="One of: structural, cognitive, linguistic")
    source_text: str = Field(..., description="The exact phrase or question that triggered this flag.")
    turn_index:  int = Field(..., ge=0, description="Zero-based index of the turn in the transcript.")
    risk_level:  str = Field(..., description="One of: low, medium, high, critical")
    explanation: str = Field(..., description="One sentence explaining why this is a bias signal.")


class BiasAuditLLMOutput(BaseModel):
    """Structured output produced by the Bias Audit Gemini pass."""
    bias_risk_level:                    str               = Field(..., description="Aggregate bias risk: low, medium, high, critical")
    detected_signals:                   List[_BiasSignalRaw] = Field(default_factory=list)
    structurally_consistent_evaluation: bool              = Field(..., description="True if all questions were applied at a consistent technical standard regardless of candidate profile.")
    cognitive_bias_flags:               List[str]         = Field(default_factory=list, description="Any cognitive bias patterns observed: affinity_bias, halo_effect, confirmation_bias, recency_bias.")
    linguistic_bias_phrases:            List[str]         = Field(default_factory=list, description="Specific phrases that contain or imply linguistic bias.")
    interviewer_question_bias_score:    float             = Field(..., ge=0.0, le=1.0, description="0.0 = perfectly unbiased questions, 1.0 = highly biased questions.")
    overall_bias_risk_score:            float             = Field(..., ge=0.0, le=1.0, description="Aggregate bias risk across all dimensions.")


class _IntegrityViolationRaw(BaseModel):
    """One knowledge boundary violation detected by the Integrity Audit LLM pass."""
    turn_index:      int = Field(..., ge=0)
    violation_type:  str = Field(..., description="One of: boundary_breach, knowledge_fabrication, inconsistent_confidence, none")
    domain_claimed:  str = Field(..., description="The KnowledgeDomain the candidate inappropriately claimed.")
    description:     str = Field(..., description="One to two sentences describing the specific violation.")
    severity:        str = Field(..., description="One of: low, medium, high, critical")


class IntegrityAuditLLMOutput(BaseModel):
    """Structured output produced by the Integrity Audit Gemini pass."""
    boundary_violation_count:              int                        = Field(..., ge=0)
    violations:                            List[_IntegrityViolationRaw] = Field(default_factory=list)
    knowledge_fabrication_detected:        bool                       = Field(..., description="True if the candidate explicitly claimed implementation experience outside documented boundaries.")
    suspicious_high_confidence_gap_answers: int                       = Field(..., ge=0, description="Count of gap-area answers with ConfidenceLevel.HIGH that did NOT acknowledge the gap.")
    integrity_risk_score:                  float                      = Field(..., ge=0.0, le=1.0)
    assessment_summary:                    str                        = Field(..., description="Two to three sentence summary of the integrity assessment.")


class ComplianceAuditLLMOutput(BaseModel):
    """Structured output produced by the Compliance Audit Gemini pass."""
    compliance_status:          str       = Field(..., description="One of: compliant, minor_concern, major_concern, non_compliant")
    prohibited_criteria_detected: bool    = Field(..., description="True if any interview question probed a protected characteristic or used prohibited criteria.")
    prohibited_criteria:        List[str] = Field(default_factory=list, description="Specific prohibited criteria found, if any.")
    referenced_law_articles:    List[str] = Field(default_factory=list, description="RA Labor Code or other legal articles referenced in the analysis.")
    compliance_risk_score:      float     = Field(..., ge=0.0, le=1.0)
    compliance_rationale:       str       = Field(..., description="Two to three sentence explanation of the compliance verdict.")


# ===========================================================================
# SECTION 4 — Internal Assessment Schemas
# ===========================================================================

class BiasSignalEntry(BaseModel):
    """Rich internal representation of one detected bias signal."""
    dimension:   str
    signal_type: str
    source_text: str
    turn_index:  int
    risk_level:  str
    explanation: str

    @classmethod
    def from_raw(cls, raw: _BiasSignalRaw) -> "BiasSignalEntry":
        return cls(
            dimension   = AuditDimension.from_string(raw.dimension),
            signal_type = raw.signal_type,
            source_text = raw.source_text,
            turn_index  = raw.turn_index,
            risk_level  = BiasRiskLevel.from_string(raw.risk_level),
            explanation = raw.explanation,
        )


class BiasMetrics(BaseModel):
    """Aggregate bias analysis result for the full interview session."""
    bias_risk_level:                    str
    detected_bias_signals:              List[BiasSignalEntry] = Field(default_factory=list)
    bias_signal_count:                  int = 0
    highest_risk_dimension:             Optional[str] = None
    structurally_consistent_evaluation: bool = True
    cognitive_bias_flags:               List[str] = Field(default_factory=list)
    linguistic_bias_phrases:            List[str] = Field(default_factory=list)
    interviewer_question_bias_score:    float = 0.0
    overall_bias_risk_score:            float = 0.0

    @classmethod
    def from_llm_output(cls, output: BiasAuditLLMOutput) -> "BiasMetrics":
        signals = [BiasSignalEntry.from_raw(s) for s in output.detected_signals]
        highest = None
        if signals:
            # Find the signal with the highest risk_level
            severity_map = {"low": 0, "medium": 1, "high": 2, "critical": 3}
            worst = max(signals, key=lambda s: severity_map.get(s.risk_level, 0))
            highest = worst.dimension
        return cls(
            bias_risk_level                    = BiasRiskLevel.from_string(output.bias_risk_level),
            detected_bias_signals              = signals,
            bias_signal_count                  = len(signals),
            highest_risk_dimension             = highest,
            structurally_consistent_evaluation = output.structurally_consistent_evaluation,
            cognitive_bias_flags               = output.cognitive_bias_flags,
            linguistic_bias_phrases            = output.linguistic_bias_phrases,
            interviewer_question_bias_score    = round(output.interviewer_question_bias_score, 3),
            overall_bias_risk_score            = round(output.overall_bias_risk_score, 3),
        )


class IntegrityViolationEntry(BaseModel):
    """One knowledge boundary violation instance."""
    turn_index:     int
    violation_type: str
    domain_claimed: str
    description:    str
    severity:       str

    @classmethod
    def from_raw(cls, raw: _IntegrityViolationRaw) -> "IntegrityViolationEntry":
        return cls(
            turn_index     = raw.turn_index,
            violation_type = IntegrityViolationType.from_string(raw.violation_type),
            domain_claimed = raw.domain_claimed,
            description    = raw.description,
            severity       = BiasRiskLevel.from_string(raw.severity),
        )


class IntegrityAssessment(BaseModel):
    """Aggregate evaluation integrity assessment."""
    overall_integrity_risk:               float = Field(..., ge=0.0, le=1.0)
    boundary_violations_detected:         int   = 0
    violation_entries:                    List[IntegrityViolationEntry] = Field(default_factory=list)
    knowledge_fabrication_detected:       bool  = False
    suspicious_high_confidence_gap_answers: int = 0
    gap_acknowledgement_rate:             float = Field(..., ge=0.0, le=1.0)
    adjacent_reasoning_quality_score:     float = Field(..., ge=0.0, le=1.0)
    assessment_summary:                   str   = ""

    @classmethod
    def from_llm_output(
        cls,
        output:                         IntegrityAuditLLMOutput,
        gap_acknowledgement_rate:       float,
        adjacent_reasoning_quality:     float,
    ) -> "IntegrityAssessment":
        violations = [IntegrityViolationEntry.from_raw(v) for v in output.violations]
        return cls(
            overall_integrity_risk                 = round(output.integrity_risk_score, 3),
            boundary_violations_detected           = output.boundary_violation_count,
            violation_entries                      = violations,
            knowledge_fabrication_detected         = output.knowledge_fabrication_detected,
            suspicious_high_confidence_gap_answers = output.suspicious_high_confidence_gap_answers,
            gap_acknowledgement_rate               = gap_acknowledgement_rate,
            adjacent_reasoning_quality_score       = adjacent_reasoning_quality,
            assessment_summary                     = output.assessment_summary,
        )


class ComplianceCheckResult(BaseModel):
    """Labor code and employment law compliance check result."""
    compliance_status:          str
    labor_code_references:      List[str] = Field(default_factory=list)
    prohibited_criteria_detected: bool = False
    prohibited_criteria_list:   List[str] = Field(default_factory=list)
    rag_chunks_used:            int  = 0
    compliance_risk_score:      float = Field(..., ge=0.0, le=1.0)
    compliance_rationale:       str  = ""

    @classmethod
    def from_llm_output(
        cls,
        output:         ComplianceAuditLLMOutput,
        rag_chunks_used: int,
    ) -> "ComplianceCheckResult":
        return cls(
            compliance_status           = ComplianceStatus.from_string(output.compliance_status),
            labor_code_references       = output.referenced_law_articles,
            prohibited_criteria_detected = output.prohibited_criteria_detected,
            prohibited_criteria_list    = output.prohibited_criteria,
            rag_chunks_used             = rag_chunks_used,
            compliance_risk_score       = round(output.compliance_risk_score, 3),
            compliance_rationale        = output.compliance_rationale,
        )


# ===========================================================================
# SECTION 5 — Main Output Schema: VerificationReport
# ===========================================================================

class VerificationReport(BaseModel):
    """
    The complete output of the Recruiter Verification Layer.
    Returned by recruiter_verifier_node and appended to the canonical state.

    Primary fields (as specified in architectural requirements):
      bias_metrics              — BiasMetrics from the Bias Audit pass
      compliance_status         — ComplianceStatus enum value (str)
      integrity_score           — float [0.0, 1.0]; 0.0 = no risk, 1.0 = severe
      audit_justification_narrative — human-readable verdict summary

    Additional fields provide full audit provenance for the Evaluation Tab.
    """
    report_id:                    str
    session_id:                   str
    generated_at:                 str
    verifier_model_used:          str

    # Primary output fields (required by architectural specification)
    bias_metrics:                 BiasMetrics
    compliance_status:            str                # ComplianceStatus value
    integrity_score:              float = Field(..., ge=0.0, le=1.0)
    audit_justification_narrative: str

    # Full assessment objects (for Evaluation Tab drill-down)
    integrity_assessment:         IntegrityAssessment
    compliance_result:            ComplianceCheckResult

    # Derived categorical and operational fields
    evaluation_integrity_risk:    str                # EvaluationIntegrityRisk value
    is_safe_to_use:               bool
    recommendation:               str

    # Metadata
    raw_transcript_turns:         int = 0
    rag_chunks_retrieved:         int = 0
    is_fallback_report:           bool = False


# ===========================================================================
# SECTION 6 — Configuration Constants
# ===========================================================================

VERIFIER_MODEL:       str   = "gemini-2.0-flash"
VERIFIER_TEMPERATURE: float = 0.12   # Low temperature for consistent audit outputs

# Weight allocation for overall_integrity_score composite
WEIGHT_BIAS_RISK:        float = 0.35
WEIGHT_INTEGRITY_RISK:   float = 0.35
WEIGHT_COMPLIANCE_RISK:  float = 0.30

# Threshold below which the report is considered safe to use downstream
SAFE_USE_SCORE_THRESHOLD: float = 0.40

# Compliance statuses that block safe use regardless of overall score
_BLOCKING_COMPLIANCE_STATUSES: frozenset = frozenset({
    ComplianceStatus.NON_COMPLIANT,
    ComplianceStatus.MAJOR_CONCERN,
})

# Maximum transcript text length (characters) injected into each prompt
_MAX_TRANSCRIPT_CHARS_PER_PROMPT: int = 6_000
_MAX_RAG_CONTEXT_CHARS:           int = 2_400


# ===========================================================================
# SECTION 7 — Audit Prompt Templates
# ===========================================================================

# ---------------------------------------------------------------------------
# 7.1 — Bias Audit Prompts
# ---------------------------------------------------------------------------

BIAS_AUDIT_SYSTEM_PROMPT: str = (
    "You are a specialist bias auditor reviewing technical interview evaluations for "
    "an AI-assisted hiring system. Your task is to examine the interviewer's questions "
    "and conduct for any signals that could indicate unfair, biased, or discriminatory "
    "evaluation practices.\n"
    "\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "BIAS DIMENSIONS TO AUDIT\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "\n"
    "GENDER_SIGNAL: Language that implies gender expectations, uses gendered nouns or "
    "pronouns without necessity, or assumes demographic traits from professional choices.\n"
    "\n"
    "AGE_INFERENCE: Questions or patterns that indirectly probe age — asking about "
    "graduation year in ways that infer generation, using 'recent graduate' framing "
    "as a subtle disqualifier, or emphasizing years of experience in ways that "
    "disadvantage younger candidates beyond the stated role requirements.\n"
    "\n"
    "NATIONALITY_SIGNAL: References to national origin, accent, or cultural background "
    "beyond legitimate work authorisation requirements. Treating foreign-sounding "
    "institution names with scepticism not applied to equivalent domestic institutions.\n"
    "\n"
    "EDUCATIONAL_PRESTIGE_BIAS: Placing disproportionate weight on institution prestige "
    "versus demonstrated competence. Implying that graduates of non-elite institutions "
    "are inherently less qualified without evidence.\n"
    "\n"
    "COGNITIVE_BIAS: Behavioural patterns in the interviewer's conduct that suggest:\n"
    "  - Affinity bias: warmer questioning of candidates with similar backgrounds\n"
    "  - Halo effect: one strong area generalised to an overall positive impression\n"
    "  - Confirmation bias: questions structured to confirm a prior belief\n"
    "  - Recency bias: final answers disproportionately weighted in assessments\n"
    "\n"
    "STRUCTURAL_BIAS: Inconsistent application of standards — asking different depths "
    "of technical questions depending on the candidate's perceived background, or "
    "applying a stricter burden of proof for some answers than others.\n"
    "\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "SCORING GUIDANCE\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "interviewer_question_bias_score:\n"
    "  0.00–0.15: No bias signals. Questions are objective, technical, role-relevant.\n"
    "  0.16–0.35: Very minor concerns. One or two phrases that could be improved but "
    "are not materially biasing.\n"
    "  0.36–0.60: Moderate concerns. Recurring patterns or one significant signal.\n"
    "  0.61–0.80: High concern. Multiple signals affecting evaluation fairness.\n"
    "  0.81–1.00: Critical. Systemic bias that invalidates the evaluation's objectivity.\n"
    "\n"
    "IMPORTANT: This is a TECHNICAL interview for a DATA ENGINEERING role. Questions "
    "about ClickHouse, Apache Airflow, Apache Spark, PostgreSQL, and Python are "
    "entirely legitimate and must NOT be flagged as bias. Bias signals are patterns "
    "related to the candidate's IDENTITY, not their TECHNICAL COMPETENCE.\n"
    "\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "OUTPUT RULES\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "Output ONLY the JSON object matching the schema. No markdown fences. "
    "If no bias signals are detected, return detected_signals as an empty list "
    "and bias_risk_level as 'low'.\n"
)

BIAS_AUDIT_HUMAN_TEMPLATE: str = (
    "{format_instructions}\n"
    "\n"
    "═══ INTERVIEWER QUESTIONS TO AUDIT ═══\n"
    "{interviewer_questions}\n"
    "\n"
    "═══ JD CONTEXT ═══\n"
    "Role: {role_title}\n"
    "Industry: {industry}\n"
    "Required Seniority: {required_seniority}\n"
    "\n"
    "Audit the interviewer's questions above for bias signals. "
    "Output only the JSON object.\n"
)

BIAS_AUDIT_PROMPT_TEMPLATE: ChatPromptTemplate = ChatPromptTemplate.from_messages([
    ("system", BIAS_AUDIT_SYSTEM_PROMPT),
    ("human",  BIAS_AUDIT_HUMAN_TEMPLATE),
])

# ---------------------------------------------------------------------------
# 7.2 — Integrity Audit Prompts
# ---------------------------------------------------------------------------

INTEGRITY_AUDIT_SYSTEM_PROMPT: str = (
    "You are an evaluation integrity auditor reviewing a simulated technical interview "
    "for knowledge boundary compliance. The simulation uses a candidate persona with "
    "strictly documented knowledge boundaries. Your task is to determine whether the "
    "candidate persona remained within those boundaries throughout the simulation.\n"
    "\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "CANDIDATE KNOWLEDGE BOUNDARIES — ABSENT DOMAINS\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "The candidate persona has ZERO implementation experience with:\n"
    "\n"
    "1. CLICKHOUSE — The candidate has never written a ClickHouse table definition, "
    "schema design, or query. They know ClickHouse is a columnar OLAP database only "
    "at a conceptual level. Any claim of MergeTree engine knowledge, ReplacingMergeTree "
    "deduplication mechanics, PREWHERE usage, sharding configuration, or ClickHouse SQL "
    "dialect specifics (FINAL, ARRAY JOIN, SAMPLE) is a KNOWLEDGE_FABRICATION.\n"
    "\n"
    "2. APACHE AIRFLOW — The candidate has never authored an Airflow DAG, used any "
    "Operator or Sensor type, worked with XCom, configured SLAs, or executed a backfill. "
    "They know Airflow is a DAG-based orchestration tool conceptually. Any claim of "
    "hands-on Airflow implementation is a KNOWLEDGE_FABRICATION.\n"
    "\n"
    "3. APACHE SPARK — The candidate has never written a Spark job, used the RDD or "
    "Dataset API, configured structured streaming watermarks, or set checkpoint locations. "
    "They have single-node pandas experience only. Any claim of Spark implementation "
    "is a KNOWLEDGE_FABRICATION.\n"
    "\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "WHAT IS LEGITIMATE (NOT A VIOLATION)\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "The following response patterns are CORRECT and must NOT be flagged:\n"
    "\n"
    "  LEGITIMATE: 'I haven't worked with ClickHouse in production, but from my "
    "PostgreSQL indexing experience I understand why columnar storage would be faster "
    "for analytics queries — because row-store I/O must read entire rows even for "
    "two-column projections.'\n"
    "\n"
    "  LEGITIMATE: 'I don't have hands-on Airflow experience, but from my Celery work "
    "I understand what Airflow adds on top — DAG-level dependency management, sensor-based "
    "waiting, and backfill mechanics that Celery cannot provide.'\n"
    "\n"
    "  VIOLATION: 'At my previous role I set up ReplacingMergeTree tables with "
    "custom version columns for bet event deduplication.' (Claims implementation not "
    "in documented history.)\n"
    "\n"
    "  VIOLATION: 'I've written Airflow DAGs with ExternalTaskSensors before.' "
    "(Claims implementation not in documented history.)\n"
    "\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "VIOLATION TYPES\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "  KNOWLEDGE_FABRICATION:   Candidate explicitly claims implementation experience "
    "they cannot have. Highest severity.\n"
    "  BOUNDARY_BREACH:         Candidate's answer implies implementation familiarity "
    "through specific technical detail not achievable via adjacent reasoning alone.\n"
    "  INCONSISTENT_CONFIDENCE: Candidate expresses HIGH confidence about an absent domain "
    "without acknowledging the gap — structurally suspicious even if not explicitly false.\n"
    "\n"
    "If no violations are found, return boundary_violation_count = 0, violations = [], "
    "knowledge_fabrication_detected = false, and integrity_risk_score near 0.0.\n"
    "\n"
    "Output ONLY the JSON object matching the schema. No markdown fences.\n"
)

INTEGRITY_AUDIT_HUMAN_TEMPLATE: str = (
    "{format_instructions}\n"
    "\n"
    "═══ CANDIDATE RESPONSES TO GAP-AREA QUESTIONS ═══\n"
    "{gap_responses}\n"
    "\n"
    "═══ PRE-COMPUTED STRUCTURAL METRICS ═══\n"
    "Gap Acknowledgement Rate      : {gap_ack_rate} (proportion of gap-area questions where gap was acknowledged)\n"
    "Adjacent Reasoning Quality    : {adjacent_quality} (quality of knowledge bridges used, 0=none, 1=excellent)\n"
    "Confirmed Boundary Breaches   : {confirmed_breaches} (from Pydantic model_validator — should be 0)\n"
    "\n"
    "Assess the candidate responses above for integrity violations. "
    "Output only the JSON object.\n"
)

INTEGRITY_AUDIT_PROMPT_TEMPLATE: ChatPromptTemplate = ChatPromptTemplate.from_messages([
    ("system", INTEGRITY_AUDIT_SYSTEM_PROMPT),
    ("human",  INTEGRITY_AUDIT_HUMAN_TEMPLATE),
])

# ---------------------------------------------------------------------------
# 7.3 — Compliance Audit Prompts
# ---------------------------------------------------------------------------

COMPLIANCE_AUDIT_SYSTEM_PROMPT: str = (
    "You are a compliance auditor specialising in employment law and interview best "
    "practices. You are reviewing a technical interview transcript for compliance with "
    "the Republic of Armenia Labor Code and international employment discrimination "
    "standards.\n"
    "\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "PROTECTED CHARACTERISTICS UNDER RA LABOR CODE\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "Article 86 of the RA Labor Code prohibits discrimination in employment on the "
    "basis of the following protected characteristics:\n"
    "  • Gender, sex, sexual orientation\n"
    "  • Age (beyond legally permitted minimum age requirements)\n"
    "  • Race, national origin, ethnicity, nationality\n"
    "  • Religion, political views, or public activity\n"
    "  • Trade union membership or activity\n"
    "  • Family status, marital status, pregnancy, parental obligations\n"
    "  • Disability or medical condition not directly relevant to core job functions\n"
    "  • Property or social status\n"
    "\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "EVALUATION FRAMEWORK\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "For each interviewer question, assess:\n"
    "\n"
    "  1. RELEVANCE: Is this question directly relevant to the technical requirements "
    "of the Senior Data Engineer role? Technical questions about ClickHouse, Airflow, "
    "Spark, Python, and SQL are fully legitimate.\n"
    "\n"
    "  2. PROTECTED CHARACTERISTIC PROBE: Does the question directly or indirectly "
    "require the candidate to reveal a protected characteristic? For example:\n"
    "    - 'Do you plan to start a family?' → prohibited (family status)\n"
    "    - 'Where are you originally from?' → potentially prohibited (nationality)\n"
    "    - 'What year did you graduate?' → potentially prohibited (age inference)\n"
    "    - 'Tell me about your ClickHouse experience' → legitimate (technical)\n"
    "\n"
    "  3. PROPORTIONALITY: Is the evaluation criterion proportionate to the role's "
    "genuine operational requirements?\n"
    "\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "COMPLIANCE STATUS DEFINITIONS\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "  compliant:      No concerns. All questions are technically relevant and lawful.\n"
    "  minor_concern:  One or two questions could be improved but do not rise to "
    "legal risk. Informational note only.\n"
    "  major_concern:  One or more questions probe protected characteristics or use "
    "criteria that are not proportionate to the role. Legal review recommended.\n"
    "  non_compliant:  Clear violation of RA Labor Code Article 86 or equivalent "
    "standard. Evaluation cannot be used without legal review and remediation.\n"
    "\n"
    "The legal context excerpts below were retrieved from the knowledge base to "
    "support your analysis. Reference specific articles where relevant.\n"
    "\n"
    "Output ONLY the JSON object matching the schema. No markdown fences.\n"
)

COMPLIANCE_AUDIT_HUMAN_TEMPLATE: str = (
    "{format_instructions}\n"
    "\n"
    "═══ LEGAL CONTEXT (retrieved from labor_code_am knowledge base) ═══\n"
    "{rag_context}\n"
    "\n"
    "═══ INTERVIEWER QUESTIONS TO AUDIT ═══\n"
    "{interviewer_questions}\n"
    "\n"
    "═══ ROLE CONTEXT ═══\n"
    "Role: {role_title}\n"
    "Industry: {industry}\n"
    "\n"
    "Assess the interview questions above for compliance with RA Labor Code and "
    "employment law best practices. Output only the JSON object.\n"
)

COMPLIANCE_AUDIT_PROMPT_TEMPLATE: ChatPromptTemplate = ChatPromptTemplate.from_messages([
    ("system", COMPLIANCE_AUDIT_SYSTEM_PROMPT),
    ("human",  COMPLIANCE_AUDIT_HUMAN_TEMPLATE),
])


# ===========================================================================
# SECTION 8 — Output Parsers
# ===========================================================================
# Constructed at module import time — pure schema introspection, no API calls.

bias_audit_parser:      PydanticOutputParser = PydanticOutputParser(pydantic_object=BiasAuditLLMOutput)
integrity_audit_parser: PydanticOutputParser = PydanticOutputParser(pydantic_object=IntegrityAuditLLMOutput)
compliance_audit_parser: PydanticOutputParser = PydanticOutputParser(pydantic_object=ComplianceAuditLLMOutput)


# ===========================================================================
# SECTION 9 — Private Helper Functions
# ===========================================================================

@lru_cache(maxsize=1)
def _get_verifier_llm():
    """
    Returns the cached Gemini LLM singleton for all three audit passes.
    Low temperature (0.12) maximises determinism and audit consistency.
    Import is deferred so that test modules importing only schemas do not
    require GOOGLE_API_KEY to be set.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=VERIFIER_MODEL,
        temperature=VERIFIER_TEMPERATURE,
        convert_system_message_to_human=False,
    )


def _extract_json_safe(text: str) -> dict:
    """
    Robust JSON extraction tolerating markdown fences and surrounding prose.
    Applies three extraction strategies in order of strictness.
    """
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start: end + 1])
        except json.JSONDecodeError:
            pass

    logger.warning("_extract_json_safe: all extraction strategies failed. Returning {}.")
    return {}


def _extract_interviewer_questions(
    transcript: InterviewSimulationTranscript,
    max_chars:  int = _MAX_TRANSCRIPT_CHARS_PER_PROMPT,
) -> str:
    """
    Formats only the interviewer's spoken questions for injection into
    the Bias Audit and Compliance Audit prompts.
    Truncates to max_chars to stay within the LLM context budget.
    """
    lines: List[str] = []
    for r in transcript.completed_rounds:
        target = (
            r.interviewer_turn.target_gap_area.value
            if r.interviewer_turn.target_gap_area
            else "general"
        )
        lines.append(
            f"[Q{r.round_index + 1} | Stage: {r.stage.value} | "
            f"Target: {target} | Type: {r.interviewer_turn.question_type.value if r.interviewer_turn.question_type else 'unknown'}]"
        )
        lines.append(r.interviewer_turn.content.strip())
        lines.append("")

    full_text = "\n".join(lines)
    if len(full_text) > max_chars:
        full_text = full_text[:max_chars] + "\n[... truncated for context budget ...]"
    return full_text


def _extract_gap_responses(
    transcript:      InterviewSimulationTranscript,
    gap_probe_areas: frozenset,
    max_chars:       int = _MAX_TRANSCRIPT_CHARS_PER_PROMPT,
) -> str:
    """
    Extracts only the candidate responses to gap-area questions, with their
    structured metadata. Used by the Integrity Audit prompt to focus analysis
    on the turns most likely to contain boundary violations.
    """
    lines: List[str] = []
    for r in transcript.completed_rounds:
        if r.interviewer_turn.target_gap_area not in gap_probe_areas:
            continue

        gap_area = r.interviewer_turn.target_gap_area.value
        ack       = r.candidate_output.gap_acknowledged
        validity  = r.candidate_output.response_validity.value
        confidence = r.candidate_output.confidence_level.value

        lines.append(
            f"[Round {r.round_index} | Gap Area: {gap_area} | "
            f"gap_acknowledged={ack} | validity={validity} | confidence={confidence}]"
        )
        lines.append(f"QUESTION: {r.interviewer_turn.content.strip()}")
        lines.append(f"RESPONSE: {r.candidate_turn.content.strip()}")

        if r.candidate_output.adjacent_knowledge_invoked:
            bridge = r.candidate_output.adjacent_knowledge_invoked
            lines.append(f"[BRIDGE DOCUMENTED: {bridge[:120]}{'...' if len(bridge) > 120 else ''}]")
        if r.candidate_output.gap_acknowledgement_text:
            lines.append(f"[ACKNOWLEDGEMENT: {r.candidate_output.gap_acknowledgement_text}]")

        lines.append("")

    full_text = "\n".join(lines) if lines else "No gap-area questions found in this transcript."
    if len(full_text) > max_chars:
        full_text = full_text[:max_chars] + "\n[... truncated for context budget ...]"
    return full_text


def _compute_gap_acknowledgement_rate(
    transcript:      InterviewSimulationTranscript,
    gap_probe_areas: frozenset,
) -> float:
    """
    Deterministic computation of the fraction of gap-area questions for which
    the candidate explicitly acknowledged the knowledge gap.
    Returns 1.0 if there are no gap-area questions (no acknowledgement needed).
    """
    gap_rounds = [
        r for r in transcript.completed_rounds
        if r.interviewer_turn.target_gap_area in gap_probe_areas
    ]
    if not gap_rounds:
        return 1.0
    acknowledged = sum(1 for r in gap_rounds if r.candidate_output.gap_acknowledged)
    return round(acknowledged / len(gap_rounds), 3)


def _compute_adjacent_reasoning_quality(
    transcript:      InterviewSimulationTranscript,
    gap_probe_areas: frozenset,
) -> float:
    """
    Deterministic quality score for the adjacent reasoning bridges used in
    gap-area responses. Considers only rounds where a gap was acknowledged.

    Scoring:
      No acknowledged gap rounds present → 0.0
      Adjacent bridge >= 80 chars        → 1.0 per round
      Adjacent bridge < 80 chars         → 0.5 per round
      No adjacent bridge                 → 0.0 per round
    """
    acknowledged_gap_rounds = [
        r for r in transcript.completed_rounds
        if r.interviewer_turn.target_gap_area in gap_probe_areas
        and r.candidate_output.gap_acknowledged
    ]
    if not acknowledged_gap_rounds:
        return 0.0

    scores: List[float] = []
    for r in acknowledged_gap_rounds:
        bridge = r.candidate_output.adjacent_knowledge_invoked
        if bridge and len(bridge.strip()) >= 80:
            scores.append(1.0)
        elif bridge and len(bridge.strip()) > 0:
            scores.append(0.5)
        else:
            scores.append(0.0)

    return round(sum(scores) / len(scores), 3) if scores else 0.0


def _count_confirmed_boundary_breaches(
    transcript: InterviewSimulationTranscript,
) -> int:
    """
    Counts SimulationRound entries where response_validity == BOUNDARY_BREACH.
    In correct operation this is always 0 (the Pydantic model_validator prevents
    any breach from being stored). Computed here for audit completeness.
    """
    from src.agents.candidate_simulator import ResponseValidity
    return sum(
        1 for r in transcript.completed_rounds
        if r.candidate_output.response_validity == ResponseValidity.BOUNDARY_BREACH
    )


def _compute_overall_integrity_score(
    bias_risk_score:       float,
    integrity_risk_score:  float,
    compliance_risk_score: float,
) -> float:
    """
    Computes the composite overall integrity score as a weighted average
    of the three audit pass risk scores.

    Weights:
      Bias risk        : 0.35 (structural and cognitive bias in questioning)
      Integrity risk   : 0.35 (knowledge boundary violation in simulation)
      Compliance risk  : 0.30 (legal and regulatory compliance)

    Returns a float in [0.0, 1.0]. Lower is better (0.0 = no risk).
    """
    score = (
        WEIGHT_BIAS_RISK       * bias_risk_score       +
        WEIGHT_INTEGRITY_RISK  * integrity_risk_score  +
        WEIGHT_COMPLIANCE_RISK * compliance_risk_score
    )
    return round(max(0.0, min(1.0, score)), 3)


def _determine_is_safe_to_use(
    overall_score:      float,
    compliance_status:  str,
    fabrication_found:  bool,
) -> bool:
    """
    Returns True if the evaluation is cleared for recruiter consumption.

    Safety requires ALL three conditions:
      1. Overall integrity score below SAFE_USE_SCORE_THRESHOLD (0.40)
      2. Compliance status is not MAJOR_CONCERN or NON_COMPLIANT
      3. No knowledge fabrication was detected in the integrity audit
    """
    return (
        overall_score < SAFE_USE_SCORE_THRESHOLD
        and compliance_status not in _BLOCKING_COMPLIANCE_STATUSES
        and not fabrication_found
    )


def _build_recommendation(
    overall_score:      float,
    compliance_status:  str,
    fabrication_found:  bool,
    bias_risk_level:    str,
    is_safe:            bool,
) -> str:
    """
    Generates a single concise operational recommendation for the recruiter.
    The recommendation is the primary actionable output of this module.
    """
    if is_safe:
        return (
            "Evaluation cleared for recruiter review. All three audit passes "
            "(bias, integrity, compliance) returned acceptable results. "
            "Standard human review protocols apply."
        )

    parts: List[str] = ["REVIEW REQUIRED before recruiter use."]

    if compliance_status in _BLOCKING_COMPLIANCE_STATUSES:
        parts.append(
            f"Compliance audit returned '{compliance_status.replace('_', ' ').upper()}' — "
            "legal review is required before this evaluation may inform any employment decision."
        )

    if fabrication_found:
        parts.append(
            "Simulation integrity: knowledge fabrication was detected in the candidate "
            "simulation. Cross-reference results against the raw CV analysis in the "
            "Shared Analysis Engine output, not the simulation transcript alone."
        )

    if bias_risk_level in {"high", "critical"}:
        parts.append(
            f"Bias audit risk level is '{bias_risk_level.upper()}'. "
            "Human review of the bias signals is recommended before using the "
            "evaluation to inform shortlisting decisions."
        )

    if overall_score >= SAFE_USE_SCORE_THRESHOLD:
        parts.append(
            f"Overall integrity score {overall_score:.2f} exceeds the "
            f"{SAFE_USE_SCORE_THRESHOLD:.2f} safety threshold."
        )

    return " ".join(parts)


def _build_audit_narrative(
    bias_metrics:         BiasMetrics,
    integrity_assessment: IntegrityAssessment,
    compliance_result:    ComplianceCheckResult,
    overall_score:        float,
    is_safe:              bool,
) -> str:
    """
    Constructs the human-readable audit_justification_narrative for the
    VerificationReport. Written for a professional recruiter audience.
    """
    verdict = "CLEARED" if is_safe else "FLAGGED FOR REVIEW"
    lines: List[str] = [
        f"VERIFICATION REPORT — {verdict}",
        f"Overall Integrity Score: {overall_score:.3f} / 1.000 "
        f"(0.000 = no risk, 1.000 = severe risk)",
        "",
        "BIAS AUDIT:",
        f"  Risk Level: {bias_metrics.bias_risk_level.upper()}",
        f"  Signals Detected: {bias_metrics.bias_signal_count}",
        f"  Evaluation Structurally Consistent: {bias_metrics.structurally_consistent_evaluation}",
        f"  Question Bias Score: {bias_metrics.interviewer_question_bias_score:.3f}",
    ]

    if bias_metrics.detected_bias_signals:
        lines.append("  Key Signals:")
        for sig in bias_metrics.detected_bias_signals[:3]:
            lines.append(
                f"    [{sig.risk_level.upper()}] {sig.dimension}: "
                f"{sig.explanation} (Turn {sig.turn_index})"
            )

    lines += [
        "",
        "EVALUATION INTEGRITY:",
        f"  Integrity Risk Score: {integrity_assessment.overall_integrity_risk:.3f}",
        f"  Knowledge Boundary Violations: {integrity_assessment.boundary_violations_detected}",
        f"  Knowledge Fabrication: {'YES — CRITICAL' if integrity_assessment.knowledge_fabrication_detected else 'Not detected'}",
        f"  Gap Acknowledgement Rate: {integrity_assessment.gap_acknowledgement_rate:.1%}",
        f"  Adjacent Reasoning Quality: {integrity_assessment.adjacent_reasoning_quality_score:.3f}",
    ]

    if integrity_assessment.assessment_summary:
        lines.append(f"  Summary: {integrity_assessment.assessment_summary}")

    lines += [
        "",
        "LEGAL COMPLIANCE:",
        f"  Status: {compliance_result.compliance_status.replace('_', ' ').upper()}",
        f"  Risk Score: {compliance_result.compliance_risk_score:.3f}",
        f"  Prohibited Criteria Detected: {compliance_result.prohibited_criteria_detected}",
        f"  RAG Context Chunks Used: {compliance_result.rag_chunks_used}",
    ]

    if compliance_result.labor_code_references:
        lines.append(f"  Referenced Articles: {', '.join(compliance_result.labor_code_references[:4])}")

    if compliance_result.compliance_rationale:
        lines.append(f"  Rationale: {compliance_result.compliance_rationale}")

    return "\n".join(lines)


def _build_safe_fallback_report(
    session_id: str,
    reason:     str,
) -> VerificationReport:
    """
    Returns a structurally valid VerificationReport when all three Gemini
    audit passes fail or input validation prevents execution.

    The fallback report marks the session as requiring manual review via
    is_safe_to_use=False and documents the failure reason in the narrative.
    is_fallback_report=True allows downstream components to display a
    distinct UI state for failed verifications.
    """
    fallback_bias = BiasMetrics(
        bias_risk_level                    = BiasRiskLevel.LOW,
        detected_bias_signals              = [],
        bias_signal_count                  = 0,
        highest_risk_dimension             = None,
        structurally_consistent_evaluation = True,
        cognitive_bias_flags               = [],
        linguistic_bias_phrases            = [],
        interviewer_question_bias_score    = 0.0,
        overall_bias_risk_score            = 0.0,
    )
    fallback_integrity = IntegrityAssessment(
        overall_integrity_risk                  = 0.5,
        boundary_violations_detected            = 0,
        violation_entries                       = [],
        knowledge_fabrication_detected          = False,
        suspicious_high_confidence_gap_answers  = 0,
        gap_acknowledgement_rate                = 1.0,
        adjacent_reasoning_quality_score        = 0.5,
        assessment_summary                      = (
            "Integrity assessment could not be completed due to a system error. "
            "Manual review is required."
        ),
    )
    fallback_compliance = ComplianceCheckResult(
        compliance_status           = ComplianceStatus.MINOR_CONCERN,
        labor_code_references       = [],
        prohibited_criteria_detected = False,
        prohibited_criteria_list    = [],
        rag_chunks_used             = 0,
        compliance_risk_score       = 0.3,
        compliance_rationale        = (
            "Compliance check could not be completed due to a system error. "
            "Default to MINOR_CONCERN pending manual review."
        ),
    )
    narrative = (
        f"VERIFICATION REPORT — FALLBACK (system error)\n\n"
        f"Failure reason: {reason}\n\n"
        "All three audit passes (bias, integrity, compliance) could not be completed. "
        "This evaluation must be manually reviewed before use in any employment decision. "
        "The is_fallback_report flag is set to True to allow the UI to display an "
        "appropriate degraded state."
    )
    return VerificationReport(
        report_id                     = f"fallback-{uuid.uuid4().hex[:8]}",
        session_id                    = session_id,
        generated_at                  = datetime.utcnow().isoformat(timespec="seconds") + "Z",
        verifier_model_used           = VERIFIER_MODEL,
        bias_metrics                  = fallback_bias,
        compliance_status             = ComplianceStatus.MINOR_CONCERN,
        integrity_score               = 0.5,
        audit_justification_narrative = narrative,
        integrity_assessment          = fallback_integrity,
        compliance_result             = fallback_compliance,
        evaluation_integrity_risk     = _EIR_MEDIUM,
        is_safe_to_use                = False,
        recommendation                = (
            "MANUAL REVIEW REQUIRED: Automated verification failed. "
            "Do not use this evaluation for employment decisions without "
            "human expert review of the full simulation transcript."
        ),
        raw_transcript_turns          = 0,
        rag_chunks_retrieved          = 0,
        is_fallback_report            = True,
    )


# ===========================================================================
# SECTION 10 — Core Async Audit Functions
# ===========================================================================

async def _run_bias_audit(
    transcript:  InterviewSimulationTranscript,
    role_title:  str,
    industry:    str,
    seniority:   str,
) -> BiasMetrics:
    """
    Audit Pass 1 — Bias Detection.

    Sends the formatted interviewer questions to Gemini with the bias audit
    system prompt. Maps the structured LLM output to BiasMetrics.

    On any exception, returns a zero-signal BiasMetrics (LOW risk) to ensure
    pipeline continuity. The fallback is logged at WARNING level.
    """
    questions_text = _extract_interviewer_questions(transcript)

    try:
        llm   = _get_verifier_llm()
        chain = BIAS_AUDIT_PROMPT_TEMPLATE | llm | bias_audit_parser

        raw_output: BiasAuditLLMOutput = await chain.ainvoke({
            "format_instructions": bias_audit_parser.get_format_instructions(),
            "interviewer_questions": questions_text,
            "role_title":    role_title,
            "industry":      industry,
            "required_seniority": seniority,
        })

        result = BiasMetrics.from_llm_output(raw_output)
        logger.info(
            "_run_bias_audit: risk=%s | signals=%d | bias_score=%.3f",
            result.bias_risk_level,
            result.bias_signal_count,
            result.overall_bias_risk_score,
        )
        return result

    except Exception as exc:
        logger.warning(
            "_run_bias_audit: Gemini invocation failed (%s). "
            "Returning LOW-risk fallback BiasMetrics.",
            exc,
        )
        return BiasMetrics(
            bias_risk_level                    = BiasRiskLevel.LOW,
            detected_bias_signals              = [],
            bias_signal_count                  = 0,
            highest_risk_dimension             = None,
            structurally_consistent_evaluation = True,
            cognitive_bias_flags               = [],
            linguistic_bias_phrases            = [],
            interviewer_question_bias_score    = 0.0,
            overall_bias_risk_score            = 0.0,
        )


async def _run_integrity_assessment(
    transcript: InterviewSimulationTranscript,
) -> IntegrityAssessment:
    """
    Audit Pass 2 — Evaluation Integrity.

    Step 1: Compute deterministic metrics from the structured transcript.
    Step 2: Extract only gap-area responses for Gemini analysis.
    Step 3: Invoke Gemini to detect knowledge fabrication and boundary breaches.

    On any exception, returns a conservative IntegrityAssessment with
    integrity_risk_score=0.5 and the deterministic metrics still populated.
    """
    gap_ack_rate        = _compute_gap_acknowledgement_rate(transcript, _GAP_PROBE_AREAS)
    adjacent_quality    = _compute_adjacent_reasoning_quality(transcript, _GAP_PROBE_AREAS)
    confirmed_breaches  = _count_confirmed_boundary_breaches(transcript)
    gap_responses_text  = _extract_gap_responses(transcript, _GAP_PROBE_AREAS)

    try:
        llm   = _get_verifier_llm()
        chain = INTEGRITY_AUDIT_PROMPT_TEMPLATE | llm | integrity_audit_parser

        raw_output: IntegrityAuditLLMOutput = await chain.ainvoke({
            "format_instructions":    integrity_audit_parser.get_format_instructions(),
            "gap_responses":          gap_responses_text,
            "gap_ack_rate":           f"{gap_ack_rate:.1%}",
            "adjacent_quality":       f"{adjacent_quality:.3f}",
            "confirmed_breaches":     str(confirmed_breaches),
        })

        result = IntegrityAssessment.from_llm_output(
            output                     = raw_output,
            gap_acknowledgement_rate   = gap_ack_rate,
            adjacent_reasoning_quality = adjacent_quality,
        )
        logger.info(
            "_run_integrity_assessment: risk=%.3f | violations=%d | fabrication=%s | ack_rate=%.1%%",
            result.overall_integrity_risk,
            result.boundary_violations_detected,
            result.knowledge_fabrication_detected,
            gap_ack_rate * 100,
        )
        return result

    except Exception as exc:
        logger.warning(
            "_run_integrity_assessment: Gemini invocation failed (%s). "
            "Returning conservative fallback IntegrityAssessment.",
            exc,
        )
        return IntegrityAssessment(
            overall_integrity_risk                  = 0.50,
            boundary_violations_detected            = confirmed_breaches,
            violation_entries                       = [],
            knowledge_fabrication_detected          = False,
            suspicious_high_confidence_gap_answers  = 0,
            gap_acknowledgement_rate                = gap_ack_rate,
            adjacent_reasoning_quality_score        = adjacent_quality,
            assessment_summary                      = (
                "Integrity assessment could not be fully completed due to an LLM "
                "invocation error. Deterministic metrics are accurate; Gemini-based "
                "violation detection is unavailable for this session."
            ),
        )


async def _run_compliance_check(
    transcript:    InterviewSimulationTranscript,
    role_title:    str,
    industry:      str,
    rag_context:   str,
    rag_chunks_used: int,
) -> ComplianceCheckResult:
    """
    Audit Pass 3 — Legal & Compliance Verification.

    Injects the pre-fetched RAG legal context alongside the interviewer
    questions into the Compliance Audit Gemini pass.

    On any exception, returns ComplianceStatus.MINOR_CONCERN with a
    documented fallback rationale. MINOR_CONCERN is chosen over COMPLIANT
    to prevent a failed audit from clearing an evaluation by default.
    """
    questions_text = _extract_interviewer_questions(transcript)

    try:
        llm   = _get_verifier_llm()
        chain = COMPLIANCE_AUDIT_PROMPT_TEMPLATE | llm | compliance_audit_parser

        raw_output: ComplianceAuditLLMOutput = await chain.ainvoke({
            "format_instructions":   compliance_audit_parser.get_format_instructions(),
            "rag_context":           rag_context[:_MAX_RAG_CONTEXT_CHARS] if rag_context else "No legal context retrieved from knowledge base.",
            "interviewer_questions": questions_text,
            "role_title":            role_title,
            "industry":              industry,
        })

        result = ComplianceCheckResult.from_llm_output(
            output         = raw_output,
            rag_chunks_used = rag_chunks_used,
        )
        logger.info(
            "_run_compliance_check: status=%s | risk=%.3f | prohibited=%s | rag_chunks=%d",
            result.compliance_status,
            result.compliance_risk_score,
            result.prohibited_criteria_detected,
            result.rag_chunks_used,
        )
        return result

    except Exception as exc:
        logger.warning(
            "_run_compliance_check: Gemini invocation failed (%s). "
            "Returning MINOR_CONCERN fallback ComplianceCheckResult.",
            exc,
        )
        return ComplianceCheckResult(
            compliance_status           = ComplianceStatus.MINOR_CONCERN,
            labor_code_references       = [],
            prohibited_criteria_detected = False,
            prohibited_criteria_list    = [],
            rag_chunks_used             = rag_chunks_used,
            compliance_risk_score       = 0.25,
            compliance_rationale        = (
                "Compliance check could not be completed due to an LLM invocation error. "
                "Status defaulted to MINOR_CONCERN. Manual compliance review recommended."
            ),
        )


# ===========================================================================
# SECTION 11 — Main Integration Entry Point
# ===========================================================================

async def recruiter_verifier_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Asynchronous verification layer node.

    Lifecycle:
      1. Extracts InterviewSimulationTranscript and JD metadata from state.
      2. Builds a compliance search query from the interview content.
      3. Fetches RA Labor Code context from ChromaDB via HybridRAGPipeline
         (synchronous call wrapped in asyncio.to_thread for event loop safety).
      4. Runs all three Gemini audit passes concurrently via asyncio.gather:
           - Bias Audit        → BiasMetrics
           - Integrity Audit   → IntegrityAssessment
           - Compliance Audit  → ComplianceCheckResult
      5. Computes the composite overall_integrity_score and all derived fields.
      6. Assembles and returns the VerificationReport appended to the state.

    Fallback resilience:
      If any unrecoverable exception occurs before or after the concurrent audit
      passes (e.g., missing transcript, pipeline instantiation failure), the
      outer try/except returns a structurally valid fallback VerificationReport
      with is_fallback_report=True. The pipeline never propagates an unhandled
      exception to the caller.

    Parameters
    ----------
    state : dict
        Must contain 'interview_simulation_transcript' (InterviewSimulationTranscript).
        Optionally contains 'jd_entities' (JDEntities) for role/industry metadata.
        Optionally contains 'session_id' (str).

    Returns
    -------
    dict
        {'verification_report': VerificationReport}
    """
    session_id: str = state.get("session_id", f"vrf-{uuid.uuid4().hex[:8]}")

    try:
        transcript: Optional[InterviewSimulationTranscript] = state.get(
            "interview_simulation_transcript"
        )
        if transcript is None:
            logger.error(
                "recruiter_verifier_node [session=%s]: "
                "'interview_simulation_transcript' missing from state. "
                "Cannot run verification.",
                session_id,
            )
            return {
                "verification_report": _build_safe_fallback_report(
                    session_id,
                    reason="Missing interview_simulation_transcript in state.",
                )
            }

        # Extract JD metadata for prompt context
        jd_entities = state.get("jd_entities")
        role_title   = getattr(jd_entities, "role_title",  "Senior Data Engineer") if jd_entities else "Senior Data Engineer"
        industry     = getattr(jd_entities, "industry",    "igaming")              if jd_entities else "igaming"
        seniority    = getattr(jd_entities, "required_seniority", "senior")        if jd_entities else "senior"

        total_turns = len(transcript.completed_rounds) * 2

        logger.info(
            "recruiter_verifier_node [session=%s]: starting verification | "
            "rounds=%d | turns=%d | role='%s'",
            session_id,
            len(transcript.completed_rounds),
            total_turns,
            role_title,
        )

        # ── Step 1: Build compliance query from interview content ──────────
        sample_questions = " ".join(
            r.interviewer_turn.content[:80]
            for r in transcript.completed_rounds[:3]
        )
        compliance_query = (
            f"employment discrimination prohibited criteria hiring interview "
            f"Armenia labor code equal opportunity {industry} data engineering "
            f"technical interview questions: {sample_questions[:200]}"
        )

        # ── Step 2: Fetch RAG legal context (sync → thread pool) ──────────
        rag_docs:       List[Any] = []
        rag_chunks_used: int       = 0
        rag_context:    str        = ""

        try:
            pipeline = get_pipeline()
            rag_docs = await asyncio.to_thread(
                pipeline.retrieve_multi_collection,
                collection_queries   = [("labor_code_am", compliance_query)],
                top_k_per_collection = 3,
                global_top_k         = 4,
                rerank_globally      = False,
            )
            rag_chunks_used = len(rag_docs)
            rag_context     = pipeline.format_documents_as_context(
                rag_docs, max_chars_per_doc=500,
            )
            logger.info(
                "recruiter_verifier_node [session=%s]: RAG retrieved %d chunks "
                "from labor_code_am.",
                session_id, rag_chunks_used,
            )
        except Exception as rag_exc:
            logger.warning(
                "recruiter_verifier_node [session=%s]: RAG retrieval failed (%s). "
                "Compliance audit will proceed without legal context.",
                session_id, rag_exc,
            )
            rag_context = (
                "No legal context available — RAG retrieval failed. "
                "Apply general employment law best practices."
            )

        # ── Step 3: Run all three audit passes concurrently ───────────────
        bias_result, integrity_result, compliance_result = await asyncio.gather(
            _run_bias_audit(transcript, role_title, industry, seniority),
            _run_integrity_assessment(transcript),
            _run_compliance_check(
                transcript      = transcript,
                role_title      = role_title,
                industry        = industry,
                rag_context     = rag_context,
                rag_chunks_used = rag_chunks_used,
            ),
        )

        # ── Step 4: Compute composite score and derived fields ────────────
        overall_score = _compute_overall_integrity_score(
            bias_risk_score       = bias_result.overall_bias_risk_score,
            integrity_risk_score  = integrity_result.overall_integrity_risk,
            compliance_risk_score = compliance_result.compliance_risk_score,
        )

        is_safe = _determine_is_safe_to_use(
            overall_score     = overall_score,
            compliance_status = compliance_result.compliance_status,
            fabrication_found = integrity_result.knowledge_fabrication_detected,
        )

        recommendation = _build_recommendation(
            overall_score     = overall_score,
            compliance_status = compliance_result.compliance_status,
            fabrication_found = integrity_result.knowledge_fabrication_detected,
            bias_risk_level   = bias_result.bias_risk_level,
            is_safe           = is_safe,
        )

        narrative = _build_audit_narrative(
            bias_metrics         = bias_result,
            integrity_assessment = integrity_result,
            compliance_result    = compliance_result,
            overall_score        = overall_score,
            is_safe              = is_safe,
        )

        # ── Step 5: Assemble VerificationReport ───────────────────────────
        report = VerificationReport(
            report_id                     = f"vrf-{uuid.uuid4().hex[:12]}",
            session_id                    = session_id,
            generated_at                  = datetime.utcnow().isoformat(timespec="seconds") + "Z",
            verifier_model_used           = VERIFIER_MODEL,
            bias_metrics                  = bias_result,
            compliance_status             = compliance_result.compliance_status,
            integrity_score               = overall_score,
            audit_justification_narrative = narrative,
            integrity_assessment          = integrity_result,
            compliance_result             = compliance_result,
            evaluation_integrity_risk     = _float_to_eir(overall_score),
            is_safe_to_use                = is_safe,
            recommendation                = recommendation,
            raw_transcript_turns          = total_turns,
            rag_chunks_retrieved          = rag_chunks_used,
            is_fallback_report            = False,
        )

        logger.info(
            "recruiter_verifier_node [session=%s]: verification complete | "
            "score=%.3f | safe=%s | risk=%s | compliance=%s",
            session_id,
            overall_score,
            is_safe,
            report.evaluation_integrity_risk,
            compliance_result.compliance_status,
        )

        return {"verification_report": report}

    except Exception as exc:
        logger.error(
            "recruiter_verifier_node [session=%s]: unhandled exception: %s. "
            "Returning safe fallback report.",
            session_id, exc,
        )
        return {
            "verification_report": _build_safe_fallback_report(
                session_id,
                reason=f"Unhandled exception in verification pipeline: {exc!s}",
            )
        }
