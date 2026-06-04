# src/ui/components/jd_version_panel.py
#
# JD Refresh / Requirement Versioning UI (Phase 20). Decision-support only.
#
#   - render_jd_version_panel()            Admin/Demo: compare (and optionally
#                                          save) demo-safe JD versions.
#   - render_recruiter_jd_version_panel()  Recruiter: compare the current JD
#                                          against a stored private version, or
#                                          save the current JD as a PRIVATE version.
#
# Privacy: the Admin tool browses demo-safe JD files only; recruiter versions
# persist exclusively under data/private/jd_version_history/. No raw private JD
# text is shown in demo selectors. Deterministic diff; no hiring decision.

from __future__ import annotations

from typing import Any, Optional

import pandas as pd
import streamlit as st

from src.engine.adapters import jd_json_to_jd_entities
from src.engine.dataset_registry import label_for_path, source_for_path
from src.engine.jd_versioning.diff import diff_versions
from src.engine.jd_versioning.models import create_jd_version
from src.engine.jd_versioning.store import (
    PrivateJDMisroutingError,
    list_versions,
    next_version_number,
    save_jd_version,
)
from src.ui.components.export_panel import render_jd_diff_export
from src.preprocessing.document_loader import (
    jd_json_to_raw_text,
    list_jd_files,
    load_jd_json,
)
from src.ui.components.ui_kit import notice, section_header
from src.ui.upload_utils import build_jd_dict

_DISCLAIMER = (
    "Decision-support only. Requirement changes are detected deterministically "
    "and are directional — human review is required; no hiring decision is made."
)


def _source_type_for_path(path: Any) -> str:
    src = source_for_path(path)
    if src is not None and src.key.startswith("jd_generated"):
        return "generated"
    return "public"


def _version_from_file(path: Any):
    jd = load_jd_json(path)
    raw = jd_json_to_raw_text(jd)
    entities = jd_json_to_jd_entities(jd)
    return create_jd_version(
        raw_text=raw, jd_entities=entities,
        source_type=_source_type_for_path(path), original_filename=path.name,
    )


# ---------------------------------------------------------------------------
# Shared diff renderer
# ---------------------------------------------------------------------------

def _bullets(label: str, items) -> None:
    if items:
        st.markdown(f"**{label}:** " + ", ".join(items))


def _render_diff(diff) -> None:
    notice(diff.summary, "warn" if (diff.became_more_senior or diff.became_more_deployment_heavy) else "info")

    if diff.became_more_senior or diff.became_more_deployment_heavy:
        flags = []
        if diff.became_more_senior:
            flags.append("more senior")
        if diff.became_more_deployment_heavy:
            flags.append("more deployment-heavy")
        st.warning("This role became " + " and ".join(flags) + " — re-check candidate fit.")

    if diff.role_title_changed:
        st.markdown(f"**Role title:** {diff.old_role_title or '—'} → {diff.new_role_title or '—'}")
    if diff.seniority_changed:
        st.markdown(f"**Seniority:** {diff.old_seniority} → {diff.new_seniority}")
    if diff.required_experience_changed:
        st.markdown(
            f"**Required experience:** {diff.old_required_experience_years:g}y → "
            f"{diff.new_required_experience_years:g}y"
        )

    _bullets("Added required skills", diff.added_required_skills)
    _bullets("Removed required skills", diff.removed_required_skills)
    _bullets("Added preferred skills", diff.added_preferred_skills)
    _bullets("Removed preferred skills", diff.removed_preferred_skills)

    if diff.required_depth_changed:
        st.markdown("**Required-depth changes**")
        rows = [{
            "Skill": c.skill,
            "Old depth": c.old_depth or "—",
            "New depth": c.new_depth or "—",
        } for c in diff.required_depth_changed]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    if diff.newly_required_depth_gaps:
        _bullets("Newly deeper requirements", diff.newly_required_depth_gaps)

    _bullets("Responsibilities added", diff.responsibilities_added)
    _bullets("Responsibilities removed", diff.responsibilities_removed)

    st.caption(_DISCLAIMER)
    render_jd_diff_export(diff)


