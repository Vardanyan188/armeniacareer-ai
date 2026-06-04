# tests/test_interview_recruiter.py
#
# Deterministic recruiter verification guide tests. No LLM, no network.

from src.engine.access_control import get_recruiter_view
from src.engine.interview.recruiter_verification import build_recruiter_verification_guide

from tests._payload_factory import MOTIVATION_TEXT, make_payload


def _guide():
    return build_recruiter_verification_guide(get_recruiter_view(make_payload()))


def test_guide_has_questions_with_full_structure():
    guide = _guide()
    assert guide.questions
    for q in guide.questions:
        assert q.question
        assert q.strong_answer_contains      # what a strong answer should contain
        assert q.weak_answer_indicates       # what weak/unclear answers may indicate
        assert q.suggested_followups         # suggested follow-ups
        assert q.importance in {"must_ask", "recommended", "optional"}


def test_guide_includes_missing_skill_must_ask():
    guide = _guide()
    targets = {q.target for q in guide.questions}
    assert "Kubernetes" in targets           # missing critical skill probed
    must_ask = [q for q in guide.questions if q.importance == "must_ask"]
    assert must_ask


def test_guide_includes_matched_skill_verification():
    guide = _guide()
    targets = {q.target for q in guide.questions}
    assert "Python" in targets               # matched skill verification


def test_guide_sorted_by_importance():
    guide = _guide()
    ranks = {"must_ask": 0, "recommended": 1, "optional": 2}
    seq = [ranks[q.importance] for q in guide.questions]
    assert seq == sorted(seq)


def test_privacy_no_candidate_coaching_in_guide():
    view = get_recruiter_view(make_payload())
    guide = build_recruiter_verification_guide(view)
    blob = " ".join(
        q.question + " " + " ".join(q.strong_answer_contains)
        + " " + " ".join(q.weak_answer_indicates)
        + " " + " ".join(q.suggested_followups)
        for q in guide.questions
    ).lower()
    assert MOTIVATION_TEXT.lower() not in blob
    assert "roadmap" not in blob
    assert "motivational" not in blob
    # Recruiter view never carried candidate coaching in the first place.
    assert "candidate_perspective" not in view
