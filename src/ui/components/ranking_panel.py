# src/ui/components/ranking_panel.py
#
# Recruiter Bulk Ranking UI: analyze multiple CVs against one JD, rank them
# deterministically, and open a recruiter-safe detail view per candidate.
#
# Synchronous batch (no background queue), capped at MAX_BATCH. Uploaded CVs go
# to temp files and are deleted after each analysis. No data/raw, no candidate
# pool, no PII in the table.

from __future__ import annotations

import contextlib
import hashlib
from typing import Any, List

import pandas as pd
import streamlit as st

from src.engine.orchestrator import AnalysisRunResult, run_analysis
from src.engine.ranking.bulk_ranker import build_bulk_result, to_candidate_record
from src.engine.ranking.models import MAX_BATCH, AnalysisStatus
from src.ui.components.export_panel import render_bulk_ranking_export, render_recruiter_export
from src.ui.components.governance_panel import render_governance_panel
from src.ui.components.interview_panel import render_recruiter_verification_panel
from src.ui.components.ui_kit import notice, section_header, stat_chips
from src.ui.tabs.tab_recruiter_room import render_recruiter_room
from src.ui.tabs.tab_shared_analysis import render_shared_analysis_tab
from src.ui.upload_utils import temp_jd_text, temp_jd_upload, temp_upload

_STATE_KEY = "recruiter_bulk"
_SEL_KEY = "recruiter_bulk_selected"


def _as_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return bytes(value)


def _short_id(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:8]


def _signature(jd_text, jd_upload, cvs, role_title, language, seniority) -> str:
    h = hashlib.sha256()
    h.update((jd_text or "").encode("utf-8"))
    if jd_upload is not None:
        h.update(_as_bytes(jd_upload.getvalue()))
    for cv in cvs:
        h.update(_as_bytes(cv.getvalue()))
    h.update(f"{role_title}|{language}|{seniority}".encode("utf-8"))
    return h.hexdigest()


def _trunc(name: str, n: int = 28) -> str:
    name = name or ""
    return name if len(name) <= n else name[: n - 1] + "…"


def _run_batch(cvs, jd_text, jd_upload, role_title, language, seniority):
    """Analyzes each CV against the same JD with a progress indicator."""
    records = []
    progress = st.progress(0.0)
    status = st.empty()
    total = len(cvs)

    with contextlib.ExitStack() as stack:
        if jd_upload is not None:
            jd_path = stack.enter_context(temp_jd_upload(jd_upload, role_title or None))
        else:
            jd_path = stack.enter_context(temp_jd_text(jd_text, role_title or None))

        for i, cv in enumerate(cvs):
            status.caption(f"Analyzed {i} / {total} …")
            data = _as_bytes(cv.getvalue())
            cid = _short_id(data)
            label = f"Candidate {i + 1}"
            try:
                with temp_upload(cv) as cv_path:
                    res = run_analysis(
                        str(cv_path), str(jd_path),
                        language=language, seniority_context=seniority,
                    )
            except Exception as exc:  # isolate per-CV failures
                res = AnalysisRunResult(success=False, failure_reason=str(exc))
            records.append(to_candidate_record(
                res, label=label, candidate_id=cid, source_filename=cv.name,
            ))
            progress.progress((i + 1) / total)

    status.empty()
    progress.empty()
    return build_bulk_result(records)


def _render_table(bulk) -> None:
    rows = []
    for c in bulk.candidates:
        rows.append({
            "Rank": c.rank,
            "Candidate": c.label,
            "ID": c.candidate_id,
            "Source file": _trunc(c.source_filename),
            "Composite": f"{c.composite_pct:.0f}%" if c.status == AnalysisStatus.SUCCESS else "—",
            "Matched": c.matched_count if c.status == AnalysisStatus.SUCCESS else "—",
            "Missing critical": c.missing_critical_count if c.status == AnalysisStatus.SUCCESS else "—",
            "Bucket": c.bucket.value,
            "Status": c.status.value,
            "Priority": c.priority_label,
            "Reason": c.failure_reason or "",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_detail(bulk) -> None:
    by_id = {c.candidate_id: c for c in bulk.candidates}
    options = [c.candidate_id for c in bulk.candidates]
    if not options:
        return

    prev = st.session_state.get(_SEL_KEY)
    index = options.index(prev) if prev in options else 0
    chosen_id = st.selectbox(
        "Open candidate detail",
        options, index=index,
        format_func=lambda cid: f"#{by_id[cid].rank} · {by_id[cid].label} "
                                f"({_trunc(by_id[cid].source_filename, 22)})",
        key="rec_bulk_detail_select",
    )
    st.session_state[_SEL_KEY] = chosen_id
    candidate = by_id[chosen_id]

    if candidate.status == AnalysisStatus.FAILED or candidate.result is None \
            or candidate.result.payload is None:
        st.error(f"Analysis failed for {candidate.label}: {candidate.failure_reason}")
        return

    result = candidate.result
    t_rec, t_verify, t_shared, t_gov = st.tabs([
        "Recruiter View", "Verification Interview", "Shared Analysis", "Governance / Fallback",
    ])
    with t_rec:
        render_recruiter_room(result)          # recruiter-safe; no coaching content
    with t_verify:
        render_recruiter_verification_panel(result)
    with t_shared:
        render_shared_analysis_tab(result)
    with t_gov:
        render_governance_panel(result)

    render_recruiter_export(result, ranked_candidate=candidate)  # recruiter-safe export


def render_bulk_ranking_panel(*, cvs, jd_text, jd_upload, role_title, language, seniority) -> None:
    section_header("Bulk ranking", "Rank all uploaded candidates against this job.")

    if len(cvs) > MAX_BATCH:
        st.warning(f"More than {MAX_BATCH} CVs uploaded — only the first {MAX_BATCH} are ranked.")
        cvs = cvs[:MAX_BATCH]

    jd_ready = bool((jd_text or "").strip()) or (jd_upload is not None)
    signature = _signature(jd_text, jd_upload, cvs, role_title, language, seniority)

    if st.button("Rank candidates", type="primary", key="rec_bulk_run"):
        if not jd_ready:
            st.warning("Provide a job description (paste text or upload a file) first.")
        else:
            with st.spinner("Ranking candidates…"):
                bulk = _run_batch(cvs, jd_text, jd_upload, role_title, language, seniority)
            st.session_state[_STATE_KEY] = {"sig": signature, "bulk": bulk}
            st.session_state.pop(_SEL_KEY, None)

    stored = st.session_state.get(_STATE_KEY)
    if stored is None or stored.get("sig") != signature:
        if stored is not None:
            st.caption("Inputs changed since the last ranking — click **Rank candidates** to refresh.")
        else:
            st.info("Upload CVs and a job description, then click **Rank candidates**.")
        return

    bulk = stored["bulk"]
    stat_chips([
        ("Candidates", str(bulk.total)),
        ("Analyzed", str(bulk.analyzed)),
        ("Failed", str(bulk.failed)),
        ("Batch cap", str(MAX_BATCH)),
    ])
    notice(
        "Ranking is decision-support only. Open a candidate for recruiter-safe "
        "detail. No candidate coaching content is shown here.",
        "info",
    )
    _render_table(bulk)
    render_bulk_ranking_export(bulk)               # recruiter-safe ranking export
    st.divider()
    _render_detail(bulk)
