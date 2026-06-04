# src/engine/adapters.py
#
# Adapter layer: converts the existing modules' output objects into the
# canonical schema objects defined in src/schemas/canonical_payload.py.
#
# Why this exists:
#   The Phase-1 agents speak a richer, extraction-oriented dialect
#   (ParsedCVOutput, SemanticAlignmentOutput, SkillsOntologyOutput) and the
#   raw JD inputs are plain JSON dicts. The PayloadAssembler, however, consumes
#   the canonical CVEntities / JDEntities / SemanticAnalysis / SkillsOntologyResult.
#   This module is the single, deterministic, LLM-free translation point.
#
# Hard rules honoured here:
#   - No LLM calls. JD skill/section extraction is pure keyword/heuristic logic.
#   - No raw PII leaves the CV mapping (masked_identifier is preserved as-is;
#     names / summaries / contact details are not copied into the canonical object).
#   - Tolerant inputs: the *_to_canonical helpers accept either a real agent
#     output (with a to_canonical_* method), an already-canonical object, a
#     duck-typed object, or a plain dict.

from __future__ import annotations

import re
from typing import Any, List, Optional, Union

from src.schemas.canonical_payload import (
    CVEntities,
    EducationEntry,
    GapSeverity,
    JDEntities,
    SemanticAnalysis,
    SeniorityLevel,
    SkillCategory,
    SkillEntry,
    SkillMatchEntry,
    SkillsOntologyResult,
    WorkExperience,
)

# ParsedCVOutput imported for type-hints / structural mapping. cv_parsing_schema
# depends only on pydantic, so this import is light and dependency-safe.
from src.schemas.cv_parsing_schema import ParsedCVOutput


# ===========================================================================
# Small helpers
# ===========================================================================

def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Reads an attribute from an object or a key from a dict, with a default."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _enum_value(value: Any) -> Any:
    """Returns the underlying .value for an Enum, otherwise the value itself."""
    return getattr(value, "value", value)


# ===========================================================================
# Normalisers
# ===========================================================================

def normalize_skill_category(value: Any) -> SkillCategory:
    """
    Coerces a category (canonical enum, the cv_parsing_schema enum, or a string)
    into a canonical SkillCategory. Unknown values default to TECHNICAL.
    """
    if isinstance(value, SkillCategory):
        return value
    raw = str(_enum_value(value)).strip().lower()
    try:
        return SkillCategory(raw)
    except ValueError:
        return SkillCategory.TECHNICAL


def normalize_seniority(value: Any) -> SeniorityLevel:
    """
    Coerces a seniority (canonical enum, the cv_parsing_schema enum, or a string)
    into a canonical SeniorityLevel. Unknown values default to JUNIOR.
    """
    if isinstance(value, SeniorityLevel):
        return value
    raw = str(_enum_value(value)).strip().lower()
    try:
        return SeniorityLevel(raw)
    except ValueError:
        return SeniorityLevel.JUNIOR


# Title keyword → seniority overrides, checked in order (first hit wins).
_TITLE_LEVEL_RULES = [
    (SeniorityLevel.EXECUTIVE, ["chief", "cto", "ceo", "cfo", "vp ", "vice president", "head of", "director"]),
    (SeniorityLevel.PRINCIPAL, ["principal"]),
    (SeniorityLevel.LEAD, ["lead", "team lead", "tech lead", "engineering manager"]),
    (SeniorityLevel.INTERN, ["intern", "trainee"]),
    (SeniorityLevel.SENIOR, ["senior", "sr."]),
    (SeniorityLevel.MID, ["middle", "mid-level", "mid level"]),
    (SeniorityLevel.JUNIOR, ["junior", "jr."]),
]


def infer_seniority_from_years(years: float, title: Optional[str] = None) -> SeniorityLevel:
    """
    Deterministically infers seniority. An explicit level signal in the title
    takes precedence over years-of-experience; otherwise a years ladder applies:
        < 1y → junior, 1–3y → junior, 3–6y → mid, 6–10y → senior, 10y+ → lead.
    """
    t = (title or "").lower()
    for level, keywords in _TITLE_LEVEL_RULES:
        if any(kw in t for kw in keywords):
            return level

    try:
        y = float(years)
    except (TypeError, ValueError):
        y = 0.0

    if y < 3:
        return SeniorityLevel.JUNIOR
    if y < 6:
        return SeniorityLevel.MID
    if y < 10:
        return SeniorityLevel.SENIOR
    return SeniorityLevel.LEAD


