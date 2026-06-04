# tests/test_cv_quality.py
#
# Deterministic CV-only analyzer tests. Temp .txt files only, no JD, no LLM,
# no orchestrator, no data/raw, no network.

from src.engine.cv_quality import CVQualityReport, analyze_cv_quality


_GOOD_CV = """
Professional Summary
Backend engineer with 4 years building APIs.

Work Experience
Acme — Backend Engineer (2020-2024)
- Built REST services in Python and Django, reduced latency by 40%.
- Deployed on Docker and PostgreSQL.

Skills
Python, Django, Docker, PostgreSQL, SQL, Git

Education
BSc Computer Science, YSU

Languages
English, Armenian

Contact: dev@example.com
"""


def _write(tmp_path, text, name="cv.txt"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_analyze_cv_quality_detects_skills_and_sections(tmp_path):
    report = analyze_cv_quality(_write(tmp_path, _GOOD_CV))
    assert isinstance(report, CVQualityReport)
    assert {"Python", "Django", "Docker", "PostgreSQL"} <= set(report.detected_skills)
    assert report.sections_present["experience"] is True
    assert report.sections_present["education"] is True
    assert report.sections_present["skills"] is True
    assert report.sections_present["summary"] is True
    assert report.contact_info_present is True
    assert "English" in report.languages
    assert report.quality_score > 0.8


def test_analyze_cv_quality_suggests_roles(tmp_path):
    report = analyze_cv_quality(_write(tmp_path, _GOOD_CV))
    # Python/Django/Docker/PostgreSQL → Backend family should rank.
    assert any("Backend" in r for r in report.role_suggestions)


def test_analyze_cv_quality_flags_weak_cv(tmp_path):
    weak = "I worked somewhere. I know things."
    report = analyze_cv_quality(_write(tmp_path, weak))
    assert report.skill_count == 0
    assert "skills" in report.missing_sections
    assert report.contact_info_present is False
    assert report.quality_score < 0.5
    assert len(report.improvement_suggestions) >= 3
    # No recognised skills → generic role direction.
    assert report.role_suggestions


def test_analyze_cv_quality_role_fallback_when_no_skills(tmp_path):
    report = analyze_cv_quality(_write(tmp_path, "Some prose with no tech terms at all."))
    assert report.role_suggestions
    assert "General" in report.role_suggestions[0]


def test_analyze_cv_quality_exposes_extraction_fields(tmp_path):
    report = analyze_cv_quality(_write(tmp_path, _GOOD_CV))
    assert report.extraction_quality_band in {"good", "partial", "low"}
    assert report.is_probably_scanned is False
    assert isinstance(report.extraction_reasons, list)


# Synthetic CV mimicking the failing real-CV template — FAKE personal data only.
_NONSTANDARD_CV = """
PROFILE
Motivated computer-science student seeking an internship. Quick learner with
hands-on project work and a strong interest in software and data.

CONTACT ME
Email: fake.student@example.com
Phone: +374 00 000000
City: Yerevan

EDUCATION
BSc Computer Science, Some University (2021-2025), GPA 3.8

WORK EXPERIENCE
Intern, Example Software LLC (2023)
- Built small tools and helped the engineering team with testing.

VOLUNTEER EXPERIENCE
Coding club mentor (2022) — taught 20 students basic programming.

LANGUAGE
English, Armenian

COMPUTER SKILLS
Python, SQL, HTML/CSS/JavaScript, MS Office, Scratch/Kturtle/FreeCad
"""


def test_nonstandard_cv_is_parsed_robustly(tmp_path):
    report = analyze_cv_quality(_write(tmp_path, _NONSTANDARD_CV, name="cv_ns.txt"))

    # Sections recognised despite non-standard headings.
    assert report.sections_present["summary"] is True       # PROFILE
    assert report.sections_present["education"] is True      # EDUCATION
    assert report.sections_present["experience"] is True     # WORK EXPERIENCE
    assert report.sections_present["skills"] is True         # COMPUTER SKILLS
    assert report.contact_info_present is True               # email/phone + CONTACT ME

    # Skills extracted, including slash-separated lists split on boundaries.
    found = set(report.detected_skills)
    assert {"Python", "SQL", "HTML", "CSS", "JavaScript"} <= found
    assert {"Scratch", "KTurtle", "FreeCAD"} <= found
    assert "MS Office" in found

    # Quality score is meaningfully higher than a false-low (< 0.5) result.
    assert report.quality_score >= 0.75

    # No real PII leaks into the structured report (fake data only here anyway).
    assert "fake.student@example.com" not in report.detected_skills


def test_education_detected_from_content_without_heading(tmp_path):
    # No EDUCATION heading, but content cues (university + year) should count.
    cv = "PROFILE\nstudent\n\nStudied at Some University, BSc 2024.\n\nCOMPUTER SKILLS\nPython, SQL\n"
    report = analyze_cv_quality(_write(tmp_path, cv, name="cv_edu.txt"))
    assert report.sections_present["education"] is True


# ---------------------------------------------------------------------------
# Phase 24.2 — advisory layer integration
# ---------------------------------------------------------------------------

_MIXED_SKILLS_CV = """
PROFILE
Backend developer.

WORK EXPERIENCE
Engineer, Company (2019-2023)

EDUCATION
BSc CS

SKILLS
Python, SQL, Docker, communication, teamwork, responsibility

LANGUAGES
English ★★★★☆
Armenian Native
"""


def test_advisory_skill_organization_and_language_warning(tmp_path):
    r = analyze_cv_quality(_write(tmp_path, _MIXED_SKILLS_CV, name="cv_mix.txt"))
    # Hard + soft skills in one section → separation recommendation.
    assert any("Soft Skills" in x for x in r.skill_organization_recommendations)
    # Visual-only language level → clarity recommendation.
    assert any("visual-only" in x.lower() for x in r.language_level_recommendations)
    # Language levels surfaced (structured), languages not in technical skills.
    assert r.languages_with_levels
    low_skills = {s.lower() for s in r.detected_skills}
    assert "english" not in low_skills and "armenian" not in low_skills
    # Strengths present for a complete CV.
    assert r.strengths


def test_advisory_page_count_metadata(tmp_path):
    student_cv = "PROFILE\nComputer science student.\n\nEDUCATION\nBSc 2025\n\nSKILLS\nPython\n"
    with_pages = analyze_cv_quality(_write(tmp_path, student_cv, name="cv_pg.txt"), page_count=2)
    assert any("single page" in x.lower() for x in with_pages.improvement_recommendations)
    # No page metadata → no page advice.
    without_pages = analyze_cv_quality(_write(tmp_path, student_cv, name="cv_pg2.txt"))
    assert not any("single page" in x.lower() for x in without_pages.improvement_recommendations)


def test_advisory_section_order_experience_above_education(tmp_path):
    r = analyze_cv_quality(_write(tmp_path, _MIXED_SKILLS_CV, name="cv_order.txt"))
    # Experience exists and is not a student CV → recommend experience above education?
    # In this CV experience already precedes education, so NO such recommendation.
    assert not any("Work Experience above Education" in x for x in r.section_order_recommendations)


def test_analyze_cv_quality_detects_multilingual_sections(tmp_path):
    hy_cv = (
        "Ամփոփում\nՓորձառու ծրագրավորող։\n\n"
        "Աշխատանքային փորձ\nԸնկերություն — Ծրագրավորող\n2020–2023\n\n"
        "Հմտություններ\nPython, SQL, Docker\n"
    )
    report = analyze_cv_quality(_write(tmp_path, hy_cv, name="cv_hy.txt"))
    assert report.sections_present["experience"] is True
    assert report.sections_present["summary"] is True
    assert report.sections_present["skills"] is True
    assert "Armenian" in report.languages
