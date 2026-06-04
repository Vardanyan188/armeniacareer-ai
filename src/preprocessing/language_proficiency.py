# src/preprocessing/language_proficiency.py
#
# Phase 24.2 — deterministic language-proficiency parsing (EN/HY/RU + CEFR +
# word levels + visual star/dot/bar/numeric levels).
#
# Returns structured proficiency objects; language names are NEVER treated as
# technical skills. No LLM, no network. Plain-text only — we can detect symbols
# but NOT color (no layout/color metadata here), so we never claim color.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# Language name token (lowercased, EN/HY/RU) → canonical English name.
_LANGUAGE_NAMES = {
    "english": "English", "անգլերեն": "English", "английский": "English",
    "armenian": "Armenian", "հայերեն": "Armenian", "армянский": "Armenian",
    "russian": "Russian", "ռուսերեն": "Russian", "русский": "Russian",
    "french": "French", "ֆրանսերեն": "French", "французский": "French",
    "german": "German", "գերմաներեն": "German", "немецкий": "German",
    "spanish": "Spanish", "իսպաներեն": "Spanish", "испанский": "Spanish",
    "italian": "Italian", "georgian": "Georgian", "persian": "Persian",
}
_NAMES_BY_LEN = sorted(_LANGUAGE_NAMES, key=len, reverse=True)

# Word-level cues (lowercased) → normalized label. Order: most specific first.
_WORD_LEVELS = [
    ("Native", ["native", "mother tongue", "mother-tongue", "մայրենի", "родной"]),
    ("Fluent", ["fluent", "fluency", "proficient", "սահուն", "ազատ", "свободно", "свободный"]),
    ("Advanced", ["advanced", "առաջադեմ", "բարձր", "продвинутый"]),
    ("Upper-Intermediate", ["upper-intermediate", "upper intermediate"]),
    ("Intermediate", [
        "intermediate", "conversational", "working", "good", "լավ", "միջին",
        "средний", "хорошо", "хороший",
    ]),
    ("Elementary", ["pre-intermediate", "elementary", "таррական"]),
    ("Basic", [
        "basic", "beginner", "սկսնակ", "տարրական", "հիմնական",
        "базовый", "начальный",
    ]),
]

# CEFR letter-grade → normalized label.
_CEFR_MAP = {
    "c2": "Proficient", "c1": "Advanced", "b2": "Upper-Intermediate",
    "b1": "Intermediate", "a2": "Elementary", "a1": "Basic",
}

# Visual indicator glyphs.
_FILLED = set("★●▰■█♦◆⬤•▮✦")
_EMPTY = set("☆○▱□◇▯")


@dataclass
class LanguageProficiency:
    language_name: str
    raw_level: str
    normalized_level: str
    confidence: str                 # high | medium | low
    warning_if_visual_only: bool = False

    def to_dict(self) -> dict:
        return {
            "language_name": self.language_name,
            "raw_level": self.raw_level,
            "normalized_level": self.normalized_level,
            "confidence": self.confidence,
            "warning_if_visual_only": self.warning_if_visual_only,
        }


def _ratio_to_level(ratio: float) -> str:
    if ratio >= 1.0:
        return "Fluent"
    if ratio >= 0.8:
        return "Advanced"
    if ratio >= 0.6:
        return "Upper-Intermediate"
    if ratio >= 0.4:
        return "Intermediate"
    if ratio >= 0.2:
        return "Basic"
    return "Basic"


def _visual_ratio(text: str) -> Optional[float]:
    filled = sum(1 for c in text if c in _FILLED)
    empty = sum(1 for c in text if c in _EMPTY)
    total = filled + empty
    if total == 0:
        return None
    return filled / total


def parse_language_line(line: str) -> Optional[LanguageProficiency]:
    """Parses a single 'Language Level' line into a LanguageProficiency, or None."""
    if not line:
        return None
    low = line.lower()
    name = None
    name_pos = -1
    for token in _NAMES_BY_LEN:
        pos = low.find(token)
        if pos != -1:
            name = _LANGUAGE_NAMES[token]
            name_pos = pos + len(token)
            break
    if name is None:
        return None

    raw_level = line[name_pos:].strip(" :：-–—\t").strip()
    level_text = raw_level.lower()

    # 1) CEFR (highest confidence).
    cefr = re.search(r"\b([abc][12])\b", level_text)
    if cefr:
        return LanguageProficiency(name, raw_level or cefr.group(1).upper(),
                                   _CEFR_MAP[cefr.group(1)], "high", False)

    # 2) Word level (scan only the text after the language name).
    for label, cues in _WORD_LEVELS:
        if any(cue in level_text for cue in cues):
            return LanguageProficiency(name, raw_level or label, label, "high", False)

    # 3) Numeric N/M (visual-only style).
    numeric = re.search(r"(\d+)\s*/\s*(\d+)", raw_level)
    if numeric:
        n, m = int(numeric.group(1)), int(numeric.group(2))
        if m > 0:
            return LanguageProficiency(name, raw_level, _ratio_to_level(n / m), "medium", True)

    # 4) Visual symbols (stars/dots/bars).
    ratio = _visual_ratio(raw_level)
    if ratio is not None:
        return LanguageProficiency(name, raw_level, _ratio_to_level(ratio), "medium", True)

    # 5) Name found but no parseable level.
    return LanguageProficiency(name, raw_level, "Unknown", "low", False)


def parse_languages(text: str) -> List[LanguageProficiency]:
    """Parses all recognizable language-proficiency lines from `text`."""
    out: List[LanguageProficiency] = []
    seen: set = set()
    for raw in (text or "").split("\n"):
        prof = parse_language_line(raw.strip())
        if prof and prof.language_name not in seen:
            seen.add(prof.language_name)
            out.append(prof)
    return out