# ===========================================================================
# CV: ParsedCVOutput → CVEntities
# ===========================================================================

def parsed_cv_to_cv_entities(parsed_cv: ParsedCVOutput) -> CVEntities:
    """
    Maps the rich ParsedCVOutput onto the canonical CVEntities subset.
    Does not copy any raw PII — masked_identifier is preserved verbatim and
    free-text personal fields (names, contact, professional_summary) are dropped.
    """
    work_history: List[WorkExperience] = []
    for exp in parsed_cv.work_history:
        work_history.append(WorkExperience(
            company=exp.company,
            title=exp.title,
            start_date=getattr(exp, "start_date_raw", None),
            end_date=getattr(exp, "end_date_raw", None),
            duration_months=exp.duration_months,
            responsibilities=list(exp.responsibilities or []),
            technologies_mentioned=list(exp.technologies_mentioned or []),
            domain=exp.domain,
        ))

    education: List[EducationEntry] = []
    for edu in parsed_cv.education:
        education.append(EducationEntry(
            institution=edu.institution,
            degree=edu.degree_label,
            field_of_study=edu.field_of_study,
            graduation_year=edu.graduation_year,
            is_relevant_to_role=edu.is_relevant_to_role,
        ))

    raw_skills: List[SkillEntry] = []
    for skill in parsed_cv.skills:
        raw_skills.append(SkillEntry(
            raw_name=skill.raw_name,
            canonical_name=skill.canonical_name,
            category=normalize_skill_category(skill.category),
            taxonomy_code=getattr(skill, "taxonomy_code", None),
            proficiency_signal=getattr(skill, "proficiency_signal", None),
        ))

    languages = [lp.language for lp in getattr(parsed_cv, "language_proficiencies", [])]
    certifications = [c.name for c in getattr(parsed_cv, "certifications", [])]

    return CVEntities(
        masked_identifier=parsed_cv.masked_identifier,
        contact_info_present=parsed_cv.contact_info_present,
        work_history=work_history,
        education=education,
        raw_skills=raw_skills,
        languages=languages,
        certifications=certifications,
        total_years_experience=parsed_cv.total_years_experience,
        inferred_seniority=normalize_seniority(parsed_cv.inferred_seniority),
        career_domain_signals=list(parsed_cv.career_domain_signals or []),
    )


# ===========================================================================
# JD: raw JSON → JDEntities  (deterministic, no LLM)
# ===========================================================================

# Canonical skill name → list of literal aliases to search for in JD text.
# Aliases are matched with alphanumeric-boundary guards so "java" does not hit
# "javascript", "git" does not hit "digital", etc.
MVP_SKILL_ALIASES = {
    "Python": ["python"],
    "JavaScript": ["javascript"],
    "TypeScript": ["typescript"],
    "Java": ["java"],
    "C#": ["c#", "csharp"],
    "Go": ["golang", "go programming"],
    "SQL": ["sql"],
    "PostgreSQL": ["postgresql", "postgres"],
    "MySQL": ["mysql"],
    "MongoDB": ["mongodb", "mongo"],
    "Redis": ["redis"],
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"],
    "AWS": ["aws", "amazon web services"],
    "Azure": ["azure"],
    "GCP": ["gcp", "google cloud"],
    "React": ["react"],
    "Angular": ["angular"],
    "Vue": ["vue"],
    "Node.js": ["node.js", "nodejs", "node js"],
    "Django": ["django"],
    "FastAPI": ["fastapi"],
    "Flask": ["flask"],
    "REST API": ["rest api", "restful", "rest apis"],
    "GraphQL": ["graphql"],
    "Kafka": ["kafka"],
    "Airflow": ["airflow"],
    "Spark": ["spark"],
    "ClickHouse": ["clickhouse"],
    "Power BI": ["power bi", "powerbi"],
    "Tableau": ["tableau"],
    "Excel": ["excel"],
    "Git": ["git"],
    "Linux": ["linux"],
}

# Phrases that mark a line as describing *preferred* (not required) skills.
_PREFERRED_INDICATORS = [
    "preferred", "nice to have", "nice-to-have", "a plus", "is a plus",
    "advantage", "an advantage", "bonus", "desirable", "would be a plus",
    "not required", "good to have", "plus but not required",
]

