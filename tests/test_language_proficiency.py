# tests/test_language_proficiency.py
#
# Phase 24.2 — language proficiency parsing. Synthetic fake data only.

from src.preprocessing.language_proficiency import parse_language_line, parse_languages


# ---------------------------------------------------------------------------
# Word levels (EN/HY/RU)
# ---------------------------------------------------------------------------

def test_english_cefr_level():
    p = parse_language_line("English B2")
    assert p.language_name == "English"
    assert p.normalized_level == "Upper-Intermediate"
    assert p.confidence == "high"
    assert p.warning_if_visual_only is False


def test_armenian_word_levels():
    assert parse_language_line("Հայերեն մայրենի").normalized_level == "Native"
    assert parse_language_line("Անգլերեն լավ").normalized_level == "Intermediate"
    assert parse_language_line("Ռուսերեն միջին").normalized_level == "Intermediate"


def test_russian_word_levels():
    assert parse_language_line("Английский продвинутый").normalized_level == "Advanced"
    assert parse_language_line("Русский свободно").normalized_level == "Fluent"


def test_english_word_native_and_fluent():
    assert parse_language_line("Armenian Native").normalized_level == "Native"
    assert parse_language_line("Russian Fluent").normalized_level == "Fluent"


# ---------------------------------------------------------------------------
# Visual levels → warning_if_visual_only
# ---------------------------------------------------------------------------

def test_star_visual_level_warns():
    p = parse_language_line("English ★★★★☆")
    assert p.warning_if_visual_only is True
    assert p.confidence == "medium"
    assert p.normalized_level == "Advanced"          # 4/5


def test_dot_visual_level_warns():
    p = parse_language_line("French ●●●○○")
    assert p.warning_if_visual_only is True
    assert p.normalized_level == "Upper-Intermediate"  # 3/5


def test_numeric_visual_level_warns():
    p = parse_language_line("German 4/5")
    assert p.warning_if_visual_only is True
    assert p.normalized_level == "Advanced"


def test_word_level_is_not_visual_only():
    assert parse_language_line("English B2").warning_if_visual_only is False
    assert parse_language_line("Russian Fluent").warning_if_visual_only is False


# ---------------------------------------------------------------------------
# Multi-line + non-language lines
# ---------------------------------------------------------------------------

def test_parse_languages_multiline():
    text = "Languages\nEnglish C1\nArmenian Native\nRussian 3/5\n"
    profs = {p.language_name: p for p in parse_languages(text)}
    assert profs["English"].normalized_level == "Advanced"
    assert profs["Armenian"].normalized_level == "Native"
    assert profs["Russian"].warning_if_visual_only is True


def test_non_language_line_returns_none():
    assert parse_language_line("Built data pipelines in Python") is None
    assert parse_language_line("") is None


# ---------------------------------------------------------------------------
# Phase 24.3 hotfix — level may appear BEFORE the language name
# ---------------------------------------------------------------------------

def test_level_before_name():
    assert parse_language_line("Native Armenian").normalized_level == "Native"
    assert parse_language_line("Advanced English").normalized_level == "Advanced"
    assert parse_language_line("Advanced Russian").normalized_level == "Advanced"


def test_level_before_name_multiline():
    text = "LANGUAGE\nNative Armenian\nAdvanced English\nAdvanced Russian\n"
    profs = {p.language_name: p.normalized_level for p in parse_languages(text)}
    assert profs == {"Armenian": "Native", "English": "Advanced", "Russian": "Advanced"}
