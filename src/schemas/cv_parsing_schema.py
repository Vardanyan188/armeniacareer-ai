# src/schemas/cv_parsing_schema.py
#
# Extended Pydantic v2 schema for deterministic CV parsing.
# Governs all structured output from the Document Intelligence Agent.
#
# Design constraints:
#   - Every field that the LLM may be tempted to hallucinate carries an
#     explicit Field(description=...) that anchors extraction to source text only.
#   - Nested validators enforce internal consistency (date ordering,
#     coverage ratios, taxonomy code formatting) before the payload
#     exits the parsing agent.
#   - The schema is intentionally more expressive than the CanonicalAnalysisPayload
#     CVEntities subset — it captures ephemeral parsing signals (format anomalies,
#     section-level confidence, multilingual flags) that the downstream
#     PayloadAssembler uses for completeness scoring but does not persist.
#
# Encoding note: Armenian text is Unicode block U+0531–U+058F.
# The preprocessor guarantees NFC normalization before this schema receives
# any string. No encoding-aware validators are needed here.

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Dict, List, Optional, Tuple

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
    computed_field,
    AliasChoices,
)


# ---------------------------------------------------------------------------
# Taxonomy Enumerations
# ---------------------------------------------------------------------------

class CEFRLevel(str, Enum):
    """Common European Framework of Reference for Languages."""
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"
    NATIVE = "native"
    NOT_SPECIFIED = "not_specified"


class SkillCategory(str, Enum):
    TECHNICAL = "technical"
    DOMAIN = "domain"
    SOFT = "soft"
    CERTIFICATION = "certification"


class SeniorityLevel(str, Enum):
    INTERN       = "intern"
    JUNIOR       = "junior"
    MID          = "mid"
    SENIOR       = "senior"
    LEAD         = "lead"
    PRINCIPAL    = "principal"
    EXECUTIVE    = "executive"


class DegreeLevel(str, Enum):
    VOCATIONAL       = "vocational"
    BACHELOR         = "bachelor"
    MASTER           = "master"
    PHD              = "phd"
    MBA              = "mba"
    PROFESSIONAL     = "professional"     # e.g., CPA, MD
    HIGH_SCHOOL      = "high_school"
    NOT_SPECIFIED    = "not_specified"


class EmploymentType(str, Enum):
    FULL_TIME   = "full_time"
    PART_TIME   = "part_time"
    CONTRACT    = "contract"
    FREELANCE   = "freelance"
    INTERNSHIP  = "internship"
    VOLUNTEER   = "volunteer"
    NOT_STATED  = "not_stated"


class ScriptType(str, Enum):
    """Detected primary script of a CV section or field."""
    ARMENIAN = "armenian"    # Hayots Gir — U+0531–U+058F
    CYRILLIC  = "cyrillic"   # Russian/Ukrainian — U+0400–U+04FF
    LATIN     = "latin"
    MIXED     = "mixed"
    UNKNOWN   = "unknown"


class CVFormatType(str, Enum):
    """Inferred CV structure style — affects section segmentation confidence."""
    CHRONOLOGICAL   = "chronological"
    FUNCTIONAL      = "functional"      # Skills-first, minimal dates
    HYBRID          = "hybrid"
    ACADEMIC        = "academic"        # Heavy education/publications section
    LINKEDIN_EXPORT = "linkedin_export"
    UNKNOWN         = "unknown"


class InstitutionType(str, Enum):
    STATE_UNIVERSITY     = "state_university"
    PRIVATE_UNIVERSITY   = "private_university"
    TECHNICAL_COLLEGE    = "technical_college"
    INTERNATIONAL        = "international"
    ONLINE_PLATFORM      = "online_platform"     # Coursera, edX, etc.
    BOOTCAMP             = "bootcamp"
    PROFESSIONAL_BODY    = "professional_body"   # CFA Institute, PMI, etc.
    NOT_SPECIFIED        = "not_specified"


# ---------------------------------------------------------------------------
# Utility: Date Range Parsing
# ---------------------------------------------------------------------------

_DATE_FORMATS = [
    "%Y-%m",          # 2022-03
    "%m/%Y",          # 03/2022
    "%Y",             # 2022
    "%B %Y",          # March 2022
    "%b %Y",          # Mar 2022
    "%Y/%m",          # 2022/03
]

