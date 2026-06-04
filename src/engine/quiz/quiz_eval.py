# src/engine/quiz/quiz_eval.py
#
# Deterministic grading + summary for the Candidate Skill Quiz (no LLM, no network).
# Feedback is constructive and educational — never shaming.

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from src.engine.quiz.models import Focus, QuizQuestion, QuizState, QuizSummary

TARGET_SCORE = 60          # %
_STRONG_BAND = 80
_SOLID_BAND = 60


@dataclass
class GradeResult:
    is_correct: bool
    correct_index: int
    correct_option: str
    feedback: str
    study_tip: str


def grade_question(question: QuizQuestion, selected_index: Optional[int]) -> GradeResult:
    """Grades one answer. Out-of-range / None selections count as incorrect."""
    options = question.options
    valid = selected_index is not None and 0 <= selected_index < len(options)
    is_correct = bool(valid and selected_index == question.correct_index)
    correct_option = options[question.correct_index]

    if is_correct:
        feedback = f"Correct — {question.explanation}"
    elif valid:
        feedback = (
            f"Not quite. The strongest answer is: \"{correct_option}\". "
            f"{question.explanation} Your choice reflects a weaker approach with less concrete evidence."
        )
    else:
        feedback = (
            f"No answer selected. The strongest answer is: \"{correct_option}\". "
            f"{question.explanation}"
        )

    return GradeResult(
        is_correct=is_correct,
        correct_index=question.correct_index,
        correct_option=correct_option,
        feedback=feedback,
        study_tip=question.study_tip,
    )


def _dedupe(seq: List[str]) -> List[str]:
    out: List[str] = []
    for s in seq:
        if s and s not in out:
            out.append(s)
    return out


def summarize_quiz(state: QuizState) -> QuizSummary:
    """Computes score, supportive band, weak areas, and a prioritized study list."""
    total = state.total()
    correct = state.correct_count()
    score_pct = round((correct / total) * 100, 1) if total else 0.0

    if score_pct >= _STRONG_BAND:
        band = "strong"
        band_message = (
            "Strong preparation — you clearly understand these areas. Keep reinforcing "
            "them with real projects and you'll interview with confidence."
        )
    elif score_pct >= _SOLID_BAND:
        band = "solid"
        band_message = (
            "Solid foundation. A bit more targeted practice on the areas below will get "
            "you interview-ready."
        )
    else:
        band = "keep_building"
        band_message = (
            "A good starting point. Focus on the study list below and try again — real "
            "improvement here is very achievable."
        )

    incorrect = [
        q for q, a in zip(state.questions, state.answers)
        if a is None or a != q.correct_index
    ]
    weak_areas = _dedupe([q.target for q in incorrect])

    wrong_missing = [q.target for q in incorrect if q.focus == Focus.MISSING_SKILL]
    all_missing = [q.target for q in state.questions if q.focus == Focus.MISSING_SKILL]
    wrong_dims = [q.target for q in incorrect if q.focus == Focus.WEAK_DIMENSION]

    study_next = _dedupe(wrong_missing + all_missing + wrong_dims)

    return QuizSummary(
        total=total,
        correct=correct,
        score_pct=score_pct,
        band=band,
        band_message=band_message,
        weak_areas=weak_areas,
        study_next=study_next,
    )
