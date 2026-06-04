# ArmeniaCareer AI — Comprehensive Implementation Specification

**Document Version:** 1.0.0  
**Classification:** Internal Engineering Reference  
**Status:** Approved for Sprint Execution  
**Authors:** ArmeniaCareer AI Engineering Team  
**Last Updated:** June 2026

---

## Table of Contents

1. [Project Alignment Matrix](#1-project-alignment-matrix)
2. [System Architecture Overview](#2-system-architecture-overview)
3. [Repository Structure and Standards](#3-repository-structure-and-standards)
4. [Canonical Analysis Payload — Complete Pydantic Schema](#4-canonical-analysis-payload--complete-pydantic-schema)
5. [Multi-Agent Orchestration Architecture](#5-multi-agent-orchestration-architecture)
6. [Shared Analysis Engine — Phase-by-Phase Implementation](#6-shared-analysis-engine--phase-by-phase-implementation)
7. [Composite Scoring — Geometric Mean with Hard Flooring](#7-composite-scoring--geometric-mean-with-hard-flooring)
8. [Prompt Engineering Architecture](#8-prompt-engineering-architecture)
9. [Hybrid RAG Pipeline](#9-hybrid-rag-pipeline)
10. [Dashboard UI — Component Architecture and State Machine](#10-dashboard-ui--component-architecture-and-state-machine)
11. [Evaluation Framework](#11-evaluation-framework)
12. [Responsible AI and Bias Testing](#12-responsible-ai-and-bias-testing)
13. [Two-Day Sprint Execution Plan](#13-two-day-sprint-execution-plan)
14. [Live Demo Scenario Script](#14-live-demo-scenario-script)

---

## 1. Project Alignment Matrix

This section maps every mandatory deliverable and technical requirement from the instructor's specification (`LLM Applications — Group Project Requirements`) against the ArmeniaCareer AI internal plan (`ԼԼՄ_2.pdf`), explicitly documenting how each baseline item is exceeded.

### 1.1 Deliverable Coverage

| Instructor Deliverable | ArmeniaCareer AI Implementation | Exceedance Level |
|---|---|---|
| GitHub repository with README and reproducible setup | Repository with full architecture documentation, `CONTRIBUTING.md`, environment-pinned `requirements.txt`, `docker-compose.yml` for local ChromaDB, `Makefile` targets for setup and evaluation runs | Significant |
| Working deployed app (Streamlit Cloud or HF Spaces) | Deployed on Streamlit Community Cloud with fallback JSON for offline demo resilience | Met with demo safeguards |
| Written report (8–12 pages) | Report structured as: problem statement, architecture and design decisions, three-stage prompt engineering rationale, evaluation methodology, bias audit results, ethical reflection, team learning | Meets and structures to academic standard |
| Presentation (15–20 min) | Structured as: (1) problem + motivation, (2) live demo pipeline trace, (3) technical architecture deep-dive, (4) evaluation and bias results, (5) responsible AI module, (6) Q&A | Fully covered |
| Optional Pitch Deck + video demo | Included: market analysis (Armenian + CIS tech hiring market), business model (SaaS per-company seat pricing), 3-minute screen-recorded demo video | Voluntary exceedance |

### 1.2 Technical Topic Coverage

The instructor mandates a minimum of four topics from the course curriculum. This project covers all seven as structural pillars, not supplementary additions.

**Topic 1 — Prompt Engineering.** Baseline: three documented versions with rationale. Implementation: five-tier prompt versioning per agent with the following structure: V1 (Base), V2 (Structured Reasoning with explicit rubric), V3 (Few-Shot with annotated ground-truth examples), V4 (Chain-of-Thought with dimension-level justification), V5 (Constitutional with self-critique pass). All versions are stored under `src/prompts/{agent_name}/` as individual Python modules, with a `PROMPT_CHANGELOG.md` per agent documenting the semantic differences and measured performance delta between versions. All evaluation metrics reported in the Evaluation tab are broken down per prompt version to make the iteration rationale empirically grounded.

**Topic 2 — LangChain Components.** Baseline: chains, memory, tools, or agents. Implementation: LangGraph-based multi-agent system with a hierarchical supervisor pattern. The orchestrator is a stateful coordinator graph with typed state transitions. Each agent is implemented as a LangChain `RunnableSequence` with: (a) a retrieval tool for RAG access, (b) a structured output parser backed by a Pydantic schema, (c) an input guardrail chain that wraps every agent invocation, and (d) a fallback chain that activates on schema parse failure. Conversation memory is session-scoped and stored in a `ConversationBufferMemory` object that persists the analysis session for the candidate simulation module.

**Topic 3 — RAG Pipeline.** Baseline: external knowledge source. Implementation: a two-retriever hybrid pipeline combining BM25 sparse retrieval and dense vector retrieval (text-embedding-3-small), fused using Reciprocal Rank Fusion. The knowledge corpus is organized into four ChromaDB collections with distinct embedding strategies. A re-ranking pass using a cross-encoder model filters the fused results before injection into the agent prompt.

**Topic 4 — Fine-Tuning or Model Adaptation.** The project implements domain-specific prompt adaptation: a systematic few-shot corpus of 15 annotated CV-JD pairs drawn from Armenian and CIS tech job market sources is constructed and used as the grounding context for V3 and V4 prompts. This constitutes in-context model adaptation without parameter updates, which is the appropriate approach given the 2-day sprint constraint. The report documents this as a form of retrieval-augmented in-context learning.

**Topic 5 — Content Detection and Classification.** Multiple classification tasks are embedded in the pipeline: (a) document format detection and parser routing, (b) seniority level classification (7-class), (c) skill category taxonomy classification (technical / domain / soft / certification), (d) language detection for Armenian/Russian/English switching, (e) industry vertical classification for JD inputs, and (f) prompt injection and jailbreak pattern detection in the Guardrail Agent.

**Topic 6 — Evaluation Framework.** Automated metrics: JSON schema validity rate, dimension score calibration against human-annotated ground truth (Cohen's Kappa for inter-rater reliability), RAG retrieval precision at k=3 and k=5, guardrail block rate on adversarial test suite (15 adversarial inputs), per-prompt-version latency and score variance. Human evaluation: structured blind evaluation protocol with two working HR professionals from the Armenian tech market.

**Topic 7 — Responsible AI.** All three sub-categories are implemented: (a) Bias testing: systematic audit across gender signal, age inference, nationality, and educational institution prestige dimensions with 32 paired test cases; (b) Safety guardrails: input PII masking, prompt injection detection, output hallucination flagging, and a mandatory Responsible AI disclaimer on every output surface; (c) Transparency: a per-session Analysis Integrity Report documenting which CV and JD phrases drove each dimensional score, the confidence interval on the composite score, and the Evaluation Integrity Risk Level.

---

## 2. System Architecture Overview

### 2.1 High-Level Design Principle

The foundational design principle is **single-backbone, dual-surface**. The Shared Analysis Engine (SAE) runs once per session and produces a single `CanonicalAnalysisPayload` object. Every subsequent user-facing feature — the Candidate Coach Room, the Recruiter Intelligence Room, the evaluation metrics — reads from this payload through typed access-control selectors. No LLM call is made twice for the same information. The bifurcation is a rendering and access-profile concern, not a computation concern.

### 2.2 Component Map

```
┌─────────────────────────────────────────────────────────────────┐
│  INPUT LAYER                                                    │
│  ┌──────────────────┐          ┌──────────────────┐            │
│  │   CV Document    │          │  Job Description  │            │
│  │  (PDF / text)    │          │  (text / URL)     │            │
│  └────────┬─────────┘          └────────┬──────────┘            │
└───────────│────────────────────────────│─────────────────────────┘
            │                            │
            ▼                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  GUARDRAIL AGENT (Input Pass — runs before any LLM call)       │
│  PII masking | Injection detection | Format validation          │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│  MULTI-AGENT ORCHESTRATOR (LangGraph StateGraph)                │
│                                                                 │
│  PHASE 1 — Parallel Execution (asyncio.gather)                 │
│  ┌─────────────────┐ ┌──────────────────┐ ┌─────────────────┐ │
│  │ Document Intel. │ │ Semantic Align.  │ │ Skills Ontology │ │
│  │ Agent (GPT-4.1) │ │ Agent (GPT-4.1)  │ │ Agent (GPT-4.1) │ │
│  └────────┬────────┘ └────────┬─────────┘ └────────┬────────┘ │
│           │                   │                     │          │
│           └───────────────────┼─────────────────────┘          │
│                               │  Phase 1 Artifacts              │
│  PHASE 2 — Sequential Audit   │                                 │
│           ┌───────────────────▼──────────┐                     │
│           │  Bias & Safety Agent         │                     │
│           │  (inspects Phase 1 outputs)  │                     │
│           └───────────────────┬──────────┘                     │
│                               │                                 │
│           ┌───────────────────▼──────────┐                     │
│           │  Payload Assembly & Scoring  │                     │
│           │  Geometric Mean + Hard Floor │                     │
│           └───────────────────┬──────────┘                     │
└───────────────────────────────│─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  CANONICAL ANALYSIS PAYLOAD (Pydantic-validated)                │
│  Single immutable object — session-scoped state store           │
└───────────┬─────────────────────────────────┬───────────────────┘
            │                                 │
            │  Access Profile: Candidate      │  Access Profile: Recruiter
            ▼                                 ▼
┌───────────────────────┐         ┌───────────────────────────┐
│  CANDIDATE COACH ROOM │         │  RECRUITER INTELLIGENCE   │
│  Gemini 2.0 Flash     │         │  ROOM                     │
│  • Radar chart (7D)   │         │  Gemini 2.0 Flash         │
│  • Skill Bridge viz   │         │  • Scoring dashboard      │
│  • Interview Terminal │         │  • Verification points    │
│  • Action Roadmap     │         │  • Semantic diff view     │
│                       │         │  • Integrity Risk report  │
└───────────────────────┘         └───────────────────────────┘
            │                                 │
            └─────────────────┬───────────────┘
                              ▼
               ┌──────────────────────────┐
               │  EVALUATION & ETHICS TAB │
               │  Prompt A/B metrics      │
               │  Bias test dashboard     │
               │  Human eval integration  │
               └──────────────────────────┘
```

### 2.3 Model Role Assignment

This is a fixed assignment. Deviating from it changes latency and cost characteristics significantly.

| Component | Model | Rationale |
|---|---|---|
| Shared Analysis Engine (all Phase 1 agents) | `gpt-4.1-mini` | Structured JSON output with Pydantic validation. Requires strong instruction-following for schema compliance. Cost-efficient at scale. |
| Candidate Coach Room (narrative generation, interview simulation) | `gemini-2.0-flash` | Superior natural language generation quality for coaching tone in Armenian/Russian/English. Lower latency for interactive simulation. |
| Recruiter Intelligence Room (screening summary, verification point generation) | `gemini-2.0-flash` | Same rationale as above — high-quality analytical prose generation. |
| Bias & Safety Agent (Phase 2) | `gpt-4.1-mini` | Structured classification output. Must produce a validated `BiasAuditResult` object, not prose. |
| Embedding (RAG) | `text-embedding-3-small` (OpenAI) | Dimensionality 1536, cost-efficient, high multilingual performance for Armenian/Russian/English terminology mix. |

---

## 3. Repository Structure and Standards

### 3.1 Directory Tree

```
armeniacareer-ai/
│
├── README.md                          # Single source of truth — architecture, setup, demo
├── CONTRIBUTING.md                    # Commit standards, branch naming, PR checklist
├── PROMPT_VERSIONING_GUIDE.md         # How to add and evaluate new prompt versions
├── .env.example                       # Template — never commit .env
├── requirements.txt                   # Pinned versions (pip freeze output)
├── Makefile                           # make setup | make run | make eval | make test
├── docker-compose.yml                 # ChromaDB local instance
│
├── streamlit_app.py                   # Entry point — tab router only, no business logic
│
├── src/
│   ├── __init__.py
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── canonical_payload.py       # Complete Pydantic model hierarchy
│   │   ├── guardrail_schemas.py       # Input/output validation schemas
│   │   └── evaluation_schemas.py     # Metric and human eval schemas
│   │
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── orchestrator.py            # LangGraph StateGraph definition
│   │   ├── scoring.py                 # Geometric mean + hard floor algorithm
│   │   ├── payload_assembler.py       # Aggregates agent outputs into payload
│   │   └── access_control.py         # Typed access-profile selectors
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base_agent.py              # Abstract base with guardrail wrapper
│   │   ├── document_intelligence.py
│   │   ├── semantic_alignment.py
│   │   ├── skills_ontology.py
│   │   ├── bias_safety.py
│   │   ├── candidate_coach.py
│   │   └── recruiter_intelligence.py
│   │
│   ├── prompts/
│   │   ├── __init__.py
│   │   ├── document_intelligence/
│   │   │   ├── v1_base.py
│   │   │   ├── v2_structured.py
│   │   │   ├── v3_fewshot.py
│   │   │   ├── v4_cot.py
│   │   │   └── PROMPT_CHANGELOG.md
│   │   ├── semantic_alignment/
│   │   │   ├── v1_base.py
│   │   │   ├── v2_structured.py
│   │   │   ├── v3_fewshot.py
│   │   │   └── PROMPT_CHANGELOG.md
│   │   ├── skills_ontology/
│   │   │   └── ... (same structure)
│   │   ├── bias_safety/
│   │   │   └── ...
│   │   ├── candidate_coach/
│   │   │   └── ...
│   │   └── recruiter_intelligence/
│   │       └── ...
│   │
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── pipeline.py                # HybridRAGPipeline class
│   │   ├── corpus_loader.py           # Ingests knowledge base into ChromaDB
│   │   └── reranker.py                # Cross-encoder reranking pass
│   │
│   ├── guardrails/
│   │   ├── __init__.py
│   │   ├── input_guardrail.py         # PII masking + injection detection
│   │   └── output_guardrail.py        # Hallucination detection + schema check
│   │
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── state_manager.py           # st.session_state wrapper
│   │   ├── styles/
│   │   │   └── custom.css
│   │   ├── components/
│   │   │   ├── radar_chart.py         # Plotly Scatterpolar — 7-axis
│   │   │   ├── skill_bridge.py        # Plotly Sankey or custom SVG
│   │   │   ├── pipeline_visualizer.py # Live agent status display
│   │   │   ├── score_cards.py         # Metric card grid
│   │   │   ├── semantic_diff.py       # Side-by-side highlighted text
│   │   │   └── verification_table.py  # st.data_editor wrapper
│   │   └── tabs/
│   │       ├── tab_home.py
│   │       ├── tab_input.py
│   │       ├── tab_shared_analysis.py
│   │       ├── tab_candidate_room.py
│   │       ├── tab_recruiter_room.py
│   │       └── tab_evaluation.py
│   │
│   └── evaluation/
│       ├── __init__.py
│       ├── automated_metrics.py
│       ├── bias_test_runner.py
│       └── human_eval_collector.py
│
├── data/
│   ├── knowledge_base/
│   │   ├── interview_guides/          # STAR method, behavioral question frameworks
│   │   ├── cv_rubrics/                # CV quality criteria, ATS formatting guides
│   │   ├── labor_code/                # RA Labor Code relevant excerpts (plain text)
│   │   └── skill_taxonomy/            # Custom Armenian tech market taxonomy JSON
│   ├── sample_inputs/
│   │   ├── sample_cv_junior_da.txt    # Junior Data Analyst CV (Armenian tech market)
│   │   └── sample_jd_data_analyst.txt # Mid-level DA JD (Armenian fintech/iGaming)
│   ├── evaluation/
│   │   ├── ground_truth_annotations.json   # 15 CV-JD pairs with human score labels
│   │   ├── bias_test_cases.json            # 32 paired bias test inputs
│   │   ├── adversarial_inputs.json         # 15 prompt injection test inputs
│   │   └── human_eval_template.json        # Structured HR evaluator questionnaire
│   └── fallback/
│       └── fallback_sample.json       # Pre-computed payload for offline demo
│
├── logs/
│   ├── .gitkeep
│   └── telemetry/                     # Agent execution traces (local only, .gitignored)
│
└── tests/
    ├── test_schemas.py                # Pydantic model validation tests
    ├── test_scoring.py                # Geometric mean and hard floor edge cases
    ├── test_guardrails.py             # Injection and PII detection tests
    └── test_bias_runner.py            # Bias test case execution tests
```

### 3.2 Commit and Branch Standards

All commits follow the Conventional Commits specification: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`. Branch names follow the pattern `{member-initials}/{feature-slug}`. Pull requests require one approving review before merge to `main`. The commit history must show distributed, incremental work across all team members — not a single bulk commit on the project deadline.

---

## 4. Canonical Analysis Payload — Complete Pydantic Schema

This is the single most critical data structure in the system. Every agent writes into it, every UI component reads from it. It is defined once and imported everywhere. No ad-hoc dictionaries are permitted as inter-agent data transfer formats.

```python
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
```

### 4.1 Access Control Selectors

The access-control module enforces the information asymmetry policy defined in Section 1.2 (Topic 7). It is the single enforcement point — no UI component reads the payload directly.

```python
# src/engine/access_control.py

from typing import Any, Dict
from src.schemas.canonical_payload import CanonicalAnalysisPayload


def get_candidate_view(payload: CanonicalAnalysisPayload) -> Dict[str, Any]:
    """
    Returns the subset of payload fields accessible in the Candidate Coach Room.
    EXCLUDED: recruiter_perspective, governance.bias_audit (raw),
              dimensional_outlier_alert numeric detail,
              governance.phase1_agent_status, hire_recommendation.
    """
    return {
        "session_id": payload.session_id,
        "composite_score_percentage": payload.dimensional_analysis.composite_score_percentage,
        "dimensional_scores": {
            dim: getattr(payload.dimensional_analysis, dim).raw_score
            for dim in [
                "technical_skills_match",
                "experience_depth_alignment",
                "educational_relevance",
                "domain_knowledge",
                "soft_skills_signals",
                "seniority_trajectory",
                "semantic_contextual_alignment",
            ]
        },
        "dimensional_outlier_alert": payload.dimensional_analysis.dimensional_outlier_alert,
        "outlier_dimensions": payload.dimensional_analysis.outlier_dimensions,
        # Note: candidate sees WHICH dimensions are weak, not the numeric floor breach
        "matched_skills": payload.skills_ontology.matched_skills,
        "missing_critical": payload.skills_ontology.missing_critical,
        "missing_preferred": payload.skills_ontology.missing_preferred,
        "transferable": payload.skills_ontology.transferable,
        "gap_severity": payload.skills_ontology.gap_severity,
        "candidate_perspective": payload.candidate_perspective,
        "overall_confidence": payload.overall_analysis_confidence,
        "role_title": payload.jd_entities.role_title,
        "required_seniority": payload.jd_entities.required_seniority,
    }


def get_recruiter_view(payload: CanonicalAnalysisPayload) -> Dict[str, Any]:
    """
    Returns the full analytical scope accessible in the Recruiter Intelligence Room.
    EXCLUDED: candidate_perspective.gap_closure_roadmap (personal development tasks),
              candidate_perspective.motivational_framing,
              raw demographic inference signals (these are never stored — by design).
    """
    return {
        "session_id": payload.session_id,
        "composite_score_percentage": payload.dimensional_analysis.composite_score_percentage,
        "dimensional_analysis": payload.dimensional_analysis,
        "skills_ontology": payload.skills_ontology,
        "semantic_analysis": payload.semantic_analysis,
        "recruiter_perspective": payload.recruiter_perspective,
        "evaluation_integrity_risk": payload.governance.bias_audit.evaluation_integrity_risk,
        "integrity_risk_rationale": payload.governance.bias_audit.risk_rationale,
        "structured_interview_recommendations": (
            payload.governance.bias_audit.structured_interview_recommendations
        ),
        "emergent_bias_detected": payload.governance.bias_audit.emergent_scoring_bias_detected,
        "emergent_bias_details": payload.governance.bias_audit.emergent_bias_details,
        "jd_exclusionary_language_flagged": (
            payload.governance.bias_audit.jd_exclusionary_language_flagged
        ),
        "analysis_completeness_score": payload.analysis_completeness_score,
        "model_chain_used": payload.governance.model_chain_used,
        "cv_entities": payload.cv_entities,
        "jd_entities": payload.jd_entities,
        "hard_floor_applied": payload.dimensional_analysis.hard_floor_applied,
        "outlier_dimensions": payload.dimensional_analysis.outlier_dimensions,
    }
```

---

## 5. Multi-Agent Orchestration Architecture

### 5.1 LangGraph State Definition

```python
# src/engine/orchestrator.py

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict

from src.schemas.canonical_payload import (
    AgentExecutionStatus,
    BiasAuditResult,
    CanonicalAnalysisPayload,
    CVEntities,
    JDEntities,
    SemanticAnalysis,
    SkillsOntologyResult,
)

logger = logging.getLogger(__name__)


class OrchestratorState(TypedDict):
    """
    The typed state object that flows through the LangGraph execution graph.
    All fields are Optional at initialization. Each node populates its
    designated output fields and leaves others unchanged.
    """
    # Input fields (set at graph entry)
    cv_text: str
    jd_text: str
    session_id: str
    language: str
    seniority_context: str
    analysis_start_time_ms: int

    # Phase 1 outputs
    cv_entities: Optional[CVEntities]
    jd_entities: Optional[JDEntities]
    semantic_result: Optional[SemanticAnalysis]
    skills_result: Optional[SkillsOntologyResult]

    # Phase 1 error tracking
    agent_errors: Dict[str, Optional[str]]
    phase1_statuses: Dict[str, AgentExecutionStatus]

    # Phase 2 output
    bias_audit_result: Optional[BiasAuditResult]
    phase2_status: AgentExecutionStatus

    # Final assembled payload
    canonical_payload: Optional[CanonicalAnalysisPayload]

    # Graph control
    current_phase: str  # "input_guard" | "phase1" | "phase2" | "assembly" | "complete"
    abort_reason: Optional[str]  # Set by guardrail if analysis must be halted


# ---------------------------------------------------------------------------
# Node: Input Guardrail
# ---------------------------------------------------------------------------

async def node_input_guardrail(state: OrchestratorState) -> Dict[str, Any]:
    """
    Validates both input texts before any LLM call.
    - Detects and masks PII (names, emails, phone numbers)
    - Detects prompt injection patterns
    - Validates minimum content length and language
    Returns the sanitized texts or sets abort_reason.
    """
    from src.guardrails.input_guardrail import InputGuardrail

    guardrail = InputGuardrail()
    cv_result = guardrail.process(state["cv_text"], document_type="cv")
    jd_result = guardrail.process(state["jd_text"], document_type="jd")

    if cv_result.injection_detected or jd_result.injection_detected:
        return {
            "abort_reason": "Prompt injection pattern detected in input documents.",
            "current_phase": "aborted",
        }

    return {
        "cv_text": cv_result.sanitized_text,
        "jd_text": jd_result.sanitized_text,
        "current_phase": "phase1",
        "agent_errors": {},
        "phase1_statuses": {},
    }


# ---------------------------------------------------------------------------
# Node: Phase 1 — Parallel Execution
# ---------------------------------------------------------------------------

async def node_phase1_parallel(state: OrchestratorState) -> Dict[str, Any]:
    """
    Executes Document Intelligence, Semantic Alignment, and Skills Ontology
    agents concurrently using asyncio.gather. Individual agent failures are
    caught and handled gracefully with fallback payloads, ensuring Phase 2
    always receives a structurally valid (if partially degraded) context.
    """
    from src.agents.document_intelligence import DocumentIntelligenceAgent
    from src.agents.semantic_alignment import SemanticAlignmentAgent
    from src.agents.skills_ontology import SkillsOntologyAgent
    from src.agents.fallback_factories import (
        create_fallback_cv_entities,
        create_fallback_jd_entities,
        create_fallback_semantic_result,
        create_fallback_skills_result,
    )

    doc_agent = DocumentIntelligenceAgent()
    sem_agent = SemanticAlignmentAgent()
    skills_agent = SkillsOntologyAgent()

    results = await asyncio.gather(
        doc_agent.arun(state["cv_text"], state["jd_text"], state["session_id"]),
        sem_agent.arun(state["cv_text"], state["jd_text"], state["session_id"]),
        skills_agent.arun(state["cv_text"], state["jd_text"], state["session_id"]),
        return_exceptions=True,
    )

    doc_result, sem_result, skills_result = results
    agent_errors: Dict[str, Optional[str]] = {}
    phase1_statuses: Dict[str, AgentExecutionStatus] = {}

    # Document Intelligence
    if isinstance(doc_result, Exception):
        logger.error("DocumentIntelligenceAgent failed: %s", doc_result)
        agent_errors["document_intelligence"] = str(doc_result)
        phase1_statuses["document_intelligence"] = AgentExecutionStatus.FALLBACK
        cv_entities = create_fallback_cv_entities()
        jd_entities = create_fallback_jd_entities()
    else:
        phase1_statuses["document_intelligence"] = AgentExecutionStatus.SUCCESS
        cv_entities = doc_result.cv_entities
        jd_entities = doc_result.jd_entities

    # Semantic Alignment
    if isinstance(sem_result, Exception):
        logger.error("SemanticAlignmentAgent failed: %s", sem_result)
        agent_errors["semantic_alignment"] = str(sem_result)
        phase1_statuses["semantic_alignment"] = AgentExecutionStatus.FALLBACK
        sem_result = create_fallback_semantic_result()
    else:
        phase1_statuses["semantic_alignment"] = AgentExecutionStatus.SUCCESS

    # Skills Ontology
    if isinstance(skills_result, Exception):
        logger.error("SkillsOntologyAgent failed: %s", skills_result)
        agent_errors["skills_ontology"] = str(skills_result)
        phase1_statuses["skills_ontology"] = AgentExecutionStatus.FALLBACK
        skills_result = create_fallback_skills_result()
    else:
        phase1_statuses["skills_ontology"] = AgentExecutionStatus.SUCCESS

    return {
        "cv_entities": cv_entities,
        "jd_entities": jd_entities,
        "semantic_result": sem_result,
        "skills_result": skills_result,
        "agent_errors": agent_errors,
        "phase1_statuses": phase1_statuses,
        "current_phase": "phase2",
    }


# ---------------------------------------------------------------------------
# Node: Phase 2 — Sequential Bias & Safety Audit
# ---------------------------------------------------------------------------

async def node_phase2_bias_audit(state: OrchestratorState) -> Dict[str, Any]:
    """
    Runs the Bias & Safety Agent sequentially after Phase 1 completes.
    The agent receives:
      - Original (PII-masked) CV and JD texts
      - All Phase 1 artifacts (entities, semantic scores, skills ontology)
    This enables detection of emergent scoring bias in the Phase 1 outputs,
    not just in the source text.
    """
    from src.agents.bias_safety import BiasSafetyAgent
    from src.agents.fallback_factories import create_fallback_bias_result

    bias_agent = BiasSafetyAgent()

    try:
        bias_result = await bias_agent.arun(
            cv_text=state["cv_text"],
            jd_text=state["jd_text"],
            cv_entities=state["cv_entities"],
            jd_entities=state["jd_entities"],
            semantic_result=state["semantic_result"],
            skills_result=state["skills_result"],
            session_id=state["session_id"],
        )
        phase2_status = AgentExecutionStatus.SUCCESS
    except Exception as exc:
        logger.error("BiasSafetyAgent failed: %s", exc)
        bias_result = create_fallback_bias_result()
        phase2_status = AgentExecutionStatus.FALLBACK

    return {
        "bias_audit_result": bias_result,
        "phase2_status": phase2_status,
        "current_phase": "assembly",
    }


# ---------------------------------------------------------------------------
# Node: Payload Assembly
# ---------------------------------------------------------------------------

async def node_assemble_payload(state: OrchestratorState) -> Dict[str, Any]:
    """
    Aggregates all agent outputs into the CanonicalAnalysisPayload.
    Computes the composite score using the geometric mean algorithm.
    Pre-computes both CandidatePerspective and RecruiterPerspective narratives
    using Gemini via their respective agent modules.
    """
    from src.engine.payload_assembler import PayloadAssembler

    assembler = PayloadAssembler()
    payload = await assembler.assemble(state)

    return {
        "canonical_payload": payload,
        "current_phase": "complete",
    }


# ---------------------------------------------------------------------------
# Graph Construction
# ---------------------------------------------------------------------------

def build_orchestrator_graph() -> StateGraph:
    graph = StateGraph(OrchestratorState)

    graph.add_node("input_guardrail", node_input_guardrail)
    graph.add_node("phase1_parallel", node_phase1_parallel)
    graph.add_node("phase2_bias_audit", node_phase2_bias_audit)
    graph.add_node("assemble_payload", node_assemble_payload)

    graph.set_entry_point("input_guardrail")

    graph.add_conditional_edges(
        "input_guardrail",
        lambda state: "aborted" if state.get("abort_reason") else "phase1_parallel",
        {
            "phase1_parallel": "phase1_parallel",
            "aborted": END,
        },
    )

    graph.add_edge("phase1_parallel", "phase2_bias_audit")
    graph.add_edge("phase2_bias_audit", "assemble_payload")
    graph.add_edge("assemble_payload", END)

    return graph.compile()


# Singleton instance — reused across Streamlit sessions
ORCHESTRATOR = build_orchestrator_graph()
```

---

## 6. Shared Analysis Engine — Phase-by-Phase Implementation

### 6.1 Document Intelligence Agent

This agent is responsible for all extraction. It is the only agent that produces `CVEntities` and `JDEntities` objects. No other agent performs entity extraction.

```python
# src/agents/document_intelligence.py

from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from src.schemas.canonical_payload import CVEntities, JDEntities
from src.prompts.document_intelligence.v3_fewshot import (
    SYSTEM_PROMPT,
    USER_TEMPLATE,
    FEW_SHOT_EXAMPLES,
)


class DocumentIntelligenceOutput(BaseModel):
    cv_entities: CVEntities
    jd_entities: JDEntities


class DocumentIntelligenceAgent:

    def __init__(self, prompt_version: str = "v3"):
        self.llm = ChatOpenAI(
            model="gpt-4.1-mini",
            temperature=0.0,    # Zero temperature mandatory for extraction tasks
            response_format={"type": "json_object"},
        )
        self.parser = PydanticOutputParser(pydantic_object=DocumentIntelligenceOutput)
        self.chain = self._build_chain(prompt_version)

    def _build_chain(self, version: str):
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", USER_TEMPLATE),
        ])
        return prompt | self.llm | self.parser

    async def arun(
        self,
        cv_text: str,
        jd_text: str,
        session_id: str,
    ) -> DocumentIntelligenceOutput:
        return await self.chain.ainvoke({
            "cv_text": cv_text,
            "jd_text": jd_text,
            "few_shot_examples": FEW_SHOT_EXAMPLES,
            "format_instructions": self.parser.get_format_instructions(),
        })
```

### 6.2 Semantic Alignment Agent

```python
# src/agents/semantic_alignment.py

import numpy as np
from openai import AsyncOpenAI
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from src.schemas.canonical_payload import SemanticAnalysis
from src.prompts.semantic_alignment.v3_fewshot import SYSTEM_PROMPT, USER_TEMPLATE


class SemanticAlignmentAgent:

    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0.0,
                              response_format={"type": "json_object"})
        self.openai_client = AsyncOpenAI()
        self.parser = PydanticOutputParser(pydantic_object=SemanticAnalysis)
        self.chain = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", USER_TEMPLATE),
        ]) | self.llm | self.parser

    async def _compute_embedding_similarity(
        self, cv_text: str, jd_text: str
    ) -> float:
        """Computes cosine similarity between mean-pooled CV and JD embeddings."""
        response = await self.openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=[cv_text[:4000], jd_text[:4000]],  # Truncate to avoid token limits
        )
        cv_emb = np.array(response.data[0].embedding)
        jd_emb = np.array(response.data[1].embedding)
        cosine_sim = float(
            np.dot(cv_emb, jd_emb) / (np.linalg.norm(cv_emb) * np.linalg.norm(jd_emb))
        )
        return round(max(0.0, cosine_sim), 4)

    async def arun(
        self,
        cv_text: str,
        jd_text: str,
        session_id: str,
    ) -> SemanticAnalysis:
        # Run embedding similarity computation and LLM extraction in parallel
        import asyncio
        cosine_sim, llm_result = await asyncio.gather(
            self._compute_embedding_similarity(cv_text, jd_text),
            self.chain.ainvoke({
                "cv_text": cv_text,
                "jd_text": jd_text,
                "format_instructions": self.parser.get_format_instructions(),
            }),
        )
        # Override the embedding_cosine_similarity with the computed value
        # (LLM cannot reliably compute this — it's always computed directly)
        result = llm_result.model_copy(
            update={"embedding_cosine_similarity": cosine_sim}
        )
        return result
```

---

## 7. Composite Scoring — Geometric Mean with Hard Flooring

### 7.1 Dimension Weight Configuration

```python
# src/engine/scoring.py

import math
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Weight Configuration
# Weights must sum to exactly 1.0. These are the default weights for a
# generic tech role. Future versions will make these role-type-adaptive.
# ---------------------------------------------------------------------------
DIMENSION_WEIGHTS: Dict[str, float] = {
    "technical_skills_match": 0.25,
    "experience_depth_alignment": 0.20,
    "semantic_contextual_alignment": 0.15,
    "domain_knowledge": 0.15,
    "educational_relevance": 0.10,
    "seniority_trajectory": 0.10,
    "soft_skills_signals": 0.05,
}

assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 1e-9, \
    "DIMENSION_WEIGHTS must sum to 1.0."

# Hard flooring parameters (derived from architectural decision #1)
HARD_FLOOR_THRESHOLD: float = 0.35
HARD_FLOOR_CAP: float = 0.50
LOG_ZERO_CLAMP: float = 1e-9  # Prevents log(0) for zero-scored dimensions


def compute_composite_score(
    dimension_scores: Dict[str, float],
    weights: Dict[str, float] = None,
) -> Tuple[float, float, bool, List[str], bool]:
    """
    Computes the weighted geometric mean composite score.

    Mathematical definition:
        D_composite = exp( Σ w_i * ln(D_i) )
                    = Π (D_i ^ w_i)

    This formulation ensures that a near-zero score on any dimension with
    positive weight produces a composite score that approaches zero, regardless
    of performance on other dimensions. This is the core property that prevents
    the masking of disqualifying weaknesses.

    Hard Floor Rule:
        If any dimension score falls below HARD_FLOOR_THRESHOLD (0.35),
        the composite is capped at HARD_FLOOR_CAP (0.50 = 50%).
        This is in addition to the natural geometric mean penalty.

    Args:
        dimension_scores: Dict mapping dimension name to float in [0.0, 1.0]
        weights: Optional override. Defaults to DIMENSION_WEIGHTS.

    Returns:
        composite_score: float in [0.0, 1.0]
        composite_percentage: float in [0.0, 100.0]
        outlier_alert: bool — True if any dimension is below HARD_FLOOR_THRESHOLD
        outlier_dimensions: list of dimension names below threshold
        hard_floor_applied: bool — True if the cap was actually binding
    """
    if weights is None:
        weights = DIMENSION_WEIGHTS

    # Validate inputs
    assert set(dimension_scores.keys()) == set(weights.keys()), \
        f"dimension_scores keys must match weights keys. " \
        f"Got: {set(dimension_scores.keys())} vs {set(weights.keys())}"

    for dim, score in dimension_scores.items():
        if not (0.0 <= score <= 1.0):
            raise ValueError(f"Dimension score out of range [0,1]: {dim}={score}")

    # Compute weighted geometric mean via log-space
    log_sum = 0.0
    for dim, score in dimension_scores.items():
        clamped_score = max(score, LOG_ZERO_CLAMP)
        log_sum += weights[dim] * math.log(clamped_score)

    composite = math.exp(log_sum)
    composite = round(min(max(composite, 0.0), 1.0), 4)

    # Hard floor detection and application
    outlier_dimensions = [
        dim for dim, score in dimension_scores.items()
        if score < HARD_FLOOR_THRESHOLD
    ]
    outlier_alert = len(outlier_dimensions) > 0
    hard_floor_applied = False

    if outlier_alert and composite > HARD_FLOOR_CAP:
        logger.info(
            "Hard floor applied. Pre-cap composite=%.4f, outlier_dimensions=%s",
            composite,
            outlier_dimensions,
        )
        composite = HARD_FLOOR_CAP
        hard_floor_applied = True

    composite_percentage = round(composite * 100, 1)

    return composite, composite_percentage, outlier_alert, outlier_dimensions, hard_floor_applied
```

### 7.2 Scoring Behavior Examples

The following table illustrates how the geometric mean with hard flooring behaves differently from a naive linear weighted sum, validating the architectural decision:

| Technical | Experience | Semantic | Domain | Education | Seniority | Soft | Linear Sum | Geo. Mean | After Floor |
|---|---|---|---|---|---|---|---|---|---|
| 0.90 | 0.85 | 0.80 | 0.75 | 0.70 | 0.80 | 0.65 | **0.811** | **0.796** | 0.796 |
| 0.90 | **0.10** | 0.80 | 0.75 | 0.70 | 0.80 | 0.65 | **0.717** | **0.523** | **0.500** (floor) |
| 0.95 | 0.90 | **0.15** | 0.85 | 0.80 | 0.85 | 0.75 | **0.768** | **0.622** | **0.500** (floor) |
| **0.20** | **0.20** | 0.70 | 0.60 | 0.50 | 0.60 | 0.55 | **0.486** | **0.337** | **0.337** (geo mean already below cap) |

The second and third rows demonstrate the masking problem that the linear sum exhibits: a 71.7% and 76.8% linear score would produce a deceptively moderate recommendation for candidates who are fundamentally unqualified on a critical dimension.

---

## 8. Prompt Engineering Architecture

### 8.1 Versioning Strategy

Each agent maintains its own five-version prompt history. The production prompt is always V3 (few-shot), which provides the best balance of output stability and quality. V4 (chain-of-thought) is used in the Evaluation Tab for comparison. V5 (constitutional) is reserved for high-stakes recruiter outputs.

### 8.2 Document Intelligence Agent — Prompt Versions

```python
# src/prompts/document_intelligence/v1_base.py

SYSTEM_PROMPT = """You are a document parser. Extract structured information from a CV and a Job Description.
Output your result as a JSON object."""

USER_TEMPLATE = """
CV:
{cv_text}

JOB DESCRIPTION:
{jd_text}

Extract the CV entities and JD entities. Output JSON.
"""
```

```python
# src/prompts/document_intelligence/v2_structured.py

SYSTEM_PROMPT = """You are a precision document parser specializing in HR and recruitment materials.
Your extractions must be exact, exhaustive, and conform strictly to the output schema provided.
Do not infer information that is not explicitly stated. Do not hallucinate skill names or job titles.
If a field cannot be extracted, leave it as null."""

USER_TEMPLATE = """
{format_instructions}

--- CV TEXT (BEGIN) ---
{cv_text}
--- CV TEXT (END) ---

--- JOB DESCRIPTION TEXT (BEGIN) ---
{jd_text}
--- JOB DESCRIPTION TEXT (END) ---

EXTRACTION RULES:
1. For total_years_experience: compute the sum of non-overlapping employment periods in years. Round to one decimal.
2. For inferred_seniority: classify based on years of experience and title signals. Use: intern/junior/mid/senior/lead/principal/executive.
3. For skill category: classify as technical (programming languages, tools, platforms), domain (industry-specific knowledge), soft (communication, leadership), or certification (formal credentials).
4. For required vs. preferred qualifications in JD: required = "must have" / "required" language; preferred = "nice to have" / "preferred" / "bonus" language.
5. Do not include contact information (email, phone, address) in any output field.

Output a single JSON object with keys: cv_entities, jd_entities.
"""
```

```python
# src/prompts/document_intelligence/v3_fewshot.py
# This is the PRODUCTION prompt used in all live analyses.

SYSTEM_PROMPT = """You are an expert HR document intelligence system. You extract structured,
validated entity data from candidate CVs and job descriptions with maximum precision.
You must produce outputs that conform exactly to the JSON schema provided. You have been
calibrated on Armenian, Russian, and English HR documents from the CIS tech market.

CRITICAL RULES:
- Never hallucinate skills, qualifications, or job titles not present in the source text.
- If a duration cannot be computed precisely, estimate conservatively.
- Classify all skills against the taxonomy: technical / domain / soft / certification.
- Distinguish required from preferred JD qualifications with strict fidelity to the source language.
- Remove all PII from output (names, emails, phone numbers are NOT extracted)."""

FEW_SHOT_EXAMPLES = """
--- EXAMPLE 1 ---

INPUT CV (excerpt):
Software Engineer | Picsart | 2021-01 to 2023-06
- Developed REST APIs using Python (FastAPI) and deployed on AWS Lambda
- Managed PostgreSQL databases, wrote complex analytical queries
Skills: Python, FastAPI, PostgreSQL, AWS, Git, Docker

INPUT JD (excerpt):
Mid-level Backend Engineer | Required: Python (3yr+), PostgreSQL, REST API design | Preferred: Docker, Kubernetes | 3+ years experience

EXPECTED OUTPUT (partial):
{{
  "cv_entities": {{
    "work_history": [{{
      "company": "Picsart",
      "title": "Software Engineer",
      "start_date": "2021-01",
      "end_date": "2023-06",
      "duration_months": 29,
      "responsibilities": ["Developed REST APIs using Python (FastAPI) and deployed on AWS Lambda", "Managed PostgreSQL databases, wrote complex analytical queries"],
      "technologies_mentioned": ["Python", "FastAPI", "AWS Lambda", "PostgreSQL"]
    }}],
    "raw_skills": [
      {{"raw_name": "Python", "canonical_name": "Python", "category": "technical"}},
      {{"raw_name": "FastAPI", "canonical_name": "FastAPI", "category": "technical"}},
      {{"raw_name": "PostgreSQL", "canonical_name": "PostgreSQL", "category": "technical"}},
      {{"raw_name": "AWS", "canonical_name": "Amazon Web Services", "category": "technical"}},
      {{"raw_name": "Git", "canonical_name": "Git", "category": "technical"}},
      {{"raw_name": "Docker", "canonical_name": "Docker", "category": "technical"}}
    ],
    "total_years_experience": 2.4,
    "inferred_seniority": "mid"
  }},
  "jd_entities": {{
    "role_title": "Mid-level Backend Engineer",
    "required_skills": [
      {{"raw_name": "Python", "canonical_name": "Python", "category": "technical", "proficiency_signal": "3yr+"}},
      {{"raw_name": "PostgreSQL", "canonical_name": "PostgreSQL", "category": "technical"}},
      {{"raw_name": "REST API design", "canonical_name": "REST API Design", "category": "technical"}}
    ],
    "preferred_skills": [
      {{"raw_name": "Docker", "canonical_name": "Docker", "category": "technical"}},
      {{"raw_name": "Kubernetes", "canonical_name": "Kubernetes", "category": "technical"}}
    ],
    "required_experience_years": 3.0,
    "required_seniority": "mid"
  }}
}}
"""

USER_TEMPLATE = """
{format_instructions}

Study these calibration examples carefully:
{few_shot_examples}

Now perform the same extraction on the following documents:

--- CV TEXT (BEGIN) ---
{cv_text}
--- CV TEXT (END) ---

--- JOB DESCRIPTION TEXT (BEGIN) ---
{jd_text}
--- JOB DESCRIPTION TEXT (END) ---

Output a single JSON object with keys: cv_entities, jd_entities.
Apply all extraction rules demonstrated in the examples above.
"""
```

```python
# src/prompts/document_intelligence/v4_cot.py
# Chain-of-thought version — used in Evaluation Tab for comparison only

USER_TEMPLATE = """
{format_instructions}

Before producing your JSON output, reason step by step:

STEP 1 — CV ANALYSIS:
List all work experience entries you can identify. For each, determine the duration.
List all explicitly mentioned skills. Classify each one.
Estimate total years of experience.
Determine the inferred seniority level and explain why.

STEP 2 — JD ANALYSIS:
Identify the role title.
Separate required qualifications from preferred qualifications. Quote the language that signals each.
List all skills explicitly mentioned.
Identify required experience years and seniority level.

STEP 3 — JSON CONSTRUCTION:
Now produce the final JSON using your reasoning from Steps 1 and 2.

--- CV TEXT (BEGIN) ---
{cv_text}
--- CV TEXT (END) ---

--- JOB DESCRIPTION TEXT (BEGIN) ---
{jd_text}
--- JOB DESCRIPTION TEXT (END) ---
"""
```

### 8.3 Skills Ontology Agent — V3 (Production Prompt)

```python
# src/prompts/skills_ontology/v3_fewshot.py

SYSTEM_PROMPT = """You are a skills taxonomy and gap analysis specialist with deep knowledge of
the CIS and Armenian technology job market. You receive structured skill lists extracted from a
candidate CV and a job description. Your task is to produce a precise skills gap analysis.

You operate against the following taxonomy categories: technical, domain, soft, certification.

MATCHING RULES:
1. Exact match: skill appears in both CV and JD with equivalent canonical name.
2. Partial / transferable match: skill has substantial functional overlap with a JD requirement
   (e.g., MySQL ↔ PostgreSQL: both are relational SQL databases, transfer confidence = 0.75).
3. Missing critical: skill is in required_qualifications and absent from CV with no transferable equivalent.
4. Missing preferred: skill is in preferred_qualifications and absent from CV.

IMPORTANT: Do not invent skills not present in the provided lists. Your output must be
100% derived from the extracted entity lists provided as input."""

USER_TEMPLATE = """
{format_instructions}

--- CANDIDATE SKILLS (extracted from CV) ---
{cv_skills_json}

--- JD REQUIRED SKILLS ---
{jd_required_skills_json}

--- JD PREFERRED SKILLS ---
{jd_preferred_skills_json}

Perform the skills gap analysis. For each transferable skill, provide a transfer_confidence (0.0–1.0)
and a transfer_rationale (one sentence explaining the functional overlap).

Compute:
- coverage_ratio = count(matched_skills) / count(jd_required_skills)
- gap_severity: "critical" if critical_gap_count >= 3 or any must-have tool is missing;
               "moderate" if 1-2 critical gaps; "minor" if only preferred skills are missing;
               "none" if full coverage.

Output JSON conforming to the SkillsOntologyResult schema.
"""
```

### 8.4 Candidate Coach Agent — Production Prompt (Gemini)

```python
# src/prompts/candidate_coach/v3_fewshot.py
# Executed via Gemini 2.0 Flash — separate from the GPT-4.1-mini chain

SYSTEM_PROMPT = """You are an expert career coach specializing in the Armenian and CIS technology
job market. You speak with warmth, precision, and genuine encouragement. You never give empty
compliments — your praise is always specific and grounded in evidence from the candidate's profile.
Your coaching is actionable: every piece of advice includes a concrete next step.

You are operating within a Responsible AI system. You are a Decision-Support Assistant only.
You do not make hiring decisions. You help candidates understand their strengths and develop a
realistic, evidence-based preparation roadmap.

You produce outputs in {language}. Maintain professional but approachable tone throughout."""

USER_TEMPLATE = """
The following candidate has applied for the role of: {role_title} (Seniority: {required_seniority})

--- ANALYSIS RESULTS ---
Composite Match Score: {composite_score_percentage}%
Dimensional Scores:
{dimensional_scores_formatted}

--- SKILL GAPS ---
Missing Critical Skills: {missing_critical_skills}
Missing Preferred Skills: {missing_preferred_skills}
Transferable Skills: {transferable_skills}
Gap Severity: {gap_severity}

--- CANDIDATE STRENGTHS ---
Matched Skills: {matched_skills}
Top Strength Evidence: {evidence_phrases}

--- YOUR TASK ---
Generate the following four components:

1. STRENGTH_NARRATIVE (2-3 paragraphs):
   Begin by acknowledging the candidate's genuine strengths with specific evidence.
   Be specific — name skills, experiences, or patterns that stand out.

2. INTERVIEW_PREPARATION_FOCUS (1-2 paragraphs):
   Based on the gap analysis, what should the candidate prioritize preparing for?
   Provide 2-3 specific areas and a brief strategy for each.

3. SALARY_POSITIONING_CONTEXT (1 paragraph):
   Given the composite score and the role's seniority requirements, provide honest,
   grounded context on salary expectations in the Armenian tech market for this role level.

4. GAP_CLOSURE_ROADMAP (structured list):
   For each critical and significant gap, produce an ActionItem with:
   - priority (1 = most urgent)
   - dimension (which scoring axis this addresses)
   - skill_or_gap (specific skill or area)
   - current_state_description
   - target_state_description
   - suggested_learning_resources (3 specific resources: course, book, or project)
   - estimated_effort_weeks

Output JSON with keys: strength_narrative, interview_preparation_focus,
salary_positioning_context, gap_closure_roadmap.
"""
```

---

## 9. Hybrid RAG Pipeline

### 9.1 Knowledge Base Architecture

The ChromaDB instance is organized into four collections with distinct retrieval strategies:

| Collection Name | Content Type | Retrieval Strategy | Primary Use Case |
|---|---|---|---|
| `interview_guides` | STAR method, behavioral frameworks, question taxonomies | Dense (semantic similarity) | Candidate Coach interview prep |
| `cv_rubrics` | ATS optimization, section formatting, Armenian market norms | Dense + BM25 hybrid | Candidate roadmap suggestions |
| `labor_code_am` | RA Labor Code excerpts (responsible hiring only) | BM25 (keyword-exact) | Governance flagging |
| `skill_taxonomy_cis` | Armenian/CIS tech market skill hierarchy JSON | BM25 + structured lookup | Skills Ontology normalization |

### 9.2 Hybrid Retrieval Implementation

```python
# src/rag/pipeline.py

import logging
from typing import Any, Dict, List, Optional

from langchain.retrievers import BM25Retriever, EnsembleRetriever
from langchain.schema import Document
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

logger = logging.getLogger(__name__)

COLLECTION_CONFIGS: Dict[str, Dict[str, Any]] = {
    "interview_guides": {
        "dense_weight": 0.70,
        "bm25_weight": 0.30,
        "k": 4,
    },
    "cv_rubrics": {
        "dense_weight": 0.60,
        "bm25_weight": 0.40,
        "k": 3,
    },
    "labor_code_am": {
        "dense_weight": 0.20,
        "bm25_weight": 0.80,   # Exact legal terminology matching dominates
        "k": 2,
    },
    "skill_taxonomy_cis": {
        "dense_weight": 0.50,
        "bm25_weight": 0.50,
        "k": 5,
    },
}


class HybridRAGPipeline:
    """
    Two-retriever ensemble pipeline combining BM25 sparse retrieval with
    dense embedding-based retrieval. Fusion is performed by the EnsembleRetriever
    using Reciprocal Rank Fusion (RRF) with collection-specific weighting.
    """

    def __init__(self, persist_directory: str = "./data/chroma_db"):
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        self.persist_directory = persist_directory
        self._vectorstores: Dict[str, Chroma] = {}
        self._loaded_documents: Dict[str, List[Document]] = {}

    def load_collection(self, collection_name: str) -> None:
        """Loads or initializes a ChromaDB collection."""
        self._vectorstores[collection_name] = Chroma(
            collection_name=collection_name,
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings,
        )
        # Load all documents for BM25 index construction
        raw_docs = self._vectorstores[collection_name].get(include=["documents", "metadatas"])
        self._loaded_documents[collection_name] = [
            Document(page_content=doc, metadata=meta)
            for doc, meta in zip(raw_docs["documents"], raw_docs["metadatas"])
        ]
        logger.info(
            "Loaded collection '%s' with %d documents.",
            collection_name,
            len(self._loaded_documents[collection_name]),
        )

    def get_ensemble_retriever(self, collection_name: str) -> EnsembleRetriever:
        """Constructs an EnsembleRetriever for the specified collection."""
        if collection_name not in self._vectorstores:
            self.load_collection(collection_name)

        config = COLLECTION_CONFIGS[collection_name]
        k = config["k"]

        dense_retriever = self._vectorstores[collection_name].as_retriever(
            search_kwargs={"k": k}
        )
        bm25_retriever = BM25Retriever.from_documents(
            self._loaded_documents[collection_name], k=k
        )

        return EnsembleRetriever(
            retrievers=[bm25_retriever, dense_retriever],
            weights=[config["bm25_weight"], config["dense_weight"]],
        )

    def retrieve_coaching_context(
        self,
        skill_gaps: List[str],
        role_title: str,
        language: str = "en",
    ) -> List[Document]:
        """
        Retrieves relevant coaching material for the Candidate Coach agent.
        Queries both interview_guides and cv_rubrics collections.
        """
        query = (
            f"career coaching preparation for {role_title}. "
            f"Skill gaps to address: {', '.join(skill_gaps[:5])}."
        )
        guides_retriever = self.get_ensemble_retriever("interview_guides")
        rubrics_retriever = self.get_ensemble_retriever("cv_rubrics")

        guides_docs = guides_retriever.get_relevant_documents(query)
        rubrics_docs = rubrics_retriever.get_relevant_documents(query)

        # Deduplicate by page_content hash
        seen_content = set()
        unique_docs = []
        for doc in guides_docs + rubrics_docs:
            content_hash = hash(doc.page_content[:200])
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                unique_docs.append(doc)

        return unique_docs[:6]  # Cap at 6 chunks to stay within context budget

    def retrieve_governance_context(self, jd_text: str) -> List[Document]:
        """
        Retrieves relevant labor code excerpts for the Bias & Safety agent.
        Used only for generating responsible hiring reminders — not legal advice.
        """
        query = f"hiring discrimination prohibited criteria employment law"
        retriever = self.get_ensemble_retriever("labor_code_am")
        return retriever.get_relevant_documents(query)
```

### 9.3 Corpus Loader

```python
# src/rag/corpus_loader.py

import json
import os
from pathlib import Path
from typing import List

from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings


def load_knowledge_base(
    knowledge_base_dir: str = "./data/knowledge_base",
    persist_directory: str = "./data/chroma_db",
) -> None:
    """
    Ingests all knowledge base text files into ChromaDB.
    Designed to be run once during project setup (via `make setup`).
    Safe to re-run — will skip collections that already contain documents.
    """
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        separators=["\n\n", "\n", ". ", " "],
    )

    collection_dir_map = {
        "interview_guides": "interview_guides",
        "cv_rubrics": "cv_rubrics",
        "labor_code_am": "labor_code",
        "skill_taxonomy_cis": "skill_taxonomy",
    }

    for collection_name, subdir in collection_dir_map.items():
        collection_path = Path(knowledge_base_dir) / subdir
        if not collection_path.exists():
            print(f"WARNING: Knowledge base subdirectory not found: {collection_path}")
            continue

        # Check if collection already has data
        vectorstore = Chroma(
            collection_name=collection_name,
            persist_directory=persist_directory,
            embedding_function=embeddings,
        )
        existing_count = vectorstore._collection.count()
        if existing_count > 0:
            print(f"Collection '{collection_name}' already loaded ({existing_count} docs). Skipping.")
            continue

        # Load and chunk all .txt and .md files
        documents: List[Document] = []
        for filepath in collection_path.glob("**/*.txt"):
            with open(filepath, encoding="utf-8") as f:
                content = f.read()
            chunks = text_splitter.create_documents(
                [content],
                metadatas=[{"source": str(filepath), "collection": collection_name}],
            )
            documents.extend(chunks)

        if documents:
            vectorstore.add_documents(documents)
            print(f"Loaded {len(documents)} chunks into '{collection_name}'.")
        else:
            print(f"WARNING: No documents found in {collection_path}.")
```

---

## 10. Dashboard UI — Component Architecture and State Machine

### 10.1 State Manager

The application maintains a single, typed session state object. All UI components read from and write to this object through controlled accessors. Direct manipulation of `st.session_state` outside of the state manager is prohibited.

```python
# src/ui/state_manager.py

from enum import Enum
from typing import Optional

import streamlit as st

from src.schemas.canonical_payload import CanonicalAnalysisPayload


class AppState(str, Enum):
    """
    The application state machine governs all tab visibility and component rendering.
    State transitions are strictly forward — no backward transitions except RESET.
    """
    LANDING = "landing"
    INPUTS_READY = "inputs_ready"
    PROCESSING = "processing"
    ANALYSIS_COMPLETE = "analysis_complete"
    ABORTED = "aborted"


class SessionStateManager:
    """Typed wrapper around st.session_state. Centralizes all state mutations."""

    @staticmethod
    def initialize() -> None:
        defaults = {
            "app_state": AppState.LANDING,
            "cv_text": "",
            "jd_text": "",
            "language": "hy",
            "seniority_context": "junior",
            "canonical_payload": None,
            "processing_log": [],
            "active_room": None,       # "candidate" | "recruiter" | None
            "interview_history": [],   # Chat messages for interview simulation
            "selected_prompt_version": "v3",
            "evaluation_run_complete": False,
        }
        for key, default_value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = default_value

    @staticmethod
    def set_state(new_state: AppState) -> None:
        st.session_state["app_state"] = new_state

    @staticmethod
    def get_state() -> AppState:
        return st.session_state.get("app_state", AppState.LANDING)

    @staticmethod
    def get_payload() -> Optional[CanonicalAnalysisPayload]:
        return st.session_state.get("canonical_payload")

    @staticmethod
    def set_payload(payload: CanonicalAnalysisPayload) -> None:
        st.session_state["canonical_payload"] = payload
        SessionStateManager.set_state(AppState.ANALYSIS_COMPLETE)

    @staticmethod
    def append_processing_log(message: str) -> None:
        st.session_state["processing_log"].append(message)

    @staticmethod
    def reset() -> None:
        keys_to_reset = [
            "app_state", "cv_text", "jd_text", "canonical_payload",
            "processing_log", "active_room", "interview_history",
        ]
        for key in keys_to_reset:
            if key in st.session_state:
                del st.session_state[key]
        SessionStateManager.initialize()
```

### 10.2 Radar Chart Component (7-Dimensional)

```python
# src/ui/components/radar_chart.py

from typing import Dict, List, Optional

import plotly.graph_objects as go
import streamlit as st


DIMENSION_DISPLAY_LABELS: Dict[str, str] = {
    "technical_skills_match": "Technical Skills",
    "experience_depth_alignment": "Experience Depth",
    "educational_relevance": "Education",
    "domain_knowledge": "Domain Knowledge",
    "soft_skills_signals": "Soft Skills",
    "seniority_trajectory": "Seniority Fit",
    "semantic_contextual_alignment": "Contextual Alignment",
}


def render_candidate_radar_chart(
    dimension_scores: Dict[str, float],
    outlier_dimensions: List[str],
    role_title: str,
    container=None,
) -> None:
    """
    Renders the 7-axis radar chart for the Candidate Coach Room.
    Overlays candidate profile against an ideal (1.0) target profile.
    Highlights outlier dimensions in a distinct warning color.
    """
    categories = list(DIMENSION_DISPLAY_LABELS.values())
    dimension_keys = list(DIMENSION_DISPLAY_LABELS.keys())

    candidate_values = [dimension_scores.get(key, 0.0) for key in dimension_keys]
    ideal_values = [1.0] * len(categories)

    # Close the polygon by repeating the first point
    categories_closed = categories + [categories[0]]
    candidate_closed = candidate_values + [candidate_values[0]]
    ideal_closed = ideal_values + [ideal_values[0]]

    fig = go.Figure()

    # Target profile (JD ideal)
    fig.add_trace(go.Scatterpolar(
        r=ideal_closed,
        theta=categories_closed,
        fill="toself",
        name=f"Target: {role_title}",
        line=dict(color="rgba(83, 74, 183, 0.4)", width=1.5, dash="dash"),
        fillcolor="rgba(83, 74, 183, 0.05)",
    ))

    # Candidate profile
    fig.add_trace(go.Scatterpolar(
        r=candidate_closed,
        theta=categories_closed,
        fill="toself",
        name="Your Profile",
        line=dict(color="rgba(29, 158, 117, 0.85)", width=2.5),
        fillcolor="rgba(29, 158, 117, 0.15)",
    ))

    # Outlier dimension markers
    if outlier_dimensions:
        outlier_labels = [DIMENSION_DISPLAY_LABELS[d] for d in outlier_dimensions]
        outlier_values = [dimension_scores.get(d, 0.0) for d in outlier_dimensions]
        fig.add_trace(go.Scatterpolar(
            r=outlier_values,
            theta=outlier_labels,
            mode="markers",
            name="Priority Development Areas",
            marker=dict(
                color="rgba(216, 90, 48, 0.9)",
                size=12,
                symbol="diamond",
            ),
        ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 1],
                tickvals=[0.25, 0.5, 0.75, 1.0],
                ticktext=["25%", "50%", "75%", "100%"],
                gridcolor="rgba(136, 135, 128, 0.2)",
                linecolor="rgba(136, 135, 128, 0.3)",
            ),
            angularaxis=dict(
                gridcolor="rgba(136, 135, 128, 0.15)",
                linecolor="rgba(136, 135, 128, 0.25)",
            ),
            bgcolor="rgba(0,0,0,0)",
        ),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.25,
            xanchor="center",
            x=0.5,
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=480,
        margin=dict(l=60, r=60, t=40, b=80),
    )

    target = container if container else st
    target.plotly_chart(fig, use_container_width=True)
```

### 10.3 Pipeline Visualizer Component

```python
# src/ui/components/pipeline_visualizer.py

import time
from typing import Dict

import streamlit as st


PIPELINE_STAGES = [
    ("input_guard", "Input Validation & PII Masking"),
    ("doc_intelligence", "Document Intelligence Agent"),
    ("semantic_alignment", "Semantic Alignment Agent"),
    ("skills_ontology", "Skills Ontology Agent"),
    ("bias_safety", "Bias & Safety Audit (Phase 2)"),
    ("assembly", "Payload Assembly & Scoring"),
]

STATUS_ICONS = {
    "pending": "○",
    "running": "◉",
    "success": "●",
    "fallback": "◈",
    "failed": "✕",
}

STATUS_COLORS = {
    "pending": "color: #888780",
    "running": "color: #185FA5; font-weight: 500",
    "success": "color: #3B6D11; font-weight: 500",
    "fallback": "color: #854F0B; font-weight: 500",
    "failed": "color: #A32D2D; font-weight: 500",
}


def render_pipeline_status(
    stage_statuses: Dict[str, str],
    placeholder=None,
) -> None:
    """
    Renders a live pipeline status display showing each agent's execution state.
    Designed to be called inside a st.empty() placeholder and re-rendered on update.
    """
    target = placeholder if placeholder else st

    rows = []
    for stage_key, stage_label in PIPELINE_STAGES:
        status = stage_statuses.get(stage_key, "pending")
        icon = STATUS_ICONS[status]
        style = STATUS_COLORS[status]
        rows.append(
            f'<div style="padding: 6px 0; font-size: 14px;">'
            f'<span style="{style}">{icon} {stage_label}</span>'
            f'</div>'
        )

    html_content = (
        '<div style="font-family: var(--font-mono, monospace); '
        'padding: 16px; border: 0.5px solid rgba(136,135,128,0.3); '
        'border-radius: 8px;">'
        + "".join(rows)
        + "</div>"
    )
    target.markdown(html_content, unsafe_allow_html=True)
```

### 10.4 Tab Architecture — Candidate Coach Room

```python
# src/ui/tabs/tab_candidate_room.py

import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage

from src.engine.access_control import get_candidate_view
from src.ui.components.radar_chart import render_candidate_radar_chart
from src.ui.state_manager import SessionStateManager


def render_candidate_room() -> None:
    """
    Renders the Candidate Coach Room — the personal development interface.
    Reads exclusively through get_candidate_view() to enforce access profile.
    """
    payload = SessionStateManager.get_payload()
    if payload is None:
        st.warning("No analysis available. Please complete the input and analysis steps first.")
        return

    view = get_candidate_view(payload)
    perspective = view["candidate_perspective"]

    # --- Page Header ---
    st.markdown("## Candidate Coach Room")
    st.caption(
        "This room contains your personalized development analysis. "
        "All information here is for your preparation only."
    )

    # --- Top Metric Row ---
    col_score, col_gap, col_conf = st.columns(3)
    with col_score:
        st.metric(
            label="Match Score",
            value=f"{view['composite_score_percentage']:.1f}%",
            delta="Hard floor applied" if payload.dimensional_analysis.hard_floor_applied else None,
            delta_color="off",
        )
    with col_gap:
        gap_count = len(view["missing_critical"])
        st.metric(label="Critical Gaps", value=str(gap_count))
    with col_conf:
        st.metric(
            label="Analysis Confidence",
            value=f"{view['overall_confidence'] * 100:.0f}%",
        )

    if view["dimensional_outlier_alert"]:
        st.warning(
            f"One or more competency dimensions require significant development: "
            f"{', '.join(view['outlier_dimensions'])}. "
            "These are highlighted in the radar chart below and have been assigned "
            "highest priority in your roadmap."
        )

    st.divider()

    # --- Radar Chart ---
    st.subheader("Competency Profile")
    render_candidate_radar_chart(
        dimension_scores=view["dimensional_scores"],
        outlier_dimensions=view["outlier_dimensions"],
        role_title=view["role_title"],
    )

    st.divider()

    # --- Strength Narrative ---
    st.subheader("Your Strengths")
    st.write(perspective.strength_narrative)

    st.divider()

    # --- Gap Closure Roadmap ---
    st.subheader("Development Roadmap")
    st.caption(
        "The following action items are prioritized by impact on your match score. "
        "Items marked as critical gap closure address dimensions that are currently below the qualification threshold."
    )

    roadmap = sorted(perspective.gap_closure_roadmap, key=lambda x: x.priority)
    for item in roadmap:
        priority_label = "Critical Priority" if item.is_critical_gap_closure else f"Priority {item.priority}"
        with st.expander(
            f"{priority_label} — {item.skill_or_gap} ({item.dimension.replace('_', ' ').title()})"
        ):
            col_current, col_target = st.columns(2)
            with col_current:
                st.markdown("**Current State**")
                st.write(item.current_state_description)
            with col_target:
                st.markdown("**Target State**")
                st.write(item.target_state_description)

            if item.estimated_effort_weeks:
                st.caption(f"Estimated effort: {item.estimated_effort_weeks} weeks")

            if item.suggested_learning_resources:
                st.markdown("**Suggested Resources**")
                for resource in item.suggested_learning_resources:
                    st.markdown(f"- {resource}")

    st.divider()

    # --- Interview Preparation Terminal ---
    st.subheader("Interview Simulation")
    st.caption(
        f"The following questions are generated based on your gap profile for the role of "
        f"{view['role_title']}. Respond as you would in a real interview."
    )

    if "interview_history" not in st.session_state:
        st.session_state["interview_history"] = []

    # Display chat history
    for message in st.session_state["interview_history"]:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    # Generate first question if history is empty
    if not st.session_state["interview_history"]:
        with st.spinner("Preparing your first interview question..."):
            question = _generate_interview_question(view, is_first=True)
        st.session_state["interview_history"].append({
            "role": "assistant",
            "content": question,
        })
        st.rerun()

    # Candidate response input
    if user_input := st.chat_input("Your response..."):
        st.session_state["interview_history"].append({
            "role": "user",
            "content": user_input,
        })
        with st.spinner("Evaluating your response..."):
            feedback = _evaluate_response(user_input, view)
            next_question = _generate_interview_question(view, is_first=False)
            combined = f"{feedback}\n\n---\n\n**Next question:** {next_question}"

        st.session_state["interview_history"].append({
            "role": "assistant",
            "content": combined,
        })
        st.rerun()


def _generate_interview_question(view: dict, is_first: bool) -> str:
    """Generates a context-aware interview question using Gemini."""
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.7)
    gap_summary = ", ".join([s.skill_name for s in view["missing_critical"][:3]])
    prompt = (
        f"Generate {'the opening' if is_first else 'a follow-up'} behavioral interview question "
        f"for a candidate applying for {view['role_title']}. "
        f"The question should probe one of these gap areas: {gap_summary}. "
        f"Use the STAR method context. Output only the question itself, nothing else."
    )
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content


def _evaluate_response(user_response: str, view: dict) -> str:
    """Evaluates a candidate's interview response using Gemini coaching persona."""
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.3)
    prompt = (
        f"You are a supportive career coach evaluating an interview response for a "
        f"{view['role_title']} role. Score the response on three axes (1–10 each): "
        f"Structure (follows STAR format), Relevance (addresses the role's requirements), "
        f"Specificity (includes measurable outcomes or concrete examples). "
        f"Provide one sentence of specific, actionable improvement advice per axis. "
        f"Be encouraging but precise.\n\n"
        f"RESPONSE TO EVALUATE:\n{user_response}"
    )
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content
```

### 10.5 Tab Architecture — Recruiter Intelligence Room

```python
# src/ui/tabs/tab_recruiter_room.py

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from src.engine.access_control import get_recruiter_view
from src.schemas.canonical_payload import HireRecommendation
from src.ui.state_manager import SessionStateManager


RECOMMENDATION_COLORS = {
    HireRecommendation.STRONG_YES: "color: #3B6D11; font-weight: 600",
    HireRecommendation.YES: "color: #1D9E75; font-weight: 500",
    HireRecommendation.MAYBE: "color: #BA7517; font-weight: 500",
    HireRecommendation.NO: "color: #A32D2D; font-weight: 600",
}

INTEGRITY_RISK_COLORS = {
    "low": "background-color: #EAF3DE; color: #27500A; padding: 4px 12px; border-radius: 8px",
    "medium": "background-color: #FAEEDA; color: #633806; padding: 4px 12px; border-radius: 8px",
    "high": "background-color: #FCEBEB; color: #501313; padding: 4px 12px; border-radius: 8px",
}


def render_recruiter_room() -> None:
    """
    Renders the Recruiter Intelligence Room — the analytical screening interface.
    Reads exclusively through get_recruiter_view() to enforce access profile.
    """
    payload = SessionStateManager.get_payload()
    if payload is None:
        st.warning("No analysis available. Please complete the input and analysis steps first.")
        return

    view = get_recruiter_view(payload)
    perspective = view["recruiter_perspective"]
    dim_analysis = view["dimensional_analysis"]

    st.markdown("## Recruiter Intelligence Room")
    st.caption(
        "RESPONSIBLE AI NOTICE: This system is a Decision-Support Assistant only. "
        "All outputs require human review before any employment decision is made."
    )

    # --- Top Section: Score + Recommendation ---
    col_score, col_rec, col_integrity = st.columns(3)

    with col_score:
        delta_text = "Hard floor applied — see dimensional breakdown" if view["hard_floor_applied"] else None
        st.metric(
            label="Composite Match Score",
            value=f"{view['composite_score_percentage']:.1f}%",
            delta=delta_text,
            delta_color="off",
        )

    with col_rec:
        rec = perspective.hire_recommendation
        rec_style = RECOMMENDATION_COLORS.get(rec, "")
        st.markdown(f"**Hire Recommendation**")
        st.markdown(
            f'<span style="{rec_style}">{rec.value.replace("_", " ").upper()}</span>',
            unsafe_allow_html=True,
        )

    with col_integrity:
        risk = view["evaluation_integrity_risk"]
        risk_style = INTEGRITY_RISK_COLORS.get(risk, "")
        st.markdown("**Evaluation Integrity**")
        st.markdown(
            f'<span style="{risk_style}">{risk.upper()} RISK</span>',
            unsafe_allow_html=True,
        )

    # --- Screening Summary ---
    with st.expander("Screening Summary", expanded=True):
        st.write(perspective.screening_summary)
        st.write(perspective.hire_recommendation_rationale)

    st.divider()

    # --- Dimensional Score Breakdown ---
    st.subheader("Dimensional Score Breakdown")
    _render_dimension_bars(dim_analysis, view["outlier_dimensions"])

    st.divider()

    # --- Verification Points Table ---
    st.subheader("Targeted Verification Points")
    st.caption(
        "These structured questions are designed to objectively verify areas where the "
        "CV evidence is insufficient or ambiguous. They are not biased probes — each question "
        "is grounded in specific skill or experience gaps identified in the analysis."
    )

    if perspective.verification_points:
        vp_df = pd.DataFrame([
            {
                "Topic": vp.topic,
                "Gap Evidence": vp.evidence_gap_description,
                "Why It Matters": vp.why_it_matters,
                "Suggested Question": vp.suggested_interview_question,
                "Importance": vp.importance_level.replace("_", " ").title(),
            }
            for vp in perspective.verification_points
        ])
        st.dataframe(vp_df, use_container_width=True, hide_index=True)

    st.divider()

    # --- Evaluation Integrity Panel ---
    st.subheader("Evaluation Integrity Report")
    _render_integrity_panel(view)


def _render_dimension_bars(dim_analysis, outlier_dimensions: list) -> None:
    """Renders a horizontal bar chart of all seven dimension scores."""
    from src.ui.components.radar_chart import DIMENSION_DISPLAY_LABELS

    dims = list(DIMENSION_DISPLAY_LABELS.keys())
    labels = list(DIMENSION_DISPLAY_LABELS.values())
    scores = [getattr(dim_analysis, d).raw_score * 100 for d in dims]
    colors = [
        "rgba(163, 45, 45, 0.75)" if d in outlier_dimensions else "rgba(29, 158, 117, 0.75)"
        for d in dims
    ]

    fig = go.Figure(go.Bar(
        x=scores,
        y=labels,
        orientation="h",
        marker_color=colors,
        text=[f"{s:.0f}%" for s in scores],
        textposition="outside",
    ))

    fig.add_vline(
        x=35,
        line_dash="dash",
        line_color="rgba(163, 45, 45, 0.4)",
        annotation_text="Floor (35%)",
        annotation_position="top right",
    )

    fig.update_layout(
        height=360,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(range=[0, 115], showgrid=True, gridcolor="rgba(136,135,128,0.15)"),
        yaxis=dict(tickfont=dict(size=12)),
        margin=dict(l=0, r=40, t=20, b=20),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_integrity_panel(view: dict) -> None:
    risk = view["evaluation_integrity_risk"]
    st.write(f"**Risk Level:** {risk.upper()}")
    st.write(view["integrity_risk_rationale"])

    if view["structured_interview_recommendations"]:
        st.markdown("**Structured Interview Recommendations**")
        for rec in view["structured_interview_recommendations"]:
            st.markdown(f"- {rec}")

    if view["emergent_bias_detected"]:
        st.error(
            "Emergent scoring bias was detected in the analysis outputs. "
            f"Details: {view['emergent_bias_details']}"
        )

    st.caption(
        "This report documents the algorithmic fairness posture of this analysis session. "
        "It does not constitute legal advice. All hiring decisions must comply with applicable "
        "employment law in the relevant jurisdiction."
    )
```

---

## 11. Evaluation Framework

### 11.1 Automated Metrics

```python
# src/evaluation/automated_metrics.py

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from src.schemas.canonical_payload import CanonicalAnalysisPayload
from src.schemas.evaluation_schemas import PromptVersionMetrics


@dataclass
class AgentRunResult:
    session_id: str
    prompt_version: str
    raw_output: str
    parsed_payload: Optional[CanonicalAnalysisPayload]
    latency_ms: int
    parse_success: bool
    validation_errors: List[str]


def compute_json_validity_rate(
    results: List[AgentRunResult],
) -> float:
    """JSON Schema Validity Rate: proportion of runs that parsed against Pydantic schema."""
    if not results:
        return 0.0
    valid_count = sum(1 for r in results if r.parse_success)
    return round(valid_count / len(results), 4)


def compute_score_calibration(
    model_scores: List[float],
    human_scores: List[float],
) -> Dict[str, float]:
    """
    Measures alignment between model composite scores and human evaluator scores.
    Returns Pearson correlation and Mean Absolute Error.
    """
    import numpy as np
    assert len(model_scores) == len(human_scores), "Score lists must be equal length."

    model_arr = np.array(model_scores)
    human_arr = np.array(human_scores)

    correlation = float(np.corrcoef(model_arr, human_arr)[0, 1])
    mae = float(np.mean(np.abs(model_arr - human_arr)))

    return {
        "pearson_correlation": round(correlation, 4),
        "mean_absolute_error": round(mae, 4),
    }


def compute_guardrail_block_rate(
    adversarial_results: List[Dict[str, Any]],
) -> float:
    """
    Guardrail Block Rate: proportion of adversarial inputs correctly blocked.
    adversarial_results is a list of {input: str, expected_blocked: bool, was_blocked: bool}
    """
    if not adversarial_results:
        return 0.0
    correct_blocks = sum(
        1 for r in adversarial_results
        if r["expected_blocked"] == r["was_blocked"]
    )
    return round(correct_blocks / len(adversarial_results), 4)


def compare_prompt_versions(
    version_results: Dict[str, List[AgentRunResult]],
) -> List[PromptVersionMetrics]:
    """
    Aggregates metrics across prompt versions for the Evaluation Tab display.
    Returns a list of PromptVersionMetrics sorted by composite quality score.
    """
    from statistics import mean, stdev

    comparison = []
    for version, results in version_results.items():
        latencies = [r.latency_ms for r in results]
        comparison.append(PromptVersionMetrics(
            version=version,
            n_runs=len(results),
            json_validity_rate=compute_json_validity_rate(results),
            mean_latency_ms=round(mean(latencies), 1),
            std_latency_ms=round(stdev(latencies), 1) if len(latencies) > 1 else 0.0,
        ))

    return sorted(comparison, key=lambda x: x.json_validity_rate, reverse=True)
```

### 11.2 Human Evaluation Protocol

The human evaluation protocol is designed for blind administration. HR evaluators receive only the CV, JD, and model output — not the prompt version, model name, or session ID. Evaluators score on five dimensions using a 1–5 Likert scale.

```json
// data/evaluation/human_eval_template.json
{
  "evaluator_id": "EVALUATOR_PLACEHOLDER",
  "session_id": "SESSION_PLACEHOLDER",
  "evaluation_date": "DATE_PLACEHOLDER",
  "dimensions": {
    "match_score_accuracy": {
      "description": "How accurately does the composite match score reflect your professional assessment of this candidate-JD fit?",
      "scale": "1 (completely wrong) to 5 (perfectly accurate)"
    },
    "skill_gap_completeness": {
      "description": "How complete is the identification of genuine skill gaps?",
      "scale": "1 (many gaps missed) to 5 (all significant gaps identified)"
    },
    "coaching_feedback_quality": {
      "description": "How useful and actionable is the coaching feedback for the candidate?",
      "scale": "1 (generic and unhelpful) to 5 (specific and immediately actionable)"
    },
    "verification_point_relevance": {
      "description": "How well do the recruiter verification points probe the actual risk areas?",
      "scale": "1 (irrelevant questions) to 5 (precisely targeted probes)"
    },
    "overall_fairness": {
      "description": "Does the analysis appear to evaluate the candidate on relevant, objective criteria only?",
      "scale": "1 (clearly biased) to 5 (fully objective)"
    }
  },
  "open_response": {
    "most_valuable_insight": "",
    "most_significant_error_or_omission": "",
    "additional_comments": ""
  },
  "scores": {
    "match_score_accuracy": null,
    "skill_gap_completeness": null,
    "coaching_feedback_quality": null,
    "verification_point_relevance": null,
    "overall_fairness": null
  }
}
```

---

## 12. Responsible AI and Bias Testing

### 12.1 Input Guardrail Pipeline

```python
# src/guardrails/input_guardrail.py

import re
from dataclasses import dataclass, field
from typing import List


# PII patterns for Armenian, Russian, and English contexts
PII_PATTERNS = {
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", re.IGNORECASE),
    "phone_international": re.compile(r"\+?[0-9]{1,3}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4}"),
    "armenian_passport": re.compile(r"[A-Z]{2}\d{7}"),
    "social_security": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
}

# Prompt injection / jailbreak patterns
INJECTION_PATTERNS = [
    re.compile(r"ignore (all |previous |above |prior )?(instructions?|rules?|guidelines?)", re.IGNORECASE),
    re.compile(r"you are now", re.IGNORECASE),
    re.compile(r"pretend (to be|you are)", re.IGNORECASE),
    re.compile(r"(override|bypass|disable) (safety|guardrail|filter|policy)", re.IGNORECASE),
    re.compile(r"<(script|img|iframe|object|embed)[^>]*>", re.IGNORECASE),
    re.compile(r"system:\s*(you|act|be|respond)", re.IGNORECASE),
    re.compile(r"\[INST\]|\[\/INST\]|<\|im_start\|>|<\|im_end\|>"),
]

MINIMUM_TEXT_LENGTH = 50  # Characters — below this, the input is too short to be meaningful


@dataclass
class GuardrailResult:
    sanitized_text: str
    injection_detected: bool = False
    injection_patterns_found: List[str] = field(default_factory=list)
    pii_fields_masked: List[str] = field(default_factory=list)
    length_valid: bool = True


class InputGuardrail:

    def process(self, text: str, document_type: str = "cv") -> GuardrailResult:
        result = GuardrailResult(sanitized_text=text)

        # Length validation
        if len(text.strip()) < MINIMUM_TEXT_LENGTH:
            result.length_valid = False

        # Injection detection
        for pattern in INJECTION_PATTERNS:
            if pattern.search(text):
                result.injection_detected = True
                result.injection_patterns_found.append(pattern.pattern[:50])

        # PII masking (applied before any LLM call)
        sanitized = text
        for pii_type, pattern in PII_PATTERNS.items():
            matches = pattern.findall(sanitized)
            if matches:
                result.pii_fields_masked.append(pii_type)
                sanitized = pattern.sub(f"[{pii_type.upper()}_REDACTED]", sanitized)

        result.sanitized_text = sanitized
        return result
```

### 12.2 Bias Test Runner

The bias test suite contains 32 paired test cases. Each pair consists of two near-identical CV inputs that differ only in a single demographic signal. The expected behavior is that the composite score and all dimensional scores should not differ significantly (defined as delta < 0.05) between the pair members.

```python
# src/evaluation/bias_test_runner.py

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

SIGNIFICANCE_THRESHOLD = 0.05  # Maximum acceptable score delta between paired inputs


@dataclass
class BiasTestCase:
    case_id: str
    bias_dimension: str   # gender_signal | age_inference | nationality | educational_prestige
    variant_a_label: str
    variant_b_label: str
    cv_text_a: str
    cv_text_b: str
    jd_text: str
    expected_delta: float = 0.0  # Expected: near-zero


@dataclass
class BiasTestResult:
    case_id: str
    bias_dimension: str
    score_a: float
    score_b: float
    delta: float
    passed: bool
    failure_reason: str = ""


class BiasTestRunner:

    def __init__(self, test_cases_path: str = "./data/evaluation/bias_test_cases.json"):
        self.test_cases = self._load_test_cases(test_cases_path)

    def _load_test_cases(self, path: str) -> List[BiasTestCase]:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return [BiasTestCase(**case) for case in raw["test_cases"]]

    async def run_all(self, orchestrator) -> List[BiasTestResult]:
        """
        Runs all 32 paired bias test cases through the full analysis pipeline.
        Returns a list of BiasTestResult objects.
        """
        results = []
        for case in self.test_cases:
            result_a, result_b = await self._run_pair(orchestrator, case)
            score_a = result_a.dimensional_analysis.composite_score
            score_b = result_b.dimensional_analysis.composite_score
            delta = abs(score_a - score_b)
            passed = delta <= SIGNIFICANCE_THRESHOLD

            results.append(BiasTestResult(
                case_id=case.case_id,
                bias_dimension=case.bias_dimension,
                score_a=round(score_a, 4),
                score_b=round(score_b, 4),
                delta=round(delta, 4),
                passed=passed,
                failure_reason=(
                    f"Score delta {delta:.4f} exceeds threshold {SIGNIFICANCE_THRESHOLD} "
                    f"between '{case.variant_a_label}' and '{case.variant_b_label}'."
                ) if not passed else "",
            ))

        self._log_summary(results)
        return results

    async def _run_pair(self, orchestrator, case: BiasTestCase):
        import asyncio
        from src.engine.orchestrator import OrchestratorState

        state_a = OrchestratorState(
            cv_text=case.cv_text_a, jd_text=case.jd_text,
            session_id=f"{case.case_id}_a", language="en",
            seniority_context="mid", analysis_start_time_ms=0,
            cv_entities=None, jd_entities=None, semantic_result=None,
            skills_result=None, agent_errors={}, phase1_statuses={},
            bias_audit_result=None, phase2_status=None,
            canonical_payload=None, current_phase="input_guard",
            abort_reason=None,
        )
        state_b = state_a.copy()
        state_b["cv_text"] = case.cv_text_b
        state_b["session_id"] = f"{case.case_id}_b"

        result_a, result_b = await asyncio.gather(
            orchestrator.ainvoke(state_a),
            orchestrator.ainvoke(state_b),
        )
        return result_a["canonical_payload"], result_b["canonical_payload"]

    def _log_summary(self, results: List[BiasTestResult]) -> None:
        passed = sum(1 for r in results if r.passed)
        total = len(results)
        logger.info("Bias test summary: %d/%d passed (%.1f%%)", passed, total, passed/total*100)

        by_dimension: Dict[str, List[BiasTestResult]] = {}
        for r in results:
            by_dimension.setdefault(r.bias_dimension, []).append(r)
        for dim, dim_results in by_dimension.items():
            dim_passed = sum(1 for r in dim_results if r.passed)
            logger.info("  %s: %d/%d", dim, dim_passed, len(dim_results))
```

### 12.3 Output Guardrail

```python
# src/guardrails/output_guardrail.py

import re
from dataclasses import dataclass, field
from typing import List


HALLUCINATION_RISK_PATTERNS = [
    # Fabricated skill names containing model-typical noise
    re.compile(r"\b(TechStack|SkillX|FrameworkY|ToolZ)\b", re.IGNORECASE),
    # Fabricated credential names
    re.compile(r"certified\s+\w+\s+professional\s+\w{3,}", re.IGNORECASE),
    # Score claims not derivable from the payload
    re.compile(r"\d+\s+years\s+of\s+experience\s+in\s+\w{20,}", re.IGNORECASE),
]

DISCLAIMER_REQUIRED_IN_CONTEXTS = [
    "screening_summary",
    "hire_recommendation_rationale",
    "comparative_profile_summary",
]

MANDATORY_DISCLAIMER = (
    "NOTE: This analysis is a Decision-Support tool only. "
    "All employment decisions must be made by a qualified human professional "
    "in compliance with applicable labor laws."
)


@dataclass
class OutputGuardrailResult:
    output_text: str
    hallucination_flags: List[str] = field(default_factory=list)
    disclaimer_appended: bool = False
    passed: bool = True


class OutputGuardrail:

    def process(self, text: str, output_context: str = "") -> OutputGuardrailResult:
        result = OutputGuardrailResult(output_text=text)

        # Hallucination pattern check
        for pattern in HALLUCINATION_RISK_PATTERNS:
            matches = pattern.findall(text)
            if matches:
                result.hallucination_flags.extend([f"Pattern '{pattern.pattern[:30]}' matched: {m}" for m in matches])

        # Disclaimer injection for high-stakes recruiter outputs
        if output_context in DISCLAIMER_REQUIRED_IN_CONTEXTS:
            if MANDATORY_DISCLAIMER not in text:
                result.output_text = text + f"\n\n{MANDATORY_DISCLAIMER}"
                result.disclaimer_appended = True

        result.passed = len(result.hallucination_flags) == 0
        return result
```

---

## 13. Two-Day Sprint Execution Plan

This plan is calibrated for a 2-day sprint with a 3–4 person team. Tasks are sequenced by dependency — no item should be started before its prerequisites are marked complete.

### Day 1 — Core Backend (Target: working JSON output from CV + JD input)

**Block 1 (Morning, ~4 hours) — Foundation**

| # | Task | Owner Role | Dependency |
|---|---|---|---|
| 1.1 | Create repository with full directory structure. Initialize README, .env.example, requirements.txt, Makefile | DevOps/All | None |
| 1.2 | Implement `src/schemas/canonical_payload.py` — full Pydantic schema as specified in Section 4 | Backend Lead | None |
| 1.3 | Implement `src/engine/scoring.py` — geometric mean + hard floor algorithm + unit tests in `tests/test_scoring.py` | Backend | 1.2 |
| 1.4 | Implement `src/guardrails/input_guardrail.py` — PII masking + injection detection | Security | None |
| 1.5 | Create `data/knowledge_base/` directory structure and populate with initial text files | Data/Content | None |

**Block 2 (Afternoon, ~4 hours) — Agents and Engine**

| # | Task | Owner Role | Dependency |
|---|---|---|---|
| 2.1 | Implement V1, V2, V3 prompt files for Document Intelligence Agent | Prompt Engineer | 1.2 |
| 2.2 | Implement V1, V2, V3 prompt files for Semantic Alignment Agent | Prompt Engineer | 1.2 |
| 2.3 | Implement V1, V2, V3 prompt files for Skills Ontology Agent | Prompt Engineer | 1.2 |
| 2.4 | Implement `DocumentIntelligenceAgent`, `SemanticAlignmentAgent`, `SkillsOntologyAgent` classes | Backend Lead | 2.1, 2.2, 2.3 |
| 2.5 | Implement `BiasSafetyAgent` (Phase 2) | Backend | 2.4 |
| 2.6 | Implement `src/rag/corpus_loader.py` and load knowledge base into ChromaDB locally | Data | 1.5 |
| 2.7 | Implement `src/rag/pipeline.py` — HybridRAGPipeline with BM25 + dense retrieval | Backend | 2.6 |

**Block 3 (End of Day 1 — Integration Test)**

| # | Task | Owner Role | Dependency |
|---|---|---|---|
| 3.1 | Implement `src/engine/orchestrator.py` — full LangGraph StateGraph as specified in Section 5 | Backend Lead | 2.4, 2.5 |
| 3.2 | Implement `src/engine/payload_assembler.py` — aggregates agent outputs, calls scoring.py, invokes Gemini for narratives | Backend | 3.1 |
| 3.3 | End-to-end integration test: `sample_cv_junior_da.txt` + `sample_jd_data_analyst.txt` → `CanonicalAnalysisPayload` JSON output | All | 3.2 |
| 3.4 | Save validated output as `data/fallback/fallback_sample.json` for demo safety | All | 3.3 |

**Day 1 success criterion:** Running `python -c "from src.engine.orchestrator import ORCHESTRATOR; import asyncio; ..."` with sample inputs produces a valid `CanonicalAnalysisPayload` object that passes Pydantic validation.

---

### Day 2 — Frontend, Evaluation, and Demo Preparation

**Block 4 (Morning, ~4 hours) — UI Construction**

| # | Task | Owner Role | Dependency |
|---|---|---|---|
| 4.1 | Implement `src/ui/state_manager.py` | Frontend | None |
| 4.2 | Implement `streamlit_app.py` — tab router with state-gated rendering | Frontend | 4.1 |
| 4.3 | Implement `tab_home.py` — project description, architecture flow, Responsible AI disclaimer | Frontend | 4.1 |
| 4.4 | Implement `tab_input.py` — split-panel upload zone with language/seniority selectors | Frontend | 4.1 |
| 4.5 | Implement `tab_shared_analysis.py` — metrics cards, skills matrix tables | Frontend | 4.1 |
| 4.6 | Implement `src/ui/components/radar_chart.py` | Frontend | None |
| 4.7 | Implement `tab_candidate_room.py` — full Candidate Coach Room as specified in Section 10.4 | Frontend | 4.6 |
| 4.8 | Implement `tab_recruiter_room.py` — full Recruiter Intelligence Room as specified in Section 10.5 | Frontend | 4.6 |

**Block 5 (Afternoon, ~4 hours) — Evaluation and Ethics Tab**

| # | Task | Owner Role | Dependency |
|---|---|---|---|
| 5.1 | Implement `src/evaluation/automated_metrics.py` | Evaluation | 3.2 |
| 5.2 | Implement `src/evaluation/bias_test_runner.py` and populate `data/evaluation/bias_test_cases.json` with at least 12 test pairs | Evaluation | 3.2 |
| 5.3 | Implement `tab_evaluation.py` — prompt version comparison, bias test dashboard, human eval input | Frontend/Evaluation | 5.1, 5.2 |
| 5.4 | Run bias test suite on sample inputs. Document results. | All | 5.2 |
| 5.5 | Deploy to Streamlit Community Cloud. Verify `.env` → `st.secrets` migration. | DevOps | 4.8 |
| 5.6 | Capture screenshots for fallback demo safety kit. Verify `fallback_sample.json` loads correctly. | All | 5.5 |
| 5.7 | Review README completeness against instructor checklist. | All | 5.5 |

---

## 14. Live Demo Scenario Script

The following script governs the 10–12 minute live demo portion of the final presentation. All team members should be familiar with every step to handle handoffs gracefully.

**Step 1 — Home Tab (1 minute).** Present the project's dual-sided value proposition using the architecture diagram on the Home tab. Read aloud the Responsible AI disclaimer to acknowledge explicitly that the system is a Decision-Support tool. Emphasize: "The system never makes a hiring decision. It informs one."

**Step 2 — Input Tab (1.5 minutes).** Paste the pre-prepared `sample_cv_junior_da.txt` (Junior Data Analyst with 2 years of sales analytics experience, transitioning into tech) and `sample_jd_data_analyst.txt` (Mid-level DA role in an Armenian fintech company requiring Python, SQL, and data pipeline experience). Select Armenian as the output language, Junior as the seniority context. Click "Run Shared Analysis Engine." Switch to the pipeline visualizer to show all five agents executing in sequence.

**Step 3 — Shared Analysis Tab (1.5 minutes).** Show the composite score (expected range: 52–68% given the gap profile of the sample inputs). Draw attention to the dimensional breakdown: if the hard floor was applied, point to it explicitly as evidence of the geometric mean architecture working correctly — "A linear sum would have given this candidate a 71%. The geometric mean and floor correctly flag an experience depth gap."

**Step 4 — Candidate Coach Room (3 minutes).** Show the seven-axis radar chart. Point to the collapsed axis (expected: experience_depth_alignment). Demonstrate the gap closure roadmap with its prioritized action items. Run one round of the interview simulation — ask the candidate question out loud, type a sample response, show the STAR-based feedback. Emphasize: "This candidate sees a personal coach, not a rejection notice."

**Step 5 — Recruiter Intelligence Room (2 minutes).** Show the hire recommendation card and dimensional bar chart. Open the Verification Points table and demonstrate that the recruiter's questions probe exactly the gaps the candidate's roadmap is addressing — without revealing the candidate's personal development tasks. Show the Evaluation Integrity Risk panel. Emphasize: "The recruiter sees objective verification tools, not demographic signals."

**Step 6 — Evaluation & Ethics Tab (2 minutes).** Show the prompt version comparison table demonstrating that V3 (few-shot) achieves the highest JSON validity rate and lowest score variance. Run the bias test visualization — show that gender signal substitution produces a score delta below 0.05 on the sample inputs. State explicitly: "We tested our own system for bias. Here are the results."

---

*End of Implementation Specification v1.0.0*
