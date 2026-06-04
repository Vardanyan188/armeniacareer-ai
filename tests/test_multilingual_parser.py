# tests/test_multilingual_parser.py
#
# Phase 24.1 — multilingual CV parsing + open-vocabulary skill extraction.
# Synthetic fake data only (no real names/emails/phones/addresses).

from src.engine.cv_quality import analyze_cv_quality
from src.preprocessing.skill_extractor import extract_skill_tokens


def _write(tmp_path, text, name="cv.txt"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# A. Armenian CV
# ---------------------------------------------------------------------------

_ARM_CV = """
Իմ մասին
Մոտիվացված ուսանող, արագ սովորող, հետաքրքրված ծրագրավորմամբ։

Կոնտակտային տվյալներ
Email: fake.candidate@example.com
Հեռախոս: +374 00 000000
Քաղաք: Երևան

Կրթություն
Բակալավր, Համալսարան (2021-2025), GPA 3.8

Աշխատանքային փորձ
Պրակտիկանտ, Ընկերություն (2023) — օգնել եմ թիմին։

Լեզուներ
Հայերեն, English, Русский

Ծրագրերի իմացություն
Python, SQL, Jira, Power BI, Excel, GitHub, Docker
"""


def test_armenian_cv_parsed_robustly(tmp_path):
    r = analyze_cv_quality(_write(tmp_path, _ARM_CV, name="cv_hy.txt"))
    assert r.sections_present["summary"] is True
    assert r.sections_present["education"] is True
    assert r.sections_present["experience"] is True
    assert r.sections_present["skills"] is True
    assert r.contact_info_present is True
    found = set(r.detected_skills)
    assert {"Python", "SQL", "Jira", "Power BI", "Excel", "GitHub", "Docker"} <= found
    assert "Armenian" in r.languages and len(r.languages) >= 2   # mixed
    assert r.quality_score >= 0.7


# ---------------------------------------------------------------------------
# B. Russian CV
# ---------------------------------------------------------------------------

_RUS_CV = """
Контакты
Email: fake.candidate@example.com
Телефон: +374 00 000000

Образование
Бакалавр, Университет (2020-2024)

Опыт работы
Стажёр, Компания (2023)

Компьютерные навыки
Python, SQL, Power BI, GitLab, Tableau
"""


def test_russian_cv_parsed_robustly(tmp_path):
    r = analyze_cv_quality(_write(tmp_path, _RUS_CV, name="cv_ru.txt"))
    assert r.sections_present["education"] is True
    assert r.sections_present["experience"] is True
    assert r.sections_present["skills"] is True
    assert r.contact_info_present is True
    found = set(r.detected_skills)
    assert {"Python", "SQL", "Power BI", "GitLab", "Tableau"} <= found
    assert "Russian" in r.languages
    assert r.quality_score >= 0.6


# ---------------------------------------------------------------------------
# C. Unknown / open-vocabulary skills
# ---------------------------------------------------------------------------

def test_unknown_skills_extracted_from_skills_section(tmp_path):
    cv = "PROFILE\nstudent\n\nTOOLS\nJira / Notion / ClickHouse / Metabase / Figma\n"
    r = analyze_cv_quality(_write(tmp_path, cv, name="cv_tools.txt"))
    assert {"Jira", "Notion", "ClickHouse", "Metabase", "Figma"} <= set(r.detected_skills)


# ---------------------------------------------------------------------------
# D. Soft skills must not be mined as technical skills (from profile prose)
# ---------------------------------------------------------------------------

def test_soft_skills_not_extracted_from_profile(tmp_path):
    cv = (
        "PROFILE\nResponsible, orderly, communication, teamwork. Motivated.\n\n"
        "COMPUTER SKILLS\nPython, SQL\n"
    )
    r = analyze_cv_quality(_write(tmp_path, cv, name="cv_soft.txt"))
    low = {s.lower() for s in r.detected_skills}
    for soft in ("responsible", "orderly", "communication", "teamwork", "motivated"):
        assert soft not in low
    assert {"Python", "SQL"} <= set(r.detected_skills)


# ---------------------------------------------------------------------------
# E. Language names are languages, not technical skills
# ---------------------------------------------------------------------------

def test_language_names_not_treated_as_skills(tmp_path):
    cv = "LANGUAGE\nArmenian, English, Russian\n\nCOMPUTER SKILLS\nPython, SQL\n"
    r = analyze_cv_quality(_write(tmp_path, cv, name="cv_lang.txt"))
    low = {s.lower() for s in r.detected_skills}
    for lang in ("armenian", "english", "russian"):
        assert lang not in low
    assert "English" in r.languages
    assert {"Python", "SQL"} <= set(r.detected_skills)


# ---------------------------------------------------------------------------
# Direct extractor behavior
# ---------------------------------------------------------------------------

def test_extract_skill_tokens_splits_and_preserves_multiword():
    toks = extract_skill_tokens("Python, SQL, HTML/CSS/JavaScript, Power BI, MS Office")
    assert toks == ["Python", "SQL", "HTML", "CSS", "JavaScript", "Power BI", "MS Office"]


def test_extract_skill_tokens_excludes_languages_and_soft():
    assert extract_skill_tokens("Armenian, English, Russian") == []
    assert extract_skill_tokens("responsible, communication, teamwork") == []


def test_extract_skill_tokens_canonical_casing():
    toks = extract_skill_tokens("jira, github, gitlab, power bi, freecad")
    assert toks == ["Jira", "GitHub", "GitLab", "Power BI", "FreeCAD"]
