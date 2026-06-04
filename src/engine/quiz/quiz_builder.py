# src/engine/quiz/quiz_builder.py
#
# Deterministic Candidate Skill Quiz builder (no LLM, no network).
#
# Reads ONLY candidate-facing data (the dict from access_control.get_candidate_view),
# so recruiter perspective, hire recommendation, verification points, and red
# flags can never enter the quiz by construction.

from __future__ import annotations

from typing import Any, Dict, List

from src.engine.quiz.models import Focus, QuizQuestion, QuizState
from src.engine.quiz.question_bank import (
    make_dimension_mcq,
    make_missing_skill_scenario,
    make_skill_mcq,
)

_MAX_MISSING = 3
_MAX_WEAK_DIMS = 2
_MAX_MATCHED = 3
_MAX_TOTAL = 8
_WEAK_DIM_THRESHOLD = 0.5


def _names(entries: List[Any]) -> List[str]:
    out: List[str] = []
    for e in entries or []:
        name = getattr(e, "canonical_name", None) or getattr(e, "skill_name", None)
        if name and name not in out:
            out.append(name)
    return out


def _seniority_str(value: Any) -> str:
    return str(getattr(value, "value", value) or "mid").lower()


def build_candidate_quiz(
    candidate_view: Dict[str, Any], source: str = "deterministic",
) -> QuizState:
    """
    Builds a prioritized, deterministic quiz from candidate-facing data only.
    `source` is an extension seam ("deterministic" today; a future "llm" path
    could populate equivalent QuizQuestion objects without changing the contract).
    """
    role_title = candidate_view.get("role_title", "this role")
    seniority = _seniority_str(candidate_view.get("required_seniority"))

    missing = _names(candidate_view.get("missing_critical", []))[:_MAX_MISSING]
    matched = _names(candidate_view.get("matched_skills", []))[:_MAX_MATCHED]

    dim_scores: Dict[str, float] = candidate_view.get("dimensional_scores", {}) or {}
    weak_dims = sorted(
        (k for k, v in dim_scores.items() if v < _WEAK_DIM_THRESHOLD),
        key=lambda k: dim_scores.get(k, 1.0),
    )[:_MAX_WEAK_DIMS]

    questions: List[QuizQuestion] = []

    # 1) Missing critical skills → best-approach scenario MCQs.
    for i, skill in enumerate(missing):
        questions.append(make_missing_skill_scenario(skill, qid=f"missing:{skill}:{i}"))

    # 2) Weak dimensions → dimension MCQs.
    for i, dim in enumerate(weak_dims):
        questions.append(make_dimension_mcq(dim, qid=f"weakdim:{dim}:{i}"))

    # 3) Matched skills → knowledge validation MCQs.
    for i, skill in enumerate(matched):
        questions.append(make_skill_mcq(skill, Focus.MATCHED_SKILL, qid=f"matched:{skill}:{i}"))

    # Fallback: always produce at least a couple of questions.
    if not questions:
        questions.append(make_dimension_mcq("technical_skills_match", qid="weakdim:general:0"))
        questions.append(make_skill_mcq("Python", Focus.MATCHED_SKILL, qid="matched:Python:0"))

    questions = questions[:_MAX_TOTAL]

    return QuizState(
        role_title=role_title,
        seniority=seniority,
        questions=questions,
        answers=[None] * len(questions),
    )