# Section header keywords (English / Armenian / Russian).
_RESP_HEADER_KW = [
    "responsibilit", "duties", "what you will", "you will", "job description",
    "պարտականություն", "обязанности", "задачи",
]
_QUAL_HEADER_KW = [
    "requirement", "qualification", "necessary skills", "required skills",
    "what we expect", "we expect", "professional skills", "skills",
    "անհրաժեշտ", "պահանջ", "հմտություն", "требовани", "квалификаци", "навыки",
]


def _alias_pattern(alias: str) -> "re.Pattern[str]":
    return re.compile(r"(?<![a-z0-9])" + re.escape(alias.lower()) + r"(?![a-z0-9])")


# Pre-compile alias patterns once.
_COMPILED_SKILL_PATTERNS = {
    canonical: [_alias_pattern(a) for a in aliases]
    for canonical, aliases in MVP_SKILL_ALIASES.items()
}


def _is_header(line: str, keywords: List[str]) -> bool:
    low = line.lower()
    if not any(kw in low for kw in keywords):
        return False
    # Headers are short or colon-terminated; this avoids treating long sentences
    # that merely contain "skills"/"requirements" as section switches.
    return line.endswith(":") or len(line) <= 35


def _is_junk_line(line: str) -> bool:
    low = line.lower()
    if len(line) < 4:
        return True
    if "@" in line or "http" in low or "📎" in line or "*" in line:
        return True
    if line.replace(" ", "").isdigit():
        return True
    junk_tokens = ["apply", "դիմել", "կցել", "пода", "terms", "պայմաններ", "contact", "կոնտակտ"]
    if any(tok in low for tok in junk_tokens):
        return True
    if re.search(r"\(?\d{2,}\)?[\d\s\-]{5,}", line):  # phone-like
        return True
    return False


def _clean_line(line: str) -> str:
    return line.lstrip("•-*–·●◦ \t").strip()


def _extract_sections(raw_text: str) -> tuple[List[str], List[str]]:
    """
    Splits raw JD text into (responsibilities, qualifications) line lists using
    deterministic header detection. Junk/form/footer lines are filtered. Each
    list is capped to keep payloads compact.
    """
    responsibilities: List[str] = []
    qualifications: List[str] = []
    current: Optional[str] = None
    cap = 12

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _is_header(line, _RESP_HEADER_KW):
            current = "resp"
            continue
        if _is_header(line, _QUAL_HEADER_KW):
            current = "qual"
            continue
        if current is None or _is_junk_line(line):
            continue

        cleaned = _clean_line(line)
        if len(cleaned) < 4:
            continue
        cleaned = cleaned[:300]
        if current == "resp" and len(responsibilities) < cap and cleaned not in responsibilities:
            responsibilities.append(cleaned)
        elif current == "qual" and len(qualifications) < cap and cleaned not in qualifications:
            qualifications.append(cleaned)

    return responsibilities, qualifications


def _extract_skills(raw_text: str) -> tuple[List[SkillEntry], List[SkillEntry]]:
    """
    Deterministic keyword skill extraction. A skill is classified as preferred
    only if every line mentioning it is a preferred-context line; otherwise it
    is required. Returns (required_skills, preferred_skills).
    """
    lines = raw_text.splitlines()
    lowered = [ln.lower() for ln in lines]
    preferred_flags = [
        any(ind in ln for ind in _PREFERRED_INDICATORS) for ln in lowered
    ]

    required: List[SkillEntry] = []
    preferred: List[SkillEntry] = []

    for canonical, patterns in _COMPILED_SKILL_PATTERNS.items():
        hit_lines = [
            i for i, ln in enumerate(lowered)
            if any(p.search(ln) for p in patterns)
        ]
        if not hit_lines:
            continue
        only_preferred = all(preferred_flags[i] for i in hit_lines)
        entry = SkillEntry(
            raw_name=canonical,
            canonical_name=canonical,
            category=SkillCategory.TECHNICAL,
        )
        if only_preferred:
            preferred.append(entry)
        else:
            required.append(entry)

    return required, preferred


