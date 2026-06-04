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
# Phase 24.3 hotfix — character-spaced PDF extraction repair
# ---------------------------------------------------------------------------

_CHAR_SPACED_CV = """P R O F I L E
M o t i v a t e d   s t u d e n t

C O N T A C T   M E
f a k e @ e x a m p l e . c o m

E D U C A T I O N
B S c   C S   2 0 1 9 - 2 0 2 3

L A N G U A G E
N a t i v e   A r m e n i a n
A d v a n c e d   E n g l i s h

C O M P U T E R   S K I L L S
M S   O f f i c e
P y t h o n
S Q L
H T M L / C S S / J a v a S c r i p t

W O R K   E X P E R I E N C E
S o f t w a r e   E n g i n e e r
"""


def test_char_spaced_extraction_is_repaired(tmp_path):
    r = analyze_cv_quality(_write(tmp_path, _CHAR_SPACED_CV, name="spaced.txt"))
    assert r.diagnostics["spacing_repaired"] is True
    assert r.diagnostics["single_char_ratio_raw"] >= 0.4
    assert r.sections_present["summary"] and r.sections_present["education"]
    assert r.sections_present["experience"] and r.sections_present["skills"]
    assert {"Python", "SQL", "MS Office", "HTML", "CSS", "JavaScript"} <= set(r.detected_skills)
    assert "Software Engineer" not in r.detected_skills
    assert r.quality_score >= 0.65


def test_repair_spacing_is_noop_on_normal_text(tmp_path):
    r = analyze_cv_quality(_write(tmp_path, _GOOD_CV))
    assert r.diagnostics["spacing_repaired"] is False
    assert r.quality_score > 0.8           # unchanged behavior


def test_layout_diagnostics_present_and_page_count_passthrough(tmp_path):
    r = analyze_cv_quality(_write(tmp_path, _GOOD_CV), page_count=2)
    assert r.diagnostics["page_count"] == 2
    assert "layout" in r.diagnostics and "warnings" in r.diagnostics["layout"]
    # Clean CV → no layout warnings (no false alarm).
    assert r.diagnostics["layout_warnings"] == []


def test_layout_warnings_for_char_spaced_cv(tmp_path):
    r = analyze_cv_quality(_write(tmp_path, _CHAR_SPACED_CV, name="spaced2.txt"))
    assert r.diagnostics["layout_warnings"]   # template/headings/char-spaced advisory present
    assert "cv.layout.warn_template" in r.diagnostics["layout_warnings"]


def test_repair_spacing_unit():
    from src.engine.cv_quality import repair_spacing
    # Repair only triggers on a realistically char-spaced document (>=30 tokens,
    # high single-char ratio) — protecting short/normal text from being altered.
    repaired = repair_spacing(_CHAR_SPACED_CV)
    assert "COMPUTER SKILLS" in repaired
    assert "Python" in repaired and "SQL" in repaired
    # Normal text is returned unchanged (guard not met).
    normal = "Python, SQL, Docker and Kubernetes for backend services and pipelines."
    assert repair_spacing(normal) == normal


def test_candidate_upload_path_repairs_char_spacing(tmp_path):
    # Mirrors mode_candidate exactly: temp_upload(uploaded) -> analyze_cv_quality(path).
    from src.ui.upload_utils import temp_upload

    class _Fake:
        def __init__(self, name, data):
            self.name = name
            self._data = data

        def getvalue(self):
            return self._data

    fake = _Fake("candidate_cv.txt", _CHAR_SPACED_CV.encode("utf-8"))
    with temp_upload(fake) as path:
        r = analyze_cv_quality(str(path))
    assert r.sections_present["skills"] is True
    assert {"Python", "SQL"} <= set(r.detected_skills)
    assert r.quality_score >= 0.65


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


# ---------------------------------------------------------------------------
# Phase 24.3 hotfix — real-CV-template regression (synthetic, fake PII only)
# ---------------------------------------------------------------------------

_REAL_TEMPLATE_CV = """PROFILE
Motivated computer engineering student and educator.

CONTACT ME
fake.person@example.com
+374 00 000000
Yerevan

VOLUNTEER EXPERIENCE
Coding club mentor

EDUCATION
BSc Computer Engineering, Some University 2019-2023

LANGUAGE
Native Armenian
Advanced English
Advanced Russian

COMPUTER SKILLS
MS Office
Python
SQL
HTML/CSS/JavaScript
Scratch/Kturtle/FreeCad

WORK EXPERIENCE
Intership at Improvise company
Software Engineer
Team Lead at Armath Engineering laboratory
"""


