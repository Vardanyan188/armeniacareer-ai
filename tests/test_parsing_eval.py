# tests/test_parsing_eval.py
#
# Enforces aggregate parsing-quality thresholds over the offline fixture set.

from src.evaluation.parsing_eval import EvalReport, run_parsing_eval


def test_run_parsing_eval_returns_report():
    report = run_parsing_eval()
    assert isinstance(report, EvalReport)
    assert report.n_cases >= 4
    assert report.n_date_cases >= 5


def test_section_recall_threshold():
    assert run_parsing_eval().section_recall >= 0.8


def test_band_accuracy_threshold():
    assert run_parsing_eval().band_accuracy >= 0.8


def test_language_accuracy_threshold():
    assert run_parsing_eval().language_accuracy >= 0.8


def test_date_parse_rate_threshold():
    assert run_parsing_eval().date_parse_rate >= 0.8
