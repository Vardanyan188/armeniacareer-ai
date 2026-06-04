# src/preprocessing/skill_extractor.py
#
# Phase 24.1 — deterministic OPEN-VOCABULARY skill/tool extraction.
#
# Used to extract skill/tool candidates from a *skills-labelled* block of text
# (CV skills section or a JD required/preferred section) even when the tool is
# not in the curated alias list. It deliberately:
#   - splits only on safe delimiters (comma/semicolon/slash/pipe/bullet/newline/
#     parentheses), preserving multi-word tools like "Power BI";
#   - never treats language names or soft skills as technical skills;
#   - never reads from summary/profile prose (the caller passes only skills text).
#
# No LLM, no network. Pure-functional and safe on empty input.

from __future__ import annotations

import re
from typing import List

# Canonical capitalization for common tools (lowercased key → display form).
CANONICAL_CASE = {
    "python": "Python", "sql": "SQL", "html": "HTML", "css": "CSS",
    "javascript": "JavaScript", "typescript": "TypeScript", "java": "Java",
    "jira": "Jira", "trello": "Trello", "notion": "Notion", "asana": "Asana",
    "power bi": "Power BI", "powerbi": "Power BI", "tableau": "Tableau",
    "looker": "Looker", "metabase": "Metabase", "clickhouse": "ClickHouse",
    "postgresql": "PostgreSQL", "postgres": "PostgreSQL", "mysql": "MySQL",
    "mongodb": "MongoDB", "redis": "Redis",
    "git": "Git", "github": "GitHub", "gitlab": "GitLab", "bitbucket": "Bitbucket",
    "docker": "Docker", "kubernetes": "Kubernetes", "k8s": "Kubernetes",
    "figma": "Figma", "canva": "Canva", "photoshop": "Photoshop",
    "google analytics": "Google Analytics", "google sheets": "Google Sheets",
    "google cloud": "GCP", "aws": "AWS", "azure": "Azure", "gcp": "GCP",
    "excel": "Excel", "ms office": "MS Office", "microsoft office": "Microsoft Office",
    "word": "Word", "powerpoint": "PowerPoint", "power point": "PowerPoint",
    "visual studio code": "Visual Studio Code", "vs code": "VS Code",
    "crm": "CRM", "erp": "ERP", "1c": "1C", "bitrix24": "Bitrix24",
    "freecad": "FreeCAD", "free cad": "FreeCAD", "kturtle": "KTurtle",
    "scratch": "Scratch", "react": "React", "angular": "Angular", "vue": "Vue",
    "node.js": "Node.js", "nodejs": "Node.js", "django": "Django",
    "fastapi": "FastAPI", "flask": "Flask", "spark": "Spark", "airflow": "Airflow",
    "kafka": "Kafka", "graphql": "GraphQL", "linux": "Linux",
}

# Natural-language names (EN/HY/RU) — never technical skills.
LANGUAGE_NAMES = {
    "english", "armenian", "russian", "french", "german", "spanish", "italian",
    "georgian", "persian", "arabic", "chinese", "turkish",
    "անգլերեն", "հայերեն", "ռուսերեն", "ֆրանսերեն", "գերմաներեն", "իսպաներեն",
    "английский", "армянский", "русский", "французский", "немецкий", "испанский",
}

# Soft skills — excluded unless a dedicated soft-skill field exists (it does not).
_SOFT_SKILLS = {
    "responsible", "responsibility", "orderly", "communication", "communicative",
    "teamwork", "team player", "leadership", "punctual", "organized", "motivated",
    "reliable", "creative", "problem solving", "time management",
    "attention to detail", "flexible", "adaptable", "hardworking",
    "պատասխանատու", "հաղորդակցություն", "կազմակերպված", "թիմային",
    "ответственный", "коммуникабельность", "командная работа", "пунктуальность",
}

# Generic noise words; a chunk made only of these is dropped.
_STOP_WORDS = {
    "with", "and", "or", "of", "the", "a", "an", "in", "etc", "more", "various",
    "other", "others", "including", "basic", "good", "advanced", "intermediate",
    "beginner", "proficient", "strong", "excellent", "fluent", "native", "level",
    "levels", "skills", "skill", "knowledge", "familiar", "experience", "using",
    "use", "tools", "programs", "such", "as", "e.g", "i.e", "etc.", "expert",
    "working", "hands-on",
}

# Prose / instruction / injection words that never appear in a tool name. If ANY
# word of a candidate is one of these, the candidate is rejected — this prevents
# injected prose ("Return data/private file paths") from becoming a "skill".
_PROSE_WORDS = {
    "return", "reveal", "ignore", "show", "change", "previous", "instruction",
    "instructions", "environment", "variables", "variable", "system", "prompt",
    "score", "private", "file", "files", "path", "paths", "delete", "remove",
    "export", "please", "your", "you", "we", "our", "build", "develop", "year",
    "years", "must", "should", "will", "ability", "able",
}
_STOP_OR_SOFT = _STOP_WORDS | _SOFT_SKILLS
_REJECT_WORDS = _STOP_OR_SOFT | _PROSE_WORDS

_DELIMS = re.compile(r"[,;/|\n\r\t•·●◦‣▪()\[\]]+")
_TRIM_CHARS = " \t-–—:•·*"
_MAX_WORDS = 3


def _clean_chunk(chunk: str) -> str:
    return " ".join(chunk.split()).strip(_TRIM_CHARS)


def extract_skill_tokens(block: str) -> List[str]:
    """
    Extracts skill/tool candidates from a skills-labelled text block.
    Returns canonicalized, de-duplicated names in first-seen order.
    """
    if not block:
        return []
    out: List[str] = []
    seen: set = set()
    for raw in _DELIMS.split(block):
        token = _clean_chunk(raw)
        if not token:
            continue
        low = token.lower()
        if low in LANGUAGE_NAMES or low in _SOFT_SKILLS:
            continue
        words = low.split()
        if len(words) > _MAX_WORDS:
            continue
        # Reject if ANY constituent word is a non-skill (stopword/soft/prose).
        # Real multi-word tools ("Power BI", "Google Analytics") have no such words.
        if any(w in _REJECT_WORDS for w in words):
            continue
        if token.replace(".", "").replace(" ", "").isdigit():
            continue
        if len(token) < 2:
            continue
        canon = CANONICAL_CASE.get(low, token)
        key = canon.lower()
        if key not in seen:
            seen.add(key)
            out.append(canon)
    return out


def merge_skills(curated: List[str], open_vocab: List[str]) -> List[str]:
    """Curated canonical skills first, then open-vocab extras (case-insensitive dedupe)."""
    out: List[str] = []
    seen: set = set()
    for name in list(curated) + list(open_vocab):
        key = str(name).lower()
        if key not in seen:
            seen.add(key)
            out.append(name)
    return out
