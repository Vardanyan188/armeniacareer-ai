# tests/test_skill_depth.py
#
# Deterministic tests for the Skill Proficiency / Requirement Depth layer
# (Phase 19). No LLM, no network, no data/raw. Explanatory only — asserts it
# never changes scoring and never leaks raw text.

from typing import List, Optional

import pytest

from src.engine.access_control import get_skill_depth_view
from src.engine.skill_depth.analyzer import analyze_skill_depth
from src.engine.skill_depth.models import DepthMatchType, SkillDepth
from src.schemas.canonical_payload import (
    CVEntities,
    JDEntities,
    SkillCategory,
    SkillEntry,
    WorkExperience,
)

from tests._payload_factory import make_payload


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _skill(name: str, prof: Optional[str] = None) -> SkillEntry:
    return SkillEntry(
        raw_name=name, canonical_name=name,
        category=SkillCategory.TECHNICAL, proficiency_signal=prof,
    )


def _cv(
    skills: List[str],
    *,
    technologies: Optional[List[str]] = None,
    responsibilities: Optional[List[str]] = None,
    years: float = 0.0,
    prof: Optional[dict] = None,
) -> CVEntities:
    prof = prof or {}
    raw_skills = [_skill(s, prof.get(s)) for s in skills]
    work = []
    if technologies or responsibilities:
        work = [WorkExperience(
            company="ACME", title="Engineer",
            technologies_mentioned=technologies or [],
            responsibilities=responsibilities or [],
        )]
    return CVEntities(raw_skills=raw_skills, work_history=work, total_years_experience=years)


def _jd(required: List[str], *, responsibilities: Optional[List[str]] = None) -> JDEntities:
    return JDEntities(
        role_title="Engineer",
        required_skills=[_skill(s) for s in required],
        responsibilities=responsibilities or [],
    )


def _entry(analysis, skill: str):
    return next(e for e in analysis.entries if e.skill == skill)


# ---------------------------------------------------------------------------
# Candidate depth detection — each tier
# ---------------------------------------------------------------------------

def test_candidate_depth_mentioned_only():
    a = analyze_skill_depth(_cv(["Python"]), _jd(["Python"]))
    assert _entry(a, "Python").candidate_depth == SkillDepth.MENTIONED


def test_candidate_depth_basic_from_years():
    a = analyze_skill_depth(_cv(["Python"], years=2.0), _jd(["Python"]))
    assert _entry(a, "Python").candidate_depth == SkillDepth.BASIC


def test_candidate_depth_applied():
    a = analyze_skill_depth(
        _cv(["Python"], technologies=["pandas", "numpy"]), _jd(["Python"]),
    )
    assert _entry(a, "Python").candidate_depth == SkillDepth.APPLIED


def test_candidate_depth_advanced():
    a = analyze_skill_depth(
        _cv(["Python"], responsibilities=["scikit-learn model training"]), _jd(["Python"]),
    )
    assert _entry(a, "Python").candidate_depth == SkillDepth.ADVANCED


def test_candidate_depth_production():
    a = analyze_skill_depth(
        _cv(["Python"], technologies=["fastapi"], responsibilities=["production optimization"]),
        _jd(["Python"]),
    )
    assert _entry(a, "Python").candidate_depth == SkillDepth.PRODUCTION


def test_candidate_depth_deployment_mlops():
    a = analyze_skill_depth(
        _cv(["Python"], technologies=["docker"], responsibilities=["mlops ci/cd monitoring"]),
        _jd(["Python"]),
    )
    e = _entry(a, "Python")
    assert e.candidate_depth == SkillDepth.DEPLOYMENT
    assert "mlops" in e.evidence_labels or "docker" in e.evidence_labels


# ---------------------------------------------------------------------------
# JD required depth detection — each tier
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("line,expected", [
    ("Basic knowledge of Python", SkillDepth.BASIC),
    ("Data analysis with Python and pandas", SkillDepth.APPLIED),
    ("Build and train Python ML models", SkillDepth.ADVANCED),
    ("Production-ready Python code", SkillDepth.PRODUCTION),
    ("Deploy and monitor Python models", SkillDepth.DEPLOYMENT),
])
def test_jd_required_depth_detection(line, expected):
    a = analyze_skill_depth(_cv(["Python"]), _jd(["Python"], responsibilities=[line]))
    assert _entry(a, "Python").required_depth == expected


def test_jd_required_depth_defaults_to_applied():
    a = analyze_skill_depth(_cv(["Python"]), _jd(["Python"]))
    assert _entry(a, "Python").required_depth == SkillDepth.APPLIED


# ---------------------------------------------------------------------------
# Match types
# ---------------------------------------------------------------------------

def test_full_depth_match():
    cv = _cv(["Python"], technologies=["docker"], responsibilities=["mlops deployment"])
    a = analyze_skill_depth(cv, _jd(["Python"]))  # required defaults to APPLIED
    e = _entry(a, "Python")
    assert e.candidate_depth == SkillDepth.DEPLOYMENT
    assert e.match_type == DepthMatchType.FULL_DEPTH_MATCH
    assert e.depth_gap == 0


