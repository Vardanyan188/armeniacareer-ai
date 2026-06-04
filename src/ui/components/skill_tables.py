# src/ui/components/skill_tables.py
#
# Renders skill-match tables from lists of SkillMatchEntry objects (as exposed by
# the access-control views). No raw CV text or PII is rendered.

from __future__ import annotations

from typing import Any, List

import pandas as pd
import streamlit as st

from src.ui.components.ui_kit import df_width_kwargs


def _skill_dataframe(entries: List[Any]) -> pd.DataFrame:
    rows = []
    for e in entries:
        rows.append({
            "Skill": getattr(e, "canonical_name", ""),
            "Critical": getattr(e, "is_critical", False),
            "Transfer confidence": getattr(e, "transfer_confidence", None),
        })
    return pd.DataFrame(rows)


def render_skill_table(title: str, entries: List[Any], empty_text: str = "None") -> None:
    st.markdown(f"**{title}** ({len(entries)})")
    if not entries:
        st.caption(empty_text)
        return
    df = _skill_dataframe(entries)
    # Drop the transfer column entirely when no entry carries a confidence value.
    if df["Transfer confidence"].isna().all():
        df = df.drop(columns=["Transfer confidence"])
    st.dataframe(df, hide_index=True, **df_width_kwargs())


def render_skill_overview(matched, missing_critical, missing_preferred, transferable) -> None:
    """Compact four-column count summary."""
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Matched", len(matched))
    c2.metric("Missing critical", len(missing_critical))
    c3.metric("Missing preferred", len(missing_preferred))
    c4.metric("Transferable", len(transferable))
