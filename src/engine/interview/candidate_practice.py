# src/engine/interview/candidate_practice.py
#
# Deterministic Candidate Interview Practice (no LLM, no network).
#
# Reads ONLY candidate-facing data (the dict from access_control.get_candidate_view),
# so hire recommendation, recruiter verification points, and red flags can never
# enter the question set by construction.

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from src.engine.interview.answer_eval import evaluate_answer
from src.engine.interview.models import (
    AnswerEvaluation,
    CandidateInterviewState,
    FollowUp,
    InterviewQuestion,
    QuestionKind,
)

_MAX_MISSING = 3
_MAX_WEAK_DIMS = 2
_MAX_MATCHED = 2
_WEAK_DIM_THRESHOLD = 0.5

_DIMENSION_QUESTIONS: Dict[str, str] = {
    "technical_skills_match":
        "Walk me through the most technically challenging problem you solved recently and how you approached it.",
    "experience_depth_alignment":
        "Tell me about the most complex project you owned end to end — your role and the result.",
    "educational_relevance":
        "How has your education or self-learning prepared you for this role's core tasks?",
    "domain_knowledge":
        "What do you understand about this role's industry or domain, and how did you build that understanding?",
    "soft_skills_signals":
        "Describe a time you handled a disagreement or a difficult collaboration on a team.",
    "seniority_trajectory":
        "What scope of responsibility have you held, and how has it grown over time?",
    "semantic_contextual_alignment":
        "Why are you a fit for this specific role? Use concrete examples from your experience.",
}

_DIMENSION_LABELS: Dict[str, str] = {
    "technical_skills_match": "Technical Skills",
    "experience_depth_alignment": "Experience Depth",
    "educational_relevance": "Education",
    "domain_knowledge": "Domain Knowledge",
    "soft_skills_signals": "Soft Skills",
    "seniority_trajectory": "Seniority Fit",
    "semantic_contextual_alignment": "Contextual Alignment",
}


def _names(entries: List[Any]) -> List[str]:
    out: List[str] = []
    for e in entries or []:
        name = getattr(e, "canonical_name", None) or getattr(e, "skill_name", None)
        if name and name not in out:
            out.append(name)
    return out


def _seniority_str(value: Any) -> str:
    return str(getattr(value, "value", value) or "mid").lower()


def _missing_skill_q(skill: str, senior: bool) -> InterviewQuestion:
    tail = (" Include the design trade-offs you would weigh."
            if senior else " Describe how you would get up to speed quickly.")
    return InterviewQuestion(
        text=(f"This role expects {skill}, which isn't evident in your CV. Have you used it "
              f"or something similar, and how would you approach a task involving it?{tail}"),
        kind=QuestionKind.MISSING_SKILL,
        target=skill,
        rationale=f"{skill} is a required skill not detected in your CV.",
    )


def _matched_skill_q(skill: str) -> InterviewQuestion:
    return InterviewQuestion(
        text=(f"Walk me through a project where you applied {skill}. What was your specific "
              f"contribution and the measurable outcome?"),
        kind=QuestionKind.MATCHED_SKILL,
        target=skill,
        rationale=f"{skill} appears in your CV — be ready to back it with evidence.",
    )


def _weak_dim_q(dim_key: str) -> InterviewQuestion:
    return InterviewQuestion(
        text=_DIMENSION_QUESTIONS.get(dim_key, _DIMENSION_QUESTIONS["technical_skills_match"]),
        kind=QuestionKind.WEAK_DIMENSION,
        target=_DIMENSION_LABELS.get(dim_key, dim_key),
        rationale="This competency scored lower in your analysis.",
    )


def build_candidate_interview(candidate_view: Dict[str, Any]) -> CandidateInterviewState:
    """Builds a prioritized practice queue from candidate-facing data only."""
    role_title = candidate_view.get("role_title", "this role")
    seniority = _seniority_str(candidate_view.get("required_seniority"))
    senior = seniority in {"senior", "lead", "principal", "executive"}

    missing = _names(candidate_view.get("missing_critical", []))[:_MAX_MISSING]
    matched = _names(candidate_view.get("matched_skills", []))[:_MAX_MATCHED]

    dim_scores: Dict[str, float] = candidate_view.get("dimensional_scores", {}) or {}
    weak_dims = sorted(
        (k for k, v in dim_scores.items() if v < _WEAK_DIM_THRESHOLD),
        key=lambda k: dim_scores.get(k, 1.0),
    )[:_MAX_WEAK_DIMS]

    queue: List[InterviewQuestion] = []
    queue += [_missing_skill_q(s, senior) for s in missing]
    queue += [_weak_dim_q(d) for d in weak_dims]
    queue += [_matched_skill_q(s) for s in matched]
    queue.append(InterviewQuestion(
        text="Tell me about a professional achievement you are proud of, and why it mattered.",
        kind=QuestionKind.GENERAL,
        target="general experience",
        rationale="A closing behavioral question.",
    ))

    return CandidateInterviewState(
        role_title=role_title,
        seniority=seniority,
        queue=queue,
        max_rounds=min(8, len(queue) + 2),
    )


def current_question(state: CandidateInterviewState) -> Optional[InterviewQuestion]:
    return state.current_question()


def current_prompt(state: CandidateInterviewState) -> Optional[str]:
    """The text to show: an active follow-up if present, else the queued question."""
    if state.active_followup:
        return state.active_followup
    q = state.current_question()
    return q.text if q else None


def _deeper_followup(target: str, evaluation: AnswerEvaluation) -> Optional[FollowUp]:
    """Returns a non-advancing follow-up for the weakest axis, or None if strong."""
    if evaluation.band == "strong":
        return None
    if evaluation.specificity < 5:
        return FollowUp(
            text="Can you give a concrete example — with numbers, tools, and the outcome?",
            reason="low specificity", advances=False)
    if evaluation.relevance < 5:
        return FollowUp(
            text=f"Let's focus specifically on {target}: describe one concrete example.",
            reason="low relevance", advances=False)
    if evaluation.structure < 5:
        return FollowUp(
            text="Re-tell that using STAR: Situation, Task, Action, Result.",
            reason="weak structure", advances=False)
    return None


def submit_answer(
    state: CandidateInterviewState, answer: str,
) -> Tuple[AnswerEvaluation, FollowUp]:
    """
    Evaluates the answer to the current question, records history, and returns
    (evaluation, follow_up). A non-advancing follow-up deepens the same question
    once; otherwise the session advances to the next queued question.
    """
    question = state.current_question()
    if question is None:
        state.finished = True
        return (
            evaluate_answer(InterviewQuestion("", QuestionKind.GENERAL, ""), answer),
            FollowUp(text="", reason="", advances=True),
        )

    evaluation = evaluate_answer(question, answer)
    state.rounds += 1

    already_followed = state.index in state.followed_up_indices
    deeper = None if already_followed else _deeper_followup(question.target, evaluation)

    if deeper is not None and state.rounds < state.max_rounds:
        state.active_followup = deeper.text
        state.followed_up_indices.append(state.index)
        follow = deeper
    else:
        # Advance to the next queued question.
        state.active_followup = None
        state.index += 1
        follow = FollowUp(text="", reason="", advances=True)

    state.history.append({
        "question": (state.active_followup if not follow.advances else question.text),
        "prompt_shown": question.text if not already_followed else state.active_followup,
        "answer": answer,
        "evaluation": evaluation,
        "follow_up": follow,
    })

    if state.index >= len(state.queue) or state.rounds >= state.max_rounds:
        state.finished = True

    return evaluation, follow
