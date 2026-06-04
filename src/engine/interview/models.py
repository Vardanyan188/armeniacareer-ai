# src/engine/interview/models.py
#
# Data models for the deterministic interview engine (no LLM, no network).
# Shared by candidate practice and recruiter verification.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class QuestionKind(str, Enum):
    MISSING_SKILL = "missing_skill"      # probe a required skill the CV lacks
    MATCHED_SKILL = "matched_skill"      # verify a claimed/matched skill
    WEAK_DIMENSION = "weak_dimension"    # behavioral probe on a weak axis
    GENERAL = "general"                  # general STAR / behavioral


@dataclass
class InterviewQuestion:
    text: str
    kind: QuestionKind
    target: str                          # skill name or dimension label
    rationale: str = ""                  # why this question (candidate-safe)


@dataclass
class AnswerEvaluation:
    structure: int                       # 0..10
    relevance: int                       # 0..10
    specificity: int                     # 0..10
    overall_pct: float                   # 0..100
    band: str                            # "strong" | "adequate" | "weak"
    feedback: str                        # supportive but realistic
    improvement_tips: List[str] = field(default_factory=list)


@dataclass
class FollowUp:
    text: str
    reason: str                          # which weakness triggered it ("" if advancing)
    advances: bool                       # True → move to next queued question


@dataclass
class CandidateInterviewState:
    """Session state for one candidate practice run (held in st.session_state)."""
    role_title: str
    seniority: str
    queue: List[InterviewQuestion] = field(default_factory=list)
    index: int = 0
    history: List[dict] = field(default_factory=list)   # [{question, answer, evaluation, follow_up}]
    rounds: int = 0
    max_rounds: int = 8
    finished: bool = False
    active_followup: Optional[str] = None          # deeper prompt for current question
    followed_up_indices: List[int] = field(default_factory=list)

    def current_question(self) -> Optional[InterviewQuestion]:
        if self.finished or self.index >= len(self.queue):
            return None
        return self.queue[self.index]

    def at_capacity(self) -> bool:
        return self.rounds >= self.max_rounds or self.index >= len(self.queue)


# ── Recruiter verification (structured guide; no live evaluation) ───────────

@dataclass
class VerificationQuestion:
    question: str
    strong_answer_contains: List[str] = field(default_factory=list)
    weak_answer_indicates: List[str] = field(default_factory=list)
    suggested_followups: List[str] = field(default_factory=list)
    importance: str = "recommended"      # "must_ask" | "recommended" | "optional"
    target: str = ""                     # skill / topic


@dataclass
class RecruiterVerificationGuide:
    role_title: str
    seniority: str
    questions: List[VerificationQuestion] = field(default_factory=list)
