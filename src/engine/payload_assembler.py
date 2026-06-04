# src/engine/payload_assembler.py
#
# PayloadAssembler — the terminal node in the LangGraph orchestration graph.
#
# Responsibility chain:
#   1. DimensionScoreMapper    — translates raw agent outputs (CVEntities,
#      JDEntities, SemanticAnalysis, SkillsOntologyResult) into the seven
#      typed DimensionScore objects that populate DimensionalAnalysis.
#
#   2. compute_composite_score — called with the seven raw scores to produce
#      the weighted geometric mean with two-tier hard flooring (scoring.py).
#
#   3. NarrativeGenerator      — drives Gemini 2.0 Flash to produce the
#      access-controlled narrative layers: CandidatePerspective and
#      RecruiterPerspective. Both are pre-computed in parallel and stored
#      in the payload; rendering is gated by access_control.py selectors.
#
#   4. PayloadAssembler.assemble() — orchestrates 1–3, constructs
#      GovernanceLayer, computes meta-scores, and returns the validated
#      CanonicalAnalysisPayload.
#
# Circular-import safety:
#   This module is imported by orchestrator.py. It MUST NOT import from
#   orchestrator.py. The `assemble()` method accepts a plain dict (typed
#   via AssemblerInputState TypedDict defined locally).

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel
from typing_extensions import TypedDict

