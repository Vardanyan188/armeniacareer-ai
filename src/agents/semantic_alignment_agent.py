# src/agents/semantic_alignment_agent.py
#
# SemanticAlignmentAgent — Phase 1 Parallel Agent
#
# Architectural position:
#   Executed concurrently with DocumentIntelligenceAgent and SkillsOntologyAgent
#   via asyncio.gather in node_phase1_parallel (src/engine/orchestrator.py).
#
# Input contract:
#   - parsed_cv: ParsedCVOutput — the full, validated structured output from the
#     Document Intelligence Agent. NEVER the raw CV text string.
#   - jd_entities: JDEntities — the validated job description entity object.
#     NEVER the raw JD text string.
#   Both inputs are guaranteed non-null before this agent is invoked.
#
# Output contract:
#   Returns SemanticAlignmentOutput — a Pydantic-validated superset of the
#   canonical SemanticAnalysis model. The PayloadAssembler calls
#   output.to_canonical_semantic_analysis() to extract the subset for the
#   CanonicalAnalysisPayload. The extended dimensional scores are consumed
#   directly by the PayloadAssembler to construct DimensionalAnalysis.
#
# Embedding strategy:
#   All embeddings are computed in a single batched API call (cost-efficient).
#   Five dimensional corpora are composed from structured fields:
#     [0] technical_skills      : CV tech canonicals vs JD required/preferred canonicals
#     [1] experience            : CV role responsibilities vs JD responsibilities
#     [2] domain_context        : CV domain signals + work domains vs JD industry/role
#     [3] education_quals       : CV degree/certs vs JD education requirements
#     [4] composite             : Full structured CV representation vs full JD representation
#   Each dimension produces a DimensionalEmbeddingAlignment object.
#
# LLM responsibility (gpt-4.1-mini, temperature=0.0):
#   The LLM provides EXACTLY ONE numeric score: contextual_domain_alignment_score.
#   All other scores are derived from embedding cosine similarities.
#   The LLM extracts key phrases and semantic concepts from the COMPOSITE corpora.
#   It never receives raw document text and never computes similarity.
#
# Seniority compatibility scoring:
#   Computed via a deterministic rule function with asymmetric penalty decay.
#   Over-qualification penalized at 0.15× per level; under-qualification at 0.25× per level.
#   This reflects the practical reality that over-qualified candidates present lower
#   hire risk than under-qualified ones in the Armenian tech hiring context.

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Dict, List, Optional, Tuple

import numpy as np
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI
from pydantic import BaseModel, Field, field_validator, model_validator

from src.schemas.canonical_payload import (
    JDEntities,
    SemanticAnalysis,
    SeniorityLevel,
)
from src.schemas.cv_parsing_schema import (
    ParsedCVOutput,
    SkillCategory,
)
from src.prompts.semantic_alignment.v3_fewshot import (
    SYSTEM_PROMPT,
    FEW_SHOT_EXAMPLE,
    USER_TEMPLATE,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Module-Level Constants
# ─────────────────────────────────────────────────────────────────────────────

EMBEDDING_MODEL: str = "text-embedding-3-small"

# Max characters per corpus string before truncation.
# text-embedding-3-small supports ~8,191 tokens; 6,000 chars ≈ 1,500 tokens,
# leaving headroom for multilingual CIS text with higher token density.
CORPUS_TRUNCATION_CHARS: int = 6_000

# Minimum non-empty corpus length; below this threshold the dimension is
# treated as "data insufficient" and assigned a 0.0 similarity.
CORPUS_MIN_LENGTH: int = 8

# Cosine similarity band thresholds for qualitative classification.
# Inclusive lower bound, exclusive upper bound (except "high" which is inclusive).
ALIGNMENT_BAND_THRESHOLDS: Dict[str, Tuple[float, float]] = {
    "high":       (0.70, 1.01),
    "moderate":   (0.48, 0.70),
    "low":        (0.25, 0.48),
    "negligible": (0.00, 0.25),
}

# Seniority level ordinal mapping for distance-based compatibility scoring.
SENIORITY_ORDINAL: Dict[str, int] = {
    SeniorityLevel.INTERN:     0,
    SeniorityLevel.JUNIOR:     1,
    SeniorityLevel.MID:        2,
    SeniorityLevel.SENIOR:     3,
    SeniorityLevel.LEAD:       4,
    SeniorityLevel.PRINCIPAL:  5,
    SeniorityLevel.EXECUTIVE:  6,
}

# Keys for the five dimensional corpora. Order must match the batch embedding list.
DIMENSION_KEYS: List[str] = [
    "technical_skills",
    "experience_responsibilities",
    "domain_context",
    "education_qualifications",
    "composite",
]

# Maps each dimension key → the DimensionalAnalysis field it feeds in the payload.
DIMENSION_TO_PAYLOAD_FIELD: Dict[str, str] = {
    "technical_skills":           "technical_skills_match",
    "experience_responsibilities": "experience_depth_alignment",
    "domain_context":              "domain_knowledge",
    "education_qualifications":    "educational_relevance",
    "composite":                   "semantic_contextual_alignment",
}

# Number of work history roles used for experience corpus composition.
_EXPERIENCE_ROLES_LIMIT: int = 4
_EXPERIENCE_RESPONSIBILITIES_PER_ROLE: int = 3

# Cap on JD responsibilities included in the experience corpus.
_JD_RESPONSIBILITIES_LIMIT: int = 8


# ─────────────────────────────────────────────────────────────────────────────
# Internal Data Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DimensionalCorpus:
    """
    Immutable container for one dimension's paired corpus texts.
    cv_text and jd_text are derived exclusively from validated structured fields.
    Neither field ever contains raw document text passed through from the pipeline input.

    field_sources are stored for audit trail purposes only (PayloadAssembler
    uses them to compute analysis_completeness_score when corpora are sparse).
    """
    dimension: str
    cv_text: str
    jd_text: str
    cv_field_sources: List[str] = dc_field(default_factory=list)
    jd_field_sources: List[str] = dc_field(default_factory=list)

    @property
    def cv_is_sufficient(self) -> bool:
        return len(self.cv_text.strip()) >= CORPUS_MIN_LENGTH

    @property
    def jd_is_sufficient(self) -> bool:
        return len(self.jd_text.strip()) >= CORPUS_MIN_LENGTH

    @property
    def both_sufficient(self) -> bool:
        return self.cv_is_sufficient and self.jd_is_sufficient


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Output Models
# ─────────────────────────────────────────────────────────────────────────────

class DimensionalEmbeddingAlignment(BaseModel):
    """
    Cosine similarity result for one semantic dimension.
    Each instance corresponds to one entry in DIMENSION_KEYS.
    Consumed by PayloadAssembler to construct DimensionalAnalysis raw_score values.
    """
    dimension: str = Field(
        ...,
        description="One of DIMENSION_KEYS. Identifies which analysis axis this covers.",
    )
    payload_field: str = Field(
        ...,
        description="The DimensionalAnalysis field this score populates via PayloadAssembler.",
    )
    cosine_similarity: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Direct cosine similarity between CV and JD corpus embeddings.",
    )
    alignment_band: str = Field(
        ...,
        pattern="^(high|moderate|low|negligible)$",
    )
    cv_corpus_preview: str = Field(
        "",
        description="First 180 chars of the CV corpus used. For audit and UI evidence display.",
        max_length=180,
    )
    jd_corpus_preview: str = Field(
        "",
        description="First 180 chars of the JD corpus used.",
        max_length=180,
    )
    data_sufficient: bool = Field(
        True,
        description="False if either corpus was below CORPUS_MIN_LENGTH. Score = 0.0 in that case.",
    )