def test_real_template_cv_full_regression(tmp_path):
    r = analyze_cv_quality(_write(tmp_path, _REAL_TEMPLATE_CV, name="cv_real.txt"))
    # Sections detected despite non-standard headings.
    assert r.sections_present["summary"] is True       # PROFILE
    assert r.sections_present["education"] is True
    assert r.sections_present["experience"] is True    # WORK / VOLUNTEER EXPERIENCE
    assert r.sections_present["skills"] is True         # COMPUTER SKILLS
    assert r.contact_info_present is True               # CONTACT ME + email/phone
    # Skills extracted, slash-lists split, NO job titles leaking in.
    found = set(r.detected_skills)
    assert {"MS Office", "Python", "SQL", "HTML", "CSS", "JavaScript",
            "Scratch", "KTurtle", "FreeCAD"} <= found
    assert "Software Engineer" not in found and "Team Lead" not in found
    # Languages with levels (level written BEFORE the name).
    levels = {d["language_name"]: d["normalized_level"] for d in r.languages_with_levels}
    assert levels.get("Armenian") == "Native"
    assert levels.get("English") == "Advanced"
    assert levels.get("Russian") == "Advanced"
    # Score reflects a mostly-parseable CV — not a 12% false-low.
    assert r.quality_score >= 0.65


def test_skills_exclude_names_titles_and_institution_artifacts(tmp_path):
    # Mirrors a real Canva CV where the skills block bled in sidebar name/title/
    # university tokens and a broken "business >>" artifact.
    cv = (
        "COMPUTER SKILLS\n"
        "SRBUHI\nKHACHATRYAN\nStudent\nYEREVAN STATE UNIVERSITY\nbusiness >>\n"
        "MS Office\nPython\nSQL\nHTML/CSS/JavaScript\nScratch/Kturtle/FreeCad\n"
    )
    r = analyze_cv_quality(_write(tmp_path, cv, name="canva.txt"))
    found = set(r.detected_skills)
    # Valid technical skills remain.
    assert {"MS Office", "Python", "SQL", "HTML", "CSS", "JavaScript",
            "Scratch", "KTurtle", "FreeCAD"} <= found
    # Names / titles / institutions / artifacts are excluded.
    for bad in ("SRBUHI", "KHACHATRYAN", "Student", "YEREVAN STATE UNIVERSITY",
                "business >>", "YEREVAN", "UNIVERSITY", "STATE", "business"):
        assert bad not in found


def test_known_acronyms_survive_uppercase_filter():
    from src.preprocessing.skill_extractor import extract_skill_tokens
    toks = extract_skill_tokens("SQL, HTML, CSS, BI, CRM, ERP, AWS")
    assert {"SQL", "HTML", "CSS", "BI", "CRM", "ERP", "AWS"} <= set(toks)
    # Person-name-like all-caps tokens are dropped.
    assert extract_skill_tokens("SRBUHI, KHACHATRYAN") == []


def test_computer_skills_maps_to_skills_section(tmp_path):
    r = analyze_cv_quality(_write(tmp_path, "COMPUTER SKILLS\nPython, SQL\n", name="cs.txt"))
    assert r.sections_present["skills"] is True


def test_contact_me_maps_to_contact(tmp_path):
    r = analyze_cv_quality(_write(tmp_path, "CONTACT ME\nfake@example.com\n", name="cm.txt"))
    assert r.contact_info_present is True


def test_profile_maps_to_summary(tmp_path):
    r = analyze_cv_quality(_write(tmp_path, "PROFILE\nMotivated student.\n", name="pr.txt"))
    assert r.sections_present["summary"] is True


def test_skills_do_not_bleed_into_work_experience(tmp_path):
    # COMPUTER SKILLS followed by WORK EXPERIENCE must not pull job titles in.
    cv = (
        "COMPUTER SKILLS\nPython, SQL\n"
        "WORK EXPERIENCE\nSoftware Engineer\nTeam Lead at Armath\n"
    )
    r = analyze_cv_quality(_write(tmp_path, cv, name="bleed.txt"))
    assert "Software Engineer" not in r.detected_skills
    assert {"Python", "SQL"} <= set(r.detected_skills)


def test_two_column_merged_headers_regression(tmp_path):
    # Simulates a two-column PDF extraction that glues two headers per line.
    merged = (
        "PROFILE                 EDUCATION\n"
        "Student.                BSc CS 2019-2023\n"
        "CONTACT ME              WORK EXPERIENCE\n"
        "fake@example.com        Software Engineer 2022\n"
        "COMPUTER SKILLS\n"
        "Python, SQL, MS Office\n"
    )
    r = analyze_cv_quality(_write(tmp_path, merged, name="merged.txt"))
    assert r.sections_present["summary"] is True
    assert r.sections_present["education"] is True
    assert r.sections_present["experience"] is True
    assert r.sections_present["skills"] is True
    assert {"Python", "SQL", "MS Office"} <= set(r.detected_skills)
    assert "Software Engineer" not in r.detected_skills
    assert r.quality_score >= 0.5


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
