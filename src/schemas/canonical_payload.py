# src/schemas/canonical_payload.py

from __future__ import annotations

import uuid
import math
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class SeniorityLevel(str, Enum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"
    EXECUTIVE = "executive"


class SkillCategory(str, Enum):
    TECHNICAL = "technical"
    DOMAIN = "domain"
    SOFT = "soft"
    CERTIFICATION = "certification"


class SkillMatchType(str, Enum):
    MATCHED = "matched"
    MISSING_CRITICAL = "missing_critical"
    MISSING_PREFERRED = "missing_preferred"
    TRANSFERABLE = "transferable"


class GapSeverity(str, Enum):
    CRITICAL = "critical"
    MODERATE = "moderate"
    MINOR = "minor"
    NONE = "none"


class EvaluationIntegrityRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AgentExecutionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    FALLBACK = "fallback"


class HireRecommendation(str, Enum):
    STRONG_YES = "strong_yes"
    YES = "yes"
    MAYBE = "maybe"
    NO = "no"


# ---------------------------------------------------------------------------
# Sub-models: Document Entity Layer
# ---------------------------------------------------------------------------

class WorkExperience(BaseModel):
    company: str
    title: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None       # "Present" is a valid value
    duration_months: Optional[int] = None
    responsibilities: List[str] = Field(default_factory=list)
    technologies_mentioned: List[str] = Field(default_factory=list)
    domain: Optional[str] = None         # e.g., "fintech", "igaming", "manufacturing"


class EducationEntry(BaseModel):
    institution: str
    degree: str
    field_of_study: str
    graduation_year: Optional[int] = None
    is_relevant_to_role: Optional[bool] = None


class SkillEntry(BaseModel):
    raw_name: str
    canonical_name: str                  # Normalized to taxonomy
    category: SkillCategory
    taxonomy_code: Optional[str] = None  # O*NET code or internal taxonomy ID
    proficiency_signal: Optional[str] = None  # e.g., "2 years", "advanced", "familiar"


class CVEntities(BaseModel):
    # NOTE: full_name is NOT stored — PII masking is applied upstream.
    # A masked_identifier is stored instead for audit trail purposes.
    masked_identifier: str = Field(
        default="[CANDIDATE]",
        description="PII-safe reference label for this candidate."
    )
    contact_info_present: bool = False
    work_history: List[WorkExperience] = Field(default_factory=list)
    education: List[EducationEntry] = Field(default_factory=list)
    raw_skills: List[SkillEntry] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    total_years_experience: float = 0.0
    inferred_seniority: SeniorityLevel = SeniorityLevel.JUNIOR
    career_domain_signals: List[str] = Field(
        default_factory=list,
        description="Domain keywords extracted from job titles and responsibilities."
    )


class JDEntities(BaseModel):
    role_title: str
    company_context: Optional[str] = None
    required_qualifications: List[str] = Field(default_factory=list)
    preferred_qualifications: List[str] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    required_skills: List[SkillEntry] = Field(default_factory=list)
    preferred_skills: List[SkillEntry] = Field(default_factory=list)
    required_experience_years: float = 0.0
    required_seniority: SeniorityLevel = SeniorityLevel.MID
    industry: str = "technology"
    location: Optional[str] = None
    work_arrangement: Optional[str] = None  # remote, hybrid, on-site


# ---------------------------------------------------------------------------
# Sub-models: Dimensional Scoring Layer
# ---------------------------------------------------------------------------

class DimensionScore(BaseModel):
    raw_score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    is_below_floor: bool = False
    weight: float = Field(..., ge=0.0, le=1.0)
    evidence_phrases_cv: List[str] = Field(
        default_factory=list,
        description="CV phrases that contributed most to this score."
    )
    evidence_phrases_jd: List[str] = Field(
        default_factory=list,
        description="JD phrases used as scoring criteria for this dimension."
    )


class DimensionalAnalysis(BaseModel):
    technical_skills_match: DimensionScore
    experience_depth_alignment: DimensionScore
    educational_relevance: DimensionScore
    domain_knowledge: DimensionScore
    soft_skills_signals: DimensionScore
    seniority_trajectory: DimensionScore
    semantic_contextual_alignment: DimensionScore

    # Computed fields — populated by scoring.py, not by LLM
    composite_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Weighted geometric mean of all seven dimension scores."
    )
    composite_score_percentage: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="composite_score * 100 for display purposes."
    )
    dimensional_outlier_alert: bool = False
    outlier_dimensions: List[str] = Field(default_factory=list)
    hard_floor_applied: bool = False

    @model_validator(mode="after")
    def validate_composite_consistency(self) -> "DimensionalAnalysis":
        assert abs(self.composite_score_percentage - self.composite_score * 100) < 0.1, \
            "composite_score and composite_score_percentage are inconsistent."
        return self


