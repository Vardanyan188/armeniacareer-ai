# src/engine/quiz/models.py
#
# Data models for the deterministic Candidate Skill Quiz (no LLM, no network).

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class QuestionType(str, Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    SCENARIO = "scenario"            # best-approach MCQ (still auto-graded)


class Focus(str, Enum):
    MISSING_SKILL = "missing_skill"
    MATCHED_SKILL = "matched_skill"
    WEAK_DIMENSION = "weak_dimension"


@dataclass
class QuizQuestion:
    qid: str
    stem: str
    options: List[str]
    correct_index: int
    explanation: str                 # why the correct option is right
    study_tip: str
    focus: Focus
    target: str                      # skill name or dimension label
    qtype: QuestionType = QuestionType.MULTIPLE_CHOICE

    def is_valid(self) -> bool:
        return (
            bool(self.stem)
            and len(self.options) >= 2
            and 0 <= self.correct_index < len(self.options)
            and bool(self.explanation)
        )


@dataclass
class QuizState:
    """Session state for one quiz run (held in st.session_state)."""
    role_title: str
    seniority: str
    questions: List[QuizQuestion] = field(default_factory=list)
    index: int = 0
    answers: List[Optional[int]] = field(default_factory=list)   # selected index per question
    finished: bool = False

    def total(self) -> int:
        return len(self.questions)

    def answered_count(self) -> int:
        return sum(1 for a in self.answers if a is not None)

    def correct_count(self) -> int:
        return sum(
            1 for q, a in zip(self.questions, self.answers)
            if a is not None and a == q.correct_index
        )

    def current(self) -> Optional[QuizQuestion]:
        if self.finished or self.index >= len(self.questions):
            return None
        return self.questions[self.index]


@dataclass
class QuizSummary:
    total: int
    correct: int
    score_pct: float
    band: str                        # "strong" | "solid" | "keep_building"
    band_message: str
    weak_areas: List[str] = field(default_factory=list)
    study_next: List[str] = field(default_factory=list)
