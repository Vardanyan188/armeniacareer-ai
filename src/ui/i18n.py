# src/ui/i18n.py
#
# Phase 24.3B — lightweight i18n for ArmeniaCareer AI (en / hy / ru).
#
# Design:
#   - One translation registry; no scattered literals.
#   - t(key, lang) returns the localized value, falling back to English, then to
#     the key itself — NEVER an empty string.
#   - Language lives in st.session_state["ui_lang"] (default English).
#   - Pure helpers (t / tlist / available_languages) are unit-testable without a
#     Streamlit runtime; the selector is a thin wrapper.

from __future__ import annotations

from typing import Any, List, Optional

from src.ui.locales.en import STRINGS as _EN
from src.ui.locales.hy import STRINGS as _HY
from src.ui.locales.ru import STRINGS as _RU

DEFAULT_LANG = "en"
LANGUAGES = ["en", "hy", "ru"]
LANGUAGE_LABELS = {"en": "English", "hy": "Հայերեն", "ru": "Русский"}
_SESSION_KEY = "ui_lang"

_LOCALES = {"en": _EN, "hy": _HY, "ru": _RU}


def available_languages() -> List[str]:
    return list(LANGUAGES)


def normalize_lang(lang: Optional[str]) -> str:
    return lang if lang in _LOCALES else DEFAULT_LANG


def t(key: str, lang: Optional[str] = None) -> str:
    """Localized string for `key`. Falls back lang→en→key; never returns ''."""
    lang = normalize_lang(lang if lang is not None else current_lang())
    value = _LOCALES[lang].get(key)
    if value is None:
        value = _EN.get(key)
    if value is None:
        return key
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    return str(value)


def tlist(key: str, lang: Optional[str] = None) -> List[str]:
    """Localized list value (e.g. stepper labels). Falls back lang→en→[]."""
    lang = normalize_lang(lang if lang is not None else current_lang())
    value = _LOCALES[lang].get(key)
    if value is None:
        value = _EN.get(key)
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return []


# ---------------------------------------------------------------------------
# Session-aware helpers (thin Streamlit wrappers)
# ---------------------------------------------------------------------------

def current_lang() -> str:
    try:
        import streamlit as st
        return normalize_lang(st.session_state.get(_SESSION_KEY, DEFAULT_LANG))
    except Exception:  # pragma: no cover - no Streamlit runtime (tests)
        return DEFAULT_LANG


def set_lang(lang: str) -> None:
    try:
        import streamlit as st
        st.session_state[_SESSION_KEY] = normalize_lang(lang)
    except Exception:  # pragma: no cover
        pass


def render_language_selector(*, label: Optional[str] = None) -> str:
    """Renders a sidebar language selector and returns the chosen language."""
    import streamlit as st
    st.selectbox(
        label or t("sidebar.language"),
        LANGUAGES,
        format_func=lambda code: LANGUAGE_LABELS.get(code, code),
        key=_SESSION_KEY,
    )
    return current_lang()
