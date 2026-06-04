# tests/test_presentation_mode.py
#
# Phase 21.3 — Focus / Presentation mode + Print comfort. CSS-only, pure
# builders. No Streamlit runtime, no API keys, no private paths, no PII.

import re

import streamlit as st

from src.ui.components import utility_bar as ub
from src.ui.components.ui_kit import focus_mode_css, presentation_css, print_css

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"\(?\+?\d[\d\s().\-]{7,}\d\)?")


def _no_private_or_pii(css: str) -> None:
    low = css.lower()
    assert "data/private" not in low and "candidate_pool" not in low
    assert "real_resumes" not in low and "company_private" not in low
    assert not _EMAIL_RE.search(css)
    assert not _PHONE_RE.search(css)


# ---------------------------------------------------------------------------
# Focus-mode flag
# ---------------------------------------------------------------------------

def test_is_focus_mode_default_false(monkeypatch):
    monkeypatch.setattr(st, "session_state", {})
    assert ub.is_focus_mode() is False


def test_is_focus_mode_reflects_flag(monkeypatch):
    monkeypatch.setattr(st, "session_state", {"focus_mode": True})
    assert ub.is_focus_mode() is True
    monkeypatch.setattr(st, "session_state", {"focus_mode": False})
    assert ub.is_focus_mode() is False


# ---------------------------------------------------------------------------
# Focus CSS
# ---------------------------------------------------------------------------

def test_focus_mode_css_has_expected_selectors():
    css = focus_mode_css()
    assert ".block-container" in css
    assert "acai-sidebar-steps" in css           # trims decorative sidebar steps
    assert "max-width" in css


def test_focus_css_does_not_blanket_hide_captions():
    css = focus_mode_css()
    # Governance/directional disclaimers are captions and must remain visible.
    assert "stCaption" not in css
    assert "caption{display:none" not in css.replace(" ", "")


# ---------------------------------------------------------------------------
# Print CSS
# ---------------------------------------------------------------------------

def test_print_css_contains_media_print():
    assert "@media print" in print_css()


def test_print_css_light_background_and_important():
    css = print_css()
    assert "#ffffff" in css.lower()
    assert "!important" in css
    assert "stSidebar" in css                     # hides chrome when printing
    assert "break-inside: avoid" in css
    assert ".acai-surface" in css and ".acai-card" in css


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

def test_presentation_css_includes_print_always():
    assert "@media print" in presentation_css(False)
    assert "acai-focus" not in presentation_css(False)


def test_presentation_css_adds_focus_when_enabled():
    css = presentation_css(True)
    assert "@media print" in css
    assert "acai-focus" in css


# ---------------------------------------------------------------------------
# Privacy / safety of CSS + labels
# ---------------------------------------------------------------------------

def test_css_has_no_private_paths_or_pii():
    for css in (focus_mode_css(), print_css(), presentation_css(True)):
        _no_private_or_pii(css)


def test_checkpoint_label_unchanged_and_safe():
    _no_private_or_pii(ub.CHECKPOINT_LABEL)