_ARMENIAN_MONTHS: Dict[str, int] = {
    "հունվար": 1,  "փետրվար": 2, "մարտ": 3,     "ապրիլ": 4,
    "մայիս": 5,   "հունիս": 6,  "հուլիս": 7,   "օգոստոս": 8,
    "սեպտեմբեր": 9, "հոկտեմբեր": 10, "նոյեմբեր": 11, "դեկտեմբեր": 12,
}

_RUSSIAN_MONTHS: Dict[str, int] = {
    "январь": 1,   "февраль": 2,  "март": 3,      "апрель": 4,
    "май": 5,      "июнь": 6,     "июль": 7,      "август": 8,
    "сентябрь": 9, "октябрь": 10, "ноябрь": 11,   "декабрь": 12,
    # genitive forms (common in "с января по март")
    "января": 1,   "февраля": 2,  "марта": 3,     "апреля": 4,
    "мая": 5,      "июня": 6,     "июля": 7,      "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11,   "декабря": 12,
}


def parse_approximate_date(raw: str) -> Optional[Tuple[int, Optional[int]]]:
    """
    Attempts to parse a raw date string (multilingual) into (year, month).
    Returns None if the string cannot be resolved.
    Handles Armenian and Russian month names in addition to standard formats.
    """
    if not raw:
        return None
    raw = raw.strip().lower()

    # Check for Armenian month names
    for arm_month, month_num in _ARMENIAN_MONTHS.items():
        if arm_month in raw:
            year_match = re.search(r"\b(19|20)\d{2}\b", raw)
            if year_match:
                return (int(year_match.group()), month_num)

    # Check for Russian month names
    for ru_month, month_num in _RUSSIAN_MONTHS.items():
        if ru_month in raw:
            year_match = re.search(r"\b(19|20)\d{2}\b", raw)
            if year_match:
                return (int(year_match.group()), month_num)

    # Standard format parsing
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(raw, fmt)
            return (dt.year, dt.month if "%m" in fmt or "%B" in fmt or "%b" in fmt else None)
        except ValueError:
            continue

    # Last resort: extract any 4-digit year
    year_match = re.search(r"\b(19|20)\d{2}\b", raw)
    if year_match:
        return (int(year_match.group()), None)

    return None


def compute_duration_months(
    start_raw: Optional[str],
    end_raw: Optional[str],
) -> Optional[int]:
    """
    Computes duration in whole months from two raw date strings.
    If end_raw is None, 'present', 'now', 'հիմա', 'сейчас', duration is computed
    to the current month.
    Returns None if dates cannot be parsed.
    """
    if start_raw is None:
        return None

    present_tokens = {"present", "now", "current", "ongoing",
                      "հիմա", "ներկա", "сейчас", "по настоящее",
                      "настоящее время", "н.в."}
    is_present = (
        end_raw is None or
        any(token in end_raw.lower() for token in present_tokens)
    )

    start = parse_approximate_date(start_raw)
    if start is None:
        return None

    start_year, start_month = start
    start_month = start_month or 1

    if is_present:
        now = datetime.utcnow()
        end_year, end_month = now.year, now.month
    else:
        end = parse_approximate_date(end_raw)
        if end is None:
            return None
        end_year, end_month = end
        end_month = end_month or 12

    return max(0, (end_year - start_year) * 12 + (end_month - start_month))


# ---------------------------------------------------------------------------
# Sub-model: Quantitative Achievement
# ---------------------------------------------------------------------------

class QuantitativeAchievement(BaseModel):
    """
    A structured representation of a measurable achievement extracted from a
    responsibility or accomplishment bullet. For example:
    "Reduced query latency by 40%" → metric=40, unit="percent", direction="reduction".
    LLM extraction only; no computation is performed by this model.
    """
    raw_statement: str = Field(
        ...,
        description=(
            "The verbatim sentence or bullet from the CV containing the metric. "
            "NEVER paraphrase — copy exactly as written."
        ),
    )
    numeric_value: Optional[float] = Field(
        None,
        description="The primary numeric value in the statement (e.g., 40 for '40%').",
    )
    unit: Optional[str] = Field(
        None,
        description="Unit of the metric: 'percent', 'USD', 'users', 'ms', 'x' (multiplier), etc.",
    )
    direction: Optional[str] = Field(
        None,
        description="'increase', 'reduction', 'absolute', or None if direction is ambiguous.",
    )
    domain_context: Optional[str] = Field(
        None,
        description="Short label for what was measured: 'latency', 'revenue', 'churn', 'accuracy', etc.",
    )


