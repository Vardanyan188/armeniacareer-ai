# tests/test_language_utils.py

from src.preprocessing.language_utils import (
    alpha_ratio,
    detect_languages,
    detect_primary_script,
    normalize_text,
)


def test_normalize_text_collapses_whitespace_and_blanks():
    raw = "Hello   world\r\n\n\n\nNext\t line  "
    out = normalize_text(raw)
    assert "   " not in out
    assert "\r" not in out
    assert "\n\n\n" not in out
    assert out.startswith("Hello world")


def test_normalize_text_empty_safe():
    assert normalize_text("") == ""
    assert normalize_text(None) == ""


def test_detect_primary_script():
    assert detect_primary_script("Hello world plain latin") == "latin"
    assert detect_primary_script("Բարև ձեզ հայերեն տեքստ") == "armenian"
    assert detect_primary_script("Привет это русский текст") == "cyrillic"
    assert detect_primary_script("") == "unknown"


def test_detect_languages_by_script_and_keyword():
    assert "English" in detect_languages("Backend engineer with Python")
    assert "Armenian" in detect_languages("Փորձառու ծրագրավորող Python")
    assert "Russian" in detect_languages("Опытный инженер Python")
    # keyword cue even without much script evidence
    assert "Armenian" in detect_languages("Languages: English, Armenian")


def test_alpha_ratio():
    assert alpha_ratio("abcd") == 1.0
    assert alpha_ratio("!!!!") == 0.0
    assert alpha_ratio("") == 0.0