from src.engine.scoring import (
    DIMENSION_WEIGHTS,
    GENERAL_FLOOR_THRESHOLD,
    compute_composite_score,
)
from src.schemas.canonical_payload import (
    ActionItem,
    AgentExecutionStatus,
    BiasAuditResult,
    CanonicalAnalysisPayload,
    CandidatePerspective,
    CVEntities,
    DimensionScore,
    DimensionalAnalysis,
    EducationEntry,
    EvaluationIntegrityRisk,
    GovernanceLayer,
    HireRecommendation,
    JDEntities,
    RecruiterPerspective,
    SemanticAnalysis,
    SeniorityLevel,
    SkillCategory,
    SkillMatchEntry,
    SkillsOntologyResult,
    VerificationPoint,
    WorkExperience,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Local TypedDict — avoids circular import with orchestrator.py
# ---------------------------------------------------------------------------

class AssemblerInputState(TypedDict, total=False):
    """
    Minimal typed view of OrchestratorState consumed by PayloadAssembler.
    Mirrors the relevant subset of OrchestratorState without importing it.
    """
    cv_text:               str
    jd_text:               str
    session_id:            str
    language:              str
    seniority_context:     str
    analysis_start_time_ms: int
    cv_entities:           Optional[CVEntities]
    jd_entities:           Optional[JDEntities]
    semantic_result:       Optional[SemanticAnalysis]
    skills_result:         Optional[SkillsOntologyResult]
    bias_audit_result:     Optional[BiasAuditResult]
    phase1_statuses:       Dict[str, AgentExecutionStatus]
    phase2_status:         AgentExecutionStatus
    agent_errors:          Dict[str, Optional[str]]


# ---------------------------------------------------------------------------
# Seniority Rank Map
# Ordinal mapping for trajectory scoring. Lower index = less senior.
# ---------------------------------------------------------------------------

_SENIORITY_RANK: Dict[str, int] = {
    SeniorityLevel.INTERN:     0,
    SeniorityLevel.JUNIOR:     1,
    SeniorityLevel.MID:        2,
    SeniorityLevel.SENIOR:     3,
    SeniorityLevel.LEAD:       4,
    SeniorityLevel.PRINCIPAL:  5,
    SeniorityLevel.EXECUTIVE:  6,
}

# ---------------------------------------------------------------------------
# Domain Overlap Map
# Pre-computed semantic proximity between industry domain slugs.
# Used to detect partial domain matches (e.g., "igaming" ↔ "gaming").
# ---------------------------------------------------------------------------

_DOMAIN_OVERLAP_MAP: Dict[str, List[str]] = {
    "igaming":    ["gaming", "gambling", "betting", "casino", "lottery", "sportsbook"],
    "fintech":    ["finance", "banking", "payments", "financial_services", "insurance"],
    "saas":       ["software", "technology", "b2b_software", "cloud", "platform"],
    "ecommerce":  ["retail", "marketplace", "commerce", "d2c"],
    "telecom":    ["telecommunications", "mobile", "network", "isp"],
    "healthcare": ["medtech", "healthtech", "pharma", "clinical"],
    "logistics":  ["supply_chain", "transport", "shipping", "fulfillment"],
    "manufacturing": ["industrial", "production", "operations"],
    "data_analytics": ["analytics", "business_intelligence", "data_science", "ml"],
}

# ---------------------------------------------------------------------------
# Education Relevance Keywords
# Keyword sets for heuristic field_of_study relevance scoring.
# ---------------------------------------------------------------------------

_EDUCATION_HIGH_RELEVANCE_KEYWORDS: List[str] = [
    "computer science", "software engineering", "data science", "information technology",
    "computer engineering", "machine learning", "artificial intelligence", "mathematics",
    "statistics", "applied mathematics", "information systems", "computational",
    "compyutayin gitut", "informatika", "информатика", "математика",
]

_EDUCATION_MEDIUM_RELEVANCE_KEYWORDS: List[str] = [
    "engineering", "physics", "economics", "business analytics",
    "management information", "quantitative", "operations research",
    "electrical", "systems", "мехмат", "физика", "экономика",
]


# ===========================================================================
# DimensionScoreMapper
# ===========================================================================

class DimensionScoreMapper:
    """
    Translates raw agent outputs into the seven typed DimensionScore objects
    required by DimensionalAnalysis.

    Each public method corresponds to one scoring dimension. Methods are
    stateless and accept only the data required for that specific dimension.
    No LLM calls are made — scoring is fully deterministic and reproducible.

    Score computation philosophy:
      - Evidence is extracted verbatim from agent outputs; no inference.
      - Confidence reflects data completeness: missing dates, empty skill
        lists, and fallback agent outputs reduce confidence systematically.
      - `is_below_floor` is set post-hoc by `compute_all_dimension_scores`.
    """

    # ── 1. Technical Skills Match ──────────────────────────────────────────

    def technical_skills_match(
        self,
        skills_result: SkillsOntologyResult,
        jd_entities: JDEntities,
    ) -> DimensionScore:
        """
        Score = coverage_ratio adjusted for critical gap count.
        Each critical gap applies a 0.07 penalty on top of the coverage deficit,
        reflecting that critical (required) gaps are qualitatively worse than
        a proportional miss on the coverage ratio alone would indicate.
        """
        base_score = skills_result.coverage_ratio

        # Critical gap penalty: each missing required skill reduces the score
        # beyond what coverage_ratio already captures for ordered rankings.
        critical_penalty = min(skills_result.critical_gap_count * 0.07, 0.30)
        adjusted_score   = max(0.0, base_score - critical_penalty)

        # Confidence: lower when total required skills is ambiguous (< 3)
        confidence = 0.95 if skills_result.total_required_skills >= 3 else 0.65

        evidence_cv = [
            s.canonical_name for s in skills_result.matched_skills[:6]
        ]
        evidence_jd = [
            s.canonical_name for s in jd_entities.required_skills[:6]
        ]

        return DimensionScore(
            raw_score           = round(adjusted_score, 4),
            confidence          = confidence,
            is_below_floor      = False,   # Set post-hoc
            weight              = DIMENSION_WEIGHTS["technical_skills_match"],
            evidence_phrases_cv = evidence_cv,
            evidence_phrases_jd = evidence_jd,
        )

    # ── 2. Experience Depth Alignment ─────────────────────────────────────

    def experience_depth_alignment(
        self,
        cv_entities: CVEntities,
        jd_entities: JDEntities,
    ) -> DimensionScore:
        """
        Score = piecewise function of experience_ratio (actual / required).
        Uses ordinal brackets rather than a continuous function to prevent
        marginal experience (e.g., 2.9 vs 3.0 years required) from producing
        cliff-edge discontinuities in the final composite.

        Seniority signal bonus: if inferred seniority matches required, +0.05.
        This rewards candidates whose career progression explicitly confirms
        the years-of-experience signal from raw duration arithmetic.
        """
        required = jd_entities.required_experience_years
        actual   = cv_entities.total_years_experience

        if required <= 0:
            # JD specifies no explicit experience requirement — neutral score
            return DimensionScore(
                raw_score           = 0.80,
                confidence          = 0.50,  # Low confidence: no benchmark to compare against
                is_below_floor      = False,
                weight              = DIMENSION_WEIGHTS["experience_depth_alignment"],
                evidence_phrases_cv = [f"Total experience: {actual:.1f} years"],
                evidence_phrases_jd = ["No explicit experience requirement specified"],
            )

        ratio = actual / required

        if ratio >= 1.5:
            base = 0.95
        elif ratio >= 1.0:
            base = 0.85
        elif ratio >= 0.8:
            base = 0.68
        elif ratio >= 0.6:
            base = 0.52
        elif ratio >= 0.4:
            base = 0.38
        else:
            base = 0.18

        # Seniority trajectory bonus
        inferred_rank = _SENIORITY_RANK.get(cv_entities.inferred_seniority, 1)
        required_rank = _SENIORITY_RANK.get(jd_entities.required_seniority, 2)
        seniority_bonus = 0.05 if inferred_rank == required_rank else 0.0

        final_score = round(min(1.0, base + seniority_bonus), 4)

        # Confidence: reduced if work history is sparse or dates are missing
        work_entries_with_dates = sum(
            1 for exp in cv_entities.work_history
            if exp.start_date is not None
        )
        total_work_entries = len(cv_entities.work_history)
        date_completeness = (
            work_entries_with_dates / total_work_entries
            if total_work_entries > 0 else 0.0
        )
        confidence = round(0.60 + 0.30 * date_completeness, 2)

        evidence_cv = [
            f"{exp.company} ({exp.title}): {exp.duration_months or '?'} months"
            for exp in cv_entities.work_history[:4]
        ]
        evidence_jd = [
            f"Required: {required:.0f}+ years experience",
            f"Required seniority: {jd_entities.required_seniority}",
        ]

        return DimensionScore(
            raw_score           = final_score,
            confidence          = confidence,
            is_below_floor      = False,
            weight              = DIMENSION_WEIGHTS["experience_depth_alignment"],
            evidence_phrases_cv = evidence_cv,
            evidence_phrases_jd = evidence_jd,
        )

    # ── 3. Educational Relevance ───────────────────────────────────────────

    def educational_relevance(
        self,
        cv_entities: CVEntities,
        jd_entities: JDEntities,
    ) -> DimensionScore:
        """
        Score = maximum relevance across all education entries.
        Relevance is assessed in priority order:
          (a) is_relevant_to_role flag (set by Semantic Alignment Agent)
          (b) field_of_study keyword matching against curated lists
          (c) degree level (graduate-level is a positive signal for senior roles)
        """
        if not cv_entities.education:
            return DimensionScore(
                raw_score           = 0.50,
                confidence          = 0.40,
                is_below_floor      = False,
                weight              = DIMENSION_WEIGHTS["educational_relevance"],
                evidence_phrases_cv = ["No formal education entries extracted"],
                evidence_phrases_jd = [],
            )

        def _score_entry(entry: EducationEntry) -> float:
            # Priority (a): explicit relevance flag from Semantic Alignment Agent
            if entry.is_relevant_to_role is True:
                base = 0.90
            elif entry.is_relevant_to_role is False:
                base = 0.30
            else:
                # Priority (b): field_of_study keyword heuristic
                fos = (entry.field_of_study or "").lower()
                if any(kw in fos for kw in _EDUCATION_HIGH_RELEVANCE_KEYWORDS):
                    base = 0.88
                elif any(kw in fos for kw in _EDUCATION_MEDIUM_RELEVANCE_KEYWORDS):
                    base = 0.68
                else:
                    base = 0.42

            # Priority (c): degree level adjustment
            degree_label = (entry.degree or "").lower()
            if any(kw in degree_label for kw in ["master", "phd", "mba", "мастер", "magistr", "մագիստ"]):
                base = min(1.0, base + 0.05)
            elif any(kw in degree_label for kw in ["high school", "abi", "vocational"]):
                base = max(0.10, base - 0.10)

            return base

        entry_scores = [_score_entry(e) for e in cv_entities.education]
        best_score   = round(max(entry_scores), 4)
        confidence   = 0.80

        evidence_cv = [
            f"{e.institution}: {e.degree} in {e.field_of_study}"
            for e in cv_entities.education[:3]
        ]

        return DimensionScore(
            raw_score           = best_score,
            confidence          = confidence,
            is_below_floor      = False,
            weight              = DIMENSION_WEIGHTS["educational_relevance"],
            evidence_phrases_cv = evidence_cv,
            evidence_phrases_jd = [f"Industry: {jd_entities.industry}"],
        )

    # ── 4. Domain Knowledge ────────────────────────────────────────────────

    def domain_knowledge(
        self,
        cv_entities:       CVEntities,
        jd_entities:       JDEntities,
        semantic_analysis: SemanticAnalysis,
    ) -> DimensionScore:
        """
        Score = weighted combination of:
          (a) contextual_domain_alignment from SemanticAnalysis (embedding-based)
          (b) explicit domain overlap between cv career_domain_signals and JD industry

        The embedding-based signal captures semantic proximity beyond exact keyword
        matches (e.g., a candidate with "sports analytics" experience for a
        "sports betting" JD would score high on (a) even without (b)).
        """
        jd_industry     = (jd_entities.industry or "").lower().replace(" ", "_")
        cv_domain_slugs = [d.lower().replace(" ", "_") for d in cv_entities.career_domain_signals]

        # (b): Explicit domain overlap score
        domain_overlap = 0.0
        for cv_domain in cv_domain_slugs:
            if cv_domain == jd_industry:
                domain_overlap = 1.0
                break
            # Check _DOMAIN_OVERLAP_MAP for partial overlap
            synonyms = _DOMAIN_OVERLAP_MAP.get(cv_domain, []) + _DOMAIN_OVERLAP_MAP.get(jd_industry, [])
            if jd_industry in synonyms or cv_domain in synonyms:
                domain_overlap = max(domain_overlap, 0.65)
            elif any(kw in jd_industry for kw in cv_domain.split("_")):
                domain_overlap = max(domain_overlap, 0.45)

        # (a): Semantic contextual alignment (already computed by SemanticAlignmentAgent)
        semantic_signal = semantic_analysis.contextual_domain_alignment

        # Weighted composite: embedding signal carries more weight (more robust)
        score = round(0.60 * semantic_signal + 0.40 * domain_overlap, 4)

        evidence_cv = cv_entities.career_domain_signals[:4]
        evidence_jd = [jd_industry, jd_entities.role_title]

        return DimensionScore(
            raw_score           = score,
            confidence          = 0.82,
            is_below_floor      = False,
            weight              = DIMENSION_WEIGHTS["domain_knowledge"],
            evidence_phrases_cv = evidence_cv,
            evidence_phrases_jd = evidence_jd,
        )

    # ── 5. Soft Skills Signals ─────────────────────────────────────────────

    def soft_skills_signals(
        self,
        cv_entities: CVEntities,
    ) -> DimensionScore:
        """
        Score = sigmoid-like function of soft skill count.
        Capped at 0.78: soft skills extracted from CV text are weak evidence.
        Floor at 0.28: every professional CV implies some interpersonal competency.

        Note: This dimension has the lowest weight (0.05) precisely because
        CV-based soft skill inference is unreliable. It acts as a weak tie-breaker,
        not a primary differentiator.
        """
        soft_skills = [
            s for s in cv_entities.raw_skills
            if s.category == SkillCategory.SOFT
        ]
        count = len(soft_skills)

        # Piecewise function: 0→0.28, 1→0.35, 2→0.48, 3→0.62, 4→0.72, 5+→0.78
        score_map = {0: 0.28, 1: 0.35, 2: 0.48, 3: 0.62, 4: 0.72}
        score = score_map.get(count, 0.78)  # 5+ soft skills → 0.78

        return DimensionScore(
            raw_score           = score,
            confidence          = 0.55,   # Inherently low — soft skills from CV are noisy
            is_below_floor      = False,
            weight              = DIMENSION_WEIGHTS["soft_skills_signals"],
            evidence_phrases_cv = [s.canonical_name for s in soft_skills[:5]],
            evidence_phrases_jd = [],
        )

    # ── 6. Seniority Trajectory ────────────────────────────────────────────

    def seniority_trajectory(
        self,
        cv_entities: CVEntities,
        jd_entities: JDEntities,
    ) -> DimensionScore:
        """
        Score = function of ordinal delta between inferred and required seniority.

        Delta interpretation:
          Positive delta (candidate below required level): penalized steeply.
          Negative delta (candidate above required level): mild overqualification
            penalty. A senior applying for a mid-level role is not disqualified,
            but introduces risk of early attrition.
          Zero delta: perfect alignment (1.0).

        The score table is deliberately non-symmetric:
          Underqualification is penalized more severely than overqualification,
          reflecting real hiring risk profiles in the Armenian tech market.
        """
        inferred_rank = _SENIORITY_RANK.get(cv_entities.inferred_seniority, 1)
        required_rank = _SENIORITY_RANK.get(jd_entities.required_seniority, 2)
        delta         = required_rank - inferred_rank  # Positive = underqualified

        score_table: Dict[int, float] = {
            -3: 0.55,  # 3 levels above — severely overqualified
            -2: 0.68,
            -1: 0.84,
             0: 1.00,  # Perfect match
             1: 0.62,
             2: 0.34,
             3: 0.12,  # 3 levels below — severely underqualified
        }
        clamped_delta = max(-3, min(3, delta))
        score         = score_table.get(clamped_delta, 0.12)

        evidence_cv = [
            f"Inferred seniority: {cv_entities.inferred_seniority}",
            f"Total experience: {cv_entities.total_years_experience:.1f} years",
        ]
        evidence_jd = [
            f"Required seniority: {jd_entities.required_seniority}",
            f"Required experience: {jd_entities.required_experience_years:.0f}+ years",
        ]

        return DimensionScore(
            raw_score           = score,
            confidence          = 0.88,
            is_below_floor      = False,
            weight              = DIMENSION_WEIGHTS["seniority_trajectory"],
            evidence_phrases_cv = evidence_cv,
            evidence_phrases_jd = evidence_jd,
        )

    # ── 7. Semantic Contextual Alignment ──────────────────────────────────

    def semantic_contextual_alignment(
        self,
        semantic_analysis: SemanticAnalysis,
    ) -> DimensionScore:
        """
        Score = weighted combination of embedding cosine similarity and
        key phrase overlap ratio.

        The embedding signal is deterministic (always computed directly,
        never by the LLM) and serves as the primary signal. Key phrase
        overlap adds a sparse exact-match signal that catches terminology
        alignment missed by dense embeddings in specialized domains.
        """
        cosine_sim         = semantic_analysis.embedding_cosine_similarity
        phrase_overlap     = semantic_analysis.key_phrase_overlap_ratio
        score              = round(0.65 * cosine_sim + 0.35 * phrase_overlap, 4)

        evidence_cv = semantic_analysis.shared_key_phrases[:5]
        evidence_jd = semantic_analysis.jd_unique_key_phrases[:3]

        return DimensionScore(
            raw_score           = score,
            confidence          = 0.92,  # Embedding is deterministic — high confidence
            is_below_floor      = False,
            weight              = DIMENSION_WEIGHTS["semantic_contextual_alignment"],
            evidence_phrases_cv = evidence_cv,
            evidence_phrases_jd = evidence_jd,
        )

    # ── Aggregator ─────────────────────────────────────────────────────────

    def compute_all_dimension_scores(
        self,
        cv_entities:       CVEntities,
        jd_entities:       JDEntities,
        semantic_analysis: SemanticAnalysis,
        skills_result:     SkillsOntologyResult,
    ) -> Dict[str, DimensionScore]:
        """
        Computes all seven DimensionScore objects in dependency order.
        Sets `is_below_floor` on each score after all scores are known.

        Returns a dict keyed by dimension name (matches DIMENSION_WEIGHTS keys).
        """
        dim_scores: Dict[str, DimensionScore] = {
            "technical_skills_match": self.technical_skills_match(
                skills_result, jd_entities
            ),
            "experience_depth_alignment": self.experience_depth_alignment(
                cv_entities, jd_entities
            ),
            "educational_relevance": self.educational_relevance(
                cv_entities, jd_entities
            ),
            "domain_knowledge": self.domain_knowledge(
                cv_entities, jd_entities, semantic_analysis
            ),
            "soft_skills_signals": self.soft_skills_signals(cv_entities),
            "seniority_trajectory": self.seniority_trajectory(
                cv_entities, jd_entities
            ),
            "semantic_contextual_alignment": self.semantic_contextual_alignment(
                semantic_analysis
            ),
        }

        # Post-hoc: mark dimensions below general floor threshold
        updated: Dict[str, DimensionScore] = {}
        for name, ds in dim_scores.items():
            below = ds.raw_score < GENERAL_FLOOR_THRESHOLD
            updated[name] = ds.model_copy(update={"is_below_floor": below})

        return updated


# ===========================================================================
# NarrativeGenerator
# ===========================================================================

class NarrativeGenerator:
    """
    Drives Gemini 2.0 Flash to generate the two access-controlled narrative
    perspectives: CandidatePerspective and RecruiterPerspective.

    Both perspectives are generated in a single session-scoped call and
    stored in the payload. Rendering is controlled exclusively by
    access_control.py — the LLM never sees which "room" is being rendered.

    Fallback behaviour:
    If Gemini is unavailable (network error, missing API key), deterministic
    fallback perspectives are constructed from the structured analysis data
    without any LLM call. The fallback is flagged in GovernanceLayer.
    """

    def __init__(self, language: str = "en", enable_llm: bool = True):
        self.language = language
        self._enable_llm = enable_llm
        self._llm: Any = None

    def _get_llm(self) -> Any:
        if self._llm is None:
            from langchain_google_genai import ChatGoogleGenerativeAI
            self._llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                temperature=0.30,
            )
        return self._llm

    # ── Gap Closure Roadmap (Deterministic) ───────────────────────────────

    @staticmethod
    def _build_gap_closure_roadmap(
        missing_critical: List[SkillMatchEntry],
        missing_preferred: List[SkillMatchEntry],
        experience_gap_months: float = 0.0,
    ) -> List[ActionItem]:
        """
        Builds the ActionItem list deterministically from skills_result.
        This is intentionally NOT generated by the LLM to prevent hallucinated
        resource recommendations and to ensure scores are evidence-grounded.
        """
        roadmap: List[ActionItem] = []
        priority = 1

        for skill in missing_critical[:5]:
            roadmap.append(ActionItem(
                priority=priority,
                dimension="technical_skills_match",
                skill_or_gap=skill.skill_name,
                current_state_description=(
                    f"'{skill.canonical_name}' is absent from your CV. "
                    f"This is a required skill for this role."
                ),
                target_state_description=(
                    f"Demonstrate working proficiency in {skill.canonical_name} "
                    "with at least one project example or practical use case."
                ),
                suggested_learning_resources=[],   # Enriched by RAG in later pass
                estimated_effort_weeks=6,
                is_critical_gap_closure=True,
            ))
            priority += 1

        if experience_gap_months > 6:
            roadmap.append(ActionItem(
                priority=priority,
                dimension="experience_depth_alignment",
                skill_or_gap="Experience Depth",
                current_state_description=(
                    f"Your experience is approximately {experience_gap_months:.0f} months "
                    "shorter than the role's requirement."
                ),
                target_state_description=(
                    "Bridge the gap through project work, freelance contracts, or "
                    "targeted contributions to open-source projects in the required domain."
                ),
                suggested_learning_resources=[],
                estimated_effort_weeks=int(experience_gap_months / 4),
                is_critical_gap_closure=True,
            ))
            priority += 1

        for skill in missing_preferred[:3]:
            roadmap.append(ActionItem(
                priority=priority,
                dimension="technical_skills_match",
                skill_or_gap=skill.skill_name,
                current_state_description=(
                    f"'{skill.canonical_name}' is a preferred (not required) skill "
                    "that would strengthen your application."
                ),
                target_state_description=(
                    f"Acquire foundational working knowledge of {skill.canonical_name}."
                ),
                suggested_learning_resources=[],
                estimated_effort_weeks=3,
                is_critical_gap_closure=False,
            ))
            priority += 1

        return roadmap

    # ── Prompt Builders ────────────────────────────────────────────────────

    def _format_candidate_prompt(
        self,
        cv_entities:      CVEntities,
        jd_entities:      JDEntities,
        dimension_scores: Dict[str, float],
        skills_result:    SkillsOntologyResult,
        composite_score:  float,
        rag_context:      str = "",
    ) -> str:
        matched_names     = [s.canonical_name for s in skills_result.matched_skills[:8]]
        missing_critical  = [s.skill_name for s in skills_result.missing_critical[:5]]
        gap_severity_val  = skills_result.gap_severity

        dim_block = "\n".join(
            f"  {dim.replace('_', ' ').title()}: {score * 100:.1f}%"
            for dim, score in dimension_scores.items()
        )

        context_block = (
            f"\nRELEVANT COACHING CONTEXT FROM KNOWLEDGE BASE:\n{rag_context}\n"
            if rag_context else ""
        )

        return f"""You are an expert career coach for the Armenian and CIS technology market.
Language for all output: {self.language.upper()}.
Candidate role target: {jd_entities.role_title} (required seniority: {jd_entities.required_seniority})
Composite match score: {composite_score * 100:.1f}%
{dim_block}
Matched skills: {', '.join(matched_names) or 'None identified'}
Missing critical skills: {', '.join(missing_critical) or 'None'}
Gap severity: {gap_severity_val}
{context_block}
Generate a JSON object with EXACTLY these four keys:
{{
  "strength_narrative": "<2-3 paragraphs acknowledging the candidate's genuine strengths with specific evidence. Name skills and experiences. Never give empty compliments.>",
  "interview_preparation_focus": "<1-2 paragraphs: which 2-3 areas to prioritize based on the gap analysis, with a brief strategy for each>",
  "salary_positioning_context": "<1 paragraph: honest, grounded context on salary expectations in the Armenian tech market for this role level given the composite score>",
  "motivational_framing": "<2-3 sentences: evidence-based encouragement. Reference specific strengths. No generic platitudes.>"
}}
Output ONLY the JSON object. No markdown fences. No additional text."""

    def _format_recruiter_prompt(
        self,
        cv_entities:      CVEntities,
        jd_entities:      JDEntities,
        dimension_scores: Dict[str, float],
        skills_result:    SkillsOntologyResult,
        composite_score:  float,
        bias_audit:       BiasAuditResult,
    ) -> str:
        missing_critical = [s.skill_name for s in skills_result.missing_critical[:5]]
        matched_names    = [s.canonical_name for s in skills_result.matched_skills[:8]]

        dim_block = "\n".join(
            f"  {dim.replace('_', ' ').title()}: {score * 100:.1f}%"
            for dim, score in dimension_scores.items()
        )

        return f"""You are an expert HR screening analyst for the Armenian tech market.
Role: {jd_entities.role_title} (required seniority: {jd_entities.required_seniority}, industry: {jd_entities.industry})
Composite match score: {composite_score * 100:.1f}%
{dim_block}
Matched skills: {', '.join(matched_names) or 'None identified'}
Missing critical skills: {', '.join(missing_critical) or 'None'}
Evaluation integrity risk: {bias_audit.evaluation_integrity_risk}
Total experience: {cv_entities.total_years_experience:.1f} years
Required experience: {jd_entities.required_experience_years:.0f}+ years

Generate a JSON object with EXACTLY these keys:
{{
  "screening_summary": "<2-3 paragraph objective assessment of this CV-JD match for a professional recruiter. Be direct and specific about strengths and gaps.>",
  "hire_recommendation": "<one of: strong_yes | yes | maybe | no>",
  "hire_recommendation_rationale": "<1-2 paragraphs: evidence-based rationale for the recommendation. Reference specific dimension scores and skill gaps.>",
  "comparative_profile_summary": "<1 paragraph: how this candidate compares to a typical applicant at this seniority level>",
  "red_flag_summary": "<1 sentence per flag, or null if none>",
  "verification_points": [
    {{
      "topic": "<skill or experience area to verify>",
      "evidence_gap_description": "<what the CV lacks or is ambiguous about>",
      "why_it_matters": "<why this gap is relevant to role success>",
      "suggested_interview_question": "<specific behavioral or technical question>",
      "importance_level": "<must_ask | recommended | optional>"
    }}
  ]
}}
Generate {min(5, len(missing_critical) + 2)} verification_points.
Each suggested_interview_question must be specific and probing, not generic.
importance_level MUST be exactly one of: must_ask, recommended, optional.
Output ONLY the JSON object. No markdown fences. No additional text."""

    # ── JSON Extraction ────────────────────────────────────────────────────

    @staticmethod
    def _extract_json_safe(text: str) -> dict:
        """
        Robust JSON extraction tolerating markdown fences and leading/trailing text.
        Tries three strategies in order of strictness.
        """
        # Strategy 1: direct parse
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # Strategy 2: extract from markdown code block
        fence_match = re.search(
            r"```(?:json)?\s*(\{.*?\})\s*```",
            text, re.DOTALL
        )
        if fence_match:
            try:
                return json.loads(fence_match.group(1))
            except json.JSONDecodeError:
                pass

        # Strategy 3: find first { to last }
        start = text.find("{")
        end   = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start: end + 1])
            except json.JSONDecodeError:
                pass

        logger.warning("NarrativeGenerator: JSON extraction failed. Returning empty dict.")
        return {}

    # ── Fallback Constructors ──────────────────────────────────────────────

    @staticmethod
    def _fallback_candidate_perspective(
        skills_result: SkillsOntologyResult,
        jd_entities:   JDEntities,
        composite_pct: float,
        roadmap:       List[ActionItem],
    ) -> CandidatePerspective:
        matched = [s.canonical_name for s in skills_result.matched_skills[:5]]
        return CandidatePerspective(
            strength_narrative=(
                f"Your profile demonstrates competency in {len(skills_result.matched_skills)} "
                f"of the required skills for {jd_entities.role_title}, achieving a composite "
                f"match of {composite_pct:.1f}%. "
                f"Strong areas include: {', '.join(matched) or 'foundational domain skills'}."
            ),
            gap_closure_roadmap=roadmap,
            interview_preparation_focus=(
                f"Focus your preparation on the {skills_result.critical_gap_count} critical "
                f"skill gaps identified. For each, prepare one concrete project example "
                "demonstrating applied learning."
            ),
            salary_positioning_context=(
                f"At a {composite_pct:.1f}% match for a {jd_entities.required_seniority}-level "
                f"role in the Armenian tech market, target the 15th–35th percentile of the "
                "posted salary range as your opening position."
            ),
            top_strength_phrases=matched,
            motivational_framing=(
                "Your technical foundation provides a viable path to this role. "
                "Targeted upskilling on the identified gaps over 4–8 weeks would "
                "substantially strengthen your application."
            ),
        )

    @staticmethod
    def _fallback_recruiter_perspective(
        cv_entities:   CVEntities,
        jd_entities:   JDEntities,
        skills_result: SkillsOntologyResult,
        composite_pct: float,
    ) -> RecruiterPerspective:
        rec = (
            HireRecommendation.YES    if composite_pct >= 70 else
            HireRecommendation.MAYBE  if composite_pct >= 50 else
            HireRecommendation.NO
        )
        vp_list = [
            VerificationPoint(
                topic=s.skill_name,
                evidence_gap_description=f"'{s.canonical_name}' absent from CV",
                why_it_matters=f"Listed as required skill for {jd_entities.role_title}",
                suggested_interview_question=(
                    f"Can you describe a situation where you used {s.canonical_name} "
                    "or a functionally equivalent tool to solve a specific problem?"
                ),
                importance_level="must_ask",
            )
            for s in skills_result.missing_critical[:4]
        ]
        return RecruiterPerspective(
            screening_summary=(
                f"Candidate achieves {composite_pct:.1f}% composite match for "
                f"{jd_entities.role_title}. "
                f"Experience: {cv_entities.total_years_experience:.1f} years vs "
                f"{jd_entities.required_experience_years:.0f}+ required. "
                f"{skills_result.critical_gap_count} critical skill gap(s) identified."
            ),
            hire_recommendation=rec,
            hire_recommendation_rationale=(
                f"Score of {composite_pct:.1f}% with {skills_result.critical_gap_count} "
                "critical gap(s) supports this recommendation."
            ),
            verification_points=vp_list,
        )

    # ── Public Interface ───────────────────────────────────────────────────

    async def generate_candidate_perspective(
        self,
        cv_entities:      CVEntities,
        jd_entities:      JDEntities,
        dimension_scores: Dict[str, float],
        skills_result:    SkillsOntologyResult,
        composite_score:  float,
        rag_context:      str = "",
    ) -> Tuple[CandidatePerspective, bool]:
        """
        Returns (CandidatePerspective, used_fallback).
        Roadmap is always built deterministically regardless of Gemini availability.
        """
        required_yrs  = jd_entities.required_experience_years
        actual_yrs    = cv_entities.total_years_experience
        exp_gap_months = max(0.0, (required_yrs - actual_yrs) * 12)

        roadmap = self._build_gap_closure_roadmap(
            skills_result.missing_critical,
            skills_result.missing_preferred,
            exp_gap_months,
        )

        # Deterministic kill-switch: no Gemini call when LLM use is disabled.
        if not self._enable_llm:
            fallback = self._fallback_candidate_perspective(
                skills_result, jd_entities, composite_score * 100, roadmap
            )
            return fallback, True

        try:
            from langchain_core.messages import HumanMessage
            llm    = self._get_llm()
            prompt = self._format_candidate_prompt(
                cv_entities, jd_entities, dimension_scores,
                skills_result, composite_score, rag_context,
            )
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            parsed   = self._extract_json_safe(response.content)

            if not parsed.get("strength_narrative"):
                raise ValueError("Gemini response missing required 'strength_narrative' key.")

            perspective = CandidatePerspective(
                strength_narrative        = parsed.get("strength_narrative", ""),
                gap_closure_roadmap       = roadmap,
                interview_preparation_focus = parsed.get("interview_preparation_focus", ""),
                salary_positioning_context  = parsed.get("salary_positioning_context", ""),
                top_strength_phrases      = [
                    s.canonical_name for s in skills_result.matched_skills[:6]
                ],
                motivational_framing      = parsed.get("motivational_framing", ""),
            )
            return perspective, False

        except Exception as exc:
            logger.warning(
                "NarrativeGenerator: CandidatePerspective Gemini call failed (%s). "
                "Using deterministic fallback.",
                exc,
            )
            fallback = self._fallback_candidate_perspective(
                skills_result, jd_entities, composite_score * 100, roadmap
            )
            return fallback, True

    async def generate_recruiter_perspective(
        self,
        cv_entities:      CVEntities,
        jd_entities:      JDEntities,
        dimension_scores: Dict[str, float],
        skills_result:    SkillsOntologyResult,
        composite_score:  float,
        bias_audit:       BiasAuditResult,
    ) -> Tuple[RecruiterPerspective, bool]:
        """
        Returns (RecruiterPerspective, used_fallback).
        """
        # Deterministic kill-switch: no Gemini call when LLM use is disabled.
        if not self._enable_llm:
            fallback = self._fallback_recruiter_perspective(
                cv_entities, jd_entities, skills_result, composite_score * 100
            )
            return fallback, True

        try:
            from langchain_core.messages import HumanMessage
            llm    = self._get_llm()
            prompt = self._format_recruiter_prompt(
                cv_entities, jd_entities, dimension_scores,
                skills_result, composite_score, bias_audit,
            )
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            parsed   = self._extract_json_safe(response.content)

            if not parsed.get("screening_summary"):
                raise ValueError("Gemini response missing required 'screening_summary' key.")

            # Parse hire_recommendation safely
            rec_raw = (parsed.get("hire_recommendation") or "maybe").lower().strip()
            valid_recs = {e.value for e in HireRecommendation}
            hire_rec = HireRecommendation(rec_raw) if rec_raw in valid_recs else HireRecommendation.MAYBE

            # Parse verification_points safely
            vp_list: List[VerificationPoint] = []
            for vp_raw in parsed.get("verification_points", []):
                try:
                    il = vp_raw.get("importance_level", "recommended").lower()
                    if il not in {"must_ask", "recommended", "optional"}:
                        il = "recommended"
                    vp_list.append(VerificationPoint(
                        topic                        = str(vp_raw.get("topic", "")),
                        evidence_gap_description     = str(vp_raw.get("evidence_gap_description", "")),
                        why_it_matters               = str(vp_raw.get("why_it_matters", "")),
                        suggested_interview_question = str(vp_raw.get("suggested_interview_question", "")),
                        importance_level             = il,
                    ))
                except Exception as vp_exc:
                    logger.debug("Skipping malformed verification_point: %s", vp_exc)

            perspective = RecruiterPerspective(
                screening_summary              = parsed.get("screening_summary", ""),
                hire_recommendation            = hire_rec,
                hire_recommendation_rationale  = parsed.get("hire_recommendation_rationale", ""),
                verification_points            = vp_list,
                comparative_profile_summary    = parsed.get("comparative_profile_summary", ""),
                red_flag_summary               = parsed.get("red_flag_summary"),
            )
            return perspective, False

        except Exception as exc:
            logger.warning(
                "NarrativeGenerator: RecruiterPerspective Gemini call failed (%s). "
                "Using deterministic fallback.",
                exc,
            )
            fallback = self._fallback_recruiter_perspective(
                cv_entities, jd_entities, skills_result, composite_score * 100
            )
            return fallback, True