def test_partial_depth_match():
    cv = _cv(["Python"], technologies=["pandas", "numpy"])             # APPLIED
    jd = _jd(["Python"], responsibilities=["Deploy and monitor Python models"])  # DEPLOYMENT
    e = _entry(analyze_skill_depth(cv, jd), "Python")
    assert e.match_type == DepthMatchType.PARTIAL_DEPTH_MATCH
    assert e.depth_gap == int(SkillDepth.DEPLOYMENT) - int(SkillDepth.APPLIED)


def test_mentioned_only_match():
    e = _entry(analyze_skill_depth(_cv(["Python"]), _jd(["Python"])), "Python")
    assert e.match_type == DepthMatchType.MENTIONED_ONLY


def test_missing_skill():
    a = analyze_skill_depth(_cv(["Python"]), _jd(["SQL"]))
    e = _entry(a, "SQL")
    assert e.match_type == DepthMatchType.MISSING_SKILL
    assert e.candidate_depth is None
    assert e.evidence_labels == []


# ---------------------------------------------------------------------------
# Unknown-skill generic fallback
# ---------------------------------------------------------------------------

def test_unknown_skill_generic_fallback():
    # An unknown skill present but with no curated rules → MENTIONED; default
    # required depth APPLIED → mentioned-only.
    a = analyze_skill_depth(_cv(["Rust"]), _jd(["Rust"]))
    e = _entry(a, "Rust")
    assert e.candidate_depth == SkillDepth.MENTIONED
    assert e.required_depth == SkillDepth.APPLIED
    assert e.match_type == DepthMatchType.MENTIONED_ONLY


def test_unknown_skill_capped_at_applied_without_rules():
    # Even with strong-sounding claims, an unknown skill cannot exceed APPLIED.
    cv = _cv(["Rust"], responsibilities=["advanced expert production deployment"])
    e = _entry(analyze_skill_depth(cv, _jd(["Rust"])), "Rust")
    assert e.candidate_depth <= SkillDepth.APPLIED


# ---------------------------------------------------------------------------
# Anti-overconfidence
# ---------------------------------------------------------------------------

def test_proficiency_claim_alone_does_not_reach_advanced():
    # "advanced"/"expert" are claims (no ecosystem evidence) → clamped to APPLIED.
    cv = _cv(["Python"], prof={"Python": "advanced expert"})
    e = _entry(analyze_skill_depth(cv, _jd(["Python"])), "Python")
    assert e.candidate_depth <= SkillDepth.APPLIED
    assert e.candidate_depth < SkillDepth.ADVANCED


def test_years_only_lifts_to_basic_not_higher():
    cv = _cv(["Python"], years=8.0)  # lots of years, but no evidence
    e = _entry(analyze_skill_depth(cv, _jd(["Python"])), "Python")
    assert e.candidate_depth == SkillDepth.BASIC


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_deterministic_output():
    cv = _cv(["Python", "SQL"], technologies=["pandas", "docker"],
             responsibilities=["scikit-learn model training", "joins query"])
    jd = _jd(["Python", "SQL"], responsibilities=["Deploy and monitor Python models"])
    a1 = analyze_skill_depth(cv, jd)
    a2 = analyze_skill_depth(cv, jd)
    sig = lambda a: [
        (e.skill, e.candidate_depth, e.required_depth, e.match_type, e.depth_gap, tuple(e.evidence_labels))
        for e in a.entries
    ]
    assert sig(a1) == sig(a2)


# ---------------------------------------------------------------------------
# Privacy — curated labels only, no raw-sentence / PII leakage
# ---------------------------------------------------------------------------

def test_labels_only_no_raw_sentence_leakage():
    leak = "Built ML models with scikit-learn; contact john@example.com immediately"
    cv = _cv(["Python"], technologies=["pandas"], responsibilities=[leak])
    e = _entry(analyze_skill_depth(cv, _jd(["Python"])), "Python")
    # Curated evidence is surfaced…
    assert "scikit-learn" in e.evidence_labels
    # …but never the raw sentence or embedded PII.
    for label in e.evidence_labels:
        assert "@" not in label
        assert label != leak
    blob = " ".join([e.gap_explanation, e.recommendation, e.verification_prompt])
    assert "john@example.com" not in blob
    assert leak not in blob


# ---------------------------------------------------------------------------
# Access-control selector + no scoring change
# ---------------------------------------------------------------------------

def test_get_skill_depth_view_is_neutral_and_changes_no_score():
    payload = make_payload()
    before = payload.dimensional_analysis.composite_score_percentage
    analysis = get_skill_depth_view(payload)
    after = payload.dimensional_analysis.composite_score_percentage
    assert before == after                       # scoring untouched
    # Neutral object shape (no perspective text fields).
    assert hasattr(analysis, "entries")
    assert hasattr(analysis, "is_directional") and analysis.is_directional is True


def test_analyzer_does_not_import_scoring():
    import src.engine.skill_depth.analyzer as mod
    assert not hasattr(mod, "scoring")
    assert not hasattr(mod, "DimensionalAnalysis")