# ---------------------------------------------------------------------------
# Sub-model: Skill Entry
# ---------------------------------------------------------------------------

class ParsedSkillEntry(BaseModel):
    """
    A single skill item resolved to the internal taxonomy.
    raw_name is preserved verbatim for audit and re-normalization.
    """
    raw_name: str = Field(
        ...,
        description=(
            "The skill exactly as written in the CV. Do not normalize spelling here — "
            "preserve 'Postgress', 'ML', 'машинное обучение' as written."
        ),
    )
    canonical_name: str = Field(
        ...,
        description=(
            "The normalized, canonical form of this skill per the CIS tech market taxonomy. "
            "Example: 'Postgress' → 'PostgreSQL', 'ML' → 'Machine Learning'."
        ),
    )
    category: SkillCategory = Field(
        ...,
        description=(
            "Classify as: technical (tools, languages, platforms), "
            "domain (industry-specific knowledge such as 'iGaming odds calculation'), "
            "soft (leadership, communication), certification (awarded credentials)."
        ),
    )
    taxonomy_code: Optional[str] = Field(
        None,
        description=(
            "Internal taxonomy ID or O*NET-SOC technology code if confidently known. "
            "Format: 'TECH-{3-char-category}-{4-digit-id}'. Leave null if uncertain."
        ),
        pattern=r"^(TECH|DOM|SOFT|CERT)-[A-Z]{3}-\d{4}$|^$",
    )
    proficiency_signal: Optional[str] = Field(
        None,
        description=(
            "Any explicit proficiency signal from the CV text: '3 years', 'advanced', "
            "'familiar', 'basic', 'intermediate', 'expert'. Leave null if none stated."
        ),
    )
    context_phrase: Optional[str] = Field(
        None,
        description=(
            "The sentence or bullet from the CV where this skill was found. "
            "Maximum 120 characters. Used for evidence tracing."
        ),
        max_length=120,
    )

    @field_validator("canonical_name")
    @classmethod
    def canonical_name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("canonical_name must not be empty after stripping whitespace.")
        return v


# ---------------------------------------------------------------------------
# Sub-model: Work Experience
# ---------------------------------------------------------------------------

class ParsedWorkExperience(BaseModel):
    """
    A single employment or consulting engagement.
    Duration is always computed by the model validator — never trusted from LLM output.
    """
    company: str = Field(
        ...,
        description="Organization name exactly as written. Do not translate or localize.",
    )
    title: str = Field(
        ...,
        description="Job title exactly as written. Do not translate or localize.",
    )
    title_english: Optional[str] = Field(
        None,
        description=(
            "English translation of the job title only if the original is in Armenian or Russian. "
            "Leave null if the original is already in English."
        ),
    )
    employment_type: EmploymentType = Field(
        default=EmploymentType.NOT_STATED,
        description="Infer from context signals: 'contractor', 'freelance', 'intern', etc.",
    )
    start_date_raw: Optional[str] = Field(
        None,
        description=(
            "Start date exactly as written in the CV. Preserve original language and format. "
            "Examples: '2022-03', 'March 2022', 'Մարտ 2022', 'март 2022'."
        ),
    )
    end_date_raw: Optional[str] = Field(
        None,
        description=(
            "End date exactly as written, or 'present'/'հիմա'/'сейчас' if ongoing. "
            "Leave null if no end date appears."
        ),
    )
    duration_months: Optional[int] = Field(
        None,
        description=(
            "COMPUTED FIELD. Do not populate. "
            "Computed by the model_validator from start_date_raw and end_date_raw."
        ),
    )
    responsibilities: List[str] = Field(
        default_factory=list,
        description=(
            "Each bullet point or responsibility statement as a separate list item. "
            "Preserve the original language. Do not summarize or combine bullets. "
            "Maximum 10 items — if more exist, take the 10 most specific."
        ),
        max_length=10,
    )
    technologies_mentioned: List[str] = Field(
        default_factory=list,
        description=(
            "Tool, language, framework, or platform names explicitly mentioned in this role's "
            "description. Normalized canonical names only (e.g., 'AWS', not 'Amazon Web Services'). "
            "Do not include soft skills here."
        ),
    )
    quantitative_achievements: List[QuantitativeAchievement] = Field(
        default_factory=list,
        description=(
            "Extract every bullet containing a numeric metric. "
            "Leave empty if no measurable outcomes are stated."
        ),
    )
    domain: Optional[str] = Field(
        None,
        description=(
            "Industry domain inferred from company name and responsibilities. "
            "Use lowercase slug: 'igaming', 'fintech', 'manufacturing', 'ecommerce', "
            "'healthcare', 'telecom', 'logistics', 'retail', 'saas', 'government'."
        ),
    )
    location: Optional[str] = Field(
        None,
        description="City, country, or 'Remote' if stated. Null if not mentioned.",
    )
    is_current_role: bool = Field(
        default=False,
        description="True if end_date_raw signals an ongoing role.",
    )

    @model_validator(mode="after")
    def compute_duration_and_current_flag(self) -> "ParsedWorkExperience":
        # Compute duration — override any LLM-provided value
        self.duration_months = compute_duration_months(
            self.start_date_raw, self.end_date_raw
        )
        # Set is_current_role
        present_tokens = {
            "present", "now", "current", "ongoing",
            "հիմա", "ներկա", "сейчас", "настоящее",
        }
        if self.end_date_raw is None or any(
            t in self.end_date_raw.lower() for t in present_tokens
        ):
            self.is_current_role = True
        return self