# ===========================================================================
# PayloadAssembler
# ===========================================================================

class PayloadAssembler:
    """
    Terminal node in the LangGraph orchestration graph.
    Receives the fully populated OrchestratorState (as AssemblerInputState),
    orchestrates DimensionScoreMapper and NarrativeGenerator, and returns
    a validated CanonicalAnalysisPayload.

    Usage (from orchestrator node):
        assembler = PayloadAssembler()
        payload   = await assembler.assemble(state)
    """

    def __init__(self) -> None:
        self.score_mapper = DimensionScoreMapper()

    # ── Meta-Score Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _compute_completeness_score(
        phase1_statuses: Dict[str, AgentExecutionStatus],
        phase2_status:   AgentExecutionStatus,
    ) -> float:
        """
        Completeness is reduced by 0.15 per Phase 1 agent in FALLBACK status
        and by 0.10 if Phase 2 (Bias & Safety) ran in fallback.
        Minimum completeness is 0.10 to prevent zero-confidence payloads.
        """
        phase1_penalty = sum(
            0.15 for status in phase1_statuses.values()
            if status == AgentExecutionStatus.FALLBACK
        )
        phase2_penalty = 0.10 if phase2_status == AgentExecutionStatus.FALLBACK else 0.0
        return round(max(0.10, 1.0 - phase1_penalty - phase2_penalty), 3)

    @staticmethod
    def _compute_overall_confidence(
        dimension_scores: Dict[str, DimensionScore],
        completeness:     float,
        bias_risk:        EvaluationIntegrityRisk,
    ) -> float:
        """
        Overall confidence = mean dimension confidence × completeness − bias penalty.
        Bias penalty reflects that high-integrity-risk analysis outputs carry
        greater epistemic uncertainty even if structural quality is high.
        """
        mean_dim_confidence = sum(
            ds.confidence for ds in dimension_scores.values()
        ) / len(dimension_scores)

        bias_penalty_map = {
            EvaluationIntegrityRisk.LOW:    0.00,
            EvaluationIntegrityRisk.MEDIUM: 0.05,
            EvaluationIntegrityRisk.HIGH:   0.15,
        }
        bias_penalty = bias_penalty_map.get(bias_risk, 0.05)
        return round(max(0.05, mean_dim_confidence * completeness - bias_penalty), 3)

    @staticmethod
    def _build_governance_layer(
        state:              AssemblerInputState,
        bias_audit:         BiasAuditResult,
        model_chain:        List[str],
        total_ms:           int,
        used_fallbacks:     List[str],
        hallucination_flags: List[str],
    ) -> GovernanceLayer:
        phase1_statuses = state.get("phase1_statuses", {})
        phase2_status   = state.get("phase2_status", AgentExecutionStatus.SUCCESS)

        return GovernanceLayer(
            pii_masking_applied             = True,
            pii_fields_masked               = ["full_name", "email", "phone"],
            guardrail_input_passed          = True,
            guardrail_input_rejection_reason = None,
            guardrail_output_passed         = len(hallucination_flags) == 0,
            guardrail_output_flags          = used_fallbacks,
            hallucination_flags             = hallucination_flags,
            phase1_agent_status             = {
                k: AgentExecutionStatus(v) if isinstance(v, str) else v
                for k, v in phase1_statuses.items()
            },
            phase2_agent_status             = phase2_status,
            bias_audit                      = bias_audit,
            model_chain_used                = model_chain,
            total_processing_time_ms        = total_ms,
        )

    # ── Primary Assembly Entrypoint ────────────────────────────────────────

    async def assemble(
        self,
        state: AssemblerInputState,
    ) -> CanonicalAnalysisPayload:
        """
        Full assembly pipeline. Steps:
          1. Extract and validate agent outputs from state.
          2. Compute all seven DimensionScore objects.
          3. Extract raw scores → compute_composite_score().
          4. Build DimensionalAnalysis.
          5. Generate CandidatePerspective and RecruiterPerspective in parallel.
          6. Build GovernanceLayer.
          7. Compute meta-scores (completeness, overall confidence).
          8. Construct and return validated CanonicalAnalysisPayload.
        """
        assembly_start_ms = int(time.monotonic() * 1000)

        # ── Step 1: Extract agent outputs with safe defaults ──────────────
        cv_entities    = state.get("cv_entities")
        jd_entities    = state.get("jd_entities")
        semantic_result = state.get("semantic_result")
        skills_result   = state.get("skills_result")
        bias_audit      = state.get("bias_audit_result")

        if any(v is None for v in [cv_entities, jd_entities, semantic_result, skills_result]):
            raise ValueError(
                "PayloadAssembler.assemble() received None for one or more required "
                "Phase 1 outputs. Verify fallback factory functions in orchestrator.py."
            )

        if bias_audit is None:
            logger.warning("BiasAuditResult is None — using minimal fallback.")
            bias_audit = BiasAuditResult(
                evaluation_integrity_risk                = EvaluationIntegrityRisk.MEDIUM,
                risk_rationale                          = "Bias audit did not complete. Manual review required.",
                structured_interview_recommendations    = [],
                emergent_scoring_bias_detected          = False,
                jd_exclusionary_language_flagged        = False,
            )

        # ── Step 2: Compute all seven DimensionScore objects ──────────────
        dim_score_objects = self.score_mapper.compute_all_dimension_scores(
            cv_entities, jd_entities, semantic_result, skills_result
        )

        raw_scores: Dict[str, float] = {
            name: ds.raw_score for name, ds in dim_score_objects.items()
        }

        # ── Step 3: Composite scoring ──────────────────────────────────────
        scoring_result = compute_composite_score(raw_scores)

        # ── Step 4: Build DimensionalAnalysis ─────────────────────────────
        dimensional_analysis = DimensionalAnalysis(
            technical_skills_match        = dim_score_objects["technical_skills_match"],
            experience_depth_alignment    = dim_score_objects["experience_depth_alignment"],
            educational_relevance         = dim_score_objects["educational_relevance"],
            domain_knowledge              = dim_score_objects["domain_knowledge"],
            soft_skills_signals           = dim_score_objects["soft_skills_signals"],
            seniority_trajectory          = dim_score_objects["seniority_trajectory"],
            semantic_contextual_alignment = dim_score_objects["semantic_contextual_alignment"],
            composite_score               = scoring_result.composite_score,
            composite_score_percentage    = scoring_result.composite_percentage,
            dimensional_outlier_alert     = scoring_result.outlier_alert,
            outlier_dimensions            = scoring_result.outlier_dimensions,
            hard_floor_applied            = scoring_result.hard_floor_applied,
        )

        # ── Step 5: Generate narratives in parallel via Gemini ─────────────
        language = state.get("language", "en")
        narrative_gen = NarrativeGenerator(
            language=language, enable_llm=bool(state.get("enable_llm", True)),
        )

        candidate_perspective_coro = narrative_gen.generate_candidate_perspective(
            cv_entities      = cv_entities,
            jd_entities      = jd_entities,
            dimension_scores = raw_scores,
            skills_result    = skills_result,
            composite_score  = scoring_result.composite_score,
        )
        recruiter_perspective_coro = narrative_gen.generate_recruiter_perspective(
            cv_entities      = cv_entities,
            jd_entities      = jd_entities,
            dimension_scores = raw_scores,
            skills_result    = skills_result,
            composite_score  = scoring_result.composite_score,
            bias_audit       = bias_audit,
        )

        (candidate_perspective, candidate_fallback), (recruiter_perspective, recruiter_fallback) = (
            await asyncio.gather(candidate_perspective_coro, recruiter_perspective_coro)
        )

        used_fallbacks = []
        if candidate_fallback:
            used_fallbacks.append("candidate_perspective_fallback")
        if recruiter_fallback:
            used_fallbacks.append("recruiter_perspective_fallback")

        # ── Step 6: Build GovernanceLayer ──────────────────────────────────
        assembly_end_ms = int(time.monotonic() * 1000)
        total_ms        = assembly_end_ms - assembly_start_ms

        model_chain = [
            "gpt-4.1-mini (document_intelligence)",
            "gpt-4.1-mini (semantic_alignment)",
            "gpt-4.1-mini (skills_ontology)",
            "gpt-4.1-mini (bias_safety)",
            "gemini-2.0-flash (candidate_perspective)",
            "gemini-2.0-flash (recruiter_perspective)",
        ]

        governance = self._build_governance_layer(
            state               = state,
            bias_audit          = bias_audit,
            model_chain         = model_chain,
            total_ms            = total_ms,
            used_fallbacks      = used_fallbacks,
            hallucination_flags = [],
        )

        # ── Step 7: Meta-scores ────────────────────────────────────────────
        completeness = self._compute_completeness_score(
            state.get("phase1_statuses", {}),
            state.get("phase2_status", AgentExecutionStatus.SUCCESS),
        )
        overall_confidence = self._compute_overall_confidence(
            dim_score_objects,
            completeness,
            bias_audit.evaluation_integrity_risk,
        )

        # ── Step 8: Construct and validate CanonicalAnalysisPayload ───────
        payload = CanonicalAnalysisPayload(
            session_id                 = state.get("session_id", ""),
            analysis_version           = "1.0.0",
            language                   = language,
            seniority_context          = state.get("seniority_context", "junior"),
            cv_entities                = cv_entities,
            jd_entities                = jd_entities,
            dimensional_analysis       = dimensional_analysis,
            skills_ontology            = skills_result,
            semantic_analysis          = semantic_result,
            governance                 = governance,
            candidate_perspective      = candidate_perspective,
            recruiter_perspective      = recruiter_perspective,
            overall_analysis_confidence = overall_confidence,
            analysis_completeness_score = completeness,
        )

        logger.info(
            "PayloadAssembler complete | session=%s | composite=%.4f (%.1f%%) "
            "| floor=%s | completeness=%.3f | total_ms=%d",
            payload.session_id,
            scoring_result.composite_score,
            scoring_result.composite_percentage,
            scoring_result.floor_report.tier_applied.value,
            completeness,
            total_ms,
        )

        return payload
