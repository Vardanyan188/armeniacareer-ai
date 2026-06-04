# src/engine/cv_recommendations.py
#
# Phase 24.2 — deterministic CV advisory layer (on top of the Phase 24.1 parser).
#
# Produces concrete, actionable recommendations about section order, hard/soft
# skill organization, language-level clarity, page density, and ATS/readability
# risk. Advisory only — never hard failures, never PII, no LLM, no network.

from __future__ import annotations

import re
from typing import Dict, List, Optional

from src.preprocessing.language_proficiency import LanguageProficiency

# Soft-skill terms (EN/HY/RU) — used to detect soft skills mixed into a generic
# Skills section. These are NOT technical skills.
SOFT_SKILL_TERMS = [
    "communication", "teamwork", "team work", "leadership", "responsibility",
    "responsible", "punctuality", "punctual", "organized", "organization",
    "problem solving", "analytical thinking", "detail-oriented", "detail oriented",
    "adaptability", "creativity", "time management", "critical thinking",
    "հաղորդակցություն", "թիմային աշխատանք", "պատասխանատվություն", "կազմակերպվածություն",
    "коммуникабельность", "ответственность", "командная работа", "организованность",
]

# Cues that suggest a student / junior candidate (education-first is fine).
_STUDENT_CUES = [
    "student", "intern", "internship", "trainee", "graduate", "fresh graduate",
    "ուսանող", "պրակտիկ", "շրջանավարտ", "студент", "стажёр", "стажер", "выпускник",
]

# Icon/decorative glyphs that can hurt ATS parsing when overused.
_ICON_GLYPHS = set("★☆●○▰▱■□◆◇♦▶◀◦‣▪➤➜✦✔✓⚡✉☎✆✈⭐➡⬤")
_LONG_PARAGRAPH_CHARS = 350
_ICON_DENSITY_THRESHOLD = 6


# ---------------------------------------------------------------------------
# Section order
# ---------------------------------------------------------------------------

def is_student_or_junior(text: str, has_experience: bool) -> bool:
    low = (text or "").lower()
    return (not has_experience) or any(cue in low for cue in _STUDENT_CUES)


def section_order_recommendations(
    ordered_labels: List[str], *, has_experience: bool, is_student: bool,
) -> List[str]:
    recs: List[str] = []
    index = {label: i for i, label in enumerate(ordered_labels)}

    if "contact" in index and index["contact"] != 0:
        recs.append("Place Contact details at the very top of the CV.")

    if "summary" in index and index["summary"] > 2:
        recs.append("Move your Summary/Profile near the top, right after Contact.")

    if "experience" in index and "education" in index:
        if has_experience and not is_student and index["education"] < index["experience"]:
            recs.append(
                "Move Work Experience above Education because you already have "
                "work experience."
            )

    if "skills" in index and "languages" in index and index["languages"] < index["skills"]:
        recs.append("List your Skills section before Languages.")

    if "projects" in index and "education" in index and is_student \
            and index["education"] < index["projects"]:
        recs.append(
            "As a student/junior with limited experience, consider placing Projects "
            "above Education to highlight practical work."
        )
    return recs


# ---------------------------------------------------------------------------
# Hard vs soft skill organization
# ---------------------------------------------------------------------------

def detect_soft_skills(skills_section_text: str) -> List[str]:
    low = (skills_section_text or "").lower()
    found: List[str] = []
    for term in SOFT_SKILL_TERMS:
        if term in low and term not in found:
            found.append(term)
    return found


def skill_organization_recommendations(
    hard_skills: List[str], soft_skills: List[str], *, is_technical_role: bool,
) -> List[str]:
    recs: List[str] = []
    if hard_skills and soft_skills:
        recs.append(
            "Your Skills section mixes technical and soft skills — separate them "
            "into 'Technical Skills' and 'Soft Skills'."
        )
        if is_technical_role:
            recs.append(
                "Put technical skills before soft skills for a technical/data/IT role."
            )
    return recs


# ---------------------------------------------------------------------------
# Language level clarity
# ---------------------------------------------------------------------------

def language_level_recommendations(profs: List[LanguageProficiency]) -> List[str]:
    recs: List[str] = []
    if any(p.warning_if_visual_only for p in profs):
        recs.append(
            "Replace visual-only language levels (stars/dots/bars or 4/5) with a "
            "clear label such as CEFR B2/C1 or Fluent/Intermediate."
        )
    if any(p.normalized_level == "Unknown" for p in profs):
        recs.append(
            "Add a clear proficiency level next to each language (e.g. English — B2)."
        )
    return recs


# ---------------------------------------------------------------------------
# Page count / density
# ---------------------------------------------------------------------------

def page_count_recommendations(page_count: Optional[int], *, is_student: bool) -> List[str]:
    if not page_count or page_count < 1:
        return []                      # no metadata → do not guess
    recs: List[str] = []
    if is_student and page_count >= 2:
        recs.append(
            "Keep your CV to a single page — for a student/junior profile two or "
            "more pages is usually too long."
        )
    if not is_student and page_count >= 3:
        recs.append(
            "Consider tightening the CV toward 1–2 pages unless the extra length is "
            "clearly relevant (e.g. senior/research roles)."
        )
    return recs


# ---------------------------------------------------------------------------
# ATS / readability risks
# ---------------------------------------------------------------------------

def ats_risks(text: str, sections_present: Dict[str, bool]) -> List[str]:
    risks: List[str] = []
    icon_count = sum(1 for ch in (text or "") if ch in _ICON_GLYPHS)
    if icon_count >= _ICON_DENSITY_THRESHOLD:
        risks.append(
            "Many icons/decorative symbols detected — these can confuse ATS parsers; "
            "prefer plain text headings and labels."
        )

    missing = [s for s in ("experience", "education", "skills") if not sections_present.get(s)]
    if missing:
        risks.append(
            "Some standard headings are missing or unusual (" + ", ".join(missing) +
            ") — use clear headings like 'Work Experience', 'Education', 'Skills'."
        )

    if any(len(line) > _LONG_PARAGRAPH_CHARS for line in (text or "").split("\n")):
        risks.append(
            "Very long paragraphs detected — break dense text into short bullet points."
        )
    return risks


# ---------------------------------------------------------------------------
# Strengths (positive signals)
# ---------------------------------------------------------------------------

def collect_strengths(
    *, contact_present: bool, sections_present: Dict[str, bool],
    skill_count: int, has_metric: bool, languages: List[str],
) -> List[str]:
    strengths: List[str] = []
    if contact_present:
        strengths.append("Contact information is present.")
    if sections_present.get("skills") and skill_count >= 3:
        strengths.append(f"Clear Skills section with {skill_count} detected skills.")
    if sections_present.get("experience"):
        strengths.append("Work experience is documented.")
    if has_metric:
        strengths.append("Includes measurable achievements (numbers/percentages).")
    if len(languages) >= 2:
        strengths.append("Multiple languages listed.")
    return strengths
