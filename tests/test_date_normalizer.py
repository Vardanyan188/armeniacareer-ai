# tests/test_date_normalizer.py

from src.preprocessing.date_normalizer import (
    NormalizedDate,
    normalize_date,
    parse_date_range,
)


# ---------------------------------------------------------------------------
# Single dates
# ---------------------------------------------------------------------------

def test_normalize_named_month():
    d = normalize_date("January 2022")
    assert d == NormalizedDate(2022, 1, d.confidence, d.raw)
    assert d.year == 2022 and d.month == 1


def test_normalize_iso_and_numeric():
    assert normalize_date("2022-05").month == 5
    assert normalize_date("05/2022").year == 2022
    assert normalize_date("2020").year == 2020


def test_normalize_two_digit_year():
    d = normalize_date("01.01.26", current_year=2026)
    assert d.year == 2026
    # 3-part DD.MM.YY with a 2-digit year that maps to the 1900s.
    d2 = normalize_date("01.06.99", current_year=2026)
    assert d2.year == 1999


def test_normalize_armenian_and_russian_month():
    assert normalize_date("մարտ 2021").month == 3
    assert normalize_date("сентябрь 2021").month == 9
    assert normalize_date("января 2020").month == 1


def test_normalize_empty():
    assert normalize_date("") is None
    assert normalize_date("no date here") is None


# ---------------------------------------------------------------------------
# Ranges
# ---------------------------------------------------------------------------

def test_range_with_present_english():
    r = parse_date_range("Jan 2024 – Present")
    assert r.start.year == 2024
    assert r.is_current is True
    assert r.duration_months is not None and r.duration_months >= 0


def test_range_two_years():
    r = parse_date_range("2021–2023")
    assert r.start.year == 2021
    assert r.end.year == 2023
    assert r.is_current is False
    assert r.duration_months == 24


def test_range_month_year_numeric():
    r = parse_date_range("01.2024-05.2025")
    assert r.start.year == 2024 and r.start.month == 1
    assert r.end.year == 2025 and r.end.month == 5
    assert r.duration_months == 16


def test_range_armenian_present():
    r = parse_date_range("2023-ից մինչ օրս")
    assert r.start.year == 2023
    assert r.is_current is True


def test_range_russian_named_months():
    r = parse_date_range("март 2020 — сентябрь 2021")
    assert r.start.year == 2020 and r.start.month == 3
    assert r.end.year == 2021 and r.end.month == 9
    assert r.is_current is False


def test_range_never_raises_on_garbage():
    r = parse_date_range("garbage with no dates")
    assert r.start is None
    assert r.duration_months is None
    assert r.confidence == 0.0
