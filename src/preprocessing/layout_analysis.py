# src/preprocessing/layout_analysis.py
#
# Phase 24.3E — CV Visual/Layout Analyzer (MVP).
#
# Honest, deterministic layout diagnostics for Canva/template/two-column CVs.
# It does NOT do OCR and does NOT claim font/color understanding — it works from
# already-extracted text + (optional) PDF page count only. Returns safe METADATA
# (counts/ratios/flags) and advisory warning KEYS for the UI to localize. No raw
# CV text, no PII, no network, no heavy dependencies (pypdf used only if present).

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

PathLike = Union[str, Path]

# Visual proficiency glyphs (stars/dots/bars) and decorative icons.
_VISUAL_LEVEL = set("★☆●○◍◐◑◒◓▰▱■□▮▯◆◇")
_ICON_GLYPHS = _VISUAL_LEVEL | set("➤➜✦✔✓⚡✉☎✆✈⭐➡⬤◦‣▪♦♟")

_LANGUAGE_HINTS = (
    "language", "languages", "english", "armenian", "russian", "french", "german",
    "լեզու", "անգլերեն", "հայերեն", "ռուսերեն", "язык", "английск", "армянск", "русск",
)

# Advisory warning keys (localized by the UI).
WARN_TEMPLATE = "cv.layout.warn_template"
WARN_VISUAL_LEVELS = "cv.layout.warn_visual_levels"
WARN_HEADINGS = "cv.layout.warn_headings"
WARN_CHAR_SPACED = "cv.layout.warn_char_spaced"

_SYMBOL_DENSITY_THRESHOLD = 0.02
_CHAR_SPACED_THRESHOLD = 0.40


@dataclass
class LayoutDiagnostics:
    page_count: Optional[int] = None
    text_length: int = 0
    word_count: int = 0
    line_count: int = 0
    single_char_ratio: float = 0.0
    symbol_density: float = 0.0
    section_header_count: int = 0
    detected_section_labels: List[str] = field(default_factory=list)
    skill_count: int = 0
    language_count: int = 0
    risk_flags: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)   # i18n keys

    def to_dict(self) -> dict:
        return {
            "page_count": self.page_count,
            "text_length": self.text_length,
            "word_count": self.word_count,
            "line_count": self.line_count,
            "single_char_ratio": self.single_char_ratio,
            "symbol_density": self.symbol_density,
            "section_header_count": self.section_header_count,
            "detected_section_labels": list(self.detected_section_labels),
            "skill_count": self.skill_count,
            "language_count": self.language_count,
            "risk_flags": list(self.risk_flags),
            "warnings": list(self.warnings),
        }


def detect_pdf_page_count(path: PathLike) -> Optional[int]:
    """Returns the PDF page count via pypdf if available; None otherwise. Never raises."""
    try:
        if not str(path).lower().endswith(".pdf"):
            return None
        from pypdf import PdfReader
        return len(PdfReader(str(path)).pages)
    except Exception:  # pragma: no cover - pypdf absent / unreadable file
        return None


def _single_char_ratio(text: str) -> float:
    tokens = text.split()
    if not tokens:
        return 0.0
    singles = sum(1 for tok in tokens if len(tok) == 1 and tok.isalpha())
    return round(singles / len(tokens), 3)


def _symbol_density(text: str) -> float:
    non_space = [c for c in text if not c.isspace()]
    if not non_space:
        return 0.0
    icons = sum(1 for c in non_space if c in _ICON_GLYPHS)
    return round(icons / len(non_space), 4)


def _has_visual_levels(text: str) -> bool:
    if not any(c in _VISUAL_LEVEL for c in text):
        return False
    low = text.lower()
    # Visual glyphs near language context, or a numeric N/M level next to a language.
    if any(h in low for h in _LANGUAGE_HINTS):
        return True
    return bool(re.search(r"\b\d\s*/\s*\d\b", text)) and any(c in _VISUAL_LEVEL for c in text)


def analyze_layout(
    raw_text: str,
    *,
    page_count: Optional[int] = None,
    detected_labels: Optional[List[str]] = None,
    skill_count: int = 0,
    language_count: int = 0,
    source_ext: Optional[str] = None,
) -> LayoutDiagnostics:
    """Computes safe layout diagnostics + advisory warning keys. Never raises."""
    text = raw_text or ""
    labels = list(detected_labels or [])
    scr = _single_char_ratio(text)
    sym = _symbol_density(text)
    visual_levels = _has_visual_levels(text)
    char_spaced = scr >= _CHAR_SPACED_THRESHOLD
    high_symbol = sym >= _SYMBOL_DENSITY_THRESHOLD
    template_like = char_spaced or high_symbol or visual_levels

    flags: List[str] = []
    if char_spaced:
        flags.append("character_spaced_extraction")
    if high_symbol:
        flags.append("high_symbol_density")
    if visual_levels:
        flags.append("visual_only_levels")
    if template_like:
        flags.append("template_two_column_risk")
    if char_spaced and labels:
        flags.append("headings_recovered")

    warnings: List[str] = []
    if template_like:
        warnings.append(WARN_TEMPLATE)
    if visual_levels:
        warnings.append(WARN_VISUAL_LEVELS)
    if char_spaced or high_symbol:
        warnings.append(WARN_HEADINGS)
    if char_spaced:
        warnings.append(WARN_CHAR_SPACED)

    return LayoutDiagnostics(
        page_count=page_count,
        text_length=len(text),
        word_count=len(text.split()),
        line_count=text.count("\n") + 1 if text else 0,
        single_char_ratio=scr,
        symbol_density=sym,
        section_header_count=len(labels),
        detected_section_labels=labels,
        skill_count=skill_count,
        language_count=language_count,
        risk_flags=flags,
        warnings=warnings,
    )
