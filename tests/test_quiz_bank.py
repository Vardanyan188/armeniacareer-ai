# tests/test_quiz_bank.py
#
# Question-bank validity tests. Deterministic, no LLM, no network.

from src.engine.quiz.models import Focus, QuestionType
from src.engine.quiz.question_bank import (
    _SKILL_BANK,
    _DIMENSION_BANK,
    has_curated_skill,
    make_dimension_mcq,
    make_missing_skill_scenario,
    make_skill_mcq,
)


def test_all_curated_skill_questions_valid():
    for skill in _SKILL_BANK:
        q = make_skill_mcq(skill, Focus.MATCHED_SKILL, qid=f"matched:{skill}:0")
        assert q.is_valid()
        assert q.options[q.correct_index]            # correct option non-empty
        assert q.explanation and q.study_tip


def test_all_dimension_questions_valid():
    for dim in _DIMENSION_BANK:
        q = make_dimension_mcq(dim, qid=f"weakdim:{dim}:0")
        assert q.is_valid()
        assert q.focus == Focus.WEAK_DIMENSION


def test_generic_fallback_for_unknown_skill():
    assert has_curated_skill("Python") is True
    assert has_curated_skill("Brainfuck") is False
    q = make_skill_mcq("Brainfuck", Focus.MATCHED_SKILL, qid="matched:Brainfuck:0")
    assert q.is_valid()
    assert "Brainfuck" in q.stem
    assert q.target == "Brainfuck"


def test_missing_skill_scenario_is_scenario_type():
    q = make_missing_skill_scenario("Kubernetes", qid="missing:Kubernetes:0")
    assert q.is_valid()
    assert q.qtype == QuestionType.SCENARIO
    assert q.focus == Focus.MISSING_SKILL


def test_correct_index_placement_is_deterministic_and_varies():
    # Same qid → same placement; the correct answer isn't hardwired to slot 0
    # across the whole bank.
    q1 = make_skill_mcq("Python", Focus.MATCHED_SKILL, qid="matched:Python:0")
    q2 = make_skill_mcq("Python", Focus.MATCHED_SKILL, qid="matched:Python:0")
    assert q1.correct_index == q2.correct_index
    indices = {
        make_skill_mcq(s, Focus.MATCHED_SKILL, qid=f"matched:{s}:0").correct_index
        for s in _SKILL_BANK
    }
    assert len(indices) > 1   # not all correct answers in the same position
