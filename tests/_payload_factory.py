# tests/_payload_factory.py
#
# Shared in-memory CanonicalAnalysisPayload builder for Phase-4 tests.
# Not a test module itself (underscore prefix) — imported by the guardrail and
# access-control test suites. No agents, no LLM, no data/raw access.

from src.schemas.canonical_payload import (
    BiasAuditResult,
    CanonicalAnalysisPayload,
    CandidatePerspective,
    CVEntities,
    DimensionScore,
    DimensionalAnalysis,
    EvaluationIntegrityRisk,
    GovernanceLayer,
    HireRecommendation,
    JDEntities,
    RecruiterPerspective,
    SemanticAnalysis,
    SkillMatchEntry,
    SkillMatchType,
    SkillsOntologyResult,
    VerificationPoint,
)

# Sentinel strings used by tests to prove view separation.
MOTIVATION_TEXT = "Keep going, you can close these gaps!"
RED_FLAG_TEXT = "Gap in production deployment experience."


def _ds(score: float) -> DimensionScore:
    return DimensionScore(raw_score=score, confidence=0.9, weight=0.1)


def make_payload(
    *,
    candidate_strength: str = "Strong Python and data background.",
    recruiter_summary: str = "Solid mid-level match with two critical gaps.",
) -> CanonicalAnalysisPayload:
    dimensional = DimensionalAnalysis(
        technical_skills_match=_ds(0.7),
        experience_depth_alignment=_ds(0.6),
        educational_relevance=_ds(0.8),
        domain_knowledge=_ds(0.55),
        soft_skills_signals=_ds(0.5),
        seniority_trajectory=_ds(0.62),
        semantic_contextual_alignment=_ds(0.66),
        composite_score=0.62,
        composite_score_percentage=62.0,
        dimensional_outlier_alert=False,
        outlier_dimensions=[],
        hard_floor_applied=False,
    )

    skills = SkillsOntologyResult(
        matched_skills=[SkillMatchEntry(
            skill_name="Python", canonical_name="Python", match_type=SkillMatchType.MATCHED,
        )],
        missing_critical=[SkillMatchEntry(
            skill_name="Kubernetes", canonical_name="Kubernetes",
            match_type=SkillMatchType.MISSING_CRITICAL, is_critical=True,
        )],
        total_required_skills=4,
        matched_count=2,
        critical_gap_count=1,
        coverage_ratio=0.5,
    )

    semantic = SemanticAnalysis(
        embedding_cosine_similarity=0.72,
        key_phrase_overlap_ratio=0.4,
        contextual_domain_alignment=0.6,
    )

    governance = GovernanceLayer(
        bias_audit=BiasAuditResult(
            evaluation_integrity_risk=EvaluationIntegrityRisk.LOW,
            risk_rationale="No demographic proxy signals materially affected scoring.",
            structured_interview_recommendations=["Use a structured rubric for all candidates."],
        ),
        model_chain_used=["gpt-4.1-mini", "gemini-2.0-flash"],
    )

    candidate = CandidatePerspective(
        strength_narrative=candidate_strength,
        interview_preparation_focus="Prepare Kubernetes fundamentals.",
        salary_positioning_context="Target the mid band for this role.",
        motivational_framing=MOTIVATION_TEXT,
    )

    recruiter = RecruiterPerspective(
        screening_summary=recruiter_summary,
        hire_recommendation=HireRecommendation.MAYBE,
        hire_recommendation_rationale="Mid match with a critical container-orchestration gap.",
        verification_points=[VerificationPoint(
            topic="Kubernetes",
            evidence_gap_description="No K8s experience evident in CV.",
            why_it_matters="Role requires container orchestration ownership.",
            suggested_interview_question="Walk through a rollout you managed on Kubernetes.",
            importance_level="must_ask",
        )],
        red_flag_summary=RED_FLAG_TEXT,
    )

    return CanonicalAnalysisPayload(
        cv_entities=CVEntities(),
        jd_entities=JDEntities(role_title="Backend Engineer"),
        dimensional_analysis=dimensional,
        skills_ontology=skills,
        semantic_analysis=semantic,
        governance=governance,
        candidate_perspective=candidate,
        recruiter_perspective=recruiter,
        overall_analysis_confidence=0.8,
        analysis_completeness_score=1.0,
    )
