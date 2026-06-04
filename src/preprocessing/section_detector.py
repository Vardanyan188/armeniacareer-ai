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

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.preprocessing.language_utils import normalize_text

# Canonical section label → multilingual alias list (lowercased, NFC).
SECTION_ALIASES: Dict[str, List[str]] = {
    "summary": [
        "summary", "professional summary", "profile", "professional profile", "objective",
        "career objective", "about", "about me",
        "ամփոփում", "իմ մասին", "ինձ մասին", "նպատակ",
        "резюме", "краткое резюме", "о себе", "цель", "профиль",
    ],
    "contact": [
        "contact", "contacts", "contact me", "contact info", "contact information",
        "contact details", "personal information", "personal details",
        "կոնտակտ", "կոնտակտներ", "կապ", "կոնտակտային տվյալներ", "անձնական տվյալներ",
        "контакты", "контактная информация", "личная информация",
    ],
    "experience": [
        "work experience", "experience", "professional experience", "employment",
        "employment history", "work history", "career", "career history",
        "volunteer experience", "volunteering", "internship", "internships",
        "project experience", "project work", "relevant experience",
        "աշխատանքային փորձ", "փորձ", "մասնագիտական փորձ", "աշխատանքային գործունեություն",
        "կամավորական փորձ", "պրակտիկա",
        "опыт работы", "опыт", "профессиональный опыт", "трудовая деятельность", "стаж",
    ],
    "education": [
        "education", "academic background", "qualifications", "academic qualifications",
        "qualification", "degree", "degrees", "academic",
        "կրթություն", "ակադեմիական կրթություն", "ուսում", "որակավորում",
        "образование", "учёба", "учеба", "академическое образование",
    ],
    "skills": [
        "skills", "technical skills", "computer skills", "digital skills",
        "programming skills", "core competencies", "competencies", "expertise",
        "tech stack", "technologies", "tools", "tools and technologies",
        "հմտություններ", "տեխնիկական հմտություններ", "համակարգչային հմտություններ",
        "կարողություններ", "մասնագիտական հմտություններ",
        "навыки", "технические навыки", "компьютерные навыки", "компетенции",
        "умения", "ключевые навыки",
    ],
    "languages": [
        "language", "languages", "language skills", "language proficiency",
        "լեզու", "լեզուներ", "լեզվի իմացություն", "լեզուների իմացություն",
        "язык", "языки", "знание языков", "иностранные языки",
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


def detect_sections(text: str) -> SectionDetectionResult:
    """
    Detects CV sections in `text`. Returns a SectionDetectionResult mapping each
    detected canonical label to the header line that introduced it (first hit).

    Two-pass strategy:
      1. Anchored headers: a short or colon-terminated line whose normalized form
         exactly equals a known alias.
      2. Soft fallback: for labels still missing, a line that *starts with* a
         known alias (e.g. "Skills: Python, SQL") counts as present.
    """
    result = SectionDetectionResult()
    norm = normalize_text(text)
    lines = norm.split("\n")

    # Pass 1 — anchored exact header match.
    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        looks_like_header = line.endswith(":") or line.endswith("：") or len(line) <= _HEADER_MAX_LEN
        if not looks_like_header:
            continue
        candidate = _normalize_header_candidate(line)
        if not candidate:
            continue
        label = _match_alias_exact(candidate)
        if label and label not in result.sections:
            result.sections[label] = DetectedSection(
                label=label, header_text=line, line_index=idx,
            )

    # Pass 2 — soft "starts-with alias" fallback for still-missing labels.
    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        low = _normalize_header_candidate(line)
        # Use the raw lowercased line for prefix checks (keeps "skills:" prefix).
        low_full = line.lower().lstrip(_BULLET_PREFIX).strip()
        for alias in _ALIASES_BY_LEN:
            label = _ALIAS_TO_LABEL[alias]
            if label in result.sections:
                continue
            if low == alias or low_full.startswith(alias + ":") or low_full.startswith(alias + " "):
                result.sections[label] = DetectedSection(
                    label=label, header_text=line, line_index=idx,
                )
                break

    result.present_labels = sorted(result.sections.keys())
    return result


def detected_section_labels(text: str) -> List[str]:
    """Convenience: sorted list of detected canonical section labels."""
    return detect_sections(text).present_labels
