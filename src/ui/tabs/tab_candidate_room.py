# src/ui/tabs/tab_candidate_room.py
#
# Candidate Coach Room. Reads ONLY through get_candidate_view, which by design
# excludes hire recommendation, recruiter verification points, and red flags.

from __future__ import annotations

from typing import Any

import streamlit as st

from src.engine.access_control import get_candidate_view
from src.ui.components.skill_tables import render_skill_overview, render_skill_table
from src.ui.components.ui_kit import (
    candidate_low_score_message,
    humanize_seniority,
    is_low_score,
    is_very_low_score,
    notice,
)


def render_candidate_room(result: Any) -> None:
    view = get_candidate_view(result.payload)
    cp = view["candidate_perspective"]
    pct = view["composite_score_percentage"]
    low = is_low_score(pct)
    very_low = is_very_low_score(pct)

    st.subheader("Candidate Coach Room")
    st.caption(
        f"Target role: {view['role_title']} · {humanize_seniority(view['required_seniority'])}. "
        "Your personalized development view, for your preparation only."
    )

    c1, c2 = st.columns(2)
    c1.metric("Match score", f"{pct:.1f}%")
    c2.metric("Analysis confidence", f"{view['overall_confidence'] * 100:.0f}%")

    if low:
        notice(candidate_low_score_message(pct), "warn")

    st.markdown("### Your strengths")
    if very_low:
        st.write(
            "Not enough role-specific evidence was extracted from your CV to "
            "highlight strengths for this position yet. Add concrete tools, "
            "projects, and measurable outcomes to surface your strengths."
        )
    else:
        st.write(cp.strength_narrative)
        if cp.top_strength_phrases:
            st.markdown("**Top strengths:** " + ", ".join(cp.top_strength_phrases))
        if cp.motivational_framing and not low:
            st.info(cp.motivational_framing)

    st.divider()
    st.markdown("### Skill picture")
    render_skill_overview(
        view["matched_skills"], view["missing_critical"],
        view["missing_preferred"], view["transferable"],
    )
    gaps_empty = (
        "Not enough CV evidence to identify specific skill gaps yet."
        if very_low else "No critical gaps."
    )
    render_skill_table("Missing critical skills", view["missing_critical"], gaps_empty)

    st.divider()
    st.markdown("### Development roadmap")
    roadmap = sorted(cp.gap_closure_roadmap, key=lambda x: x.priority)
    if not roadmap:
        st.caption("No roadmap items generated.")
    for item in roadmap:
        header = f"Priority {item.priority} — {item.skill_or_gap}"
        if item.is_critical_gap_closure:
            header = "★ " + header
        with st.expander(header):
            st.markdown(f"**Current:** {item.current_state_description}")
            st.markdown(f"**Target:** {item.target_state_description}")
            if item.estimated_effort_weeks:
                st.caption(f"Estimated effort: {item.estimated_effort_weeks} weeks")
            for res in item.suggested_learning_resources:
                st.markdown(f"- {res}")

    st.divider()
    st.markdown("### Interview preparation focus")
    st.write(cp.interview_preparation_focus)

    st.markdown("### Salary positioning")
    st.write(cp.salary_positioning_context)