def jd_json_to_jd_entities(jd: dict) -> JDEntities:
    """
    Builds a canonical JDEntities from a raw job-description dict (the structure
    found in data/raw/job_descriptions/*.json). Skills, responsibilities, and
    qualifications are extracted from raw_text with deterministic heuristics only.
    """
    if not isinstance(jd, dict):
        raise ValueError(f"jd_json_to_jd_entities expects a dict, got {type(jd).__name__}.")

    role_title = (jd.get("role_title") or "Unspecified Role").strip() or "Unspecified Role"
    company_name = jd.get("company_name")
    industry = (jd.get("industry") or "technology").strip() or "technology"
    geography = jd.get("geography")

    try:
        required_years = float(jd.get("required_experience_years") or 0.0)
    except (TypeError, ValueError):
        required_years = 0.0

    employment_type = _get(jd.get("meta") or {}, "employment_type")
    company_context = company_name
    if company_name and employment_type:
        company_context = f"{company_name} ({employment_type})"

    raw_text = jd.get("raw_text") or ""

    # Work arrangement heuristic from raw_text.
    low_text = raw_text.lower()
    work_arrangement: Optional[str] = None
    if "remote" in low_text:
        work_arrangement = "remote"
    elif "hybrid" in low_text:
        work_arrangement = "hybrid"
    elif "on-site" in low_text or "onsite" in low_text or "on site" in low_text:
        work_arrangement = "on-site"

    responsibilities, qualifications = _extract_sections(raw_text)
    required_skills, preferred_skills = _extract_skills(raw_text)

    # Fold the stated education level into the qualifications list, deterministically.
    edu_level = jd.get("required_education_level")
    if edu_level:
        qual_line = f"{edu_level} degree or equivalent"
        if qual_line not in qualifications:
            qualifications.insert(0, qual_line)

    return JDEntities(
        role_title=role_title,
        company_context=company_context,
        required_qualifications=qualifications,
        preferred_qualifications=[],
        responsibilities=responsibilities,
        required_skills=required_skills,
        preferred_skills=preferred_skills,
        required_experience_years=required_years,
        required_seniority=infer_seniority_from_years(required_years, role_title),
        industry=industry,
        location=geography,
        work_arrangement=work_arrangement,
    )


# ===========================================================================
# Agent output → canonical (tolerant unwrapping)
# ===========================================================================

def semantic_output_to_canonical(output: Union[Any, dict]) -> SemanticAnalysis:
    """
    Returns a canonical SemanticAnalysis from a SemanticAlignmentAgent output.
    Prefers output.to_canonical_semantic_analysis(); falls back to a manual,
    field-by-field map for already-canonical / duck-typed / dict inputs.
    """
    if isinstance(output, SemanticAnalysis):
        return output

    method = getattr(output, "to_canonical_semantic_analysis", None)
    if callable(method):
        return method()

    return SemanticAnalysis(
        embedding_cosine_similarity=float(_get(output, "embedding_cosine_similarity", 0.0)),
        key_phrase_overlap_ratio=float(_get(output, "key_phrase_overlap_ratio", 0.0)),
        cv_unique_key_phrases=list(_get(output, "cv_unique_key_phrases", []) or []),
        jd_unique_key_phrases=list(_get(output, "jd_unique_key_phrases", []) or []),
        shared_key_phrases=list(_get(output, "shared_key_phrases", []) or []),
        contextual_domain_alignment=float(_get(output, "contextual_domain_alignment", 0.0)),
    )


def skills_output_to_canonical(output: Union[Any, dict]) -> SkillsOntologyResult:
    """
    Returns a canonical SkillsOntologyResult from a SkillsOntologyAgent output.
    Prefers output.to_canonical_skills_result(); falls back to a manual map for
    already-canonical / duck-typed / dict inputs.
    """
    if isinstance(output, SkillsOntologyResult):
        return output

    method = getattr(output, "to_canonical_skills_result", None)
    if callable(method):
        return method()

    def _entries(name: str) -> List[SkillMatchEntry]:
        raw = _get(output, name, []) or []
        return [e if isinstance(e, SkillMatchEntry) else SkillMatchEntry(**e) for e in raw]

    return SkillsOntologyResult(
        matched_skills=_entries("matched_skills"),
        missing_critical=_entries("missing_critical"),
        missing_preferred=_entries("missing_preferred"),
        transferable=_entries("transferable"),
        total_required_skills=int(_get(output, "total_required_skills", 0)),
        matched_count=int(_get(output, "matched_count", 0)),
        critical_gap_count=int(_get(output, "critical_gap_count", 0)),
        coverage_ratio=float(_get(output, "coverage_ratio", 0.0)),
        gap_severity=_get(output, "gap_severity", GapSeverity.MODERATE),
    )
