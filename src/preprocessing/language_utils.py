# src/preprocessing/language_utils.py
#
# Unified, deterministic script + language detection and text normalization for
# the deterministic parsing path (Armenian / Russian / English / mixed).
#
# No LLM, no network. Pure-functional and safe on empty/garbled input.

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List

# Unicode block ranges.
_ARMENIAN = (0x0531, 0x058F)
_CYRILLIC = (0x0400, 0x04FF)
_LATIN_RANGES = ((0x0041, 0x005A), (0x0061, 0x007A))

# Keyword cues for explicit language mentions (helps short CVs).
_LANGUAGE_KEYWORDS: Dict[str, List[str]] = {
    "English": ["english", "անգլերեն", "английск"],
    "Armenian": ["armenian", "հայերեն", "армянск"],
    "Russian": ["russian", "ռուսերեն", "русск"],
    "French": ["french", "ֆրանսերեն", "французск"],
    "German": ["german", "գերմաներեն", "немецк"],
}

# Minimum share of a script's letters (relative to all letters) to count it as
# a present language by character evidence.
_SCRIPT_PRESENCE_RATIO = 0.10


def _in(cp: int, lo: int, hi: int) -> bool:
    return lo <= cp <= hi


def normalize_text(text: str) -> str:
    """
    Safe text normalization:
      - Unicode NFC (composes Armenian/accented forms consistently)
      - normalizes line endings and non-breaking spaces
      - collapses runs of spaces/tabs, trims trailing space per line
      - collapses 3+ blank lines to a single blank line
    Returns "" for falsy input. Never raises.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFC", str(text))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace(" ", " ").replace("​", "")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def script_counts(text: str) -> Dict[str, int]:
    """Counts letters by script: armenian / cyrillic / latin / other."""
    counts = {"armenian": 0, "cyrillic": 0, "latin": 0, "other": 0}
    for ch in text or "":
        if not ch.isalpha():
            continue
        cp = ord(ch)
        if _in(cp, *_ARMENIAN):
            counts["armenian"] += 1
        elif _in(cp, *_CYRILLIC):
            counts["cyrillic"] += 1
        elif any(_in(cp, lo, hi) for lo, hi in _LATIN_RANGES):
            counts["latin"] += 1
        else:
            counts["other"] += 1
    return counts


def detect_primary_script(text: str) -> str:
    """
    Returns the dominant script: 'armenian' | 'cyrillic' | 'latin' | 'mixed' |
    'unknown'. 'mixed' when the top two scripts are within 20% of each other.
    """
    counts = script_counts(text)
    relevant = {k: v for k, v in counts.items() if k != "other"}
    total = sum(relevant.values())
    if total == 0:
        return "unknown"
    ordered = sorted(relevant.items(), key=lambda kv: kv[1], reverse=True)
    top_name, top_val = ordered[0]
    if len(ordered) > 1:
        second_val = ordered[1][1]
        if second_val > 0 and (top_val - second_val) / total < 0.20:
            return "mixed"
    return top_name


def detect_languages(text: str) -> List[str]:
    """
    Detects present natural languages by script evidence + explicit keyword cues.
    Returns English names, ordered: Armenian, Russian, English, then keyword-only.
    """
    text = text or ""
    counts = script_counts(text)
    total_letters = counts["armenian"] + counts["cyrillic"] + counts["latin"]
    languages: List[str] = []

    if total_letters > 0:
        if counts["armenian"] / total_letters >= _SCRIPT_PRESENCE_RATIO:
            languages.append("Armenian")
        if counts["cyrillic"] / total_letters >= _SCRIPT_PRESENCE_RATIO:
            languages.append("Russian")
        if counts["latin"] / total_letters >= _SCRIPT_PRESENCE_RATIO:
            languages.append("English")

    low = text.lower()
    for lang, cues in _LANGUAGE_KEYWORDS.items():
        if lang not in languages and any(c in low for c in cues):
            languages.append(lang)

    return languages


def alpha_ratio(text: str) -> float:
    """Share of letters among all non-whitespace characters. 0.0 for empty."""
    non_ws = [c for c in (text or "") if not c.isspace()]
    if not non_ws:
        return 0.0
    letters = sum(1 for c in non_ws if c.isalpha())
    return round(letters / len(non_ws), 4)
