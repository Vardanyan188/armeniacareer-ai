# src/engine/cv_quality.py
#
# CV-only intelligence — deterministic, no JD, no LLM, no orchestrator.
#
# Produces a CVQualityReport from a single resume file:
#   - detected skills (reusing the shared MVP skill aliases)
#   - section / contact presence
#   - missing or weak sections
#   - possible role-family directions (static skill→role map)
#   - concrete improvement suggestions
#   - a simple 0..1 quality score
#
# This path intentionally does NOT touch run_analysis / PayloadAssembler — a
# CV-quality review does not require a job description.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

from src.engine.adapters import MVP_SKILL_ALIASES
from src.engine.cv_recommendations import (
    ats_risks,
    collect_strengths,
    detect_soft_skills,
    is_student_or_junior,
    language_level_recommendations,
    page_count_recommendations,
    section_order_recommendations,
    skill_organization_recommendations,
)
from src.guardrails.input_guardrail import mask_pii
from src.preprocessing.document_loader import load_resume_text
from src.preprocessing.language_proficiency import parse_languages
from src.preprocessing.language_utils import detect_languages
from src.preprocessing.parsing_quality import assess_parsing_quality
from src.preprocessing.section_detector import detect_sections, detected_section_labels, section_content
from src.preprocessing.skill_extractor import extract_skill_tokens, merge_skills

PathLike = Union[str, Path]

# Canonical section labels this report tracks (subset of the detector's labels).
_TRACKED_SECTIONS = ["experience", "education", "skills", "summary"]

# Boundary-guarded skill patterns (same approach used elsewhere).
_SKILL_PATTERNS = {
    canonical: [
        re.compile(r"(?<![a-z0-9])" + re.escape(alias.lower()) + r"(?![a-z0-9])")
        for alias in aliases
    ]
    for canonical, aliases in MVP_SKILL_ALIASES.items()
}

# Section header cues (English / Armenian / Russian).
_SECTION_KEYWORDS: Dict[str, List[str]] = {
    "experience": ["experience", "work history", "employment", "աշխատանք", "փորձ", "опыт работы", "опыт"],
    "education": ["education", "degree", "university", "կրթություն", "образование", "университет"],
    "skills": ["skills", "technologies", "tech stack", "հմտություն", "навыки", "технологии"],
    "summary": ["summary", "objective", "profile", "about me", "ամփոփում", "о себе"],
}

_LANGUAGE_KEYWORDS: Dict[str, List[str]] = {
    "English": ["english", "անգլերեն", "английск"],
    "Armenian": ["armenian", "հայերեն", "армянск"],
    "Russian": ["russian", "ռուսերեն", "русск"],
    "French": ["french", "ֆրանսերեն", "французск"],
    "German": ["german", "գերմաներեն", "немецк"],
}

# Role family → indicative canonical skills (deterministic, extensible).
_ROLE_FAMILIES: Dict[str, set] = {
    "Backend Engineer": {"Python", "Java", "Go", "C#", "SQL", "PostgreSQL", "Django", "FastAPI", "Flask", "Node.js"},
    "Frontend Engineer": {"JavaScript", "TypeScript", "React", "Angular", "Vue", "Node.js"},
    "Data Analyst / Scientist": {"Python", "SQL", "Excel", "Power BI", "Tableau", "Spark"},
    "Data Engineer": {"SQL", "Spark", "Airflow", "Kafka", "ClickHouse", "Python"},
    "DevOps / Cloud Engineer": {"Docker", "Kubernetes", "AWS", "Azure", "GCP", "Linux"},
}

_MIN_ROLE_OVERLAP = 2


@dataclass
class CVQualityReport:
    detected_skills: List[str] = field(default_factory=list)
    skill_count: int = 0
    sections_present: Dict[str, bool] = field(default_factory=dict)
    missing_sections: List[str] = field(default_factory=list)
    contact_info_present: bool = False
    languages: List[str] = field(default_factory=list)
    word_count: int = 0
    role_suggestions: List[str] = field(default_factory=list)
    improvement_suggestions: List[str] = field(default_factory=list)
    quality_score: float = 0.0
    # Extraction-quality diagnostics (Phase 10).
    extraction_quality_band: str = "good"
    is_probably_scanned: bool = False
    extraction_reasons: List[str] = field(default_factory=list)
    # Safe runtime diagnostics (Phase 24.3 hotfix) — metadata only, no CV text.
    diagnostics: Dict[str, object] = field(default_factory=dict)
    # Advisory layer (Phase 24.2) — all additive, default empty.
    languages_with_levels: List[dict] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    improvement_recommendations: List[str] = field(default_factory=list)
    ats_risks: List[str] = field(default_factory=list)
    section_order_recommendations: List[str] = field(default_factory=list)
    language_level_recommendations: List[str] = field(default_factory=list)
    skill_organization_recommendations: List[str] = field(default_factory=list)


def _detect_skills(low_text: str) -> List[str]:
    found: List[str] = []
    for canonical, patterns in _SKILL_PATTERNS.items():
        if any(p.search(low_text) for p in patterns):
            found.append(canonical)
    return found


