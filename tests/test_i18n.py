# tests/test_i18n.py
#
# Phase 24.3B — i18n foundation. Pure, no Streamlit runtime required.

import pytest

from src.ui.i18n import (
    DEFAULT_LANG,
    LANGUAGES,
    available_languages,
    normalize_lang,
    t,
    tlist,
)
from src.ui.locales.en import STRINGS as EN
from src.ui.locales.hy import STRINGS as HY
from src.ui.locales.ru import STRINGS as RU

# Keys whose values are lists (steppers), excluded from the "string" assertions.
_LIST_KEYS = {"steps.candidate", "steps.recruiter", "steps.admin"}
_CORE_KEYS = [
    "app.name", "app.tagline", "sidebar.workspace", "sidebar.disclaimer",
    "mode.candidate", "mode.recruiter", "mode.admin",
    "hero.candidate.title", "hero.recruiter.title", "hero.admin.title",
    "candidate.no_cv_title", "recruiter.no_cv_title", "admin.internal_notice",
]


def test_languages_list():
    assert available_languages() == ["en", "hy", "ru"]
    assert DEFAULT_LANG == "en"
    assert set(LANGUAGES) == {"en", "hy", "ru"}


def test_locale_key_parity():
    # All three locales must define exactly the same keys (no drift).
    assert set(EN) == set(HY) == set(RU)


@pytest.mark.parametrize("lang", ["en", "hy", "ru"])
def test_core_keys_resolve_nonempty(lang):
    for key in _CORE_KEYS:
        value = t(key, lang)
        assert isinstance(value, str) and value.strip(), f"{key}/{lang} empty"


def test_translations_differ_across_languages():
    # A representative key should actually be translated (not identical EN copy).
    assert t("mode.candidate", "hy") != t("mode.candidate", "en")
    assert t("mode.candidate", "ru") != t("mode.candidate", "en")
    assert t("hero.candidate.title", "hy") != t("hero.candidate.title", "en")


def test_missing_key_falls_back_to_key():
    assert t("nonexistent.key.xyz", "en") == "nonexistent.key.xyz"
    assert t("nonexistent.key.xyz", "hy") == "nonexistent.key.xyz"


def test_missing_lang_falls_back_to_english():
    assert normalize_lang("zz") == "en"
    assert t("mode.candidate", "zz") == t("mode.candidate", "en")


def test_partial_locale_falls_back_to_english(monkeypatch):
    # If a locale lacks a key, t() returns the English value (never empty).
    import src.ui.i18n as i18n
    monkeypatch.setitem(i18n._LOCALES, "hy", {"app.name": "ArmeniaCareer AI"})
    assert t("mode.candidate", "hy") == EN["mode.candidate"]
    assert t("app.name", "hy") == "ArmeniaCareer AI"


def test_tlist_returns_localized_lists():
    for lang in ("en", "hy", "ru"):
        steps = tlist("steps.candidate", lang)
        assert isinstance(steps, list) and len(steps) == 5
    # Missing list key → empty list, not error.
    assert tlist("steps.nonexistent", "en") == []


def test_no_core_key_is_empty_in_any_locale():
    for locale in (EN, HY, RU):
        for key in _CORE_KEYS:
            val = locale.get(key)
            if key in _LIST_KEYS:
                continue
            assert val is None or (isinstance(val, str) and val.strip())
