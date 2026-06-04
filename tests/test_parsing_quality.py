# tests/test_parsing_quality.py

from src.preprocessing.parsing_quality import (
    BAND_GOOD,
    BAND_LOW,
    assess_parsing_quality,
)

_GOOD_CV = (
    "Summary\nBackend engineer with 4 years of experience building services.\n\n"
    "Work Experience\nAcme — Backend Engineer\nJan 2022 – Present\n"
    "- Built REST services in Python and Django with PostgreSQL.\n\n"
    "Education\nBSc Computer Science, 2018-2022\n\n"
    "Skills\nPython, Django, Docker, PostgreSQL, SQL, Git\n"
)


def test_good_cv_band():
    r = assess_parsing_quality(_GOOD_CV, source_ext=".txt")
    assert r.extraction_quality_band == BAND_GOOD
    assert r.is_probably_scanned is False
    assert "experience" in r.detected_sections
    assert "English" in r.detected_languages
    assert r.confidence >= 0.8


def test_scanned_pdf_flagged():
    # Near-empty text from a .pdf → low band + scanned flag (no OCR performed).
    r = assess_parsing_quality("   \n \n", source_ext=".pdf")
    assert r.extraction_quality_band == BAND_LOW
    assert r.is_probably_scanned is True
    assert any("scanned" in reason for reason in r.reasons)


def test_short_txt_is_low_but_not_scanned():
    r = assess_parsing_quality("John Doe", source_ext=".txt")
    assert r.extraction_quality_band == BAND_LOW
    assert r.is_probably_scanned is False


def test_report_fields_present():
    r = assess_parsing_quality(_GOOD_CV, source_ext=".txt")
    for attr in (
        "extraction_quality_band", "is_probably_scanned", "reasons", "confidence",
        "detected_languages", "detected_sections",
    ):
        assert hasattr(r, attr)
