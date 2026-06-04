# tests/test_layout_analysis.py
#
# Phase 24.3E — CV layout/visual analyzer MVP. Deterministic, no OCR, no network.
# Synthetic fake data only — no raw CV text, no PII.

import re

from src.preprocessing.layout_analysis import (
    WARN_CHAR_SPACED,
    WARN_HEADINGS,
    WARN_TEMPLATE,
    WARN_VISUAL_LEVELS,
    analyze_layout,
    detect_pdf_page_count,
)

_PHONE = re.compile(r"\(?\+?\d[\d\s().\-]{7,}\d\)?")


# ---------------------------------------------------------------------------
# Page count
# ---------------------------------------------------------------------------

def test_page_count_none_for_non_pdf(tmp_path):
    f = tmp_path / "cv.txt"
    f.write_text("hello", encoding="utf-8")
    assert detect_pdf_page_count(str(f)) is None


def test_page_count_graceful_on_missing_or_bad_file(tmp_path):
    assert detect_pdf_page_count(str(tmp_path / "nope.pdf")) is None
    bad = tmp_path / "broken.pdf"
    bad.write_text("not a real pdf", encoding="utf-8")
    assert detect_pdf_page_count(str(bad)) is None     # never raises


def test_page_count_passed_through_when_known():
    d = analyze_layout("Some CV text here", page_count=2)
    assert d.page_count == 2 and d.to_dict()["page_count"] == 2


def test_page_count_none_when_unavailable():
    d = analyze_layout("Some CV text here", page_count=None)
    assert d.page_count is None


# ---------------------------------------------------------------------------
# Risk signals
# ---------------------------------------------------------------------------

_CHAR_SPACED = ("C O M P U T E R   S K I L L S\nP y t h o n   S Q L\n"
                "E D U C A T I O N\nB S c   2 0 2 0\n") * 3


def test_character_spaced_risk_detected():
    d = analyze_layout(_CHAR_SPACED, detected_labels=["skills", "education"])
    assert d.single_char_ratio >= 0.4
    assert "character_spaced_extraction" in d.risk_flags
    assert WARN_CHAR_SPACED in d.warnings and WARN_TEMPLATE in d.warnings
    assert WARN_HEADINGS in d.warnings


def test_template_two_column_warning_from_symbols():
    text = "★ ★ ★ ➤ ➤ ✦ ✦ ⬤ ◦ ‣ ▪ Name Title Education Experience Skills"
    d = analyze_layout(text, detected_labels=["education"])
    assert "high_symbol_density" in d.risk_flags
    assert WARN_TEMPLATE in d.warnings


def test_visual_only_language_level_warning():
    text = "LANGUAGES\nEnglish ★★★★☆\nArmenian ●●●○○\nRussian 4/5\n"
    d = analyze_layout(text, detected_labels=["languages"])
    assert "visual_only_levels" in d.risk_flags
    assert WARN_VISUAL_LEVELS in d.warnings


def test_no_false_alarm_for_clean_plaintext_cv():
    text = ("PROFILE\nBackend engineer.\n\nWORK EXPERIENCE\nEngineer at Company (2019-2023)\n\n"
            "EDUCATION\nBSc Computer Science\n\nSKILLS\nPython, SQL, Docker\n")
    d = analyze_layout(text, detected_labels=["summary", "experience", "education", "skills"])
    assert d.risk_flags == []
    assert d.warnings == []
    assert d.single_char_ratio < 0.4


# ---------------------------------------------------------------------------
# Privacy of diagnostics
# ---------------------------------------------------------------------------

def test_diagnostics_contain_no_raw_text_or_pii():
    text = "Contact: fake.person@example.com  Phone: +374 00 000000  Python SQL"
    d = analyze_layout(text, detected_labels=["skills"], skill_count=2)
    blob = str(d.to_dict())
    assert "fake.person@example.com" not in blob and "@" not in blob
    assert not _PHONE.search(blob)
    assert "Python" not in blob      # only counts/labels, never tokens
    # Only safe metadata keys are exposed.
    assert set(d.to_dict()) == {
        "page_count", "text_length", "word_count", "line_count",
        "single_char_ratio", "symbol_density", "section_header_count",
        "detected_section_labels", "skill_count", "language_count",
        "risk_flags", "warnings",
    }


# ---------------------------------------------------------------------------
# Public-demo debug gating (raw diagnostics hidden in public)
# ---------------------------------------------------------------------------

def test_debug_diagnostics_hidden_in_public(monkeypatch):
    for f in ("APP_ENV", "ACAI_DEBUG", "ACAI_PUBLIC_DEMO"):
        monkeypatch.delenv(f, raising=False)
    monkeypatch.setenv("ACAI_PUBLIC_DEMO", "1")
    from src.ui.app_gates import is_debug_enabled
    assert is_debug_enabled() is False