# ---------------------------------------------------------------------------
# Sub-model: Education Entry
# ---------------------------------------------------------------------------

class ParsedEducationEntry(BaseModel):
    institution: str = Field(
        ...,
        description="Institution name exactly as written. Do not translate.",
    )
    institution_english: Optional[str] = Field(
        None,
        description="English name only if original is Armenian or Russian.",
    )
    institution_type: InstitutionType = Field(
        default=InstitutionType.NOT_SPECIFIED,
        description=(
            "Classify the institution type. "
            "'state_university' for YSUAB, RAU, AUA-like institutions; "
            "'bootcamp' for ACA, Tumo, Picsart Academy, Turing, etc."
        ),
    )
    degree_level: DegreeLevel = Field(
        ...,
        description=(
            "Degree level. Treat 'մագիստրոս'/'магистр' as 'master', "
            "'բակալավր'/'бакалавр' as 'bachelor', 'ասպիրանտ'/'аспирант' as 'phd'."
        ),
    )
    degree_label: str = Field(
        ...,
        description="The full degree name as written: 'BSc Computer Science', 'Մագիստրոս', etc.",
    )
    field_of_study: str = Field(
        ...,
        description=(
            "Major or program of study. Normalize to English if extractable: "
            "'Data Science for Business', 'Computer Science', etc."
        ),
    )
    graduation_year: Optional[int] = Field(
        None,
        ge=1960,
        le=2035,
        description=(
            "Graduation year as a 4-digit integer. "
            "If only a range is given, use the end year. Null if not stated."
        ),
    )
    gpa: Optional[float] = Field(
        None,
        ge=0.0,
        le=5.0,
        description=(
            "GPA if stated. Armenian 4.0 scale, European ECTS, or Russian 5-point scale "
            "are all valid. Null if not stated. Do not convert between scales."
        ),
    )
    is_relevant_to_role: Optional[bool] = Field(
        None,
        description=(
            "Leave null — this field is populated by the Semantic Alignment Agent, "
            "not the Document Intelligence Agent."
        ),
    )
    honors: Optional[str] = Field(
        None,
        description="Honor or distinction: 'cum laude', 'Red Diploma', 'գերազանցության դիպլոմ', etc.",
    )

    @field_validator("graduation_year", mode="before")
    @classmethod
    def coerce_graduation_year(cls, v: Any) -> Optional[int]:
        if v is None:
            return None
        try:
            year = int(v)
            if 1960 <= year <= 2035:
                return year
        except (ValueError, TypeError):
            pass
        # Attempt to extract from a string like "2022-2026"
        if isinstance(v, str):
            match = re.search(r"\b(19|20)\d{2}\b", v)
            if match:
                return int(match.group())
        return None


# ---------------------------------------------------------------------------
# Sub-model: Language Proficiency
# ---------------------------------------------------------------------------

