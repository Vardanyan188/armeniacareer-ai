# src/ui/tabs/tab_input.py
#
# Input controls: pick one resume + one JD from data/raw, choose language and
# seniority, then run the analysis through the orchestrator. Files are read
# locally only; nothing is uploaded anywhere.

from __future__ import annotations

import streamlit as st

from src.engine.dataset_registry import label_for_path, source_for_path
from src.engine.orchestrator import run_analysis
from src.preprocessing.document_loader import list_jd_files, list_resume_files

_LANGUAGES = ["hy", "en", "ru"]
_SENIORITY = ["intern", "junior", "mid", "senior", "lead"]


def _file_label(path) -> str:
    return f"[{label_for_path(path)}]  {path.name}"


def render_input_tab() -> None:
    st.subheader("1. Select inputs")

    # Demo loaders read recursively from data/raw, never from data/private or
    # data/uploads (the candidate pool). Real private CVs never appear here.
    resumes = list_resume_files()
    jds = list_jd_files()

    if not resumes:
        st.warning("No resume files found under data/raw/resumes.")
        return
    if not jds:
        st.warning("No job-description files found under data/raw/job_descriptions.")
        return

    st.caption(
        "Internal demo data only. Generated sets are demo-safe; LinkedIn/Profile and "
        "Kaggle sets are sensitive and shown for internal testing only. Private real "
        "CVs are excluded."
    )

    col_left, col_right = st.columns(2)
    with col_left:
        resume = st.selectbox("Resume", resumes, format_func=_file_label)
        language = st.selectbox("Language", _LANGUAGES, index=0)
    with col_right:
        jd = st.selectbox("Job description", jds, format_func=_file_label)
        seniority = st.selectbox("Seniority context", _SENIORITY, index=1)

    src = source_for_path(resume)
    if src is not None and not src.demo_safe:
        st.warning(
            f"Selected resume source is **{src.label}** ({src.sensitivity} sensitivity) — "
            "internal testing only; may contain real profile data."
        )

    if st.button("Run Analysis", type="primary"):
        with st.spinner("Running analysis (deterministic fallback if no API key)…"):
            result = run_analysis(
                str(resume),
                str(jd),
                language=language,
                seniority_context=seniority,
            )
        st.session_state["analysis_result"] = result
        if result.success:
            st.success("Analysis complete. See the tabs below.")
        else:
            st.error(f"Analysis failed: {result.failure_reason}")