# ---------------------------------------------------------------------------
# Sub-models: Skills Ontology Layer
# ---------------------------------------------------------------------------

class SkillMatchEntry(BaseModel):
    skill_name: str
    canonical_name: str
    match_type: SkillMatchType
    transfer_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    transfer_rationale: Optional[str] = None
    is_critical: bool = False            # True if this skill is in required_qualifications


class SkillsOntologyResult(BaseModel):
    matched_skills: List[SkillMatchEntry] = Field(default_factory=list)
    missing_critical: List[SkillMatchEntry] = Field(default_factory=list)
    missing_preferred: List[SkillMatchEntry] = Field(default_factory=list)
    transferable: List[SkillMatchEntry] = Field(default_factory=list)

    # Summary metrics
    total_required_skills: int = 0
    matched_count: int = 0
    critical_gap_count: int = 0
    coverage_ratio: float = Field(0.0, ge=0.0, le=1.0)
    gap_severity: GapSeverity = GapSeverity.MODERATE

    @model_validator(mode="after")
    def compute_coverage_ratio(self) -> "SkillsOntologyResult":
        if self.total_required_skills > 0:
            computed = self.matched_count / self.total_required_skills
            assert abs(computed - self.coverage_ratio) < 0.01, \
                "coverage_ratio does not match matched_count / total_required_skills."
        return self


# ---------------------------------------------------------------------------
# Sub-models: Semantic Analysis Layer
# ---------------------------------------------------------------------------

class SemanticAnalysis(BaseModel):
    embedding_cosine_similarity: float = Field(..., ge=0.0, le=1.0)
    key_phrase_overlap_ratio: float = Field(..., ge=0.0, le=1.0)
    cv_unique_key_phrases: List[str] = Field(default_factory=list)
    jd_unique_key_phrases: List[str] = Field(default_factory=list)
    shared_key_phrases: List[str] = Field(default_factory=list)
    contextual_domain_alignment: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Similarity between CV domain context and JD industry context."
    )


# ---------------------------------------------------------------------------
# Sub-models: Governance Layer
# ---------------------------------------------------------------------------

class BiasAuditResult(BaseModel):
    """
    ARCHITECTURAL NOTE ON PRIVACY:
    The Bias & Safety Agent detects proxy signals for gender, age, and nationality
    in both the CV and JD texts. However, these raw signals are NEVER stored in the
    payload. They are used internally by the agent to compute the risk level, then
    discarded. Only the processed EvaluationIntegrityRisk level and structured
    recommendations are persisted. This design choice prevents the recruiter from
    using the bias audit as a secondary source of demographic inference.
    """
    evaluation_integrity_risk: EvaluationIntegrityRisk
    risk_rationale: str = Field(
        ...,
        description="Plain-language explanation of why this risk level was assigned, "
                    "without referencing specific demographic signals."
    )
    structured_interview_recommendations: List[str] = Field(
        default_factory=list,
        description="Objective structured interview techniques to counteract "
                    "identified systemic bias in the JD or evaluation criteria."
    )
    # Emergent bias: bias potentially introduced by the scoring model itself
    emergent_scoring_bias_detected: bool = False
    emergent_bias_details: Optional[str] = None
    jd_exclusionary_language_flagged: bool = False
    jd_exclusionary_phrases: List[str] = Field(default_factory=list)


