# tests/test_quiz_eval.py
#
# Deterministic quiz grading + summary tests. No LLM, no network.

from src.engine.access_control import get_candidate_view
from src.engine.quiz.quiz_builder import build_candidate_quiz
from src.engine.quiz.quiz_eval import grade_question, summarize_quiz

from tests._payload_factory import make_payload


def _quiz():
    return build_candidate_quiz(get_candidate_view(make_payload()))


def test_correct_answer_graded_correct():
    quiz = _quiz()
    q = quiz.questions[0]
    res = grade_question(q, q.correct_index)
    assert res.is_correct is True
    assert "correct" in res.feedback.lower()


def test_incorrect_answer_graded_with_constructive_feedback():
    quiz = _quiz()
    q = quiz.questions[0]
    wrong = (q.correct_index + 1) % len(q.options)
    res = grade_question(q, wrong)
    assert res.is_correct is False
    assert q.options[q.correct_index] in res.feedback     # shows the strong answer
    assert res.study_tip                                  # offers guidance
    # No shaming language.
    low = res.feedback.lower()
    for bad in ("stupid", "dumb", "idiot", "failure", "pathetic"):
        assert bad not in low


def test_out_of_range_and_none_are_incorrect_not_raising():
    quiz = _quiz()
    q = quiz.questions[0]
    assert grade_question(q, None).is_correct is False
    assert grade_question(q, 999).is_correct is False


def test_all_correct_scores_higher_than_all_wrong():
    quiz_a = _quiz()
    for i, q in enumerate(quiz_a.questions):
        quiz_a.answers[i] = q.correct_index
    quiz_a.finished = True
    sa = summarize_quiz(quiz_a)

    quiz_b = _quiz()
    for i, q in enumerate(quiz_b.questions):
        quiz_b.answers[i] = (q.correct_index + 1) % len(q.options)
    quiz_b.finished = True
    sb = summarize_quiz(quiz_b)

    assert sa.score_pct > sb.score_pct
    assert sa.score_pct == 100.0
    assert sa.band == "strong"
    assert sb.band == "keep_building"


def test_study_next_prioritizes_missing_and_weak_areas():
    quiz = _quiz()
    # Answer everything wrong → study list should include the missing skill (Kubernetes).
    for i, q in enumerate(quiz.questions):
        quiz.answers[i] = (q.correct_index + 1) % len(q.options)
    quiz.finished = True
    summary = summarize_quiz(quiz)
    assert summary.study_next
    assert "Kubernetes" in summary.study_next
    assert summary.weak_areas


def test_band_messages_are_supportive():
    quiz = _quiz()
    for i, q in enumerate(quiz.questions):
        quiz.answers[i] = (q.correct_index + 1) % len(q.options)
    quiz.finished = True
    summary = summarize_quiz(quiz)
    low = summary.band_message.lower()
    assert "achievable" in low or "starting point" in low   # encouraging
    for bad in ("stupid", "dumb", "failure", "hopeless"):
        assert bad not in low
