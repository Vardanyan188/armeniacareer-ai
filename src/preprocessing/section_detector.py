# src/preprocessing/section_detector.py
#
# Robust, deterministic multilingual (EN/HY/RU) CV section-header detection for
# the deterministic parsing path. Tolerant to inconsistent header names, casing,
# trailing punctuation, and bullet prefixes. No LLM, no network.
#
# A line is treated as a header when its normalized form matches a known alias
# AND it looks like a heading (short, or colon-terminated). A soft substring
# fallback catches header-less / inline section labels.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.preprocessing.language_utils import normalize_text

# Canonical section label → multilingual alias list (lowercased, NFC).
SECTION_ALIASES: Dict[str, List[str]] = {
    "summary": [
        "summary", "professional summary", "profile", "professional profile", "objective",
        "career objective", "about", "about me",
        "ամփոփում", "ամփոփագիր", "մասնագիտական ամփոփագիր", "իմ մասին", "ինձ մասին",
        "անձնական նկարագիր", "նպատակ",
        "резюме", "краткое резюме", "о себе", "цель", "профиль",
    ],
    "contact": [
        "contact", "contacts", "contact me", "contact info", "contact information",
        "contact details", "personal information", "personal details",
        "կոնտակտ", "կոնտակտներ", "կապ", "կոնտակտային տվյալներ", "անձնական տվյալներ",
        "контакты", "контактная информация", "личная информация", "личные данные",
    ],
    "experience": [
        "work experience", "experience", "professional experience", "employment",
        "employment history", "work history", "career", "career history",
        "volunteer experience", "volunteering", "internship", "internships",
        "project experience", "project work", "relevant experience", "projects",
        "աշխատանքային փորձ", "փորձ", "մասնագիտական փորձ", "աշխատանքային գործունեություն",
        "կամավորական փորձ", "պրակտիկա", "նախագծեր",
        "опыт работы", "опыт", "профессиональный опыт", "трудовая деятельность", "стаж",
        "стажировка", "проекты", "волонтерский опыт",
    ],
    "education": [
        "education", "academic background", "qualifications", "academic qualifications",
        "qualification", "degree", "degrees", "academic",
        "կրթություն", "ակադեմիական կրթություն", "ուսում", "որակավորում",
        "образование", "учёба", "учеба", "академическое образование", "квалификация",
    ],
    "skills": [
        "skills", "technical skills", "computer skills", "digital skills",
        "programming skills", "core competencies", "competencies", "expertise",
        "tech stack", "technologies", "tools", "tools and technologies",
        "հմտություններ", "տեխնիկական հմտություններ", "համակարգչային հմտություններ",
        "կարողություններ", "մասնագիտական հմտություններ", "ծրագրերի իմացություն",
        "գործիքներ", "տեխնոլոգիաներ",
        "навыки", "технические навыки", "компьютерные навыки", "компетенции",
        "умения", "ключевые навыки", "владение программами", "инструменты",
        "технологии",
    ],
    "languages": [
        "language", "languages", "language skills", "language proficiency",
        "լեզու", "լեզուներ", "լեզվի իմացություն", "լեզուների իմացություն",
        "язык", "языки", "знание языков", "иностранные языки", "владение языками",
    ],
    "certifications": [
        "certifications", "certification", "certificates", "certificate", "licenses",
        "license", "credentials", "courses",
        "հավաստագրեր", "վկայականներ", "դասընթացներ",
        "сертификаты", "сертификат", "удостоверения", "лицензии", "курсы",
    ],
    "projects": [
        "projects", "project", "personal projects", "side projects", "portfolio",
        "նախագծեր", "անձնական նախագծեր", "պորտֆոլիո",
        "проекты", "личные проекты", "портфолио",
    ],
}

# Reverse lookup: alias → canonical label (longest aliases first for matching).
_ALIAS_TO_LABEL = {
    alias: label
    for label, aliases in SECTION_ALIASES.items()
    for alias in aliases
}
_ALIASES_BY_LEN = sorted(_ALIAS_TO_LABEL, key=len, reverse=True)

_HEADER_MAX_LEN = 42
_BULLET_PREFIX = "•-*–·●◦‣▪◦ \t"


@dataclass
class DetectedSection:
    label: str
    header_text: str
    line_index: int


@dataclass
class SectionDetectionResult:
    sections: Dict[str, DetectedSection] = field(default_factory=dict)
    present_labels: List[str] = field(default_factory=list)

    def has(self, label: str) -> bool:
        return label in self.sections


