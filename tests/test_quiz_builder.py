# tests/test_quiz_builder.py
#
# Deterministic quiz-builder tests. No LLM, no network.

from src.engine.access_control import get_candidate_view
from src.engine.quiz.models import Focus
from src.engine.quiz.quiz_builder import build_candidate_quiz

from tests._payload_factory import RED_FLAG_TEXT, make_payload


def test_quiz_built_from_candidate_view():
    view = get_candidate_view(make_payload())
    quiz = build_candidate_quiz(view)
    assert 1 <= quiz.total() <= 8
    targets = {q.target for q in quiz.questions}
    focuses = {q.focus for q in quiz.questions}
    assert "Kubernetes" in targets            # missing critical → scenario question
    assert "Python" in targets                # matched skill → validation question
    assert Focus.MISSING_SKILL in focuses
    assert Focus.MATCHED_SKILL in focuses
    assert len(quiz.answers) == quiz.total()
    assert all(a is None for a in quiz.answers)


def test_weak_dimension_questions_included():
    view = {
        "role_title": "Backend Engineer",
        "required_seniority": "mid",
        "missing_critical": [], "matched_skills": [],
        "dimensional_scores": {"technical_skills_match": 0.2, "domain_knowledge": 0.3},
    }
    quiz = build_candidate_quiz(view)
    assert any(q.focus == Focus.WEAK_DIMENSION for q in quiz.questions)


def test_quiz_is_deterministic():
    view = get_candidate_view(make_payload())
    a = build_candidate_quiz(view)
    b = build_candidate_quiz(view)
    assert [q.qid for q in a.questions] == [q.qid for q in b.questions]
    assert [q.correct_index for q in a.questions] == [q.correct_index for q in b.questions]


def test_empty_view_still_produces_quiz():
    quiz = build_candidate_quiz({})
    assert quiz.total() >= 1
    assert all(q.is_valid() for q in quiz.questions)


def test_privacy_no_recruiter_content_in_quiz():
    view = get_candidate_view(make_payload())
    quiz = build_candidate_quiz(view)
    blob = " ".join(
        q.stem + " " + " ".join(q.options) + " " + q.explanation + " " + q.study_tip
        for q in quiz.questions
    ).lower()
    assert RED_FLAG_TEXT.lower() not in blob
    assert "walk through a rollout you managed on kubernetes" not in blob  # recruiter VP text
    assert "hire recommendation" not in blob
    # Candidate view never carried recruiter-only keys.
    assert "recruiter_perspective" not in view
    assert "hire_recommendation" not in view
