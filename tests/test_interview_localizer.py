# tests/test_interview_localizer.py
#
# Phase 24.3C — multilingual interview localizer. Deterministic, no LLM, no
# network, no API keys, no provider logic. Synthetic fake data only.

import re

from src.engine.interview.localizer import (
    localize_band,
    localize_candidate_question,
    localize_followup,
    localize_verification,
)
from src.engine.interview.models import (
    InterviewQuestion,
    QuestionKind,
    VerificationQuestion,
)

_ARMENIAN = re.compile(r"[Ա-֏]")
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def _q(kind, target):
    return InterviewQuestion(text="english placeholder", kind=kind, target=target)


# ---------------------------------------------------------------------------
# Candidate question generation per language
# ---------------------------------------------------------------------------

def test_english_question_generation():
    out = localize_candidate_question(_q(QuestionKind.MATCHED_SKILL, "Python"), "en")
    assert "Python" in out and out.strip()


def test_armenian_question_uses_armenian_script():
    out = localize_candidate_question(_q(QuestionKind.MATCHED_SKILL, "Python"), "hy")
    assert out.strip()
    assert _ARMENIAN.search(out)            # natural Armenian, not English
    assert "Python" in out


def test_russian_question_uses_cyrillic():
    out = localize_candidate_question(_q(QuestionKind.MISSING_SKILL, "SQL"), "ru")
    assert out.strip()
    assert _CYRILLIC.search(out)
    assert "SQL" in out


def test_weak_dimension_question_localized():
    for lang, pat in (("hy", _ARMENIAN), ("ru", _CYRILLIC)):
        out = localize_candidate_question(_q(QuestionKind.WEAK_DIMENSION, "Technical Skills"), lang)
        assert out.strip() and pat.search(out)


def test_unknown_dimension_falls_back_to_generic():
    out = localize_candidate_question(_q(QuestionKind.WEAK_DIMENSION, "Nonexistent Dim"), "hy")
    assert out.strip() and _ARMENIAN.search(out)


# ---------------------------------------------------------------------------
# Deterministic + safe (no keys, no leaks)
# ---------------------------------------------------------------------------

def test_deterministic_without_keys(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    q = _q(QuestionKind.MATCHED_SKILL, "Docker")
    assert localize_candidate_question(q, "hy") == localize_candidate_question(q, "hy")


def test_no_provider_or_prompt_leakage():
    for lang in ("en", "hy", "ru"):
        out = localize_candidate_question(_q(QuestionKind.GENERAL, ""), lang)
        low = out.lower()
        for bad in ("sk-", "api_key", "openai", "gemini", "system prompt", "traceback"):
            assert bad not in low


def test_missing_lang_falls_back_to_english():
    out = localize_candidate_question(_q(QuestionKind.MATCHED_SKILL, "Python"), "zz")
    assert out == localize_candidate_question(_q(QuestionKind.MATCHED_SKILL, "Python"), "en")


# ---------------------------------------------------------------------------
# Candidate vs recruiter distinction
# ---------------------------------------------------------------------------

def test_candidate_and_recruiter_questions_differ():
    cand = localize_candidate_question(_q(QuestionKind.MATCHED_SKILL, "Python"), "en")
    vq = VerificationQuestion(question="x", importance="recommended", target="Python")
    rec = localize_verification(vq, "en")
    # Candidate is asked directly ("you"); recruiter is told to "ask the candidate".
    assert "ask the candidate" in rec["question"].lower()
    assert rec["question"] != cand
    assert rec["strong"] and rec["weak"] and rec["followups"]


def test_recruiter_gap_vs_verify_categories():
    gap = localize_verification(
        VerificationQuestion(question="x", importance="must_ask", target="Kubernetes"), "en")
    verify = localize_verification(
        VerificationQuestion(question="x", importance="recommended", target="Kubernetes"), "en")
    assert "required but not evident" in gap["question"].lower()
    assert "ask the candidate to describe" in verify["question"].lower()
    assert gap["question"] != verify["question"]


def test_recruiter_localized_armenian():
    vq = VerificationQuestion(question="x", importance="must_ask", target="Docker")
    loc = localize_verification(vq, "hy")
    assert _ARMENIAN.search(loc["question"])
    assert all(_ARMENIAN.search(s) for s in loc["strong"])
    assert "Docker" in loc["question"]


# ---------------------------------------------------------------------------
# Adaptation + safe defaults
# ---------------------------------------------------------------------------

def test_questions_adapt_to_skill():
    a = localize_candidate_question(_q(QuestionKind.MISSING_SKILL, "Kafka"), "en")
    b = localize_candidate_question(_q(QuestionKind.MISSING_SKILL, "Airflow"), "en")
    assert "Kafka" in a and "Airflow" in b and a != b


def test_missing_data_still_safe():
    # Empty target / general kind must still return a useful, non-empty question.
    out = localize_candidate_question(_q(QuestionKind.GENERAL, ""), "ru")
    assert out.strip() and _CYRILLIC.search(out)


def test_followup_and_band_localized():
    fu = localize_followup("Can you give a concrete example — with numbers, tools, and the outcome?",
                           "Python", "hy")
    assert _ARMENIAN.search(fu)
    assert _ARMENIAN.search(localize_band("strong", "hy"))
    assert _CYRILLIC.search(localize_band("weak", "ru"))
    # Unknown follow-up text returned unchanged.
    assert localize_followup("custom unmatched text", "x", "hy") == "custom unmatched text"