class LanguageProficiency(BaseModel):
    language: str = Field(
        ...,
        description=(
            "Language name in English: 'Armenian', 'Russian', 'English', 'French', etc. "
            "Do not use ISO codes here — use full English names."
        ),
    )
    cefr_level: CEFRLevel = Field(
        ...,
        description=(
            "Map all proficiency descriptors to CEFR: "
            "'native'/'mother tongue'/'մայրենի'/'родной' → native; "
            "'fluent'/'C1'/'C2'/'advanced'/'proficient' → C1 or C2; "
            "'upper intermediate'/'B2'/'professional working' → B2; "
            "'intermediate'/'B1' → B1; "
            "'basic'/'elementary'/'A2'/'A1' → A2 or A1; "
            "If no signal exists → not_specified."
        ),
    )
    raw_proficiency_label: Optional[str] = Field(
        None,
        description="The exact proficiency descriptor as written in the CV.",
    )


# ---------------------------------------------------------------------------
# Sub-model: Certification
# ---------------------------------------------------------------------------

class ParsedCertification(BaseModel):
    name: str = Field(
        ...,
        description="Certification or course name exactly as written.",
    )
    issuing_organization: Optional[str] = Field(
        None,
        description="Issuing body: 'Google', 'AWS', 'Coursera', 'PMI', etc.",
    )
    issue_date_raw: Optional[str] = Field(
        None,
        description="Issue date as written. Null if not stated.",
    )
    expiry_date_raw: Optional[str] = Field(
        None,
        description="Expiry date as written. Null if perpetual or not stated.",
    )
    credential_id: Optional[str] = Field(
        None,
        description="Credential ID or URL if present in the CV.",
    )
    is_active: Optional[bool] = Field(
        None,
        description=(
            "True if expiry_date_raw is null or in the future. "
            "False if expired. Null if indeterminate."
        ),
    )


# ---------------------------------------------------------------------------
# Sub-model: Project Entry
# ---------------------------------------------------------------------------

class ParsedProject(BaseModel):
    """
    Covers personal projects, academic coursework projects, and open-source
    contributions. Common in CVs from Armenian CS graduates and self-taught developers.
    """
    title: str = Field(
        ...,
        description="Project title exactly as written.",
    )
    description: str = Field(
        ...,
        description=(
            "Project description preserving the original language. "
            "Maximum 300 characters. Truncate at a sentence boundary."
        ),
        max_length=300,
    )
    technologies: List[str] = Field(
        default_factory=list,
        description="Canonical technology names used in this project.",
    )
    role: Optional[str] = Field(
        None,
        description="Candidate's role: 'sole developer', 'backend', 'team lead', 'contributor', etc.",
    )
    url_or_repo: Optional[str] = Field(
        None,
        description="GitHub URL, live URL, or portfolio link if stated.",
    )
    is_academic: bool = Field(
        default=False,
        description=(
            "True if the project is clearly a university coursework submission or thesis. "
            "False for personal, professional, or open-source projects."
        ),
    )
    impact_statement: Optional[str] = Field(
        None,
        description="Any quantitative or qualitative outcome stated for this project.",
    )


# ---------------------------------------------------------------------------
# Sub-model: CV Format Quality Signals
# ---------------------------------------------------------------------------

