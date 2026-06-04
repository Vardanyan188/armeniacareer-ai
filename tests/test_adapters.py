# tests/test_adapters.py
#
# Lightweight, dependency-safe tests for the adapter layer.
# - Uses only in-memory pydantic objects / dicts / SimpleNamespace.
# - Does NOT import the live agents (avoids instructor/langchain requirements).
# - Does NOT call any LLM and does NOT read private data files.

from types import SimpleNamespace

import pytest

from src.engine.adapters import (
    infer_seniority_from_years,
    jd_json_to_jd_entities,
    normalize_seniority,
    normalize_skill_category,
    parsed_cv_to_cv_entities,
    semantic_output_to_canonical,
    skills_output_to_canonical,
)
from src.schemas.canonical_payload import (
    CVEntities,
    GapSeverity,
    JDEntities,
    SemanticAnalysis,
    SeniorityLevel,
    SkillCategory,
    SkillsOntologyResult,
)
from src.schemas.cv_parsing_schema import (
    CEFRLevel,
    DegreeLevel,
    LanguageProficiency,
    ParsedCertification,
    ParsedCVOutput,
    ParsedEducationEntry,
    ParsedSkillEntry,
    ParsedWorkExperience,
)
from src.schemas.cv_parsing_schema import SeniorityLevel as ParsedSeniority
from src.schemas.cv_parsing_schema import SkillCategory as ParsedSkillCategory


# ---------------------------------------------------------------------------
# Normalisers
# ---------------------------------------------------------------------------

def test_normalize_skill_category():
    assert normalize_skill_category("technical") == SkillCategory.TECHNICAL
    assert normalize_skill_category(ParsedSkillCategory.SOFT) == SkillCategory.SOFT
    assert normalize_skill_category(SkillCategory.DOMAIN) == SkillCategory.DOMAIN
    assert normalize_skill_category("nonsense") == SkillCategory.TECHNICAL


def test_normalize_seniority():
    assert normalize_seniority("senior") == SeniorityLevel.SENIOR
    assert normalize_seniority(ParsedSeniority.LEAD) == SeniorityLevel.LEAD
    assert normalize_seniority(SeniorityLevel.MID) == SeniorityLevel.MID
    assert normalize_seniority("nonsense") == SeniorityLevel.JUNIOR


def test_infer_seniority_from_years_ladder():
    assert infer_seniority_from_years(0.5) == SeniorityLevel.JUNIOR
    assert infer_seniority_from_years(4) == SeniorityLevel.MID
    assert infer_seniority_from_years(7) == SeniorityLevel.SENIOR
    assert infer_seniority_from_years(12) == SeniorityLevel.LEAD


def test_infer_seniority_title_overrides_years():
    assert infer_seniority_from_years(2, "Senior Data Analyst") == SeniorityLevel.SENIOR
    assert infer_seniority_from_years(1, "Engineering Lead") == SeniorityLevel.LEAD
    assert infer_seniority_from_years(1, "Software Engineering Intern") == SeniorityLevel.INTERN
    assert infer_seniority_from_years(20, "Head of Engineering") == SeniorityLevel.EXECUTIVE


# ---------------------------------------------------------------------------
# parsed_cv_to_cv_entities
# ---------------------------------------------------------------------------

