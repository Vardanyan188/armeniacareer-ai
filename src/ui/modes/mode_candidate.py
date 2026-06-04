# src/ui/modes/mode_candidate.py
#
# Candidate Mode.
#   Section A — CV-only intelligence (no JD, no orchestrator): upload own CV,
#               analyze quality, skills, weak sections, role directions, tips.
#   Section B — optional comparison against a pasted/uploaded JD via the existing
#               orchestrator. Shows ONLY shared analysis + candidate-facing view.
#
# Privacy: never lists the local resume database; uploaded CV is written to a
# temp file and deleted after analysis; recruiter-only content is never shown.

from __future__ import annotations

import streamlit as st

from src.engine.access_control import get_shared_view
from src.engine.audit_log import log_security_event, sanitize_error
from src.engine.cv_quality import analyze_cv_quality
from src.engine.orchestrator import run_analysis
from src.ui.app_gates import is_candidate_pool_enabled
from src.ui.components.candidate_pool_panel import render_candidate_pool_section
from src.ui.components.cv_quality_panel import render_cv_quality
from src.ui.components.export_panel import render_candidate_export
from src.ui.components.interview_panel import render_candidate_interview_panel
from src.ui.components.quiz_panel import render_candidate_quiz_panel
from src.ui.components.skill_depth_panel import render_candidate_skill_depth
from src.ui.components.ui_kit import (
    empty_state,
    hero_panel,
    score_card,
    stepper,
    step_header,
    trust_badges,
)
from src.ui.tabs.tab_candidate_room import render_candidate_room
from src.ui.tabs.tab_shared_analysis import render_shared_analysis_tab
from src.ui.upload_utils import temp_jd_text, temp_upload

_LANGUAGES = ["hy", "en", "ru"]
_SENIORITY = ["intern", "junior", "mid", "senior", "lead"]


_CANDIDATE_STEPS = ["CV", "Compare", "Results", "Practice", "Quiz"]


def render_candidate_mode() -> None:
    hero_panel(
        "Improve your CV and prepare for interviews",
        "Upload your CV for a private, local analysis — quality, skills, gaps, and practice.",
        icon="◆",
    )
    has_result = st.session_state.get("candidate_result") is not None
    has_cv = st.session_state.get("candidate_cv_upload") is not None
    stepper(_CANDIDATE_STEPS, active=("Results" if has_result else "Compare" if has_cv else "CV"))
    trust_badges()

    st.caption(
        "Upload your own CV. Your file is processed locally in a temporary file "
        "and deleted right after analysis."
    )

    step_header("1", "Your CV")
    uploaded = st.file_uploader(
        "Upload your CV", type=["pdf", "docx", "txt", "md"], key="candidate_cv_upload"
    )
    st.caption(
        "Accepted: PDF, DOCX, TXT, MD. Text-based PDFs work best — scanned/image "
        "PDFs may be flagged as low extraction quality (OCR is not implemented yet)."
    )
    if uploaded is None:
        empty_state("◆", "No CV uploaded yet", "Upload a CV to see your CV intelligence report.")
        return

    # ── Section A: CV-only intelligence ────────────────────────────────────
    try:
        with temp_upload(uploaded) as cv_path:
            report = analyze_cv_quality(cv_path)
        render_cv_quality(report)
    except Exception as exc:
        log_security_event("sanitized_error_shown", severity="error", mode="Candidate")
        st.error(f"Could not analyze the CV: {sanitize_error(exc)}")
        return

    st.divider()

    # Low extraction quality → do not offer pool storage (and warn clearly).
    if getattr(report, "extraction_quality_band", "good") == "low":
        st.warning(
            "Because the extracted text quality is low, comparison and pool "
            "features are limited. Upload a text-based PDF/DOCX for full results."
        )
    elif is_candidate_pool_enabled():
        # ── Candidate Pool: consent-gated, threshold-gated (never automatic) ─
        render_candidate_pool_section(report, uploaded)
    else:
        log_security_event("candidate_pool_persistence_disabled", severity="info")
        st.caption(
            "Candidate Pool storage is disabled in this environment. Your CV is "
            "analyzed locally and not stored."
        )

    st.divider()

    # ── Section B: optional comparison against a specific job ──────────────
    step_header("2", "Compare to a specific job (optional)")
    jd_text = st.text_area("Paste the job description text", key="candidate_jd_text", height=160)
    col1, col2, col3 = st.columns(3)
    role_title = col1.text_input("Target role (optional)", key="candidate_role")
    language = col2.selectbox("Language", _LANGUAGES, index=1, key="candidate_lang")
    seniority = col3.selectbox("Seniority", _SENIORITY, index=1, key="candidate_seniority")

    running = st.session_state.get("candidate_compare_running", False)
    clicked = st.button(
        "Running analysis…" if running else "Compare with this job",
        type="primary", key="candidate_compare", disabled=running,
    )
    if clicked and not running:
        if not jd_text.strip():
            st.warning("Paste a job description first.")
        else:
            st.session_state["candidate_compare_running"] = True
            try:
                with st.spinner("Running analysis…"):
                    with temp_upload(uploaded) as cv_path, \
                            temp_jd_text(jd_text, role_title or None) as jd_path:
                        result = run_analysis(
                            str(cv_path), str(jd_path),
                            language=language, seniority_context=seniority,
                        )
                st.session_state["candidate_result"] = result
            except Exception as exc:
                log_security_event("sanitized_error_shown", severity="error", mode="Candidate")
                st.error(f"Comparison failed: {sanitize_error(exc)}")
            finally:
                st.session_state["candidate_compare_running"] = False

    result = st.session_state.get("candidate_result")
    if result is None:
        return
    if not result.success:
        st.error(f"Comparison failed: {sanitize_error(result.failure_reason)}")
        return

    # ── Results ────────────────────────────────────────────────────────────
    st.divider()
    step_header("3", "Results")
    shared = get_shared_view(result.payload)
    score_card("Composite match", shared["composite_score_percentage"])

    ct_candidate, ct_shared, ct_depth, ct_interview, ct_quiz = st.tabs(
        ["Your Match", "Shared Analysis", "Skill Depth", "Interview Practice", "Skill Quiz"]
    )
    with ct_candidate:
        render_candidate_room(result)      # candidate-facing view only
    with ct_shared:
        render_shared_analysis_tab(result)  # neutral analysis; no recruiter content
    with ct_depth:
        render_candidate_skill_depth(result)  # explanatory depth gaps (no score impact)
    with ct_interview:
        render_candidate_interview_panel(result)  # candidate-safe practice loop
    with ct_quiz:
        render_candidate_quiz_panel(result)        # candidate-safe deterministic quiz

    render_candidate_export(result)                # candidate-safe Markdown export
