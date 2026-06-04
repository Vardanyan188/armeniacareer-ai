# src/engine/access_control.py
#
# Access-control selectors — the single enforcement point for the
# information-asymmetry policy between the Candidate Coach Room and the
# Recruiter Intelligence Room. No UI component reads the payload directly;
# every surface goes through one of these selectors.
#
# Policy summary:
#   Candidate view  EXCLUDES: recruiter_perspective (hire recommendation,
#                   verification points, red flags) and raw bias-audit details.
#   Recruiter view  EXCLUDES: candidate_perspective (motivational framing and
#                   the personal coaching roadmap).
#   Shared view     exposes only neutral analysis: dimensional analysis, skills/
#                   semantic summaries, and governance status — no perspectives,
#                   no hire recommendation, no raw bias signals.

from __future__ import annotations

from typing import Any, Dict

from src.schemas.canonical_payload import CanonicalAnalysisPayload

# Canonical dimension field names, in display order.
_DIMENSIONS = [
    "technical_skills_match",
    "experience_depth_alignment",
    "educational_relevance",
    "domain_knowledge",
    "soft_skills_signals",
    "seniority_trajectory",
    "semantic_contextual_alignment",
]


def get_candidate_view(payload: CanonicalAnalysisPayload) -> Dict[str, Any]:
    """
    Candidate Coach Room view. Excludes the recruiter perspective entirely
    (hire recommendation, verification points, red flags) and all raw bias-audit
    details. The candidate sees which dimensions are weak, not the recruiter's
    assessment of them.
    """
    da = payload.dimensional_analysis
    skills = payload.skills_ontology
    return {
        "session_id": payload.session_id,
        "composite_score_percentage": da.composite_score_percentage,
        "dimensional_scores": {
            dim: getattr(da, dim).raw_score for dim in _DIMENSIONS
        },
        "dimensional_outlier_alert": da.dimensional_outlier_alert,
        "outlier_dimensions": da.outlier_dimensions,
        "matched_skills": skills.matched_skills,
        "missing_critical": skills.missing_critical,
        "missing_preferred": skills.missing_preferred,
        "transferable": skills.transferable,
        "gap_severity": skills.gap_severity,
        "candidate_perspective": payload.candidate_perspective,
        "overall_confidence": payload.overall_analysis_confidence,
        "role_title": payload.jd_entities.role_title,
        "required_seniority": payload.jd_entities.required_seniority,
    }


def get_recruiter_view(payload: CanonicalAnalysisPayload) -> Dict[str, Any]:
    """
    Recruiter Intelligence Room view. Full analytical scope plus processed bias
    risk. Excludes the candidate's personal coaching roadmap and motivational
    framing (by omitting candidate_perspective entirely).
    """
    bias = payload.governance.bias_audit
    da = payload.dimensional_analysis
    return {
        "session_id": payload.session_id,
        "composite_score_percentage": da.composite_score_percentage,
        "dimensional_analysis": da,
        "skills_ontology": payload.skills_ontology,
        "semantic_analysis": payload.semantic_analysis,
        "recruiter_perspective": payload.recruiter_perspective,
        "evaluation_integrity_risk": bias.evaluation_integrity_risk,
        "integrity_risk_rationale": bias.risk_rationale,
        "structured_interview_recommendations": bias.structured_interview_recommendations,
        "emergent_bias_detected": bias.emergent_scoring_bias_detected,
        "emergent_bias_details": bias.emergent_bias_details,
        "jd_exclusionary_language_flagged": bias.jd_exclusionary_language_flagged,
        "analysis_completeness_score": payload.analysis_completeness_score,
        "model_chain_used": payload.governance.model_chain_used,
        "cv_entities": payload.cv_entities,
        "jd_entities": payload.jd_entities,
        "hard_floor_applied": da.hard_floor_applied,
        "outlier_dimensions": da.outlier_dimensions,
    }


def get_skill_depth_view(payload: CanonicalAnalysisPayload) -> Any:
    """
    Neutral Skill Proficiency / Requirement Depth view (Phase 19).

    Computes a deterministic SkillDepthAnalysis from the structured CV/JD
    entities only. It is explanatory and PII-free: skill names, candidate/
    required depth levels, match types, depth gaps, curated evidence labels,
    and templated neutral explanations — no raw CV/JD text, no perspective
    (candidate-only / recruiter-only) narrative. Safe for all three rooms;
    each surface applies its own framing.
    """
    # Imported lazily to keep access_control import-light and free of cycles.
    from src.engine.skill_depth.analyzer import analyze_skill_depth

    return analyze_skill_depth(payload.cv_entities, payload.jd_entities)


def get_shared_view(payload: CanonicalAnalysisPayload) -> Dict[str, Any]:
    """
    Neutral shared analysis view. Exposes dimensional analysis, skills/semantic
    summaries, and governance status only — no perspectives, no hire
    recommendation, no raw demographic/bias signals.
    """
    skills = payload.skills_ontology
    sem = payload.semantic_analysis
    gov = payload.governance
    da = payload.dimensional_analysis
    return {
        "session_id": payload.session_id,
        "composite_score_percentage": da.composite_score_percentage,
        "dimensional_analysis": da,
        "skills_ontology_summary": {
            "total_required_skills": skills.total_required_skills,
            "matched_count": skills.matched_count,
            "critical_gap_count": skills.critical_gap_count,
            "coverage_ratio": skills.coverage_ratio,
            "gap_severity": skills.gap_severity,
        },
        "semantic_analysis_summary": {
            "embedding_cosine_similarity": sem.embedding_cosine_similarity,
            "key_phrase_overlap_ratio": sem.key_phrase_overlap_ratio,
            "contextual_domain_alignment": sem.contextual_domain_alignment,
        },
        "governance_status": {
            "pii_masking_applied": gov.pii_masking_applied,
            "guardrail_input_passed": gov.guardrail_input_passed,
            "guardrail_output_passed": gov.guardrail_output_passed,
            "guardrail_output_flags": gov.guardrail_output_flags,
            "phase1_agent_status": gov.phase1_agent_status,
            "phase2_agent_status": gov.phase2_agent_status,
            "analysis_completeness_score": payload.analysis_completeness_score,
        },
    }
