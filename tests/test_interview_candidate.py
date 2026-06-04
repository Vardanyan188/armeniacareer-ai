# tests/test_interview_candidate.py
#
# Deterministic candidate interview practice tests. No LLM, no network.

from src.engine.access_control import get_candidate_view
from src.engine.interview.candidate_practice import (
    build_candidate_interview,
    current_prompt,
    submit_answer,
)
from src.engine.interview.models import QuestionKind

from tests._payload_factory import MOTIVATION_TEXT, RED_FLAG_TEXT, make_payload

_STRONG = (
    "At my last company I led a project where I used Python and Docker to build a service. "
    "The task was to cut deployment time; I designed the pipeline and as a result we reduced "
    "it by 50% and saved 8 hours per week."
)
_WEAK = "I know it a bit."


def test_queue_built_from_candidate_view():
    view = get_candidate_view(make_payload())
    state = build_candidate_interview(view)
    assert len(state.queue) >= 2
    kinds = {q.kind for q in state.queue}
    targets = {q.target for q in state.queue}
    assert QuestionKind.MISSING_SKILL in kinds   # Kubernetes missing
    assert QuestionKind.MATCHED_SKILL in kinds   # Python matched
    assert "Kubernetes" in targets and "Python" in targets
    assert state.queue[-1].kind == QuestionKind.GENERAL


def test_weak_dimension_questions_added():
    view = {
        "role_title": "Backend Engineer",
        "required_seniority": "mid",
        "missing_critical": [], "matched_skills": [],
        "missing_preferred": [], "transferable": [],
        "dimensional_scores": {
            "technical_skills_match": 0.2,
            "experience_depth_alignment": 0.3,
            "domain_knowledge": 0.8,
        },
    }
    state = build_candidate_interview(view)
    assert any(q.kind == QuestionKind.WEAK_DIMENSION for q in state.queue)


def test_weak_answer_triggers_non_advancing_followup():
    state = build_candidate_interview(get_candidate_view(make_payload()))
    start_index = state.index
    evaluation, follow = submit_answer(state, _WEAK)
    assert evaluation.band == "weak"
    assert follow.advances is False
    assert follow.reason            # explains the weakness
    assert state.index == start_index          # stayed on same question
    assert state.active_followup == follow.text


def test_strong_answer_advances():
    state = build_candidate_interview(get_candidate_view(make_payload()))
    start_index = state.index
    evaluation, follow = submit_answer(state, _STRONG)
    assert evaluation.overall_pct > 45
    assert follow.advances is True
    assert state.index == start_index + 1


def test_followup_used_once_then_advances():
    state = build_candidate_interview(get_candidate_view(make_payload()))
    submit_answer(state, _WEAK)                 # non-advancing follow-up
    idx_after_first = state.index
    _, follow2 = submit_answer(state, _WEAK)    # second weak answer must advance
    assert follow2.advances is True
    assert state.index == idx_after_first + 1


def test_session_caps_and_finishes():
    state = build_candidate_interview(get_candidate_view(make_payload()))
    guard = 0
    while not state.finished and guard < 50:
        submit_answer(state, _STRONG)
        guard += 1
    assert state.finished is True
    assert current_prompt(state) is None


def test_privacy_no_recruiter_content_in_questions():
    view = get_candidate_view(make_payload())
    state = build_candidate_interview(view)
    blob = " ".join(q.text + " " + q.rationale for q in state.queue).lower()
    assert RED_FLAG_TEXT.lower() not in blob
    # The recruiter's verification question text must not appear in candidate prompts.
    assert "walk through a rollout you managed on kubernetes" not in blob
    assert "hire recommendation" not in blob
    # Candidate view never carried recruiter-only keys in the first place.
    assert "recruiter_perspective" not in view
    assert "hire_recommendation" not in view
    # Motivational framing belongs to the candidate; it is fine that it's allowed,
    # but it must not leak into the (separate) interview question text.
    assert MOTIVATION_TEXT.lower() not in blob