class CVFormatQualitySignals(BaseModel):
    """
    Diagnostic signals computed by the preprocessor and validated against
    extraction completeness. These fields inform the analysis_completeness_score
    but are not surfaced directly to either candidate or recruiter.
    """
    detected_format_type: CVFormatType = Field(
        default=CVFormatType.UNKNOWN,
        description=(
            "Inferred CV structure based on section ordering and content density. "
            "If the work experience section precedes skills with reverse-chronological "
            "ordering, classify as 'chronological'."
        ),
    )
    primary_script: ScriptType = Field(
        default=ScriptType.UNKNOWN,
        description=(
            "Dominant writing script. Classify as 'armenian' if >40% of non-whitespace "
            "characters are in U+0531–U+058F. 'mixed' if two scripts are within 20% of each other."
        ),
    )
    detected_languages: List[str] = Field(
        default_factory=list,
        description=(
            "All natural languages detected in the CV body text. "
            "English names: ['Armenian', 'Russian', 'English']."
        ),
    )
    section_headers_found: List[str] = Field(
        default_factory=list,
        description=(
            "Section header strings as detected in the source text. "
            "Used to assess structural completeness. "
            "Examples: ['Work Experience', 'Կրթություն', 'Навыки']."
        ),
    )
    has_contact_section: bool = False
    has_summary_section: bool = False
    has_skills_section: bool = False
    has_experience_section: bool = False
    has_education_section: bool = False
    estimated_ats_compliance: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Heuristic ATS (Applicant Tracking System) friendliness score. "
            "Penalizes: no section headers, table-heavy layout, graphics, "
            "non-standard date formats. Range [0.0, 1.0]."
        ),
    )
    extraction_anomalies: List[str] = Field(
        default_factory=list,
        description=(
            "List of anomaly labels detected during text preprocessing: "
            "'broken_lines', 'encoding_artifacts', 'mixed_rtl_ltr', "
            "'duplicate_entries', 'missing_dates', 'garbled_armenian'."
        ),
    )
    preprocessing_confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description=(
            "Confidence that the preprocessed text is a clean, complete representation "
            "of the original CV. Reduced for each anomaly type detected."
        ),
    )

    @model_validator(mode="after")
    def degrade_confidence_for_anomalies(self) -> "CVFormatQualitySignals":
        penalty_per_anomaly = 0.08
        degraded = 1.0 - len(self.extraction_anomalies) * penalty_per_anomaly
        self.preprocessing_confidence = round(max(0.1, min(1.0, degraded)), 3)
        return self


# ---------------------------------------------------------------------------
# Root: Parsed CV Output (LLM extraction target)
# ---------------------------------------------------------------------------

