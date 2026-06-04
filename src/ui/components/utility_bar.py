# src/ui/components/utility_bar.py
#
# Phase 21.1 product-comfort utilities: a compact global status bar and a sidebar
# status block. Visual/status only — no business logic, no raw CV/JD text, no PII,
# no private-file listing, no API keys. Pure builders are unit-testable.

from __future__ import annotations

from typing import Any, List, Optional, Tuple

import streamlit as st

from src.ui.components.ui_kit import badge

# Static product / checkpoint label (NOT read from git at runtime).
CHECKPOINT_LABEL = "ArmeniaCareer AI · MVP (build 21.1)"

_FOCUS_KEY = "focus_mode"


def is_focus_mode() -> bool:
    """True when focus/presentation mode is enabled (default False)."""
    try:
        return bool(st.session_state.get(_FOCUS_KEY, False))
    except Exception:  # pragma: no cover - defensive (no Streamlit runtime)
        return False

# Session keys cleared by the Reset action (kept in sync with streamlit_app).
_RESET_KEYS = [
    "analysis_result", "candidate_result", "recruiter_result",
    "recruiter_bulk", "recruiter_bulk_selected",
    "jdver_diff", "rec_jdver_diff", "candidate_result",
]


# ---------------------------------------------------------------------------
# Status helpers (pure)
# ---------------------------------------------------------------------------

def ingest_enabled() -> bool:
    """True only when ACAI_ENABLE_INGEST is explicitly enabled (read-only check)."""
    try:
        from src.engine.data_ingest import ingest_enabled as _enabled
        return bool(_enabled())
    except Exception:  # pragma: no cover - defensive
        return False


def ingest_status_label() -> str:
    return "Ingest: enabled" if ingest_enabled() else "Ingest: disabled"


def provider_status_label(result: Any = None) -> str:
    """
    Calm provider summary. Defaults to 'Deterministic-ready' (no API key needed);
    if a result carries provider_status, reflect the semantic provider.
    """
    status = getattr(result, "provider_status", None) or {}
    provider = status.get("semantic_alignment") if isinstance(status, dict) else None
    if provider == "openai":
        return "Provider: OpenAI"
    if provider == "google":
        return "Provider: Google"
    if provider == "deterministic":
        return "Provider: deterministic"
    return "Deterministic-ready"


def status_chips(mode: str, result: Any = None) -> List[Tuple[str, str]]:
    """Pure list of (label, kind) chips for the global utility bar."""
    return [
        (CHECKPOINT_LABEL, "neutral"),
        (f"Workspace: {mode}", "info"),
        ("Local only · not committed", "good"),
        (provider_status_label(result), "neutral"),
        (ingest_status_label(), "warn" if ingest_enabled() else "neutral"),
    ]


def sidebar_status_chips(mode: str) -> List[Tuple[str, str]]:
    """Pure list of (label, kind) chips for the sidebar status block."""
    return [
        (f"Mode: {mode}", "info"),
        ("Local data safe", "good"),
        ("Candidate Pool protected", "good"),
        (ingest_status_label(), "warn" if ingest_enabled() else "neutral"),
        ("Fallback-ready · API optional", "neutral"),
        ("Decision-support only", "neutral"),
    ]


def _chips_html(chips: List[Tuple[str, str]]) -> str:
    return "".join(badge(label, kind) for label, kind in chips)


def utility_bar_html(mode: str, result: Any = None) -> str:
    """Pure builder for the global status bar markup."""
    return (
        "<div style='display:flex;flex-wrap:wrap;align-items:center;gap:2px;"
        "margin:0 0 10px'>" + _chips_html(status_chips(mode, result)) + "</div>"
    )


def sidebar_status_html(mode: str) -> str:
    """Pure builder for the sidebar status block markup."""
    return (
        "<div style='border-top:1px solid #1b2230;margin:12px 0 8px'></div>"
        "<div style='color:#8b929e;font-size:0.72rem;text-transform:uppercase;"
        "letter-spacing:1px;margin-bottom:6px'>Status</div>"
        "<div style='display:flex;flex-wrap:wrap;gap:2px'>"
        + _chips_html(sidebar_status_chips(mode)) + "</div>"
    )


# ---------------------------------------------------------------------------
# Render wrappers
# ---------------------------------------------------------------------------

def render_utility_bar(mode: str, result: Any = None) -> None:
    """Compact global status bar + focus toggle + a safe Reset action."""
    col_bar, col_focus, col_reset = st.columns([5, 1.4, 1])
    with col_bar:
        st.markdown(utility_bar_html(mode, result), unsafe_allow_html=True)
    with col_focus:
        st.toggle(
            "Focus mode", key=_FOCUS_KEY,
            help="Presentation-friendly layout. Warnings and disclaimers stay visible.",
        )
    with col_reset:
        if st.button("Reset", key="util_reset", help="Clear analysis results for this session."):
            for key in _RESET_KEYS:
                st.session_state.pop(key, None)
            st.rerun()

    if is_focus_mode():
        st.markdown(
            badge("Presentation ready", "good")
            + badge("Print: Ctrl/Cmd + P", "info"),
            unsafe_allow_html=True,
        )


def render_sidebar_status(mode: str) -> None:
    """Sidebar status chips block."""
    st.markdown(sidebar_status_html(mode), unsafe_allow_html=True)
