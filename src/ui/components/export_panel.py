# src/ui/components/export_panel.py
#
# Phase 21.2 — Export / Copy panel. Renders a role-safe Markdown summary in a
# collapsed expander with a copyable code block, a .md download, and a
# print-via-browser tip. No HTML/PDF, no heavy deps. All summaries are built
# from role-safe access-control views via summary_builders.

from __future__ import annotations

from typing import Any, Optional

import streamlit as st

from src.engine.access_control import (
    get_candidate_view,
    get_recruiter_view,
    get_shared_view,
    get_skill_depth_view,
)
from src.ui.components.summary_builders import (
    build_admin_demo_markdown_summary,
    build_bulk_ranking_markdown_summary,
    build_candidate_markdown_summary,
    build_governance_markdown_summary,
    build_jd_diff_markdown_summary,
    build_recruiter_markdown_summary,
)

_PRIVACY_NOTE = (
    "Role-safe summary — no raw CV/JD text, no PII. You copy or download it "
    "manually; nothing is uploaded or shared."
)
_PRINT_TIP = "Tip: use your browser's Print (Ctrl/Cmd + P) to save this as PDF."


def render_export_panel(
    title: str, markdown: str, *, filename: str, note: Optional[str] = None,
) -> None:
    """Generic collapsed export/copy panel."""
    with st.expander(f"Export / Copy summary · {title}", expanded=False):
        st.caption(note or _PRIVACY_NOTE)
        st.code(markdown, language="markdown")
        st.download_button(
            "Download .md", data=markdown, file_name=filename,
            mime="text/markdown", key=f"dl_{filename}",
        )
        st.caption(_PRINT_TIP)


# ---------------------------------------------------------------------------
# Role-safe wrappers
# ---------------------------------------------------------------------------

def render_candidate_export(result: Any) -> None:
    payload = result.payload
    md = build_candidate_markdown_summary(
        get_candidate_view(payload),
        shared_view=get_shared_view(payload),
        skill_depth=get_skill_depth_view(payload),
    )
    render_export_panel("Candidate", md, filename="candidate_summary.md")


def render_recruiter_export(result: Any, ranked_candidate: Any = None) -> None:
    payload = result.payload
    md = build_recruiter_markdown_summary(
        get_recruiter_view(payload),
        shared_view=get_shared_view(payload),
        skill_depth=get_skill_depth_view(payload),
        ranked_candidate=ranked_candidate,
    )
    render_export_panel("Recruiter", md, filename="recruiter_summary.md")


def render_governance_export(result: Any) -> None:
    md = build_governance_markdown_summary(result)
    render_export_panel("Governance", md, filename="governance_summary.md")


def render_jd_diff_export(diff: Any) -> None:
    md = build_jd_diff_markdown_summary(diff)
    render_export_panel("JD changes", md, filename="jd_diff_summary.md")


def render_bulk_ranking_export(bulk_result: Any) -> None:
    md = build_bulk_ranking_markdown_summary(bulk_result)
    render_export_panel("Ranking", md, filename="ranking_summary.md")


def render_admin_export(result: Any) -> None:
    payload = result.payload
    md = build_admin_demo_markdown_summary(
        get_candidate_view(payload),
        get_recruiter_view(payload),
        shared_view=get_shared_view(payload),
    )
    render_export_panel(
        "Internal demo", md, filename="admin_demo_summary.md",
        note="INTERNAL DEMO export — decision-support only, not a hiring decision. "
             "No private files or paths are included.",
    )
