# src/preprocessing/parsing_quality.py
#
# Deterministic parsing-quality assessment for extracted CV/JD text.
#
# Produces an extraction-quality band, a scanned/image-PDF flag (detect only —
# NO OCR), human-readable reasons, a confidence, and the detected languages and
# sections. Composes language_utils + section_detector. No LLM, no network.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.preprocessing.language_utils import (
    alpha_ratio,
    detect_languages,
    detect_primary_script,
    normalize_text,
)
from src.preprocessing.section_detector import detected_section_labels

# Thresholds.
_LOW_CHAR_THRESHOLD = 120       # below this → too little text extracted
_LOW_ALPHA_RATIO = 0.35         # below this → mostly symbols/garbage
_GOOD_MIN_SECTIONS = 2          # sections needed for a "good" band
_GOOD_MIN_CHARS = 250

BAND_GOOD = "good"
BAND_PARTIAL = "partial"
BAND_LOW = "low"


@dataclass
class ParsingQualityReport:
    extraction_quality_band: str = BAND_LOW
    is_probably_scanned: bool = False
    confidence: float = 0.0
    char_count: int = 0
    word_count: int = 0
    alpha_ratio: float = 0.0
    primary_script: str = "unknown"
    detected_languages: List[str] = field(default_factory=list)
    detected_sections: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)


def assess_parsing_quality(
    text: str,
    source_ext: Optional[str] = None,
) -> ParsingQualityReport:
    """
    Assesses how well text was extracted from a CV/JD document.

    `source_ext` (e.g. ".pdf") enables the scanned-PDF heuristic: a PDF that
    yields almost no extractable text is flagged is_probably_scanned (detection
    only — no OCR is performed).
    """
    norm = normalize_text(text)
    char_count = len(norm)
    word_count = len(norm.split())
    a_ratio = alpha_ratio(norm)
    script = detect_primary_script(norm)
    languages = detect_languages(norm)
    sections = detected_section_labels(norm)

    ext = (source_ext or "").lower()
    reasons: List[str] = []

    too_short = char_count < _LOW_CHAR_THRESHOLD
    too_few_letters = a_ratio < _LOW_ALPHA_RATIO

    if too_short:
        reasons.append(f"very little text extracted ({char_count} chars)")
    if too_few_letters:
        reasons.append(f"low letter ratio ({a_ratio:.2f}) — text may be garbled")

    # Scanned/image-PDF heuristic (detect & flag only).
    is_probably_scanned = ext == ".pdf" and (too_short or too_few_letters)
    if is_probably_scanned:
        reasons.append(
            "possibly a scanned/image PDF — no usable text layer (OCR not applied)"
        )

    # Band assignment.
    if too_short or too_few_letters:
        band = BAND_LOW
    elif len(sections) >= _GOOD_MIN_SECTIONS and char_count >= _GOOD_MIN_CHARS:
        band = BAND_GOOD
    else:
        band = BAND_PARTIAL
        if len(sections) < _GOOD_MIN_SECTIONS:
            reasons.append("few recognisable sections detected")

    # Confidence: anchored to band, nudged by section evidence.
    base = {BAND_GOOD: 0.9, BAND_PARTIAL: 0.6, BAND_LOW: 0.2}[band]
    confidence = round(min(1.0, base + 0.03 * len(sections)), 3)

    return ParsingQualityReport(
        extraction_quality_band=band,
        is_probably_scanned=is_probably_scanned,
        confidence=confidence,
        char_count=char_count,
        word_count=word_count,
        alpha_ratio=a_ratio,
        primary_script=script,
        detected_languages=languages,
        detected_sections=sections,
        reasons=reasons,
    )
