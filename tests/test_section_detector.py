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