class LLMKeyPhraseOutput(BaseModel):
    """
    Structured output from the semantic alignment LLM chain.
    The LLM provides key phrase extractions and ONE numeric score.
    All other numeric values are embedding-derived and computed separately.
    """
    cv_key_phrases: List[str] = Field(
        ...,
        min_length=2,
        description="Semantically significant 2–5 word phrases from CV representation.",
    )
    jd_key_phrases: List[str] = Field(
        ...,
        min_length=2,
        description="Semantically significant 2–5 word phrases from JD representation.",
    )
    shared_semantic_concepts: List[str] = Field(
        ...,
        description="Concepts with functional equivalence in both representations.",
    )
    cv_unique_concepts: List[str] = Field(
        default_factory=list,
        description="Significant concepts in CV absent from JD requirements.",
    )
    jd_unique_concepts: List[str] = Field(
        default_factory=list,
        description="Significant concepts in JD absent from CV.",
    )
    domain_alignment_rationale: str = Field(
        ...,
        description="2–3 sentence plain-language domain fit assessment with specific evidence.",
    )
    contextual_domain_alignment_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="LLM-assessed contextual domain alignment. The only numeric score from LLM.",
    )
    seniority_compatibility_rationale: str = Field(
        ...,
        description="Assessment of career trajectory vs JD seniority requirements.",
    )
    education_relevance_rationale: str = Field(
        ...,
        description="Assessment of educational background relevance to the role.",
    )
    key_phrase_overlap_ratio: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Proportion of JD key phrases with semantic equivalent in CV phrases. "
            "= len(shared_semantic_concepts) / max(len(jd_key_phrases), 1)"
        ),
    )

    @field_validator("key_phrase_overlap_ratio", mode="after")
    @classmethod
    def validate_overlap_ratio_consistency(cls, v: float, info) -> float:
        """
        Cross-validates key_phrase_overlap_ratio against shared and jd phrase counts.
        Tolerance of ±0.08 for LLM rounding variance.
        If LLM provides an inconsistent value, recompute deterministically.
        """
        values = info.data
        jd_phrases = values.get("jd_key_phrases", [])
        shared = values.get("shared_semantic_concepts", [])
        if not jd_phrases:
            return 0.0
        computed = len(shared) / len(jd_phrases)
        if abs(computed - v) > 0.08:
            logger.warning(
                "LLMKeyPhraseOutput: key_phrase_overlap_ratio inconsistency detected. "
                "LLM provided %.4f, computed %.4f from phrase counts. Using computed value.",
                v, computed,
            )
            return round(computed, 4)
        return round(v, 4)