def _make_parsed_cv() -> ParsedCVOutput:
    return ParsedCVOutput(
        masked_identifier="[CANDIDATE]",
        contact_info_present=True,
        work_history=[ParsedWorkExperience(
            company="Picsart",
            title="Software Engineer",
            start_date_raw="2021-01",
            end_date_raw="2023-06",
            responsibilities=["Built REST APIs"],
            technologies_mentioned=["Python", "FastAPI"],
            domain="saas",
        )],
        education=[ParsedEducationEntry(
            institution="YSU",
            degree_level=DegreeLevel.BACHELOR,
            degree_label="BSc Computer Science",
            field_of_study="Computer Science",
            graduation_year=2020,
            is_relevant_to_role=True,
        )],
        skills=[
            ParsedSkillEntry(raw_name="Python", canonical_name="Python", category=ParsedSkillCategory.TECHNICAL),
            ParsedSkillEntry(raw_name="Leadership", canonical_name="Leadership", category=ParsedSkillCategory.SOFT),
        ],
        language_proficiencies=[LanguageProficiency(language="English", cefr_level=CEFRLevel.C1)],
        certifications=[ParsedCertification(name="AWS Certified Developer")],
        inferred_seniority=ParsedSeniority.MID,
        career_domain_signals=["saas", "fintech"],
    )


def test_parsed_cv_to_cv_entities_maps_all_sections():
    pcv = _make_parsed_cv()
    ce = parsed_cv_to_cv_entities(pcv)

    assert isinstance(ce, CVEntities)
    assert ce.masked_identifier == "[CANDIDATE]"
    assert ce.contact_info_present is True

    assert len(ce.work_history) == 1
    we = ce.work_history[0]
    assert we.company == "Picsart"
    assert we.start_date == "2021-01"      # mapped from start_date_raw
    assert we.end_date == "2023-06"        # mapped from end_date_raw
    assert "Python" in we.technologies_mentioned

    assert ce.education[0].degree == "BSc Computer Science"  # mapped from degree_label
    assert ce.education[0].field_of_study == "Computer Science"
    assert ce.education[0].is_relevant_to_role is True

    assert len(ce.raw_skills) == 2
    assert ce.raw_skills[0].category == SkillCategory.TECHNICAL
    assert ce.raw_skills[1].category == SkillCategory.SOFT

    assert ce.languages == ["English"]
    assert ce.certifications == ["AWS Certified Developer"]
    assert ce.inferred_seniority == SeniorityLevel.MID
    assert ce.career_domain_signals == ["saas", "fintech"]
    # total_years_experience is preserved verbatim from the (validated) source object
    assert ce.total_years_experience == pcv.total_years_experience
    assert ce.total_years_experience > 0  # ~2.4y from the 2021-01..2023-06 role


def test_parsed_cv_does_not_leak_summary_or_names():
    pcv = _make_parsed_cv()
    pcv.professional_summary = "My name is Jane Doe, jane@example.com"
    ce = parsed_cv_to_cv_entities(pcv)
    blob = ce.model_dump_json()
    assert "Jane Doe" not in blob
    assert "jane@example.com" not in blob
    assert ce.masked_identifier == "[CANDIDATE]"


# ---------------------------------------------------------------------------
# jd_json_to_jd_entities
# ---------------------------------------------------------------------------

def _sample_jd() -> dict:
    return {
        "role_title": "Backend Engineer",
        "company_name": "Acme",
        "industry": "fintech",
        "geography": "Armenia",
        "required_experience_years": 3.0,
        "required_education_level": "Bachelor",
        "meta": {"employment_type": "Full-time"},
        "raw_text": (
            "Responsibilities:\n"
            "Build REST API services in Python and Django.\n"
            "Necessary skills:\n"
            "Strong SQL and PostgreSQL knowledge. Docker required.\n"
            "Kubernetes is a plus.\n"
        ),
    }


def test_jd_json_to_jd_entities_basic_fields():
    je = jd_json_to_jd_entities(_sample_jd())
    assert isinstance(je, JDEntities)
    assert je.role_title == "Backend Engineer"
    assert je.industry == "fintech"
    assert je.location == "Armenia"
    assert je.company_context == "Acme (Full-time)"
    assert je.required_experience_years == 3.0
    assert je.required_seniority == SeniorityLevel.MID


