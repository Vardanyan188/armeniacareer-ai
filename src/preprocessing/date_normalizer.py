# src/preprocessing/date_normalizer.py
#
# Deterministic, multilingual date + date-range normalization for CV parsing.
# Handles numeric forms, named months (EN/HY/RU incl. abbreviations and Russian
# genitive), 2-digit years, present/current forms, and ranges. Never raises.
#
# No LLM, no network.

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

from src.preprocessing.language_utils import normalize_text

# ---------------------------------------------------------------------------
# Month vocabularies (lowercased)
# ---------------------------------------------------------------------------

_MONTHS = {
    # English full + abbreviations
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
    # Armenian
    "հունվար": 1, "փետրվար": 2, "մարտ": 3, "ապրիլ": 4, "մայիս": 5, "հունիս": 6,
    "հուլիս": 7, "օգոստոս": 8, "սեպտեմբեր": 9, "հոկտեմբեր": 10, "նոյեմբեր": 11,
    "դեկտեմբեր": 12,
    # Russian nominative
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6,
    "июль": 7, "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12,
    # Russian genitive (".. с января ..")
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

_MONTH_ALT = "|".join(re.escape(m) for m in sorted(_MONTHS, key=len, reverse=True))

# Present / current tokens (lowercased).
_PRESENT_TOKENS = [
    "present", "current", "currently", "now", "ongoing", "to date", "till now",
    "till date", "until now",
    "հիմա", "ներկա", "ներկայումս", "մինչ օրս", "առ այսօր", "այժմ",
    "по настоящее время", "по настоящее", "настоящее время", "по сей день",
    "сейчас", "н.в", "нв",
]

# ---------------------------------------------------------------------------
# Compiled patterns (priority order: lower number = stronger match)
# ---------------------------------------------------------------------------

_MONTH_NAME_RE = re.compile(r"(" + _MONTH_ALT + r")\.?\s*['`]?\s*((?:19|20)\d{2})")
_ISO_RE = re.compile(r"\b((?:19|20)\d{2})[-/.](\d{1,2})(?:[-/.](\d{1,2}))?\b")
_DMY_RE = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{2,4})\b")
_MY_RE = re.compile(r"\b(\d{1,2})[./]((?:19|20)\d{2})\b")
_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")

# Range separators (lowercased text).
_SEPARATORS = ["–", "—", "to", "until", "по", "до", "—", " - ", "-", "մինչ"]


@dataclass(frozen=True)
class NormalizedDate:
    year: int
    month: Optional[int]
    confidence: float
    raw: str


@dataclass
class DateRange:
    start: Optional[NormalizedDate]
    end: Optional[NormalizedDate]
    is_current: bool
    duration_months: Optional[int]
    confidence: float
    raw: str


def _current_year() -> int:
    return datetime.now().year


def _valid_month(m: Optional[int]) -> Optional[int]:
    return m if (m is not None and 1 <= m <= 12) else None


def _expand_year(token: str, current_year: int) -> int:
    if len(token) == 4:
        return int(token)
    yy = int(token)
    year = 2000 + yy
    if year > current_year + 1:
        year = 1900 + yy
    return year


def has_present_token(text: str) -> bool:
    low = (text or "").lower()
    return any(tok in low for tok in _PRESENT_TOKENS)


def _collect_dates(low: str, current_year: int) -> List[Tuple[int, int, int, NormalizedDate]]:
    """Returns (start, end, priority, NormalizedDate) for every date-like span."""
    out: List[Tuple[int, int, int, NormalizedDate]] = []

    for m in _MONTH_NAME_RE.finditer(low):
        month = _MONTHS.get(m.group(1))
        out.append((m.start(), m.end(), 1, NormalizedDate(
            int(m.group(2)), _valid_month(month), 0.95, m.group(0))))

    for m in _ISO_RE.finditer(low):
        out.append((m.start(), m.end(), 2, NormalizedDate(
            int(m.group(1)), _valid_month(int(m.group(2))), 0.9, m.group(0))))

    for m in _DMY_RE.finditer(low):
        a, b, c = int(m.group(1)), int(m.group(2)), m.group(3)
        year = _expand_year(c, current_year)
        if a > 12 and b <= 12:
            month, conf = b, 0.85           # a = day, b = month
        elif b > 12 and a <= 12:
            month, conf = a, 0.85           # b = day, a = month
        elif a <= 12 and b <= 12:
            month, conf = b, 0.6            # ambiguous; assume DD.MM
        else:
            month, conf = None, 0.4
        out.append((m.start(), m.end(), 3, NormalizedDate(
            year, _valid_month(month), conf, m.group(0))))

    for m in _MY_RE.finditer(low):
        mm = int(m.group(1))
        if 1 <= mm <= 12:
            out.append((m.start(), m.end(), 4, NormalizedDate(
                int(m.group(2)), mm, 0.85, m.group(0))))

    for m in _YEAR_RE.finditer(low):
        out.append((m.start(), m.end(), 5, NormalizedDate(
            int(m.group(1)), None, 0.75, m.group(0))))

    return out


def _find_all_dates(text: str, current_year: int) -> List[NormalizedDate]:
    """Resolves overlapping matches, keeping the strongest, ordered by position."""
    low = (text or "").lower()
    candidates = _collect_dates(low, current_year)
    # Prefer earlier start, then stronger priority.
    candidates.sort(key=lambda t: (t[0], t[2]))
    accepted: List[Tuple[int, int, NormalizedDate]] = []
    for start, end, _prio, date in candidates:
        if any(not (end <= a_s or start >= a_e) for a_s, a_e, _ in accepted):
            continue  # overlaps an already-accepted (stronger/earlier) span
        accepted.append((start, end, date))
    accepted.sort(key=lambda t: t[0])
    return [d for _s, _e, d in accepted]


def normalize_date(s: str, current_year: Optional[int] = None) -> Optional[NormalizedDate]:
    """Parses the first date found in `s`. Returns None if none is parseable."""
    cy = current_year or _current_year()
    dates = _find_all_dates(normalize_text(s), cy)
    return dates[0] if dates else None


def parse_date_range(s: str, current_year: Optional[int] = None) -> DateRange:
    """
    Parses an employment/education date range. Returns a DateRange with start,
    end (or present), is_current, duration_months, and confidence. Never raises.
    """
    cy = current_year or _current_year()
    raw = s or ""
    norm = normalize_text(raw)
    present = has_present_token(norm)
    dates = _find_all_dates(norm, cy)

    start: Optional[NormalizedDate] = dates[0] if dates else None
    end: Optional[NormalizedDate] = None
    is_current = False

    if present:
        is_current = True
        end = None  # represented by is_current; effective end is "today"
    elif len(dates) >= 2:
        end = dates[1]

    # Effective end for duration computation.
    end_eff: Optional[NormalizedDate]
    if end is not None:
        end_eff = end
    elif is_current:
        now = datetime.now()
        end_eff = NormalizedDate(cy, now.month, 0.9, "present")
    else:
        end_eff = None

    duration_months: Optional[int] = None
    if start and end_eff:
        sm = start.month or 1
        em = end_eff.month or sm  # missing month → pure year difference
        duration_months = max(0, (end_eff.year - start.year) * 12 + (em - sm))

    confs = [d.confidence for d in (start, end_eff) if d is not None]
    confidence = round(min(confs), 3) if confs else 0.0

    return DateRange(
        start=start,
        end=end,
        is_current=is_current,
        duration_months=duration_months,
        confidence=confidence,
        raw=raw,
    )
