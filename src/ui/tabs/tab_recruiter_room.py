# src/ui/tabs/tab_recruiter_room.py
#
# Recruiter Intelligence Room. Reads ONLY through get_recruiter_view, which
# excludes the candidate's coaching roadmap and motivational framing. Only the
# PROCESSED bias risk level is shown — never raw demographic signals.

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from src.ui.components.ui_kit import (
    df_width_kwargs,
    humanize_label,
    humanize_seniority,
    is_low_score,
    is_very_low_score,
    notice,
    recruiter_low_score_message,
)


def render_recruiter_room(result: Any) -> None:
    from src.engine.access_control import get_recruiter_view

    view = get_recruiter_view(result.payload)
    rp = view["recruiter_perspective"]
    pct = view["composite_score_percentage"]
    low = is_low_score(pct)
    very_low = is_very_low_score(pct)

    st.subheader("Recruiter Intelligence Room")
    st.caption(
        f"Target role: {view['jd_entities'].role_title} · "
        f"{humanize_seniority(view['jd_entities'].required_seniority)}. "
        "Decision-support only — all outputs require human review."
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Composite score", f"{pct:.1f}%")
    c2.metric("Hire recommendation", humanize_label(rp.hire_recommendation))
    c3.metric("Evaluation integrity risk", humanize_label(view["evaluation_integrity_risk"]))

    if low:
        notice(recruiter_low_score_message(pct), "warn")

    st.markdown("### Screening summary")
    st.write(rp.screening_summary)
    if very_low:
        st.caption(
            "Note: low evidence — an absence of detected skill gaps reflects "
            "limited CV extraction, not strong coverage."
        )
    st.markdown("**Recommendation rationale**")
    st.write(rp.hire_recommendation_rationale)

    if rp.comparative_profile_summary:
        st.markdown("### Comparative profile")
        st.write(rp.comparative_profile_summary)

    if rp.red_flag_summary:
        st.markdown("### Red flags")
        st.warning(rp.red_flag_summary)

    st.divider()
    st.markdown("### Verification points")
    if rp.verification_points:
        df = pd.DataFrame([{
            "Topic": vp.topic,
            "Gap evidence": vp.evidence_gap_description,
            "Why it matters": vp.why_it_matters,
            "Suggested question": vp.suggested_interview_question,
            "Importance": vp.importance_level.replace("_", " ").title(),
        } for vp in rp.verification_points])
        st.dataframe(df, hide_index=True, **df_width_kwargs())
    elif very_low:
        st.caption(
            "No verification points — insufficient CV evidence. Verify core "
            "competencies directly in the interview."
        )
    else:
        st.caption("No verification points generated.")

    recs = view["structured_interview_recommendations"]
    if recs:
        st.markdown("### Structured interview recommendations")
        for r in recs:
            st.markdown(f"- {r}")
