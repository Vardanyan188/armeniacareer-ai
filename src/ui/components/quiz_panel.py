# src/ui/components/quiz_panel.py
#
# Premium dark UI for the deterministic Candidate Skill Quiz.
# Candidate Mode only. Reads candidate-safe data; renders no raw CV text / PII.

from __future__ import annotations

from typing import Any

import streamlit as st

from src.engine.quiz.models import Focus
from src.engine.quiz.quiz_builder import build_candidate_quiz
from src.engine.quiz.quiz_eval import TARGET_SCORE, grade_question, summarize_quiz
from src.ui.components.ui_kit import (
    badge,
    humanize_seniority,
    notice,
    progress_row,
    section_header,
    stat_chips,
)

_STATE_KEY = "candidate_quiz"

_FOCUS_BADGE = {
    Focus.MISSING_SKILL: ("Missing skill", "warn"),
    Focus.MATCHED_SKILL: ("Validate skill", "good"),
    Focus.WEAK_DIMENSION: ("Weak area", "info"),
}
_BAND_KIND = {"strong": "good", "solid": "info", "keep_building": "warn"}


def _get_state(result: Any):
    from src.engine.access_control import get_candidate_view

    sid = getattr(result, "session_id", "")
    stored = st.session_state.get(_STATE_KEY)
    if stored is None or stored.get("sid") != sid:
        state = build_candidate_quiz(get_candidate_view(result.payload))
        st.session_state[_STATE_KEY] = {"sid": sid, "state": state}
    return st.session_state[_STATE_KEY]["state"]


def _rationale(focus: Focus, target: str) -> str:
    if focus == Focus.MISSING_SKILL:
        return f"{target} is a required skill not evident in your CV."
    if focus == Focus.MATCHED_SKILL:
        return f"Confirming your understanding of {target}."
    return f"{target} scored lower in your analysis."


def render_candidate_quiz_panel(result: Any) -> None:
    state = _get_state(result)

    section_header(
        "Skill Quiz",
        f"{state.role_title} · {humanize_seniority(state.seniority)}",
    )
    notice(
        "Practice quiz based on your analysis. It's a learning tool — answers are "
        "private and not stored or shared.",
        "info",
    )

    total = state.total()
    answered = state.answered_count()
    correct = state.correct_count()
    score = round((correct / answered) * 100) if answered else 0
    current_no = min(state.index + 1, total) if not state.finished else total
    stat_chips([
        ("Question", f"{current_no} / {total}"),
        ("Answered", str(answered)),
        ("Score", f"{score}%" if answered else "—"),
        ("Target", f"{TARGET_SCORE}%"),
    ])
    progress_row("Quiz progress", (answered / total * 100) if total else 0.0)
    st.divider()

    # ── Final summary ──────────────────────────────────────────────────────
    if state.finished or state.index >= total:
        summary = summarize_quiz(state)
        st.markdown(badge(summary.band.replace("_", " ").title(),
                          _BAND_KIND.get(summary.band, "neutral")), unsafe_allow_html=True)
        st.metric("Final score", f"{summary.score_pct:.0f}%  ({summary.correct}/{summary.total})")
        st.write(summary.band_message)
        if summary.study_next:
            st.markdown("**Study next**")
            for item in summary.study_next:
                st.markdown(f"- {item}")
        elif summary.weak_areas:
            st.markdown("**Review**")
            for item in summary.weak_areas:
                st.markdown(f"- {item}")
        else:
            st.success("No weak areas flagged in this quiz — well done.")
        if st.button("Restart quiz", key="quiz_restart"):
            st.session_state.pop(_STATE_KEY, None)
            st.rerun()
        return

    # ── Current question ───────────────────────────────────────────────────
    q = state.current()
    label, kind = _FOCUS_BADGE.get(q.focus, ("Question", "neutral"))
    st.markdown(badge(label, kind), unsafe_allow_html=True)
    st.caption(_rationale(q.focus, q.target))
    st.markdown(f"**Q{state.index + 1}. {q.stem}**")

    answered_this = state.answers[state.index] is not None
    if not answered_this:
        choice = st.radio(
            "Choose one", list(range(len(q.options))),
            format_func=lambda i: q.options[i], index=None,
            key=f"quiz_opt_{state.index}",
        )
        if st.button("Submit answer", type="primary", key=f"quiz_submit_{state.index}"):
            if choice is None:
                st.warning("Select an option before submitting.")
            else:
                state.answers[state.index] = choice
                st.rerun()
    else:
        selected = state.answers[state.index]
        result_grade = grade_question(q, selected)
        for i, opt in enumerate(q.options):
            mark = "✓" if i == q.correct_index else ("✗" if i == selected else "•")
            st.markdown(f"{mark} {opt}")
        if result_grade.is_correct:
            notice(result_grade.feedback, "good")
        else:
            notice(result_grade.feedback, "warn")
        st.caption(f"Study tip: {result_grade.study_tip}")

        is_last = state.index + 1 >= total
        if st.button("See results" if is_last else "Next question",
                     type="primary", key=f"quiz_next_{state.index}"):
            state.index += 1
            if state.index >= total:
                state.finished = True
            st.rerun()