def _normalize_header_candidate(line: str) -> str:
    cleaned = line.strip().lstrip(_BULLET_PREFIX).strip()
    cleaned = cleaned.rstrip(":：.").strip()
    return cleaned.lower()


def _match_alias_exact(candidate: str) -> Optional[str]:
    return _ALIAS_TO_LABEL.get(candidate)


def _match_header_label(raw_line: str) -> Optional[str]:
    """
    Returns the canonical label if `raw_line` is a section header, else None.
    Combines anchored exact-alias matching with a 'starts-with alias' fallback
    (e.g. "Skills: Python, SQL"). Used for both detection and content bounding.
    """
    line = (raw_line or "").strip()
    if not line:
        return None
    candidate = _normalize_header_candidate(line)
    if not candidate:
        return None
    looks_like_header = line.endswith(":") or line.endswith("：") or len(line) <= _HEADER_MAX_LEN
    if looks_like_header:
        label = _match_alias_exact(candidate)
        if label:
            return label
    low_full = line.lower().lstrip(_BULLET_PREFIX).strip()
    for alias in _ALIASES_BY_LEN:
        if candidate == alias or low_full.startswith(alias + ":") or low_full.startswith(alias + " "):
            return _ALIAS_TO_LABEL[alias]
    return None


def _uppercase_ratio(line: str) -> float:
    letters = [c for c in line if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if c.isupper()) / len(letters)


def _multi_header_labels(line: str) -> List[str]:
    """
    For an ALL-CAPS-ish header-like line (common when two-column PDFs merge two
    headers onto one extracted line, e.g. 'PROFILE EDUCATION'), returns every
    section alias present as a whole token.
    """
    if not line or len(line) > 60 or _uppercase_ratio(line) < 0.6:
        return []
    padded = " " + line.lower().strip() + " "
    found: List[str] = []
    for alias in _ALIASES_BY_LEN:
        label = _ALIAS_TO_LABEL[alias]
        if label not in found and (" " + alias + " ") in padded:
            found.append(label)
    return found


def detect_sections(text: str) -> SectionDetectionResult:
    """
    Detects CV sections in `text`. Robust to non-standard headings, colon/bullet
    prefixes, and two-column PDF merges that glue two headers onto one line.
    """
    result = SectionDetectionResult()
    lines = normalize_text(text).split("\n")

    # Pass 1 — single-header lines (exact or starts-with alias).
    for idx, raw_line in enumerate(lines):
        label = _match_header_label(raw_line)
        if label and label not in result.sections:
            result.sections[label] = DetectedSection(
                label=label, header_text=raw_line.strip(), line_index=idx,
            )

    # Pass 2 — two-column merged headers on a single ALL-CAPS line.
    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        for label in _multi_header_labels(line):
            if label not in result.sections:
                result.sections[label] = DetectedSection(
                    label=label, header_text=line, line_index=idx,
                )

    result.present_labels = sorted(result.sections.keys())
    return result


def _all_header_indices(lines: List[str]) -> List[int]:
    """Indices of EVERY header-like line (including repeated section labels)."""
    out: List[int] = []
    for idx, raw in enumerate(lines):
        if _match_header_label(raw) is not None or _multi_header_labels(raw.strip()):
            out.append(idx)
    return out


def detected_section_labels(text: str) -> List[str]:
    """Convenience: sorted list of detected canonical section labels."""
    return detect_sections(text).present_labels


def section_content(text: str, label: str) -> List[str]:
    """
    Returns the non-empty content lines belonging to `label`'s section — the
    lines between its header and the next detected section header — plus any
    inline tail on the header line after a ':' (e.g. "Skills: Python, SQL").
    Returns [] if the section is not detected.
    """
    res = detect_sections(text)
    if label not in res.sections:
        return []
    lines = normalize_text(text).split("\n")
    start = res.sections[label].line_index
    # Bound at the next HEADER-LIKE line (re-scanned), so a repeated section
    # label later in the CV (e.g. a second 'WORK EXPERIENCE') still ends this
    # block and skills don't bleed into the next section.
    header_indices = _all_header_indices(lines)
    end = len(lines)
    for idx in header_indices:
        if idx > start:
            end = idx
            break

    content: List[str] = []
    header_line = lines[start] if 0 <= start < len(lines) else ""
    if ":" in header_line or "：" in header_line:
        tail = re.split(r"[:：]", header_line, 1)[1].strip()
        if tail:
            content.append(tail)
    for raw in lines[start + 1:end]:
        stripped = raw.strip()
        if stripped:
            content.append(stripped)
    return content
