# tests/test_answer_eval.py
#
# Deterministic answer-evaluation tests. No LLM, no network.

from src.engine.interview.answer_eval import evaluate_answer
from src.engine.interview.models import InterviewQuestion, QuestionKind

_Q = InterviewQuestion(
    text="Walk me through a project where you used Python.",
    kind=QuestionKind.MATCHED_SKILL,
    target="Python",
)

_STRONG = (
    "At my previous company I led a project where I used Python and Django to build a "
    "reporting service. The situation was slow manual reports; my task was to automate "
    "them. I designed and implemented an ETL pipeline, and as a result we reduced report "
    "time by 60% and saved 10 hours per week."
)
_WEAK = "I know Python."


def test_strong_scores_higher_than_weak():
    strong = evaluate_answer(_Q, _STRONG)
    weak = evaluate_answer(_Q, _WEAK)
    assert strong.overall_pct > weak.overall_pct
    assert strong.band in {"strong", "adequate"}
    assert weak.band == "weak"


def test_strong_answer_axes_high():
    ev = evaluate_answer(_Q, _STRONG)
    assert ev.relevance >= 8           # mentions target "Python"
    assert ev.specificity >= 6         # numbers + tools
    assert ev.structure >= 6           # STAR cues present


def test_empty_answer_is_weak_and_supportive():
    ev = evaluate_answer(_Q, "")
    assert ev.band == "weak"
    assert ev.overall_pct < 30
    assert ev.improvement_tips                       # gives guidance
    assert "viable path" not in ev.feedback.lower()  # no false positives


def test_low_specificity_triggers_tip():
    ev = evaluate_answer(_Q, "I used Python at my job for some tasks on the team.")
    assert ev.specificity < 6
    assert any("concrete" in t.lower() or "numbers" in t.lower() for t in ev.improvement_tips)


def test_never_raises_on_garbage():
    ev = evaluate_answer(_Q, "!!!   ???")
    assert ev.band in {"weak", "adequate", "strong"}
