# tests/test_cv_recommendations.py
#
# Phase 24.2 — CV advisory layer. Synthetic fake data only.

from src.engine.cv_recommendations import (
    ats_risks,
    detect_soft_skills,
    is_student_or_junior,
    language_level_recommendations,
    page_count_recommendations,
    section_order_recommendations,
    skill_organization_recommendations,
)
from src.preprocessing.language_proficiency import LanguageProficiency


# ---------------------------------------------------------------------------
# Section order
# ---------------------------------------------------------------------------

def test_recommend_experience_above_education_when_experience_exists():
    recs = section_order_recommendations(
        ["contact", "education", "experience", "skills"],
        has_experience=True, is_student=False,
    )
    assert any("Work Experience above Education" in r for r in recs)


def test_no_warning_for_student_education_before_experience():
    recs = section_order_recommendations(
        ["contact", "education", "experience", "skills"],
        has_experience=True, is_student=True,
    )
    assert not any("Work Experience above Education" in r for r in recs)


def test_no_warning_when_no_experience():
    recs = section_order_recommendations(
        ["contact", "education", "skills"], has_experience=False, is_student=True,
    )
    assert not any("Work Experience above Education" in r for r in recs)


def test_skills_before_languages_recommendation():
    recs = section_order_recommendations(
        ["contact", "languages", "skills"], has_experience=False, is_student=True,
    )
    assert any("Skills section before Languages" in r for r in recs)


def test_is_student_or_junior_detection():
    assert is_student_or_junior("Computer science student at YSU", True) is True
    assert is_student_or_junior("Senior engineer with 8 years", True) is False
    assert is_student_or_junior("no work history here", False) is True   # no experience


# ---------------------------------------------------------------------------
# Hard/soft skill organization
# ---------------------------------------------------------------------------

def test_detect_soft_skills_in_skills_section():
    soft = detect_soft_skills("Python, SQL, communication, teamwork, responsibility")
    assert "communication" in soft and "teamwork" in soft


def test_recommend_separate_and_technical_first():
    recs = skill_organization_recommendations(
        ["Python", "SQL"], ["communication", "teamwork"], is_technical_role=True,
    )
    assert any("Technical Skills" in r and "Soft Skills" in r for r in recs)
    assert any("technical skills before soft skills" in r.lower() for r in recs)


def test_no_skill_org_rec_when_no_soft_skills():
    recs = skill_organization_recommendations(["Python", "SQL"], [], is_technical_role=True)
    assert recs == []


# ---------------------------------------------------------------------------
# Language level clarity
# ---------------------------------------------------------------------------

def test_visual_only_language_recommendation():
    profs = [LanguageProficiency("English", "★★★★☆", "Advanced", "medium", True)]
    recs = language_level_recommendations(profs)
    assert any("visual-only language levels" in r.lower() for r in recs)


def test_no_language_rec_for_clear_levels():
    profs = [LanguageProficiency("English", "B2", "Upper-Intermediate", "high", False)]
    assert language_level_recommendations(profs) == []


# ---------------------------------------------------------------------------
# Page count
# ---------------------------------------------------------------------------

def test_junior_two_page_warning():
    recs = page_count_recommendations(2, is_student=True)
    assert any("single page" in r.lower() for r in recs)


def test_no_page_warning_without_metadata():
    assert page_count_recommendations(None, is_student=True) == []
    assert page_count_recommendations(1, is_student=True) == []


# ---------------------------------------------------------------------------
# ATS risks
# ---------------------------------------------------------------------------

def test_ats_flags_icon_density_and_missing_headings():
    text = "★ ★ ★ ✦ ✦ ✦ ➤ ➤\nSome heading\n"
    risks = ats_risks(text, {"experience": False, "education": False, "skills": False})
    assert any("icons" in r.lower() for r in risks)
    assert any("standard headings" in r.lower() for r in risks)


def test_ats_no_false_alarm_on_clean_cv():
    text = "Work Experience\nEngineer\n\nEducation\nBSc\n\nSkills\nPython, SQL\n"
    risks = ats_risks(text, {"experience": True, "education": True, "skills": True})
    assert risks == []