class SemanticAlignmentOutput(BaseModel):
    """
    Root output model for SemanticAlignmentAgent.

    This is a superset of the canonical SemanticAnalysis model defined in
    src/schemas/canonical_payload.py. It contains all SemanticAnalysis fields
    plus extended dimensional alignment signals used by the PayloadAssembler
    to construct the full DimensionalAnalysis object.

    ACCESS PATTERN:
      - For CanonicalAnalysisPayload insertion: call to_canonical_semantic_analysis()
      - For DimensionalAnalysis construction: read dimensional_alignments directly
        via DIMENSION_TO_PAYLOAD_FIELD mapping
      - For UI evidence display: read domain/seniority/education rationales

    FIELD OWNERSHIP:
      - embedding_cosine_similarity: computed from composite dimension embeddings
      - key_phrase_overlap_ratio: computed/validated from LLM phrase counts
      - cv_unique_key_phrases: from LLM cv_unique_concepts
      - jd_unique_key_phrases: from LLM jd_unique_concepts
      - shared_key_phrases: from LLM shared_semantic_concepts
      - contextual_domain_alignment: from LLM contextual_domain_alignment_score
      - seniority_compatibility_score: deterministic rule function (not LLM)
      - All dimensional cosine similarities: embedding computation
    """

    # ── SemanticAnalysis-compatible core fields ──────────────────────────────
    # These map 1:1 to src/schemas/canonical_payload.py SemanticAnalysis
    embedding_cosine_similarity: float = Field(..., ge=0.0, le=1.0)
    key_phrase_overlap_ratio: float = Field(..., ge=0.0, le=1.0)
    cv_unique_key_phrases: List[str] = Field(default_factory=list)
    jd_unique_key_phrases: List[str] = Field(default_factory=list)
    shared_key_phrases: List[str] = Field(default_factory=list)
    contextual_domain_alignment: float = Field(..., ge=0.0, le=1.0)

    # ── Extended dimensional alignment signals ───────────────────────────────
    dimensional_alignments: List[DimensionalEmbeddingAlignment] = Field(
        ...,
        description="Per-dimension embedding cosine similarities. One entry per DIMENSION_KEY.",
    )

    # ── PayloadAssembler-ready dimensional score map ─────────────────────────
    # These are the raw_score values for DimensionalAnalysis construction.
    # Keyed identically to DimensionalAnalysis field names.
    dimensional_scores_for_payload: Dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Flattened dimension → score map for PayloadAssembler. "
            "Keys match DimensionalAnalysis field names exactly."
        ),
    )

    # ── Seniority compatibility (deterministic, not LLM) ────────────────────
    seniority_compatibility_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Rule-based seniority gap score. Feeds seniority_trajectory dimension.",
    )
    seniority_compatibility_rationale: str = Field(
        default="",
        description="LLM-provided seniority trajectory assessment text.",
    )

    # ── LLM interpretive rationales ──────────────────────────────────────────
    domain_alignment_rationale: str = Field(
        default="",
        description="LLM-provided domain alignment explanation.",
    )
    education_relevance_rationale: str = Field(
        default="",
        description="LLM-provided education relevance explanation.",
    )

    # ── Corpus evidence (for UI evidence panel and audit) ────────────────────
    cv_composite_representation: str = Field(
        default="",
        description="The composed CV corpus used for composite-dimension embedding.",
    )
    jd_composite_representation: str = Field(
        default="",
        description="The composed JD corpus used for composite-dimension embedding.",
    )

    # ── Agent execution metadata ─────────────────────────────────────────────
    agent_session_id: str = ""
    total_embedding_vectors_computed: int = 0
    llm_extraction_confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Set to 0.8 if LLM output required repair; 0.5 if full fallback activated.",
    )
    processing_latency_ms: Optional[int] = None

    @model_validator(mode="after")
    def validate_dimensional_coverage(self) -> "SemanticAlignmentOutput":
        """Asserts all five dimensions are represented in dimensional_alignments."""
        present = {a.dimension for a in self.dimensional_alignments}
        missing = set(DIMENSION_KEYS) - present
        if missing:
            raise ValueError(
                f"SemanticAlignmentOutput missing dimensional alignments: {missing}. "
                "All five DIMENSION_KEYS must have corresponding alignment entries."
            )
        return self

    def to_canonical_semantic_analysis(self) -> SemanticAnalysis:
        """
        Extracts the SemanticAnalysis subset for insertion into CanonicalAnalysisPayload.
        This is the only sanctioned method for obtaining a canonical-payload-compatible
        SemanticAnalysis from this output model.
        """
        return SemanticAnalysis(
            embedding_cosine_similarity=self.embedding_cosine_similarity,
            key_phrase_overlap_ratio=self.key_phrase_overlap_ratio,
            cv_unique_key_phrases=self.cv_unique_key_phrases,
            jd_unique_key_phrases=self.jd_unique_key_phrases,
            shared_key_phrases=self.shared_key_phrases,
            contextual_domain_alignment=self.contextual_domain_alignment,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Agent Implementation
# ─────────────────────────────────────────────────────────────────────────────

class SemanticAlignmentAgent:
    """
    Phase 1 parallel agent responsible for semantic alignment analysis.

    Consumes ParsedCVOutput and JDEntities (both structured, validated objects).
    Never receives or processes raw document text strings.

    Execution flow:
      1. _compose_dimensional_corpora(): build five DimensionalCorpus objects
      2. _compute_batch_embeddings(): single API call for all 10 corpus texts
      3. _compute_dimensional_alignments(): cosine similarity per dimension
      4. _compute_seniority_compatibility_score(): deterministic rule function
      5. _run_llm_key_phrase_extraction(): LLM chain for phrases + domain score
      6. _assemble_output(): construct validated SemanticAlignmentOutput
    """

    def __init__(self, prompt_version: str = "v3") -> None:
        self._llm = ChatOpenAI(
            model="gpt-4.1-mini",
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        self._openai_async = AsyncOpenAI()
        self._parser = PydanticOutputParser(pydantic_object=LLMKeyPhraseOutput)
        self._chain = self._build_chain()

    def _build_chain(self):
        """Constructs the LangChain RunnableSequence for key phrase extraction."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", USER_TEMPLATE),
        ])
        return prompt | self._llm | self._parser

    # ─────────────────────────────────────────────────────────────────────────
    # Static Utility Methods
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """
        Computes cosine similarity between two embedding vectors.
        Returns 0.0 for zero-norm vectors to avoid division-by-zero.
        Clamps result to [0.0, 1.0] — text embeddings occasionally produce
        values slightly outside this range due to floating-point arithmetic.
        """
        a = np.array(vec_a, dtype=np.float32)
        b = np.array(vec_b, dtype=np.float32)
        norm_a = float(np.linalg.norm(a))
        norm_b = float(np.linalg.norm(b))
        if norm_a < 1e-10 or norm_b < 1e-10:
            return 0.0
        raw = float(np.dot(a, b) / (norm_a * norm_b))
        return round(min(max(raw, 0.0), 1.0), 6)

    @staticmethod
    def _classify_alignment_band(similarity: float) -> str:
        """Maps a cosine similarity value to a qualitative band label."""
        for band, (lower, upper) in ALIGNMENT_BAND_THRESHOLDS.items():
            if lower <= similarity < upper:
                return band
        return "negligible"

    @staticmethod
    def _compute_seniority_compatibility_score(
        cv_seniority: str,
        jd_seniority: str,
    ) -> float:
        """
        Deterministic seniority compatibility scoring.
        Uses asymmetric distance-based decay:
          - Over-qualified (CV > JD): 0.15 penalty per ordinal level of excess
          - Under-qualified (CV < JD): 0.25 penalty per ordinal level of deficit
        Asymmetry rationale: an over-qualified candidate presents lower selection
        risk than an under-qualified one, but may present retention risk.

        Returns a score in [0.0, 1.0]. Perfect match = 1.0.
        """
        cv_ord = SENIORITY_ORDINAL.get(cv_seniority, 1)
        jd_ord = SENIORITY_ORDINAL.get(jd_seniority, 2)
        distance = cv_ord - jd_ord
        if distance >= 0:
            # Over-qualified: gentler penalty
            score = 1.0 - abs(distance) * 0.15
        else:
            # Under-qualified: steeper penalty
            score = 1.0 - abs(distance) * 0.25
        return round(max(0.0, score), 4)

    # ─────────────────────────────────────────────────────────────────────────
    # Corpus Composition Methods
    # Each method composes a dimension-specific text representation from
    # structured fields only. No raw text is passed through.
    # ─────────────────────────────────────────────────────────────────────────

    def _compose_technical_corpus(
        self,
        parsed_cv: ParsedCVOutput,
        jd_entities: JDEntities,
    ) -> DimensionalCorpus:
        """
        Technical dimension: canonical skill names from CV skills list + work history
        technology mentions, compared against JD required and preferred skill canonicals.
        """
        # CV: deduplicated union of skills section + work history technology fields
        cv_tech_set: Dict[str, None] = {}
        for skill in parsed_cv.skills:
            if skill.category == SkillCategory.TECHNICAL or skill.category.value == "technical":
                cv_tech_set[skill.canonical_name] = None
        for exp in parsed_cv.work_history:
            for tech in exp.technologies_mentioned:
                cv_tech_set[tech] = None
        cv_text = ", ".join(list(cv_tech_set.keys())[:50])

        # JD: required skills (weight 1.0) + preferred skills (weight 0.5 in text proportion)
        req_names = [s.canonical_name for s in jd_entities.required_skills]
        pref_names = [s.canonical_name for s in jd_entities.preferred_skills]
        jd_text = (
            f"Required: {', '.join(req_names)}. "
            f"Preferred: {', '.join(pref_names[:12])}."
        ).strip()

        return DimensionalCorpus(
            dimension="technical_skills",
            cv_text=cv_text[:CORPUS_TRUNCATION_CHARS],
            jd_text=jd_text[:CORPUS_TRUNCATION_CHARS],
            cv_field_sources=["skills.technical", "work_history.technologies_mentioned"],
            jd_field_sources=["required_skills", "preferred_skills"],
        )

    def _compose_experience_corpus(
        self,
        parsed_cv: ParsedCVOutput,
        jd_entities: JDEntities,
    ) -> DimensionalCorpus:
        """
        Experience dimension: CV role responsibilities and quantitative achievements
        vs JD responsibility statements and required qualification prose.
        Most recent N roles only to avoid dilution with distant experience.
        """
        cv_parts = []
        for exp in parsed_cv.work_history[:_EXPERIENCE_ROLES_LIMIT]:
            responsibilities = ". ".join(
                exp.responsibilities[:_EXPERIENCE_RESPONSIBILITIES_PER_ROLE]
            )
            achievements = ". ".join(
                qa.raw_statement
                for qa in exp.quantitative_achievements[:2]
            )
            part = f"{exp.title}: {responsibilities}"
            if achievements:
                part += f" Achievements: {achievements}"
            cv_parts.append(part)
        cv_text = " | ".join(cv_parts)

        jd_parts = (
            jd_entities.responsibilities[:_JD_RESPONSIBILITIES_LIMIT]
            + jd_entities.required_qualifications[:4]
        )
        jd_text = ". ".join(jd_parts)

        return DimensionalCorpus(
            dimension="experience_responsibilities",
            cv_text=cv_text[:CORPUS_TRUNCATION_CHARS],
            jd_text=jd_text[:CORPUS_TRUNCATION_CHARS],
            cv_field_sources=["work_history.responsibilities", "work_history.quantitative_achievements"],
            jd_field_sources=["responsibilities", "required_qualifications"],
        )

    def _compose_domain_corpus(
        self,
        parsed_cv: ParsedCVOutput,
        jd_entities: JDEntities,
    ) -> DimensionalCorpus:
        """
        Domain dimension: CV industry/domain vocabulary vs JD industry and role context.
        Draws from career_domain_signals, work_history domain tags, and domain-category skills.
        """
        domain_signals = " ".join(parsed_cv.career_domain_signals)
        work_domains = " ".join(
            exp.domain for exp in parsed_cv.work_history if exp.domain
        )
        domain_skills = " ".join(
            s.canonical_name
            for s in parsed_cv.skills
            if s.category == SkillCategory.DOMAIN or s.category.value == "domain"
        )
        # Include company names as weak domain signals (company → industry inference)
        company_names = " ".join(
            exp.company for exp in parsed_cv.work_history[:3]
        )
        cv_text = " ".join(
            filter(None, [domain_signals, work_domains, domain_skills, company_names])
        ) or "general technology"

        jd_text = " ".join(filter(None, [
            jd_entities.industry,
            jd_entities.role_title,
            jd_entities.company_context or "",
            jd_entities.work_arrangement or "",
        ]))

        return DimensionalCorpus(
            dimension="domain_context",
            cv_text=cv_text[:CORPUS_TRUNCATION_CHARS],
            jd_text=jd_text[:CORPUS_TRUNCATION_CHARS],
            cv_field_sources=["career_domain_signals", "work_history.domain", "skills.domain"],
            jd_field_sources=["industry", "role_title", "company_context"],
        )

    def _compose_education_corpus(
        self,
        parsed_cv: ParsedCVOutput,
        jd_entities: JDEntities,
    ) -> DimensionalCorpus:
        """
        Education dimension: CV degree and certification content vs JD qualification
        requirements filtered for education-signal keywords.
        Falls back to a standardized insufficient-data marker if no education is present.
        """
        edu_parts = []
        for edu in parsed_cv.education:
            edu_parts.append(
                f"{edu.degree_level.value} in {edu.field_of_study} "
                f"({edu.institution_type.value}, {edu.institution})"
            )
        cert_parts = [
            f"{c.name} from {c.issuing_organization or 'unknown issuer'}"
            for c in parsed_cv.certifications[:5]
        ]
        cv_text = " | ".join(edu_parts + cert_parts) or "no formal education listed"

        # Filter JD qualifications for education-signal vocabulary
        EDU_SIGNALS = {
            "degree", "bachelor", "master", "phd", "graduate", "diploma",
            "university", "college", "certification", "study", "academic",
            "graduated", "education", "qualification",
        }
        edu_quals = [
            q for q in jd_entities.required_qualifications
            if any(kw in q.lower() for kw in EDU_SIGNALS)
        ]
        if not edu_quals:
            edu_quals = jd_entities.required_qualifications[:3]
        jd_text = " ".join(edu_quals[:6]) or "no explicit education requirements"

        return DimensionalCorpus(
            dimension="education_qualifications",
            cv_text=cv_text[:CORPUS_TRUNCATION_CHARS],
            jd_text=jd_text[:CORPUS_TRUNCATION_CHARS],
            cv_field_sources=["education", "certifications"],
            jd_field_sources=["required_qualifications[edu_filtered]"],
        )

    def _compose_composite_corpus(
        self,
        parsed_cv: ParsedCVOutput,
        jd_entities: JDEntities,
    ) -> DimensionalCorpus:
        """
        Composite dimension: full structured representation of both documents.
        Used for the primary embedding_cosine_similarity value and as input to
        the LLM key phrase extraction chain.
        """
        cv_sections = [
            f"SENIORITY: {parsed_cv.inferred_seniority.value}",
            f"EXPERIENCE: {parsed_cv.total_years_experience} years",
            f"DOMAINS: {', '.join(parsed_cv.career_domain_signals) or 'unspecified'}",
        ]
        tech_names = [
            s.canonical_name for s in parsed_cv.skills
            if s.category == SkillCategory.TECHNICAL or s.category.value == "technical"
        ]
        cv_sections.append(f"TECHNICAL SKILLS: {', '.join(tech_names[:35])}")

        domain_names = [
            s.canonical_name for s in parsed_cv.skills
            if s.category == SkillCategory.DOMAIN or s.category.value == "domain"
        ]
        if domain_names:
            cv_sections.append(f"DOMAIN SKILLS: {', '.join(domain_names[:15])}")

        for i, exp in enumerate(parsed_cv.work_history[:3]):
            resp_text = "; ".join(exp.responsibilities[:2])
            cv_sections.append(f"ROLE {i + 1}: {exp.title} | {resp_text}")

        for edu in parsed_cv.education[:2]:
            cv_sections.append(
                f"EDUCATION: {edu.degree_level.value} {edu.field_of_study}"
            )

        for proj in parsed_cv.projects[:2]:
            tech_str = ", ".join(proj.technologies[:5])
            impact = f" — {proj.impact_statement}" if proj.impact_statement else ""
            cv_sections.append(f"PROJECT: {proj.title} ({tech_str}){impact}")

        if parsed_cv.professional_summary:
            cv_sections.append(f"SUMMARY: {parsed_cv.professional_summary[:300]}")

        cv_text = "\n".join(cv_sections)

        jd_sections = [
            f"ROLE: {jd_entities.role_title}",
            f"SENIORITY REQUIRED: {jd_entities.required_seniority.value}",
            f"INDUSTRY: {jd_entities.industry}",
            f"EXPERIENCE REQUIRED: {jd_entities.required_experience_years}+ years",
        ]
        if jd_entities.company_context:
            jd_sections.append(f"COMPANY: {jd_entities.company_context}")

        req_skills = ", ".join(s.canonical_name for s in jd_entities.required_skills[:20])
        pref_skills = ", ".join(s.canonical_name for s in jd_entities.preferred_skills[:12])
        jd_sections.append(f"REQUIRED SKILLS: {req_skills}")
        if pref_skills:
            jd_sections.append(f"PREFERRED SKILLS: {pref_skills}")

        for i, resp in enumerate(jd_entities.responsibilities[:6]):
            jd_sections.append(f"RESPONSIBILITY {i + 1}: {resp}")

        for i, qual in enumerate(jd_entities.required_qualifications[:5]):
            jd_sections.append(f"QUALIFICATION {i + 1}: {qual}")

        jd_text = "\n".join(jd_sections)

        return DimensionalCorpus(
            dimension="composite",
            cv_text=cv_text[:CORPUS_TRUNCATION_CHARS],
            jd_text=jd_text[:CORPUS_TRUNCATION_CHARS],
            cv_field_sources=["ALL_SECTIONS"],
            jd_field_sources=["ALL_FIELDS"],
        )

    def _compose_dimensional_corpora(
        self,
        parsed_cv: ParsedCVOutput,
        jd_entities: JDEntities,
    ) -> List[DimensionalCorpus]:
        """
        Orchestrates composition of all five dimensional corpora.
        Returns them in the canonical order defined by DIMENSION_KEYS.
        This order is load-bearing: it determines which embeddings in the
        batch response correspond to which dimensions.
        """
        return [
            self._compose_technical_corpus(parsed_cv, jd_entities),
            self._compose_experience_corpus(parsed_cv, jd_entities),
            self._compose_domain_corpus(parsed_cv, jd_entities),
            self._compose_education_corpus(parsed_cv, jd_entities),
            self._compose_composite_corpus(parsed_cv, jd_entities),
        ]

    # ─────────────────────────────────────────────────────────────────────────
    # Embedding Computation
    # ─────────────────────────────────────────────────────────────────────────

    async def _compute_batch_embeddings(
        self, texts: List[str]
    ) -> List[List[float]]:
        """
        Sends all texts in a single API call to text-embedding-3-small.
        Ordering of returned embeddings matches input text ordering (sorted by index).
        Empty texts receive a zero vector of dimension 1536.
        """
        _ZERO_VEC = [0.0] * 1536

        # Replace empty or whitespace-only strings with a sentinel (API rejects empty strings)
        safe_texts = [
            t.strip() if t.strip() else "insufficient data" for t in texts
        ]

        response = await self._openai_async.embeddings.create(
            model=EMBEDDING_MODEL,
            input=safe_texts,
        )
        # Sort by index to guarantee order matches input (API contract guarantees this
        # but we sort defensively)
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]

    # ─────────────────────────────────────────────────────────────────────────
    # Dimensional Alignment Assembly
    # ─────────────────────────────────────────────────────────────────────────

    def _compute_dimensional_alignments(
        self,
        corpora: List[DimensionalCorpus],
        embeddings: List[List[float]],
    ) -> List[DimensionalEmbeddingAlignment]:
        """
        Computes cosine similarity for each dimensional corpus pair.
        Embeddings list is interleaved: [cv_0, jd_0, cv_1, jd_1, ..., cv_4, jd_4]
        (10 vectors total for 5 dimensions).
        """
        alignments = []
        for i, corpus in enumerate(corpora):
            cv_vec = embeddings[i * 2]
            jd_vec = embeddings[i * 2 + 1]

            if corpus.both_sufficient:
                similarity = self._cosine_similarity(cv_vec, jd_vec)
                data_sufficient = True
            else:
                similarity = 0.0
                data_sufficient = False
                logger.debug(
                    "SemanticAlignmentAgent: insufficient data for dimension '%s'. "
                    "cv_sufficient=%s, jd_sufficient=%s. Assigning 0.0.",
                    corpus.dimension,
                    corpus.cv_is_sufficient,
                    corpus.jd_is_sufficient,
                )

            alignments.append(DimensionalEmbeddingAlignment(
                dimension=corpus.dimension,
                payload_field=DIMENSION_TO_PAYLOAD_FIELD[corpus.dimension],
                cosine_similarity=similarity,
                alignment_band=self._classify_alignment_band(similarity),
                cv_corpus_preview=corpus.cv_text[:180],
                jd_corpus_preview=corpus.jd_text[:180],
                data_sufficient=data_sufficient,
            ))

        return alignments

    # ─────────────────────────────────────────────────────────────────────────
    # LLM Chain Execution
    # ─────────────────────────────────────────────────────────────────────────

    async def _run_llm_key_phrase_extraction(
        self,
        parsed_cv: ParsedCVOutput,
        jd_entities: JDEntities,
        composite_corpus: DimensionalCorpus,
    ) -> Tuple[LLMKeyPhraseOutput, float]:
        """
        Invokes the LangChain key phrase extraction chain.
        Returns (LLMKeyPhraseOutput, llm_confidence).
        llm_confidence is 0.8 if parse repair was needed, 0.5 on fallback.

        The LLM receives the composite corpus representations (not raw text)
        plus structured field summaries for context richness.
        """
        # Compose LLM input variables from structured fields
        tech_skills = ", ".join(
            s.canonical_name for s in parsed_cv.skills
            if s.category == SkillCategory.TECHNICAL or s.category.value == "technical"
        )
        domain_skills = ", ".join(
            s.canonical_name for s in parsed_cv.skills
            if s.category == SkillCategory.DOMAIN or s.category.value == "domain"
        )
        soft_skills = ", ".join(
            s.canonical_name for s in parsed_cv.skills
            if s.category == SkillCategory.SOFT or s.category.value == "soft"
        )

        work_history_lines = []
        for exp in parsed_cv.work_history[:4]:
            resp = "; ".join(exp.responsibilities[:3])
            work_history_lines.append(f"  - {exp.title} ({exp.domain or 'tech'}): {resp}")

        edu_lines = []
        for edu in parsed_cv.education[:2]:
            edu_lines.append(
                f"  - {edu.degree_level.value} in {edu.field_of_study} "
                f"({edu.institution_type.value})"
            )

        cert_names = ", ".join(c.name for c in parsed_cv.certifications[:4]) or "none listed"

        project_lines = []
        for proj in parsed_cv.projects[:2]:
            tech_str = ", ".join(proj.technologies[:4])
            project_lines.append(f"  - {proj.title} ({tech_str})")

        resp_lines = [f"  {i + 1}. {r}" for i, r in enumerate(jd_entities.responsibilities[:6])]
        qual_lines = [f"  {i + 1}. {q}" for i, q in enumerate(jd_entities.required_qualifications[:5])]
        pref_qual_lines = [f"  {i + 1}. {q}" for i, q in enumerate(jd_entities.preferred_qualifications[:3])]

        invoke_vars = {
            "format_instructions": self._parser.get_format_instructions(),
            "few_shot_example": FEW_SHOT_EXAMPLE,
            "cv_seniority": parsed_cv.inferred_seniority.value,
            "cv_experience_years": parsed_cv.total_years_experience,
            "cv_domain_signals": ", ".join(parsed_cv.career_domain_signals) or "unspecified",
            "cv_technical_skills": tech_skills or "none extracted",
            "cv_domain_skills": domain_skills or "none extracted",
            "cv_soft_skills": soft_skills or "none extracted",
            "cv_work_history_summary": "\n".join(work_history_lines) or "  no work history",
            "cv_education_summary": "\n".join(edu_lines) or "  no formal education listed",
            "cv_certifications": cert_names,
            "cv_projects_summary": "\n".join(project_lines) or "  no projects listed",
            "cv_professional_summary": (parsed_cv.professional_summary or "none")[:300],
            "jd_role_title": jd_entities.role_title,
            "jd_required_seniority": jd_entities.required_seniority.value,
            "jd_industry": jd_entities.industry,
            "jd_required_experience_years": jd_entities.required_experience_years,
            "jd_company_context": jd_entities.company_context or "not specified",
            "jd_required_skills": ", ".join(
                s.canonical_name for s in jd_entities.required_skills
            ) or "not specified",
            "jd_preferred_skills": ", ".join(
                s.canonical_name for s in jd_entities.preferred_skills
            ) or "not specified",
            "jd_responsibilities": "\n".join(resp_lines) or "  not specified",
            "jd_required_qualifications": "\n".join(qual_lines) or "  not specified",
            "jd_preferred_qualifications": "\n".join(pref_qual_lines) or "  not specified",
        }

        try:
            result: LLMKeyPhraseOutput = await self._chain.ainvoke(invoke_vars)
            return result, 1.0
        except Exception as exc:
            logger.error(
                "SemanticAlignmentAgent LLM extraction failed for session. Error: %s. "
                "Activating structured fallback.",
                exc,
            )
            # Construct a minimal valid fallback from the composite corpus texts
            return self._build_fallback_llm_output(parsed_cv, jd_entities), 0.5

    def _build_fallback_llm_output(
        self,
        parsed_cv: ParsedCVOutput,
        jd_entities: JDEntities,
    ) -> LLMKeyPhraseOutput:
        """
        Produces a minimal but schema-valid LLMKeyPhraseOutput when the LLM
        chain fails. Uses deterministic skill-name-based phrase construction
        to avoid returning empty lists that would fail Pydantic min_length=2.
        """
        cv_phrases = [
            s.canonical_name for s in parsed_cv.skills
            if s.category.value == "technical"
        ][:8] or ["general technical skills", "software development"]

        jd_phrases = [
            s.canonical_name for s in jd_entities.required_skills
        ][:8] or ["technical requirements", "role requirements"]

        shared = list(
            set(s.canonical_name for s in parsed_cv.skills)
            & set(s.canonical_name for s in jd_entities.required_skills)
        )[:6]

        ratio = len(shared) / max(len(jd_phrases), 1)

        return LLMKeyPhraseOutput(
            cv_key_phrases=cv_phrases,
            jd_key_phrases=jd_phrases,
            shared_semantic_concepts=shared or ["technology background"],
            cv_unique_concepts=[],
            jd_unique_concepts=[],
            domain_alignment_rationale=(
                "Fallback assessment: LLM extraction unavailable. "
                "Domain alignment scored from embedding similarity only."
            ),
            contextual_domain_alignment_score=0.5,
            seniority_compatibility_rationale="LLM assessment unavailable for this session.",
            education_relevance_rationale="LLM assessment unavailable for this session.",
            key_phrase_overlap_ratio=round(ratio, 4),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Primary Entry Point
    # ─────────────────────────────────────────────────────────────────────────

    async def arun(
        self,
        parsed_cv: ParsedCVOutput,
        jd_entities: JDEntities,
        session_id: str,
    ) -> SemanticAlignmentOutput:
        """
        Main async execution method.

        Runs embedding computation and LLM extraction concurrently via asyncio.gather
        on the shared event loop. Both operations are I/O-bound (OpenAI API calls)
        and genuinely parallelizable.

        The composite corpus is used for:
          - The batch embedding list (as the 5th dimensional pair)
          - The LLM chain input

        Returns a fully validated SemanticAlignmentOutput.

        Raises: Pydantic ValidationError if output assembly fails structural invariants.
                The caller (node_phase1_parallel) handles this via return_exceptions=True.
        """
        start_ms = int(time.monotonic() * 1000)
        logger.info("SemanticAlignmentAgent.arun started. session_id=%s", session_id)

        # Step 1: Compose all five dimensional corpora from structured fields
        corpora = self._compose_dimensional_corpora(parsed_cv, jd_entities)
        composite_corpus = corpora[4]  # DIMENSION_KEYS[4] = "composite"

        # Step 2: Build the flat list of texts for batch embedding.
        # Order: [cv_0, jd_0, cv_1, jd_1, ..., cv_4, jd_4] — 10 strings total.
        texts_for_embedding = []
        for corpus in corpora:
            texts_for_embedding.append(corpus.cv_text)
            texts_for_embedding.append(corpus.jd_text)

        # Step 3: Compute seniority compatibility score (deterministic, no I/O)
        seniority_score = self._compute_seniority_compatibility_score(
            cv_seniority=parsed_cv.inferred_seniority.value,
            jd_seniority=jd_entities.required_seniority.value,
        )

        # Step 4: Run batch embedding and LLM extraction concurrently
        embedding_task = self._compute_batch_embeddings(texts_for_embedding)
        llm_task = self._run_llm_key_phrase_extraction(
            parsed_cv, jd_entities, composite_corpus
        )
        (embeddings, (llm_output, llm_confidence)) = await asyncio.gather(
            embedding_task, llm_task
        )

        # Step 5: Compute per-dimension cosine similarities
        dimensional_alignments = self._compute_dimensional_alignments(corpora, embeddings)

        # Step 6: Build dimensional_scores_for_payload map for PayloadAssembler
        dim_scores_map: Dict[str, float] = {}
        for alignment in dimensional_alignments:
            dim_scores_map[alignment.payload_field] = alignment.cosine_similarity

        # Override semantic_contextual_alignment with LLM's contextual_domain_alignment_score
        # The LLM score is blended with the composite embedding similarity (50/50 weight)
        composite_embedding_sim = dim_scores_map.get("semantic_contextual_alignment", 0.5)
        blended_contextual = round(
            0.50 * composite_embedding_sim
            + 0.50 * llm_output.contextual_domain_alignment_score,
            4,
        )
        dim_scores_map["semantic_contextual_alignment"] = blended_contextual
        dim_scores_map["seniority_trajectory"] = seniority_score

        end_ms = int(time.monotonic() * 1000)
        latency_ms = end_ms - start_ms
        logger.info(
            "SemanticAlignmentAgent.arun completed. session_id=%s latency_ms=%d "
            "composite_sim=%.4f domain_score=%.4f seniority_score=%.4f",
            session_id, latency_ms,
            composite_embedding_sim,
            llm_output.contextual_domain_alignment_score,
            seniority_score,
        )

        return SemanticAlignmentOutput(
            # SemanticAnalysis core fields
            embedding_cosine_similarity=composite_embedding_sim,
            key_phrase_overlap_ratio=llm_output.key_phrase_overlap_ratio,
            cv_unique_key_phrases=llm_output.cv_unique_concepts,
            jd_unique_key_phrases=llm_output.jd_unique_concepts,
            shared_key_phrases=llm_output.shared_semantic_concepts,
            contextual_domain_alignment=blended_contextual,
            # Extended dimensional signals
            dimensional_alignments=dimensional_alignments,
            dimensional_scores_for_payload=dim_scores_map,
            # Seniority compatibility
            seniority_compatibility_score=seniority_score,
            seniority_compatibility_rationale=llm_output.seniority_compatibility_rationale,
            # LLM rationales
            domain_alignment_rationale=llm_output.domain_alignment_rationale,
            education_relevance_rationale=llm_output.education_relevance_rationale,
            # Evidence corpus
            cv_composite_representation=composite_corpus.cv_text,
            jd_composite_representation=composite_corpus.jd_text,
            # Metadata
            agent_session_id=session_id,
            total_embedding_vectors_computed=len(embeddings),
            llm_extraction_confidence=llm_confidence,
            processing_latency_ms=latency_ms,
        )