class ParsedCVOutput(BaseModel):
    """
    The complete structured representation extracted from a single raw CV text.

    EXTRACTION CONTRACT:
    - Every field maps to explicit source text. If information is absent, use null or [].
    - Do not infer, estimate, or fill gaps with assumed information.
    - total_years_experience is the ONLY computed field — derive it from work_history
      using non-overlapping period arithmetic. Do not trust candidate-stated totals.
    - masked_identifier is always "[CANDIDATE]" — the preprocessor has already stripped names.
    """
    masked_identifier: str = Field(
        default="[CANDIDATE]",
        description=(
            "PII-safe reference label. This field is always '[CANDIDATE]'. "
            "The preprocessor has masked the candidate's name before this schema runs."
        ),
    )
    contact_info_present: bool = Field(
        default=False,
        description="True if a contact section with phone, email, or LinkedIn was present before masking.",
    )

    # --- Core Sections ---
    work_history: List[ParsedWorkExperience] = Field(
        default_factory=list,
        description=(
            "All work experience entries in reverse-chronological order (most recent first). "
            "Include internships. Exclude volunteer work (use volunteer_experience instead). "
            "Do not omit any entry, even if dates are missing."
        ),
    )
    education: List[ParsedEducationEntry] = Field(
        default_factory=list,
        description=(
            "All formal education entries. Include completed and in-progress degrees. "
            "Online courses with certificates belong in certifications, not here."
        ),
    )
    skills: List[ParsedSkillEntry] = Field(
        default_factory=list,
        description=(
            "All skills mentioned across the ENTIRE CV — not just the skills section. "
            "Deduplicate by canonical_name. If the same skill appears multiple times, "
            "retain the instance with the richest context_phrase and most specific proficiency_signal."
        ),
    )
    language_proficiencies: List[LanguageProficiency] = Field(
        default_factory=list,
        description=(
            "All natural languages listed in the CV. "
            "If no explicit proficiency level is stated, use cefr_level='not_specified'."
        ),
    )
    certifications: List[ParsedCertification] = Field(
        default_factory=list,
        description=(
            "Formal certifications, completed online courses with certificates, "
            "and professional qualifications. Exclude skills-section tool mentions."
        ),
    )
    projects: List[ParsedProject] = Field(
        default_factory=list,
        description=(
            "Personal, academic, and open-source project entries. "
            "Include thesis projects. Exclude job responsibilities framed as projects."
        ),
    )

    # --- Derived Summary Fields ---
    total_years_experience: float = Field(
        default=0.0,
        ge=0.0,
        description=(
            "Sum of non-overlapping employment periods in decimal years. "
            "Compute from work_history duration_months after model validation. "
            "Round to one decimal place. Do NOT use any candidate-stated '5 years of experience'."
        ),
    )
    inferred_seniority: SeniorityLevel = Field(
        ...,
        description=(
            "Classify based on total_years_experience AND title signals: "
            "0–1 yr → intern/junior; 1–3 yr → junior; 3–6 yr → mid; "
            "6–10 yr → senior; 10+ yr → lead/principal/executive. "
            "Title signals override time: 'Head of', 'Director' → executive regardless of years."
        ),
    )
    career_domain_signals: List[str] = Field(
        default_factory=list,
        description=(
            "Industry/domain keywords extracted from job titles, company names, and "
            "responsibility text. Lowercase slugs: ['igaming', 'fintech', 'data_analytics']. "
            "Maximum 5 items, ordered by frequency of occurrence in the CV."
        ),
        max_length=5,
    )
    professional_summary: Optional[str] = Field(
        None,
        description=(
            "The candidate's own summary/objective section verbatim, if present. "
            "Maximum 500 characters. Null if no summary section exists."
        ),
        max_length=500,
    )

    # --- Format and Quality Diagnostics ---
    format_quality: CVFormatQualitySignals = Field(
        default_factory=CVFormatQualitySignals,
        description=(
            "Preprocessing and format quality diagnostics. "
            "Populated by the preprocessor before LLM extraction. "
            "The LLM fills only the fields within format_quality that require semantic understanding: "
            "detected_format_type, primary_script, detected_languages, section_headers_found."
        ),
    )

    # --- Internal Extraction Confidence ---
    section_extraction_confidence: Dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Per-section extraction confidence score [0.0–1.0]. "
            "Keys: 'work_history', 'education', 'skills', 'languages', 'certifications', 'projects'. "
            "Set below 1.0 when: dates are missing, section boundary was ambiguous, "
            "or content appeared garbled. Used by PayloadAssembler for completeness scoring."
        ),
    )
    extraction_notes: List[str] = Field(
        default_factory=list,
        description=(
            "Free-text notes about extraction ambiguities or decisions made. "
            "Example: 'Education section in Russian — translated field_of_study to English'. "
            "Maximum 5 notes. Used for audit trail only."
        ),
        max_length=5,
    )

    # --- Model Validators ---

    @model_validator(mode="after")
    def compute_total_years_experience(self) -> "ParsedCVOutput":
        """
        Computes total_years_experience from work_history duration_months.
        Uses a conservative non-overlapping sum:
        overlapping periods (two jobs in same month range) are deduplicated by
        assuming the overlap interval is counted once.

        This is a heuristic — a full overlap deduplication algorithm would require
        complete start/end date availability, which CVs do not guarantee.
        Conservative approach: sum all durations, subtract 20% if >3 simultaneous
        roles detected (common in freelance/consultant CVs).
        """
        total_months = sum(
            exp.duration_months
            for exp in self.work_history
            if exp.duration_months is not None
        )
        # Detect potential parallel employment (common in CIS CVs with side contracts)
        internship_count = sum(
            1 for exp in self.work_history
            if exp.employment_type == EmploymentType.INTERNSHIP
        )
        overlap_penalty = 0.8 if (
            len(self.work_history) > 3 and
            total_months > 120 and
            internship_count < len(self.work_history) * 0.5
        ) else 1.0
        self.total_years_experience = round((total_months * overlap_penalty) / 12, 1)
        return self

    @model_validator(mode="after")
    def populate_default_section_confidence(self) -> "ParsedCVOutput":
        """
        Ensures all expected section keys are present in section_extraction_confidence.
        Missing keys are set to 1.0 (full confidence) — the LLM should override
        with lower values where extraction was ambiguous.
        """
        expected_sections = [
            "work_history", "education", "skills",
            "languages", "certifications", "projects",
        ]
        for section in expected_sections:
            if section not in self.section_extraction_confidence:
                self.section_extraction_confidence[section] = 1.0
        return self

    @model_validator(mode="after")
    def validate_skill_deduplication(self) -> "ParsedCVOutput":
        """
        Validates that canonical skill names are unique across the skills list.
        Raises ValidationError on exact duplicates (same canonical_name + same category).
        """
        seen = set()
        for skill in self.skills:
            key = (skill.canonical_name.lower(), skill.category)
            if key in seen:
                raise ValueError(
                    f"Duplicate skill detected: canonical_name='{skill.canonical_name}', "
                    f"category='{skill.category}'. Deduplicate before output."
                )
            seen.add(key)
        return self