def _detect_sections(low_text: str) -> Dict[str, bool]:
    return {
        section: any(kw in low_text for kw in cues)
        for section, cues in _SECTION_KEYWORDS.items()
    }


def _detect_languages(low_text: str) -> List[str]:
    return [lang for lang, cues in _LANGUAGE_KEYWORDS.items() if any(c in low_text for c in cues)]


# Content cues that imply a section even when its heading is unusual or the text
# order is messy (e.g. a two-column PDF). Used only to ADD presence, never remove.
_EDU_CONTENT_CUES = [
    "university", "bachelor", "master", "faculty", "diploma", "phd", "b.sc", "m.sc",
    "b.s.", "m.s.", "institute", "college", "high school", "gpa", "degree",
    # Armenian / Russian
    "համալսարան", "բակալավր", "մագիստրոս", "ֆակուլտետ", "դպրոց",
    "университет", "бакалавр", "магистр", "факультет", "институт", "колледж",
]
_EXP_ROLE_CUES = [
    "intern", "internship", "engineer", "developer", "analyst", "manager",
    "team lead", "tech lead", "consultant", "specialist", "designer", "company",
    "ltd", "llc",
    # Armenian / Russian
    "ընկերություն", "պրակտիկա", "մասնագետ", "ծրագրավորող", "մենեջեր",
    "компания", "стажировка", "инженер", "разработчик", "специалист", "менеджер",
]
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _augment_sections(sections: Dict[str, bool], low_text: str, skill_count: int) -> Dict[str, bool]:
    """Adds section presence from content cues (heading-agnostic robustness)."""
    if not sections.get("education") and any(c in low_text for c in _EDU_CONTENT_CUES):
        sections["education"] = True
    if not sections.get("experience") and _YEAR_RE.search(low_text) \
            and any(c in low_text for c in _EXP_ROLE_CUES):
        sections["experience"] = True
    if not sections.get("skills") and skill_count >= 2:
        sections["skills"] = True
    return sections


def _suggest_roles(skills: List[str]) -> List[str]:
    skill_set = set(skills)
    scored = []
    for family, family_skills in _ROLE_FAMILIES.items():
        overlap = len(skill_set & family_skills)
        if overlap >= _MIN_ROLE_OVERLAP:
            scored.append((overlap, family))
    scored.sort(key=lambda x: (-x[0], x[1]))
    suggestions = [family for _, family in scored[:3]]
    if not suggestions:
        suggestions = ["General IT / Entry-level (broaden and specialise your skill set)"]
    return suggestions


def _improvements(
    sections: Dict[str, bool],
    contact_present: bool,
    skill_count: int,
    word_count: int,
    has_metric: bool,
) -> List[str]:
    tips: List[str] = []
    if not contact_present:
        tips.append("Add contact information (a professional email).")
    if not sections.get("summary"):
        tips.append("Add a short professional summary at the top.")
    if not sections.get("skills"):
        tips.append("Add a dedicated Skills section listing tools and technologies.")
    if not sections.get("experience"):
        tips.append("Add a Work Experience section with roles, dates, and outcomes.")
    if not sections.get("education"):
        tips.append("Add an Education section.")
    if skill_count < 3:
        tips.append("List more concrete technical skills relevant to your target role.")
    if word_count < 150:
        tips.append("Expand your CV — it currently looks too short to be informative.")
    if not has_metric:
        tips.append("Add measurable achievements (numbers, %, or impact statements).")
    return tips


def _single_char_ratio(text: str) -> float:
    tokens = text.split()
    if not tokens:
        return 0.0
    singles = sum(1 for tok in tokens if len(tok) == 1 and tok.isalpha())
    return singles / len(tokens)


def repair_spacing(text: str) -> str:
    """
    Repairs character-spaced PDF extraction (a common pypdf failure on some CVs),
    e.g. 'C O M P U T E R   S K I L L S' / 'P y t h o n'. Words are separated by
    runs of 2+ spaces, letters within a word by single spaces — so we collapse
    single spaces inside each 2+-space-delimited chunk. No-op on normal text.
    """
    if _single_char_ratio(text) < 0.40 or len(text.split()) < 30:
        return text
    out_lines: List[str] = []
    for line in text.split("\n"):
        if not line.strip():
            out_lines.append("")
            continue
        chunks = re.split(r" {2,}", line.strip())
        words = [re.sub(r"\s+", "", chunk) for chunk in chunks]
        out_lines.append(" ".join(w for w in words if w))
    return "\n".join(out_lines)


