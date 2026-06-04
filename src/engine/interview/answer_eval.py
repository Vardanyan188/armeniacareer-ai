# src/engine/interview/answer_eval.py
#
# Deterministic interview-answer evaluation (no LLM, no network).
# Scores three axes — Structure, Relevance, Specificity — and returns
# supportive-but-realistic feedback. Extension seam: an optional LLM layer could
# later refine `feedback`/`improvement_tips` without changing this contract.

from __future__ import annotations

import re
from typing import List

from src.engine.adapters import MVP_SKILL_ALIASES
from src.engine.interview.models import AnswerEvaluation, InterviewQuestion

# STAR cue vocabularies (lowercased).
_SITUATION = ("when", "at ", "during", "project", "team", "company", "role", "faced", "situation")
_TASK = ("needed to", "had to", "goal", "responsible", "task", "objective", "my job", "asked to")
_ACTION = ("i ", "we ", "implemented", "built", "designed", "developed", "led", "created",
           "used", "wrote", "configured", "decided", "migrated", "optimized", "automated")
_RESULT = ("result", "outcome", "improved", "reduced", "increased", "achieved", "delivered",
           "saved", "grew", "%", "faster", "boosted")

_TOOL_NAMES = {name.lower() for name in MVP_SKILL_ALIASES}

_MIN_MEANINGFUL_WORDS = 4

_W_STRUCTURE = 0.30
_W_RELEVANCE = 0.40
_W_SPECIFICITY = 0.30


def _clamp10(v: float) -> int:
    return int(max(0, min(10, round(v))))


def _structure_score(low: str, word_count: int) -> int:
    cats = [
        any(c in low for c in _SITUATION),
        any(c in low for c in _TASK),
        any(c in low for c in _ACTION),
        any(c in low for c in _RESULT),
    ]
    score = sum(cats) * 2          # 0..8
    if word_count >= 30:
        score += 2                 # rewards a developed answer
    return _clamp10(score)


def _relevance_score(low: str, target: str) -> int:
    target_l = (target or "").lower().strip()
    if target_l and target_l in low:
        return 9
    tokens = [t for t in re.split(r"[^a-z0-9+#.]+", target_l) if len(t) > 2]
    if tokens and any(t in low for t in tokens):
        return 6
    # Generic relevance: some role/work vocabulary present.
    if any(w in low for w in ("project", "experience", "role", "system", "data", "team", "code")):
        return 4
    return 2


def _specificity_score(answer: str, low: str) -> int:
    score = 0
    if re.search(r"\d", answer):
        score += 4
    if "%" in answer:
        score += 2
    tool_hits = sum(1 for name in _TOOL_NAMES if name in low)
    score += min(tool_hits, 2) * 2     # 0..4
    return _clamp10(score)


def evaluate_answer(question: InterviewQuestion, answer: str) -> AnswerEvaluation:
    """Scores an answer deterministically. Never raises."""
    answer = answer or ""
    low = answer.lower()
    words = answer.split()
    word_count = len(words)
    target = getattr(question, "target", "") or ""

    # Empty / trivially short answers.
    if word_count < _MIN_MEANINGFUL_WORDS:
        return AnswerEvaluation(
            structure=1,
            relevance=_relevance_score(low, target) if word_count else 0,
            specificity=0,
            overall_pct=10.0,
            band="weak",
            feedback=(
                "The answer is empty or very short. Describe a concrete example: "
                "what the situation was, what you did, and what the outcome was."
            ),
            improvement_tips=[
                "Use the STAR structure: Situation, Task, Action, Result.",
                f"Tie your answer directly to {target}." if target else
                "Focus on a specific, relevant example.",
            ],
        )

    structure = _structure_score(low, word_count)
    relevance = _relevance_score(low, target)
    specificity = _specificity_score(answer, low)

    overall = (
        structure * _W_STRUCTURE
        + relevance * _W_RELEVANCE
        + specificity * _W_SPECIFICITY
    ) * 10
    overall_pct = round(overall, 1)

    if overall_pct >= 70:
        band = "strong"
    elif overall_pct >= 45:
        band = "adequate"
    else:
        band = "weak"

    tips: List[str] = []
    if structure < 6:
        tips.append("Use the STAR structure: Situation, Task, Action, Result.")
    if relevance < 6:
        tips.append(f"Tie your answer directly to {target}." if target
                    else "Keep the answer focused on the question's topic.")
    if specificity < 6:
        tips.append("Add concrete details: numbers, tools used, and the outcome you achieved.")

    if band == "strong":
        feedback = (
            "Strong answer — it is well structured and backed with specifics. "
            "Keep this level of concrete detail in your other examples."
        )
    elif band == "adequate":
        feedback = (
            "A reasonable answer with a solid foundation. Tightening the points "
            "below will make it noticeably more convincing."
        )
    else:
        feedback = (
            "This answer needs more substance to be convincing, but it is a fine "
            "starting point. Work through the suggestions below and try again."
        )

    return AnswerEvaluation(
        structure=structure,
        relevance=relevance,
        specificity=specificity,
        overall_pct=overall_pct,
        band=band,
        feedback=feedback,
        improvement_tips=tips,
    )
