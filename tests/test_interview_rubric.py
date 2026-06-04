# tests/test_interview_rubric.py
#
# Phase 24.3D — interview rubric / evaluation quality. Deterministic, no LLM,
# no network, no keys, no provider logic. Synthetic fake data only.

import re
from types import SimpleNamespace

from src.engine.interview.rubric import (
    DIMENSIONS,
    candidate_rubric_feedback,
    evaluate_rubric,
    recruiter_confidence_summary,
)

_ARMENIAN = re.compile(r"[Ա-֏]")
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")

_STRONG = (
    "At my previous company I led a migration of our billing service to Python and "
    "PostgreSQL. I redesigned the schema, added indexes, and reduced p95 latency by "
    "40% while cutting infra cost by 25%. I decided to batch writes because the trade-off "
    "favored throughput over latency for that workload."
)
_VAGUE = "I worked on some projects and did my best. It went well overall."
_GENERIC = "I am a hard worker and a team player with good communication and passion."
_IRRELEVANT = "My favourite hobby is hiking on weekends with my friends and family."
_SHORT = "Yes I did."


def _q(target="Python", kind="matched_skill"):
    return SimpleNamespace(target=target, kind=kind)


# ---------------------------------------------------------------------------
# Per-pattern evaluation
# ---------------------------------------------------------------------------

def test_strong_technical_answer():
    r = evaluate_rubric(_STRONG, _q())
    assert r.band == "strong"
    assert r.dimensions["practical_example"] >= 0.6
    assert r.dimensions["technical_correctness"] >= 0.5
    assert r.confidence_band in ("medium", "high")


def test_vague_answer_flagged():
    r = evaluate_rubric(_VAGUE, _q())
    assert r.band in ("weak", "adequate")
    assert "vague" in r.flags or "no_practical_example" in r.flags


def test_generic_memorized_answer_flagged():
    r = evaluate_rubric(_GENERIC, _q())
    assert "generic_memorized" in r.flags


def test_irrelevant_answer_flagged():
    r = evaluate_rubric(_IRRELEVANT, _q(target="Kubernetes"))
    assert "irrelevant" in r.flags or "does_not_address" in r.flags
    assert r.dimensions["relevance"] <= 0.4


def test_practical_example_detected():
    r = evaluate_rubric(_STRONG, _q())
    assert r.dimensions["practical_example"] >= 0.6
    assert "no_practical_example" not in r.flags


def test_missing_key_concept_flagged():
    r = evaluate_rubric("I built a web service and shipped it on time with the team.",
                        _q(target="Kubernetes", kind="missing_skill"))
    assert "missing_key_concept" in r.flags


def test_too_short_answer_flagged():
    r = evaluate_rubric(_SHORT, _q())
    assert "too_short_shallow" in r.flags
    assert r.confidence_band == "low"


# ---------------------------------------------------------------------------
# Bounded ranges + valid bands
# ---------------------------------------------------------------------------

def test_bounded_score_ranges():
    for ans in (_STRONG, _VAGUE, _GENERIC, _IRRELEVANT, _SHORT, ""):
        r = evaluate_rubric(ans, _q())
        assert 0.0 <= r.overall <= 1.0
        assert set(r.dimensions) == set(DIMENSIONS)
        for v in r.dimensions.values():
            assert 0.0 <= v <= 1.0
        assert r.band in ("strong", "adequate", "weak")


def test_valid_confidence_bands():
    for ans in (_STRONG, _VAGUE, _SHORT):
        assert evaluate_rubric(ans, _q()).confidence_band in ("low", "medium", "high")


# ---------------------------------------------------------------------------
# Recruiter summary
# ---------------------------------------------------------------------------

def test_recruiter_confidence_summary_generated():
    skills = SimpleNamespace(
        coverage_ratio=0.4,
        missing_critical=[SimpleNamespace(canonical_name="Kubernetes")],
    )
    view = {"skills_ontology": skills, "analysis_completeness_score": 0.8}
    summ = recruiter_confidence_summary(view, "en")
    assert summ["confidence_band"] in ("low", "medium", "high")
    assert any("Kubernetes" in s for s in summ["risk_signals"])
    assert summ["validate"] and len(summ["distinction"]) == 4


def test_recruiter_summary_avoids_overclaiming():
    view = {"skills_ontology": SimpleNamespace(coverage_ratio=0.9, missing_critical=[]),
            "analysis_completeness_score": 0.95}
    summ = recruiter_confidence_summary(view, "en")
    blob = " ".join([summ["confidence_band"]] + summ["validate"] + list(summ["distinction"].values())).lower()
    for bad in ("definitely", "proves", "guaranteed", "certainly good", "certainly bad"):
        assert bad not in blob


# ---------------------------------------------------------------------------
# Localization
# ---------------------------------------------------------------------------

def test_armenian_localized_feedback():
    fb = candidate_rubric_feedback(evaluate_rubric(_VAGUE, _q()), _q(), "hy")
    assert _ARMENIAN.search(fb["better_answer"])
    assert _ARMENIAN.search(fb["learning_focus"])
    assert _ARMENIAN.search(fb["follow_up"])
    assert fb["improvements"] and all(_ARMENIAN.search(x) for x in fb["improvements"])


def test_russian_localized_feedback():
    fb = candidate_rubric_feedback(evaluate_rubric(_VAGUE, _q()), _q(), "ru")
    assert _CYRILLIC.search(fb["better_answer"])
    assert _CYRILLIC.search(fb["follow_up"])
    summ = recruiter_confidence_summary(
        {"skills_ontology": SimpleNamespace(coverage_ratio=0.3,
                                            missing_critical=[SimpleNamespace(canonical_name="SQL")]),
         "analysis_completeness_score": 0.7}, "ru")
    assert _CYRILLIC.search(summ["validate"][0])
    assert any(_CYRILLIC.search(s) for s in summ["risk_signals"])


def test_missing_lang_falls_back_to_english():
    fb_en = candidate_rubric_feedback(evaluate_rubric(_VAGUE, _q()), _q(), "en")
    fb_zz = candidate_rubric_feedback(evaluate_rubric(_VAGUE, _q()), _q(), "zz")
    assert fb_en["better_answer"] == fb_zz["better_answer"]


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------

def test_no_secret_or_prompt_leakage():
    for lang in ("en", "hy", "ru"):
        fb = candidate_rubric_feedback(evaluate_rubric(_STRONG, _q()), _q(), lang)
        blob = " ".join([fb["better_answer"], fb["learning_focus"], fb["follow_up"]]
                        + fb["strengths"] + fb["improvements"]).lower()
        for bad in ("sk-", "api_key", "openai", "gemini", "system prompt", "traceback"):
            assert bad not in blob