def analyze_cv_quality(cv_path: PathLike, page_count: Optional[int] = None) -> CVQualityReport:
    """
    Deterministic CV-only quality analysis. No JD, no LLM, no orchestrator.

    `page_count` is optional layout metadata; when provided, page-density advice
    is added. When None it is never guessed.
    """
    raw_text = load_resume_text(cv_path)
    # Repair character-spaced extraction before any detection runs.
    text = repair_spacing(raw_text)
    spacing_repaired = text != raw_text
    low_text = text.lower()
    source_ext = Path(cv_path).suffix

    # Extraction-quality assessment (robust, multilingual; flags scanned PDFs).
    quality = assess_parsing_quality(text, source_ext=source_ext)

    # Contact detection from the original text (before any masking of display).
    _, pii_fields = mask_pii(text)
    contact_present = any(f in pii_fields for f in ("email", "phone")) or \
        any(kw in low_text for kw in ("email", "e-mail", "phone", "հեռախոս", "эл. почта"))

    curated_skills = _detect_skills(low_text)
    # Open-vocabulary skills: extracted ONLY from a detected skills section, so
    # unknown tools are captured while summary/profile prose is never mined.
    open_vocab = extract_skill_tokens("\n".join(section_content(text, "skills")))
    skills = merge_skills(curated_skills, open_vocab)
    # Robust multilingual section detection (canonical labels → tracked subset),
    # then augment from content cues so unusual headings / two-column layouts
    # don't produce false "missing section" results.
    detected_labels = set(detected_section_labels(text))
    sections = {s: (s in detected_labels) for s in _TRACKED_SECTIONS}
    sections = _augment_sections(sections, low_text, len(skills))
    # A detected Contact heading also counts as contact present.
    contact_present = contact_present or ("contact" in detected_labels)
    languages = detect_languages(text)
    word_count = len(text.split())
    has_metric = ("%" in text) or bool(re.search(r"\b\d{2,}\b", text))

    missing_sections = [s for s, present in sections.items() if not present]
    improvements = _improvements(sections, contact_present, len(skills), word_count, has_metric)
    if quality.is_probably_scanned:
        improvements.insert(
            0,
            "This looks like a scanned/image PDF with no text layer. Upload a "
            "text-based PDF or DOCX for an accurate analysis.",
        )

    # Simple, transparent quality score over 8 binary signals.
    signals = [
        contact_present,
        sections.get("summary", False),
        sections.get("skills", False),
        sections.get("experience", False),
        sections.get("education", False),
        len(skills) >= 3,
        word_count >= 150,
        has_metric,
    ]
    quality_score = round(sum(1 for s in signals if s) / len(signals), 3)

    # ── Advisory layer (Phase 24.2) — additive, deterministic, no PII ──────────
    detection = detect_sections(text)
    ordered_labels = [
        lbl for lbl, _ in sorted(detection.sections.items(), key=lambda kv: kv[1].line_index)
    ]
    has_experience = sections.get("experience", False)
    student = is_student_or_junior(low_text, has_experience)

    profs = parse_languages("\n".join(section_content(text, "languages")) or text)
    soft_in_skills = detect_soft_skills("\n".join(section_content(text, "skills")))
    is_technical = len(skills) >= 1

    section_recs = section_order_recommendations(
        ordered_labels, has_experience=has_experience, is_student=student,
    )
    skill_org_recs = skill_organization_recommendations(
        skills, soft_in_skills, is_technical_role=is_technical,
    )
    lang_recs = language_level_recommendations(profs)
    page_recs = page_count_recommendations(page_count, is_student=student)
    risks = ats_risks(text, sections)
    strengths = collect_strengths(
        contact_present=contact_present, sections_present=sections,
        skill_count=len(skills), has_metric=has_metric, languages=languages,
    )

    improvement_recommendations = (
        improvements + section_recs + skill_org_recs + lang_recs + page_recs
    )

    # Safe diagnostics (metadata only; no raw CV text, no PII).
    diagnostics = {
        "analyzer": "analyze_cv_quality",
        "source_ext": source_ext,
        "raw_word_count": len(raw_text.split()),
        "repaired_word_count": word_count,
        "raw_line_count": raw_text.count("\n") + 1,
        "single_char_ratio_raw": round(_single_char_ratio(raw_text), 3),
        "spacing_repaired": spacing_repaired,
        "detected_section_labels": sorted(detected_labels),  # generic labels only
        "languages_count": len(languages),
        "language_levels": [d.get("normalized_level") for d in
                            [p.to_dict() for p in profs]],
    }

    return CVQualityReport(
        detected_skills=skills,
        skill_count=len(skills),
        sections_present=sections,
        missing_sections=missing_sections,
        contact_info_present=contact_present,
        languages=languages,
        word_count=word_count,
        role_suggestions=_suggest_roles(skills),
        improvement_suggestions=improvements,
        quality_score=quality_score,
        extraction_quality_band=quality.extraction_quality_band,
        is_probably_scanned=quality.is_probably_scanned,
        extraction_reasons=quality.reasons,
        diagnostics=diagnostics,
        languages_with_levels=[p.to_dict() for p in profs],
        strengths=strengths,
        improvement_recommendations=improvement_recommendations,
        ats_risks=risks,
        section_order_recommendations=section_recs,
        language_level_recommendations=lang_recs,
        skill_organization_recommendations=skill_org_recs,
    )