# ---------------------------------------------------------------------------
# Admin / Demo
# ---------------------------------------------------------------------------

def render_jd_version_panel() -> None:
    """Internal Admin tool: compare two demo-safe JD files (and optionally save)."""
    with st.expander("JD version compare (internal · demo data)", expanded=False):
        section_header(
            "Compare job-description versions",
            "Detect added/removed skills, seniority, experience, and requirement-depth changes.",
        )
        jds = list_jd_files()
        if len(jds) < 2:
            st.caption("Need at least two demo JD files under data/raw/job_descriptions.")
            return

        c1, c2 = st.columns(2)
        old_path = c1.selectbox(
            "Baseline JD", jds, format_func=lambda p: f"[{label_for_path(p)}] {p.name}", key="jdver_old",
        )
        new_path = c2.selectbox(
            "Updated JD", jds, index=min(1, len(jds) - 1),
            format_func=lambda p: f"[{label_for_path(p)}] {p.name}", key="jdver_new",
        )
        if old_path == new_path:
            st.info("Pick two different JD files to compare.")
            return

        if st.button("Compare versions", key="jdver_compare", type="primary"):
            old_v = _version_from_file(old_path)
            new_v = _version_from_file(new_path)
            st.session_state["jdver_diff"] = diff_versions(old_v, new_v)

        diff = st.session_state.get("jdver_diff")
        if diff is not None:
            _render_diff(diff)


# ---------------------------------------------------------------------------
# Recruiter
# ---------------------------------------------------------------------------

def _current_recruiter_jd(jd_text: str, jd_upload: Any, role_title: Optional[str]):
    raw = (jd_text or "").strip()
    if not raw and jd_upload is not None:
        data = jd_upload.getvalue()
        raw = data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data)
    if not raw:
        return None
    jd = build_jd_dict(raw, role_title or None)
    return create_jd_version(
        raw_text=raw, jd_entities=jd_json_to_jd_entities(jd),
        source_type="recruiter",            # private → persists only to data/private
    )


def render_recruiter_jd_version_panel(
    *, jd_text: str = "", jd_upload: Any = None, role_title: Optional[str] = None,
) -> None:
    """Recruiter: compare the current JD vs a stored PRIVATE version, or save one."""
    with st.expander("Compare JD versions (private)", expanded=False):
        section_header(
            "JD requirement versioning",
            "Track how this role's requirements change over time. Versions are "
            "stored privately (data/private) and never shown in demo selectors.",
        )
        current = _current_recruiter_jd(jd_text, jd_upload, role_title)
        if current is None:
            st.caption("Provide a job description above to version or compare it.")
            return

        jd_id = st.text_input(
            "JD id (editable)", value=current.jd_id, key="rec_jdver_id",
        ).strip() or current.jd_id
        current.jd_id = jd_id
        notes = st.text_input("Notes (optional)", key="rec_jdver_notes")

        col_save, col_cmp = st.columns(2)

        if col_save.button("Save current as private version", key="rec_jdver_save"):
            try:
                current.version_number = next_version_number(jd_id, private=True)
                current.notes = notes
                save_jd_version(current)        # routed to private by source_type
                st.success(
                    f"Saved private version {current.version_number} of '{jd_id}'."
                )
            except PrivateJDMisroutingError as exc:
                st.error(str(exc))
            except Exception as exc:  # pragma: no cover - defensive
                st.error(f"Could not save version: {exc}")

        stored = list_versions(jd_id, private=True)
        if not stored:
            st.caption("No stored private versions yet for this JD id.")
            return

        baseline = col_cmp.selectbox(
            "Baseline version", stored,
            format_func=lambda v: f"v{v.version_number} · {v.created_at[:10]}",
            key="rec_jdver_baseline",
        )
        if col_cmp.button("Compare with current", key="rec_jdver_compare", type="primary"):
            st.session_state["rec_jdver_diff"] = diff_versions(baseline, current)

        diff = st.session_state.get("rec_jdver_diff")
        if diff is not None:
            _render_diff(diff)