class GovernanceLayer(BaseModel):
    pii_masking_applied: bool = True
    pii_fields_masked: List[str] = Field(default_factory=list)
    guardrail_input_passed: bool = True
    guardrail_input_rejection_reason: Optional[str] = None
    guardrail_output_passed: bool = True
    guardrail_output_flags: List[str] = Field(default_factory=list)
    hallucination_flags: List[str] = Field(default_factory=list)

    phase1_agent_status: Dict[str, AgentExecutionStatus] = Field(
        default_factory=lambda: {
            "document_intelligence": AgentExecutionStatus.SUCCESS,
            "semantic_alignment": AgentExecutionStatus.SUCCESS,
            "skills_ontology": AgentExecutionStatus.SUCCESS,
        }
    )
    phase2_agent_status: AgentExecutionStatus = AgentExecutionStatus.SUCCESS

    bias_audit: BiasAuditResult
    analysis_timestamp: datetime = Field(default_factory=datetime.utcnow)
    model_chain_used: List[str] = Field(default_factory=list)
    total_processing_time_ms: Optional[int] = None


# ---------------------------------------------------------------------------
# Sub-models: Perspective Narrative Layer (Access-Controlled)
# ---------------------------------------------------------------------------

class ActionItem(BaseModel):
    priority: int = Field(..., ge=1)     # 1 = highest urgency
    dimension: str
    skill_or_gap: str
    current_state_description: str
    target_state_description: str
    suggested_learning_resources: List[str] = Field(default_factory=list)
    estimated_effort_weeks: Optional[int] = None
    is_critical_gap_closure: bool = False


class VerificationPoint(BaseModel):
    """
    Recruiter-facing only. Derived from the candidate's skill gaps but
    framed as objective interview probes — not as personal development tasks.
    The candidate never sees VerificationPoint objects directly.
    """
    topic: str
    evidence_gap_description: str
    why_it_matters: str
    suggested_interview_question: str
    importance_level: str = Field(
        ...,
        pattern="^(must_ask|recommended|optional)$"
    )


class CandidatePerspective(BaseModel):
    """
    Access Profile: Candidate Coach Room only.
    Contains: coaching narrative, roadmap, interview prep.
    Does NOT contain: hire recommendation, risk flags, recruiter's raw assessment,
    bias audit details, dimensional_outlier_alert in numeric form.
    """
    strength_narrative: str
    gap_closure_roadmap: List[ActionItem] = Field(default_factory=list)
    interview_preparation_focus: str
    salary_positioning_context: str
    top_strength_phrases: List[str] = Field(default_factory=list)
    motivational_framing: str = ""


class RecruiterPerspective(BaseModel):
    """
    Access Profile: Recruiter Intelligence Room only.
    Contains: screening summary, hire recommendation, verification points,
    bias risk level, emergent bias flag, full dimensional analysis access.
    Does NOT contain: candidate's personal development roadmap,
    motivational framing, or coaching narrative.
    """
    screening_summary: str
    hire_recommendation: HireRecommendation
    hire_recommendation_rationale: str
    verification_points: List[VerificationPoint] = Field(default_factory=list)
    comparative_profile_summary: str = ""
    red_flag_summary: Optional[str] = None


# ---------------------------------------------------------------------------
# Root: Canonical Analysis Payload
# ---------------------------------------------------------------------------

class CanonicalAnalysisPayload(BaseModel):

    # Session metadata
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    analysis_version: str = "1.0.0"
    language: str = "hy"                 # ISO 639-1: hy=Armenian, ru=Russian, en=English
    seniority_context: str = "junior"    # User-provided at input time

    # Document entities
    cv_entities: CVEntities
    jd_entities: JDEntities

    # Analysis results
    dimensional_analysis: DimensionalAnalysis
    skills_ontology: SkillsOntologyResult
    semantic_analysis: SemanticAnalysis

    # Governance and audit
    governance: GovernanceLayer

    # Perspective narratives — access-controlled by access_control.py selectors
    candidate_perspective: CandidatePerspective
    recruiter_perspective: RecruiterPerspective

    # Overall confidence and completeness
    overall_analysis_confidence: float = Field(..., ge=0.0, le=1.0)
    analysis_completeness_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Reduced below 1.0 if any Phase 1 agent executed in fallback mode."
    )

    class Config:
        use_enum_values = True