def test_jd_json_skill_extraction_required_vs_preferred():
    je = jd_json_to_jd_entities(_sample_jd())
    required = {s.canonical_name for s in je.required_skills}
    preferred = {s.canonical_name for s in je.preferred_skills}

    assert {"Python", "Django", "SQL", "PostgreSQL", "Docker", "REST API"} <= required
    assert "Kubernetes" in preferred
    assert "Kubernetes" not in required


def test_jd_json_section_extraction_and_education():
    je = jd_json_to_jd_entities(_sample_jd())
    assert any("REST API" in r or "Python" in r for r in je.responsibilities)
    assert any("Bachelor" in q for q in je.required_qualifications)


def test_jd_json_requires_dict():
    with pytest.raises(ValueError):
        jd_json_to_jd_entities(["not", "a", "dict"])  # type: ignore[arg-type]


def test_jd_json_minimal_dict_is_valid():
    je = jd_json_to_jd_entities({"role_title": "Data Analyst"})
    assert je.role_title == "Data Analyst"
    assert je.industry == "technology"
    assert je.required_experience_years == 0.0


# ---------------------------------------------------------------------------
# semantic_output_to_canonical
# ---------------------------------------------------------------------------

def test_semantic_output_uses_to_canonical_method():
    class FakeSem:
        def to_canonical_semantic_analysis(self):
            return SemanticAnalysis(
                embedding_cosine_similarity=0.11,
                key_phrase_overlap_ratio=0.22,
                contextual_domain_alignment=0.33,
            )

    sa = semantic_output_to_canonical(FakeSem())
    assert isinstance(sa, SemanticAnalysis)
    assert sa.embedding_cosine_similarity == 0.11


def test_semantic_output_manual_map_from_namespace():
    ns = SimpleNamespace(
        embedding_cosine_similarity=0.8,
        key_phrase_overlap_ratio=0.5,
        cv_unique_key_phrases=["a"],
        jd_unique_key_phrases=["b"],
        shared_key_phrases=["c"],
        contextual_domain_alignment=0.7,
    )
    sa = semantic_output_to_canonical(ns)
    assert sa.embedding_cosine_similarity == 0.8
    assert sa.shared_key_phrases == ["c"]


def test_semantic_output_passthrough_canonical():
    sa_in = SemanticAnalysis(
        embedding_cosine_similarity=0.5,
        key_phrase_overlap_ratio=0.5,
        contextual_domain_alignment=0.5,
    )
    assert semantic_output_to_canonical(sa_in) is sa_in


# ---------------------------------------------------------------------------
# skills_output_to_canonical
# ---------------------------------------------------------------------------

def test_skills_output_uses_to_canonical_method():
    class FakeSkills:
        def to_canonical_skills_result(self):
            return SkillsOntologyResult(total_required_skills=0, matched_count=0, coverage_ratio=0.0)

    res = skills_output_to_canonical(FakeSkills())
    assert isinstance(res, SkillsOntologyResult)


def test_skills_output_manual_map_from_namespace():
    ns = SimpleNamespace(
        matched_skills=[],
        missing_critical=[],
        missing_preferred=[],
        transferable=[],
        total_required_skills=2,
        matched_count=1,
        critical_gap_count=1,
        coverage_ratio=0.5,
        gap_severity=GapSeverity.MODERATE,
    )
    res = skills_output_to_canonical(ns)
    assert res.total_required_skills == 2
    assert res.coverage_ratio == 0.5


def test_skills_output_manual_map_from_dict_with_entries():
    d = {
        "matched_skills": [{"skill_name": "Python", "canonical_name": "Python", "match_type": "matched"}],
        "missing_critical": [],
        "missing_preferred": [],
        "transferable": [],
        "total_required_skills": 1,
        "matched_count": 1,
        "critical_gap_count": 0,
        "coverage_ratio": 1.0,
        "gap_severity": "minor",
    }
    res = skills_output_to_canonical(d)
    assert len(res.matched_skills) == 1
    assert res.matched_skills[0].canonical_name == "Python"
    assert res.gap_severity == GapSeverity.MINOR
