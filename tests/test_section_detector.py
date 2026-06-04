# tests/test_section_detector.py

from src.preprocessing.section_detector import detect_sections, detected_section_labels


def test_english_sections():
    text = (
        "Summary\nEngineer.\n\n"
        "Work Experience\nAcme — Engineer\n\n"
        "Education\nBSc CS\n\n"
        "Skills\nPython, SQL\n\n"
        "Languages\nEnglish\n"
    )
    labels = detected_section_labels(text)
    assert {"summary", "experience", "education", "skills", "languages"} <= set(labels)


def test_armenian_sections():
    text = "Ամփոփում\nտեքստ\n\nԱշխատանքային փորձ\nտեքստ\n\nԿրթություն\nտեքստ\n\nՀմտություններ\nPython\n"
    labels = detected_section_labels(text)
    assert {"summary", "experience", "education", "skills"} <= set(labels)


def test_russian_sections():
    text = "О себе\nтекст\n\nОпыт работы\nтекст\n\nОбразование\nтекст\n\nНавыки\nPython\n"
    labels = detected_section_labels(text)
    assert {"summary", "experience", "education", "skills"} <= set(labels)


def test_alias_variants_and_colon_headers():
    text = "Profile:\nabout\n\nEmployment History:\nrole\n\nTech Stack:\nPython, Docker\n"
    res = detect_sections(text)
    assert res.has("summary")
    assert res.has("experience")
    assert res.has("skills")


def test_soft_inline_prefix_detection():
    # Header-less, inline "Skills:" line should still register.
    text = "Some intro line.\nSkills: Python, SQL, Docker\nMore text.\n"
    assert "skills" in detected_section_labels(text)


def test_no_false_positive_on_prose():
    text = "I have strong skills in communication and I gained experience over years of work."
    # These are long prose lines, not headers; anchored pass should not fire,
    # but the soft pass keys on "skills"/"experience" prefixes — ensure prose
    # that doesn't START with the alias is not misdetected.
    labels = detected_section_labels(text)
    assert "education" not in labels


def test_nonstandard_heading_aliases_phase24():
    # Mirrors the failing real-CV template (uppercase, non-standard headings).
    text = (
        "PROFILE\nMotivated student.\n\n"
        "CONTACT ME\ncity\n\n"
        "EDUCATION\nDegree\n\n"
        "WORK EXPERIENCE\nrole\n\n"
        "VOLUNTEER EXPERIENCE\nhelped\n\n"
        "LANGUAGE\nEnglish\n\n"
        "COMPUTER SKILLS\nPython, SQL\n"
    )
    labels = set(detected_section_labels(text))
    assert {"summary", "contact", "education", "experience", "languages", "skills"} <= labels


def test_internship_and_degree_aliases():
    text = "INTERNSHIP\nIntern at X\n\nDEGREE\nBSc\n"
    labels = set(detected_section_labels(text))
    assert "experience" in labels and "education" in labels


# ---------------------------------------------------------------------------
# Phase 24.3 hotfix — content bounding + two-column merged headers
# ---------------------------------------------------------------------------

def test_section_content_does_not_bleed_past_repeated_label():
    from src.preprocessing.section_detector import section_content
    # 'experience' is first registered at VOLUNTEER EXPERIENCE (before skills);
    # the later WORK EXPERIENCE must still bound the skills block.
    text = (
        "VOLUNTEER EXPERIENCE\nmentor\n"
        "COMPUTER SKILLS\nPython\nSQL\n"
        "WORK EXPERIENCE\nSoftware Engineer\n"
    )
    content = section_content(text, "skills")
    joined = " ".join(content)
    assert "Python" in joined and "SQL" in joined
    assert "Software Engineer" not in joined      # bounded at WORK EXPERIENCE
    assert "WORK EXPERIENCE" not in joined


def test_two_column_merged_header_line_detects_both():
    text = "PROFILE                 EDUCATION\nstudent  BSc 2020\n"
    labels = set(detected_section_labels(text))
    assert "summary" in labels and "education" in labels
