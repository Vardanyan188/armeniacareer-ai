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
from src.ui.components.ui_kit import inject_global_style, inject_presentation_css
from src.ui.components.utility_bar import (
    is_focus_mode,
    render_sidebar_status,
    render_utility_bar,
)
from src.ui.modes.mode_admin import render_admin_mode
from src.ui.modes.mode_candidate import render_candidate_mode
from src.ui.modes.mode_recruiter import render_recruiter_mode

_MODES = ["Candidate", "Recruiter / HR", "Admin · Demo"]

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


def _render_sidebar() -> str:
    with st.sidebar:
        st.markdown(
            "<div style='display:flex;align-items:center;gap:9px;margin-bottom:2px'>"
            "<span style='width:26px;height:26px;border-radius:8px;background:#15301f;"
            "border:1px solid #243; display:inline-flex;align-items:center;"
            "justify-content:center;color:#7fd1a3;font-weight:700'>A</span>"
            "<span style='font-size:1.05rem;font-weight:700;letter-spacing:0.3px;"
            "color:#e6e8eb'>ArmeniaCareer&nbsp;AI</span></div>"
            "<div style='color:#8b929e;font-size:0.7rem;text-transform:uppercase;"
            "letter-spacing:1.5px;margin:0 0 14px 35px'>Career Intelligence</div>",
            unsafe_allow_html=True,
        )

        st.markdown(
            "<div style='color:#8b929e;font-size:0.72rem;text-transform:uppercase;"
            "letter-spacing:1px;margin-bottom:4px'>Workspace</div>",
            unsafe_allow_html=True,
        )
        modes = available_modes()             # Admin · Demo hidden unless gated on
        mode = st.radio(
            "Workspace", modes, index=0, label_visibility="collapsed",
            format_func=lambda m: f"{_MODE_META[m][0]}   {m}",
        )

        # Contextual "how it works" steps for the active workspace.
        steps = "".join(
            f"<div style='display:flex;gap:8px;align-items:flex-start;margin:5px 0'>"
            f"<span style='color:#4f9d77;font-size:0.7rem;margin-top:2px'>{i}</span>"
            f"<span style='color:#aeb4bf;font-size:0.78rem;line-height:1.35'>{s}</span></div>"
            for i, s in enumerate(_MODE_STEPS[mode], start=1)
        )
        st.markdown(
            "<div class='acai-sidebar-steps'>"
            "<div style='border-top:1px solid #1b2230;margin:14px 0 8px'></div>"
            "<div style='color:#8b929e;font-size:0.72rem;text-transform:uppercase;"
            f"letter-spacing:1px;margin-bottom:4px'>How it works</div>{steps}</div>",
            unsafe_allow_html=True,
        )

        render_sidebar_status(mode)

        st.markdown(
            "<div style='border-top:1px solid #1b2230;margin:12px 0 8px'></div>"
            "<div style='color:#6b7280;font-size:0.72rem;line-height:1.5'>"
            "Decision-support only. Human review is required before any hiring "
            "decision. Files are processed locally and not committed.</div>",
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

    icon, intro = _MODE_META[mode]
    is_admin = mode == "Admin · Demo"
    tag = (
        "<span style='background:#2e2410;color:#e0b766;border:1px solid #262c37;"
        "padding:2px 10px;border-radius:10px;font-size:0.72rem;margin-left:10px'>"
        "Internal Demo Mode</span>" if is_admin else ""
    )
    st.markdown(
        f"<div style='background:#161b22;border:1px solid #262c37;border-radius:14px;"
        f"padding:16px 20px;margin-bottom:14px'>"
        f"<span style='font-size:1.15rem;font-weight:660;color:#e6e8eb'>"
        f"{icon}&nbsp; {mode}</span>{tag}<br>"
        f"<span style='color:#8b929e;font-size:0.9rem'>{intro}</span></div>",
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
