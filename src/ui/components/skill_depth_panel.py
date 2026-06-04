# src/ui/components/skill_depth_panel.py
#
# Skill Proficiency / Requirement Depth UI (Phase 19). Explanatory only.
#
# Renders the neutral SkillDepthAnalysis (from access_control.get_skill_depth_view)
# with role-specific framing:
#   - Candidate: "Skill depth gaps" / "What to strengthen" (supportive).
#   - Recruiter: "Requirement depth evidence" / "Depth gaps to verify" + probes.
#   - Shared:    one neutral summary line only.
#
# Privacy: shows skill names, depth labels, curated evidence labels, and
# templated neutral text only — never raw CV/JD text or PII.

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from src.engine.access_control import get_skill_depth_view
from src.engine.skill_depth.models import DepthMatchType
from src.ui.components.ui_kit import df_width_kwargs, notice, section_header

_DIRECTIONAL = (
    "Directional only — depth is inferred heuristically from CV/JD evidence and "
    "must be verified in conversation. It does not affect the match score."
)

_GAP_TYPES = {
    DepthMatchType.PARTIAL_DEPTH_MATCH,
    DepthMatchType.MENTIONED_ONLY,
    DepthMatchType.MISSING_SKILL,
}


def _evidence(entry: Any) -> str:
    return ", ".join(entry.evidence_labels) if entry.evidence_labels else "—"


# ---------------------------------------------------------------------------
# Candidate surface
# ---------------------------------------------------------------------------

def render_candidate_skill_depth(result: Any) -> None:
    """Supportive candidate-facing skill-depth section."""
    analysis = get_skill_depth_view(result.payload)
    section_header(
        "Skill depth",
        "How deep your evidence looks versus what the role asks for.",
    )
    if not analysis.entries:
        st.caption("No required skills were detected for depth analysis.")
        return

    rows = [{
        "Skill": e.skill,
        "Your depth": e.candidate_depth_label,
        "Needed": e.required_depth_label,
        "Gap": e.depth_gap if e.depth_gap else "—",
    } for e in analysis.entries]
    st.dataframe(pd.DataFrame(rows), hide_index=True, **df_width_kwargs())

    strengthen = [e for e in analysis.entries if e.match_type in _GAP_TYPES]
    if strengthen:
        st.markdown("**What to strengthen**")
        for e in strengthen:
            st.markdown(f"- **{e.skill}** — {e.recommendation}")
    else:
        st.success("Your evidence meets the required depth for the detected skills.")

    st.caption(_DIRECTIONAL)


# ---------------------------------------------------------------------------
# Recruiter surface
# ---------------------------------------------------------------------------

def render_recruiter_skill_depth(result: Any) -> None:
    """Recruiter-facing requirement-depth evidence + verification probes."""
    analysis = get_skill_depth_view(result.payload)
    section_header(
        "Requirement depth evidence",
        "Observed depth vs. required depth, with safe evidence labels.",
    )
    if not analysis.entries:
        st.caption("No required skills were detected for depth analysis.")
        return

    rows = [{
        "Skill": e.skill,
        "Required": e.required_depth_label,
        "Observed": e.candidate_depth_label,
        "Match": e.match_type.value.replace("_", " "),
        "Evidence": _evidence(e),
    } for e in analysis.entries]
    st.dataframe(pd.DataFrame(rows), hide_index=True, **df_width_kwargs())

    gaps = [e for e in analysis.entries if e.match_type in _GAP_TYPES]
    if gaps:
        st.markdown("**Depth gaps to verify**")
        for e in gaps:
            st.markdown(f"- **{e.skill}** ({e.required_depth_label} needed) — {e.verification_prompt}")
    else:
        st.caption("No depth gaps flagged for verification.")

    notice(_DIRECTIONAL, "info")


# ---------------------------------------------------------------------------
# Shared surface (one neutral line)
# ---------------------------------------------------------------------------

def render_shared_skill_depth_summary(result: Any) -> None:
    analysis = get_skill_depth_view(result.payload)
    st.caption("Skill depth: " + analysis.summary_line())
