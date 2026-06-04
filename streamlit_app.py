# streamlit_app.py
#
# ArmeniaCareer AI — role-based MVP dashboard.
# Thin router only: picks a role mode and dispatches to the corresponding
# renderer. All business logic lives behind the orchestrator, the access-control
# selectors, and the deterministic CV-quality analyzer. No LLM/agents here.
#
# Run with:  streamlit run streamlit_app.py

from __future__ import annotations

import streamlit as st

from src.engine.audit_log import log_workflow_event
from src.ui.app_gates import available_modes
from src.ui.i18n import current_lang, render_language_selector, t, tlist
from src.ui.components.ui_kit import (
    app_header_html,
    brand_lockup_html,
    inject_global_style,
    inject_presentation_css,
)
from src.ui.components.utility_bar import (
    is_focus_mode,
    render_sidebar_status,
    render_utility_bar,
)
from src.ui.modes.mode_admin import render_admin_mode
from src.ui.modes.mode_candidate import render_candidate_mode
from src.ui.modes.mode_recruiter import render_recruiter_mode

_MODES = ["Candidate", "Recruiter / HR", "Admin · Demo"]

# Canonical mode → i18n key (the radio VALUE stays canonical English for gating).
_MODE_KEY = {"Candidate": "candidate", "Recruiter / HR": "recruiter", "Admin · Demo": "admin"}
_MODE_ICON = {"Candidate": "◆", "Recruiter / HR": "◈", "Admin · Demo": "▣"}

# Result keys that must not leak across modes.
_RESULT_KEYS = ["analysis_result", "candidate_result", "recruiter_result"]


def _enforce_mode_isolation(mode: str) -> None:
    """Clears prior results when the active mode changes (privacy isolation)."""
    if st.session_state.get("_active_mode") != mode:
        for key in _RESULT_KEYS:
            st.session_state.pop(key, None)
        st.session_state["_active_mode"] = mode


_MODE_META = {
    "Candidate": ("◆", "Analyze and improve your own CV."),
    "Recruiter / HR": ("◈", "Screen candidates against a job."),
    "Admin · Demo": ("▣", "Internal demo with local sample data."),
}


_MODE_STEPS = {
    "Candidate": ["Upload your CV", "Review CV intelligence", "Compare to a job", "Practice interview"],
    "Recruiter / HR": ["Add a job description", "Upload candidate CV(s)", "Review screening", "Verification guide"],
    "Admin · Demo": ["Pick a local resume", "Pick a local JD", "Run analysis", "Inspect all tabs"],
}


def _mode_label(mode: str, lang: str) -> str:
    return f"{_MODE_ICON.get(mode, '')}   {t('mode.' + _MODE_KEY[mode], lang)}"


def _render_sidebar() -> str:
    with st.sidebar:
        lang = current_lang()

        st.markdown(
            brand_lockup_html(t("app.name", lang), t("app.tagline", lang)),
            unsafe_allow_html=True,
        )

        render_language_selector(label=t("sidebar.language", lang))
        lang = current_lang()                 # reflect a just-changed selection

        st.markdown(
            "<div style='color:#8b929e;font-size:0.72rem;text-transform:uppercase;"
            f"letter-spacing:1px;margin-bottom:4px'>{t('sidebar.workspace', lang)}</div>",
            unsafe_allow_html=True,
        )
        modes = available_modes()             # Admin · Demo hidden unless gated on
        mode = st.radio(
            "Workspace", modes, index=0, label_visibility="collapsed",
            format_func=lambda m: _mode_label(m, lang),
        )

        # Contextual "how it works" steps for the active workspace.
        step_labels = tlist(f"steps.{_MODE_KEY[mode]}", lang) or _MODE_STEPS[mode]
        steps = "".join(
            f"<div style='display:flex;gap:8px;align-items:flex-start;margin:5px 0'>"
            f"<span style='color:#4f9d77;font-size:0.7rem;margin-top:2px'>{i}</span>"
            f"<span style='color:#aeb4bf;font-size:0.78rem;line-height:1.35'>{s}</span></div>"
            for i, s in enumerate(step_labels, start=1)
        )
        st.markdown(
            "<div class='acai-sidebar-steps'>"
            "<div style='border-top:1px solid #1b2230;margin:14px 0 8px'></div>"
            "<div style='color:#8b929e;font-size:0.72rem;text-transform:uppercase;"
            f"letter-spacing:1px;margin-bottom:4px'>{t('sidebar.how_it_works', lang)}</div>{steps}</div>",
            unsafe_allow_html=True,
        )

        render_sidebar_status(mode)

        import html as _html
        st.markdown(
            "<div style='border-top:1px solid #1b2230;margin:12px 0 8px'></div>"
            "<div style='color:#6b7280;font-size:0.72rem;line-height:1.5'>"
            f"{_html.escape(t('sidebar.disclaimer', lang))}</div>",
            unsafe_allow_html=True,
        )
    return mode


def main() -> None:
    st.set_page_config(page_title="ArmeniaCareer AI", layout="wide")
    inject_global_style()
    log_workflow_event("app_started")

    mode = _render_sidebar()
    _enforce_mode_isolation(mode)
    log_workflow_event("mode_selected", mode=mode)

    inject_presentation_css(is_focus_mode())
    render_utility_bar(mode)

    lang = current_lang()
    icon = _MODE_ICON.get(mode, "")
    mode_name = t("mode." + _MODE_KEY[mode], lang)
    intro = t("mode." + _MODE_KEY[mode] + ".intro", lang)
    badge_text = t("mode.admin.badge", lang) if mode == "Admin · Demo" else ""
    st.markdown(
        app_header_html(t("app.name", lang), mode_name, intro, badge_text=badge_text, icon=icon),
        unsafe_allow_html=True,
    )

    if mode == "Candidate":
        render_candidate_mode()
    elif mode == "Recruiter / HR":
        render_recruiter_mode()
    else:
        render_admin_mode()


if __name__ == "__main__":
    main()
