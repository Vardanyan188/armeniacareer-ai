# src/ui/modes/mode_admin.py
#
# Admin / Demo Mode — preserves the original MVP behavior EXACTLY:
# local dataset selectors (data/raw) + the four detail tabs. This is the ONLY
# mode permitted to browse the local resume / JD database.

from __future__ import annotations

import streamlit as st

from src.engine.audit_log import log_security_event, sanitize_error
from src.ui.app_gates import is_admin_enabled
from src.ui.components.data_ingest_panel import render_data_ingest_panel
from src.ui.components.export_panel import render_admin_export
from src.ui.components.governance_panel import render_governance_panel
from src.ui.components.jd_version_panel import render_jd_version_panel
from src.ui.components.ui_kit import empty_state, hero_panel, notice, stepper
from src.ui.i18n import current_lang, t, tlist
from src.ui.tabs.tab_candidate_room import render_candidate_room
from src.ui.tabs.tab_input import render_input_tab
from src.ui.tabs.tab_recruiter_room import render_recruiter_room
from src.ui.tabs.tab_shared_analysis import render_shared_analysis_tab


_ADMIN_STEPS = ["Select data", "Analyze", "Inspect", "Governance"]


def render_admin_mode() -> None:
    lang = current_lang()
    if not is_admin_enabled():
        # Defense in depth: Admin is normally hidden from the switcher in public.
        log_security_event("admin_access_denied", severity="blocked", mode="Admin · Demo")
        notice(t("admin.disabled_notice", lang), "warn")
        return

    hero_panel(t("hero.admin.title", lang), t("hero.admin.subtitle", lang), icon="▣")
    stepper(
        tlist("steps.admin", lang) or _ADMIN_STEPS,
        active=(3 if st.session_state.get("analysis_result") else 1),
    )
    notice(t("admin.internal_notice", lang), "warn")

    render_input_tab()

    # Internal-only private data ingest (hidden unless ACAI_ENABLE_INGEST is set).
    render_data_ingest_panel()

    # Internal JD requirement-versioning compare tool (demo-safe data only).
    render_jd_version_panel()

    result = st.session_state.get("analysis_result")
    if result is None:
        empty_state(
            "▣", "No analysis yet",
            "Select a resume and a job description above, then run the analysis.",
        )
        return
    if not result.success:
        st.error(f"Analysis failed: {sanitize_error(result.failure_reason)}")
        return

    st.divider()
    tab_shared, tab_candidate, tab_recruiter, tab_gov = st.tabs([
        "Shared Analysis",
        "Candidate Coach Room",
        "Recruiter Intelligence Room",
        "Governance / Fallback Status",
    ])
    with tab_shared:
        render_shared_analysis_tab(result)
    with tab_candidate:
        render_candidate_room(result)
    with tab_recruiter:
        render_recruiter_room(result)
    with tab_gov:
        render_governance_panel(result)

    render_admin_export(result)                    # stamped internal demo export
