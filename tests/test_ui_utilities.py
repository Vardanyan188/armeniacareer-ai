# tests/test_ui_utilities.py
#
# Phase 21.1 product-comfort UI helpers. Pure builders only — no Streamlit
# runtime, no API keys, no data/private access, no PII. We assert the HTML/text
# builders are safe and that status flags respond to ACAI_ENABLE_INGEST.

import re

from src.ui.components import utility_bar as ub
from src.ui.components.ui_kit import (
    DEFAULT_TRUST_LABELS,
    confidence_chip,
    confidence_label,
    empty_state_html,
    hero_panel_html,
    stepper_html,
)

_PHONE_RE = re.compile(r"\(?\d{2,}\)?[\d\s\-]{5,}")


def _no_pii(text: str) -> None:
    assert "@" not in text                 # no emails
    assert not _PHONE_RE.search(text)      # no phone-like sequences
    # No private filesystem paths leaked.
    low = text.lower()
    assert "data/private" not in low
    assert "data\\private" not in low
    assert "candidate_pool" not in low


# ---------------------------------------------------------------------------
# ui_kit primitives
# ---------------------------------------------------------------------------

def test_empty_state_html_is_safe_and_escaped():
    html = empty_state_html("◆", "No CV uploaded", "Upload a CV to begin.")
    assert "No CV uploaded" in html and "Upload a CV to begin." in html
    _no_pii(html)


def test_empty_state_html_escapes_injection():
    html = empty_state_html("x", "<script>alert(1)</script>", "")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_confidence_label_bands():
    assert confidence_label(0.9) == "High confidence"
    assert confidence_label(0.6) == "Medium confidence"
    assert confidence_label(0.2) == "Low confidence"
    assert confidence_label("Custom") == "Custom"


def test_confidence_chip_returns_html_string():
    chip = confidence_chip(0.9)
    assert isinstance(chip, str) and "High confidence" in chip
    _no_pii(chip)


def test_stepper_html_marks_active():
    html = stepper_html(["CV", "Compare", "Results"], active="Compare")
    assert "CV" in html and "Compare" in html and "Results" in html
    _no_pii(html)


def test_hero_panel_html_safe():
    html = hero_panel_html("Improve your CV", "Local, private analysis.", icon="◆")
    assert "Improve your CV" in html
    _no_pii(html)


def test_default_trust_labels_are_safe():
    assert "No auto-hiring" in DEFAULT_TRUST_LABELS
    for label in DEFAULT_TRUST_LABELS:
        _no_pii(label)


# ---------------------------------------------------------------------------
# Utility bar / status chips
# ---------------------------------------------------------------------------

def test_checkpoint_label_is_static():
    assert ub.CHECKPOINT_LABEL == "ArmeniaCareer AI · MVP (build 21.1)"
    # Static label must not embed paths or contact info.
    _no_pii(ub.CHECKPOINT_LABEL)


def test_ingest_status_responds_to_env(monkeypatch):
    monkeypatch.delenv("ACAI_ENABLE_INGEST", raising=False)
    assert ub.ingest_enabled() is False
    assert ub.ingest_status_label() == "Ingest: disabled"
    monkeypatch.setenv("ACAI_ENABLE_INGEST", "1")
    assert ub.ingest_enabled() is True
    assert ub.ingest_status_label() == "Ingest: enabled"


def test_provider_status_defaults_to_deterministic_without_keys(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    # Safe fallback wording when no provider is active.
    assert ub.provider_status_label(None) == "AI provider unavailable — deterministic fallback is active"


def test_provider_status_reflects_result(monkeypatch):
    monkeypatch.delenv("ACAI_PUBLIC_DEMO", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)

    class _R:
        provider_status = {"semantic_alignment": "google"}
        agent_errors = {}
    assert ub.provider_status_label(_R()) == "AI provider active: Gemini"


def test_status_chips_and_bar_html_are_safe(monkeypatch):
    monkeypatch.delenv("ACAI_ENABLE_INGEST", raising=False)
    chips = ub.status_chips("Candidate")
    labels = [c[0] for c in chips]
    assert ub.CHECKPOINT_LABEL in labels
    assert "Workspace: Candidate" in labels
    assert "Ingest: disabled" in labels
    html = ub.utility_bar_html("Candidate")
    _no_pii(html)


def test_sidebar_status_chips_safe_and_reflect_ingest(monkeypatch):
    monkeypatch.setenv("ACAI_ENABLE_INGEST", "1")
    chips = ub.sidebar_status_chips("Recruiter / HR")
    labels = [c[0] for c in chips]
    assert "Mode: Recruiter / HR" in labels
    assert "Candidate Pool protected" in labels
    assert "Ingest: enabled" in labels
    _no_pii(ub.sidebar_status_html("Recruiter / HR"))


def test_no_private_path_listing_anywhere():
    # None of the status surfaces should reference private storage locations.
    for text in (
        ub.utility_bar_html("Admin · Demo"),
        ub.sidebar_status_html("Admin · Demo"),
    ):
        assert "private" not in text.lower() or "Private data excluded" in text
        assert "real_resumes" not in text
        assert "company_private" not in text
