# src/ui/components/candidate_pool_panel.py
#
# Candidate-side: consent + "Add to Candidate Pool" flow (threshold gated).
# Recruiter-side: read-only approved-pool metadata list (no raw CV, no filename).
#
# Privacy: nothing is stored without an explicit consent checkbox + button click;
# the recruiter list shows only non-identifying metadata.

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from src.engine.candidate_pool import (
    CANDIDATE_POOL_QUALITY_THRESHOLD,
    ConsentRequiredError,
    DuplicateCandidateError,
    add_candidate,
    compute_file_hash,
    is_duplicate,
    list_candidates,
)
from src.ui.components.ui_kit import section_header


def _as_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return bytes(value)


def render_candidate_pool_section(report: Any, uploaded_file: Any) -> None:
    """Candidate-facing consent + add-to-pool flow. Never adds automatically."""
    threshold = CANDIDATE_POOL_QUALITY_THRESHOLD
    section_header(
        "Candidate Pool",
        f"Optionally add your CV to the local talent pool (quality threshold "
        f"{threshold * 100:.0f}%).",
    )

    if report.quality_score < threshold:
        st.warning(
            f"Not ready yet — your CV quality is {report.quality_score * 100:.0f}%, "
            f"below the {threshold * 100:.0f}% threshold. Apply the improvement "
            "suggestions above and re-upload."
        )
        return

    st.success(
        f"Your CV meets the quality threshold ({report.quality_score * 100:.0f}%)."
    )

    data = _as_bytes(uploaded_file.getvalue())
    file_hash = compute_file_hash(data)

    # Track files added during this session so the button hides immediately.
    added_hashes = st.session_state.setdefault("pool_added_hashes", set())

    if file_hash in added_hashes or is_duplicate(file_hash):
        st.info("✓ Already added to Candidate Pool.")
        return

    consent = st.checkbox(
        "I consent to storing my CV in the local candidate pool.",
        key="candidate_pool_consent",
    )
    if st.button("Add to Candidate Pool", key="candidate_pool_add", disabled=not consent):
        try:
            record = add_candidate(
                data=data,
                original_filename=uploaded_file.name,
                quality_score=report.quality_score,
                detected_skills=report.detected_skills,
                role_families=report.role_suggestions,
                consent=consent,
            )
            added_hashes.add(file_hash)
            st.success(f"Added to the candidate pool (id {record.candidate_id[:8]}…).")
        except DuplicateCandidateError:
            added_hashes.add(file_hash)
            st.info("✓ Already added to Candidate Pool.")
        except ConsentRequiredError:
            st.warning("Consent is required to store your CV.")
        except Exception as exc:  # pragma: no cover - defensive
            st.error(f"Could not add CV to the pool: {exc}")


def render_approved_pool(base_dir=None) -> None:
    """Recruiter-facing read-only pool list. Metadata only — no raw CV, no filenames."""
    section_header(
        "Approved candidate pool",
        "Read-only metadata for candidates who consented to being stored.",
    )
    records = list_candidates(base_dir)
    if not records:
        st.caption("No approved candidates yet.")
        return

    df = pd.DataFrame([{
        "Candidate": r.candidate_id[:8],
        "Quality": f"{r.quality_score * 100:.0f}%",
        "Role directions": ", ".join(r.recommended_role_families[:2]),
        "Skills": ", ".join(r.detected_skills[:6]),
        "Added": (r.created_at or "")[:10],
    } for r in records])
    st.dataframe(df, use_container_width=True, hide_index=True)
