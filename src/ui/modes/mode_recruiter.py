# src/ui/modes/mode_recruiter.py
#
# Recruiter / HR Mode.
#   - Provide ONE JD (paste or upload). Local JD browsing stays in Admin only.
#   - Upload one or more candidate CVs.
#   - Bulk-rank all CVs against the JD, then open a recruiter-safe detail view
#     per candidate (single-candidate analysis = upload one CV).
#
# Privacy: never lists the local resume database; uploaded CVs go to temp files
# and are deleted after analysis. The candidate coaching room (roadmap /
# motivational framing) is never rendered here.

from __future__ import annotations

import streamlit as st

from src.ui.components.candidate_pool_panel import render_approved_pool
from src.ui.components.jd_version_panel import render_recruiter_jd_version_panel
from src.ui.components.ranking_panel import render_bulk_ranking_panel
from src.ui.components.skill_depth_panel import render_recruiter_skill_depth
from src.ui.components.ui_kit import (
    empty_state,
    hero_panel,
    stepper,
    step_header,
    trust_badges,
)

_RECRUITER_STEPS = ["JD", "CVs", "Ranking", "Review", "Verify"]

_LANGUAGES = ["hy", "en", "ru"]
_SENIORITY = ["intern", "junior", "mid", "senior", "lead"]


def render_recruiter_mode() -> None:
    hero_panel(
        "Rank candidates and verify evidence",
        "Provide a job description, upload candidate CVs, then review a recruiter-safe ranking.",
        icon="◈",
    )
    stepper(_RECRUITER_STEPS, active=("Ranking" if st.session_state.get("recruiter_bulk") else "JD"))
    trust_badges()

    st.caption(
        "Decision-support only. Provide a job description and upload candidate "
        "CV(s). Uploaded files are processed in temporary files and deleted after."
    )

    # ── JD source ──────────────────────────────────────────────────────────
    step_header("1", "Job description")
    jd_source = st.radio("JD source", ["Paste text", "Upload file"], horizontal=True, key="rec_jd_src")
    jd_text = ""
    jd_upload = None
    role_title = st.text_input("Role title (optional)", key="rec_role")
    if jd_source == "Paste text":
        jd_text = st.text_area("Paste the job description text", key="rec_jd_text", height=160)
    else:
        jd_upload = st.file_uploader("Upload JD (.json / .txt / .md)", type=["json", "txt", "md"], key="rec_jd_file")
    st.caption("JD formats: JSON or pasted text preferred (TXT/MD also accepted).")

    # ── JD requirement versioning (private; compare/save this role over time) ─
    render_recruiter_jd_version_panel(
        jd_text=jd_text, jd_upload=jd_upload, role_title=role_title,
    )

    # ── CV uploads ─────────────────────────────────────────────────────────
    st.divider()
    step_header("2", "Candidate CVs")
    cvs = st.file_uploader(
        "Upload candidate CV(s)", type=["pdf", "docx", "txt", "md"],
        accept_multiple_files=True, key="rec_cvs",
    )
    st.caption(
        "Accepted: PDF, DOCX, TXT, MD. Text-based PDFs work best — scanned/image "
        "PDFs may be flagged as low extraction quality (OCR is not implemented yet)."
    )
    col1, col2 = st.columns(2)
    language = col1.selectbox("Language", _LANGUAGES, index=1, key="rec_lang")
    seniority = col2.selectbox("Required seniority", _SENIORITY, index=2, key="rec_seniority")

    if not cvs:
        empty_state("◈", "No candidate CVs yet", "Upload at least one candidate CV to continue.")
        with st.expander("Approved candidate pool (read-only)"):
            render_approved_pool()
        return

    # ── Bulk ranking + recruiter-safe detail ───────────────────────────────
    st.divider()
    step_header("3", "Rank & review")
    render_bulk_ranking_panel(
        cvs=cvs, jd_text=jd_text, jd_upload=jd_upload,
        role_title=role_title, language=language, seniority=seniority,
    )

    _render_selected_depth()

    with st.expander("Approved candidate pool (read-only)"):
        render_approved_pool()


def _render_selected_depth() -> None:
    """
    Explanatory requirement-depth view for the candidate currently selected in
    the bulk-ranking detail. Reads the ranking panel's session state read-only;
    never re-runs analysis and never affects ranking.
    """
    stored = st.session_state.get("recruiter_bulk")
    if not stored or "bulk" not in stored:
        return
    bulk = stored["bulk"]
    selected = st.session_state.get("recruiter_bulk_selected")
    candidate = next(
        (c for c in bulk.candidates if c.candidate_id == selected), None
    )
    if candidate is None and bulk.candidates:
        candidate = bulk.candidates[0]
    if candidate is None or candidate.result is None or candidate.result.payload is None:
        return

    with st.expander(f"Requirement depth · {candidate.label}", expanded=False):
        render_recruiter_skill_depth(candidate.result)
