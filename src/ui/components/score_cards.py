# src/ui/components/score_cards.py
#
# Composite score + seven dimension scores. Reads a shared-view dict produced by
# src.engine.access_control.get_shared_view (never the raw payload directly).

from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from src.ui.components.ui_kit import is_very_low_score, progress_row, score_card

DIMENSION_LABELS: Dict[str, str] = {
    "technical_skills_match": "Technical Skills",
    "experience_depth_alignment": "Experience Depth",
    "educational_relevance": "Education",
    "domain_knowledge": "Domain Knowledge",
    "soft_skills_signals": "Soft Skills",
    "seniority_trajectory": "Seniority Fit",
    "semantic_contextual_alignment": "Contextual Alignment",
}


def _dimension_percentages(dimensional_analysis: Any) -> Dict[str, float]:
    return {
        label: round(getattr(dimensional_analysis, key).raw_score * 100, 1)
        for key, label in DIMENSION_LABELS.items()
    }


def render_score_cards(shared_view: Dict[str, Any]) -> None:
    """Renders the composite score card and seven calm, contained dimension bars."""
    pct = shared_view["composite_score_percentage"]
    score_card("Composite Match Score", pct)
    if is_very_low_score(pct):
        st.caption(
            "Reported as-is from the extracted CV evidence — a low score reflects "
            "limited evidence, not a system error."
        )

    da = shared_view["dimensional_analysis"]
    scores = _dimension_percentages(da)

    st.caption("Dimension breakdown")
    with st.container():
        for label, pct in scores.items():
            progress_row(label, pct)

    if getattr(da, "hard_floor_applied", False):
        st.caption("A hard floor was applied: a critical dimension fell below threshold.")
