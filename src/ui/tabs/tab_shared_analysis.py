# src/ui/tabs/tab_shared_analysis.py
#
# Neutral shared-analysis surface. Reads through get_shared_view / get_candidate_view.
# Only public, non-sensitive analysis fields are shown — no perspectives, no PII.

from __future__ import annotations

from typing import Any

import streamlit as st

from src.engine.access_control import get_candidate_view, get_shared_view
from src.ui.components.score_cards import render_score_cards
from src.ui.components.skill_depth_panel import render_shared_skill_depth_summary
from src.ui.components.skill_tables import render_skill_table
from src.ui.components.ui_kit import humanize_seniority, is_very_low_score


def render_shared_analysis_tab(result: Any) -> None:
    payload = result.payload
    shared = get_shared_view(payload)
    candidate = get_candidate_view(payload)
    very_low = is_very_low_score(shared["composite_score_percentage"])

    # JD role title (from candidate view) + public industry metadata.
    st.markdown(
        f"### {candidate['role_title']} — *{payload.jd_entities.industry}*"
    )
    st.caption(f"Required level: {humanize_seniority(candidate['required_seniority'])}")

    render_score_cards(shared)

    st.divider()
    summary = shared["skills_ontology_summary"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Matched skills", summary["matched_count"])
    c2.metric("Critical gaps", summary["critical_gap_count"])
    c3.metric("Coverage", f"{summary['coverage_ratio'] * 100:.0f}%")

    gaps_empty = (
        "Not enough CV evidence to identify specific skill gaps yet."
        if very_low else "No critical gaps."
    )
    render_skill_table("Missing critical skills", candidate["missing_critical"], gaps_empty)

    render_shared_skill_depth_summary(result)

    st.divider()
    st.subheader("Semantic alignment")
    sem = shared["semantic_analysis_summary"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Embedding similarity", f"{sem['embedding_cosine_similarity'] * 100:.0f}%")
    c2.metric("Key-phrase overlap", f"{sem['key_phrase_overlap_ratio'] * 100:.0f}%")
    c3.metric("Domain alignment", f"{sem['contextual_domain_alignment'] * 100:.0f}%")

    shared_phrases = payload.semantic_analysis.shared_key_phrases
    if shared_phrases:
        st.markdown("**Shared key phrases:** " + ", ".join(shared_phrases))
    else:
        st.caption("No shared key phrases identified.")
