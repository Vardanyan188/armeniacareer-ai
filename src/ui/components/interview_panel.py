# src/ui/components/interview_panel.py
#
# Premium dark UI for the deterministic interview engine.
#   - render_candidate_interview_panel: interactive practice loop (candidate view).
#   - render_recruiter_verification_panel: structured guide (recruiter view).
#
# No raw CV text / PII is rendered — only canonical skill/role/dimension data.

from __future__ import annotations

from typing import Any

import streamlit as st

from src.engine.interview.candidate_practice import (
    build_candidate_interview,
    current_prompt,
    submit_answer,
)
from src.engine.interview.recruiter_verification import build_recruiter_verification_guide
from src.ui.components.ui_kit import (
    badge,
    humanize_seniority,
    notice,
    progress_row,
    section_header,
    stat_chips,
)

_BAND_KIND = {"strong": "good", "adequate": "info", "weak": "warn"}
_IMPORTANCE_KIND = {"must_ask": "bad", "recommended": "info", "optional": "neutral"}
_STATE_KEY = "candidate_interview"
_PASS_THRESHOLD = 60   # target average answer score (%)


# ── Candidate practice ─────────────────────────────────────────────────────

def _get_candidate_state(result: Any):
    from src.engine.access_control import get_candidate_view

    sid = getattr(result, "session_id", "")
    stored = st.session_state.get(_STATE_KEY)
    if stored is None or stored.get("sid") != sid:
        state = build_candidate_interview(get_candidate_view(result.payload))
        st.session_state[_STATE_KEY] = {"sid": sid, "state": state}
    return st.session_state[_STATE_KEY]["state"]


def _render_evaluation(ev: Any) -> None:
    st.markdown(badge(ev.band.title(), _BAND_KIND.get(ev.band, "neutral")), unsafe_allow_html=True)
    progress_row("Structure", ev.structure * 10)
    progress_row("Relevance", ev.relevance * 10)
    progress_row("Specificity", ev.specificity * 10)
    st.write(ev.feedback)
    for tip in ev.improvement_tips:
        st.markdown(f"- {tip}")


def render_candidate_interview_panel(result: Any) -> None:
    state = _get_candidate_state(result)

    section_header(
        "Interview Practice",
        f"{state.role_title} · {humanize_seniority(state.seniority)}",
    )
    notice(
        "Practice mode — private, supportive coaching. Your answers are not stored "
        "or shared.",
        "info",
    )

    # ── Progress visibility ────────────────────────────────────────────────
    total = len(state.queue)
    answered = len(state.history)
    current_no = min(state.index + 1, total) if not state.finished else total
    avg = (round(sum(t["evaluation"].overall_pct for t in state.history) / answered, 1)
           if answered else None)
    stat_chips([
        ("Question", f"{current_no} / {total}"),
        ("Answered", str(answered)),
        ("Avg score", f"{avg:.0f}%" if avg is not None else "—"),
        ("Target", f"{_PASS_THRESHOLD}%"),
    ])
    progress_row("Session progress", (answered / total * 100) if total else 0.0)
    if avg is not None:
        meets = avg >= _PASS_THRESHOLD
        st.caption(
            f"On track — average meets the {_PASS_THRESHOLD}% target."
            if meets else
            f"Keep going — aim to lift your average to {_PASS_THRESHOLD}%."
        )
    st.divider()

    # History of completed turns.
    for i, turn in enumerate(state.history, start=1):
        st.markdown(f"**Q{i}.** {turn['prompt_shown']}")
        st.caption(f"Your answer: {turn['answer'][:300]}")
        _render_evaluation(turn["evaluation"])
        if not turn["follow_up"].advances and turn["follow_up"].text:
            st.caption(f"Follow-up: {turn['follow_up'].text}")
        st.divider()

    prompt = current_prompt(state)
    if state.finished or prompt is None:
        st.success("Practice session complete. Review the feedback above.")
        if state.history:
            avg = round(sum(t["evaluation"].overall_pct for t in state.history) / len(state.history), 1)
            st.metric("Average answer score", f"{avg:.0f}%")
        if st.button("Restart practice", key="cand_iv_restart"):
            st.session_state.pop(_STATE_KEY, None)
            st.rerun()
        return

    st.markdown("### Current question")
    st.markdown(prompt)
    answer_key = f"cand_iv_answer_{state.rounds}"
    answer = st.text_area("Your answer", key=answer_key, height=140)

    c1, c2, c3 = st.columns(3)
    if c1.button("Submit answer", type="primary", key=f"cand_iv_submit_{state.rounds}"):
        if answer.strip():
            submit_answer(state, answer)
            st.rerun()
        else:
            st.warning("Write an answer before submitting.")
    if c2.button("Skip question", key=f"cand_iv_skip_{state.rounds}"):
        state.active_followup = None
        state.index += 1
        state.rounds += 1
        if state.index >= len(state.queue) or state.rounds >= state.max_rounds:
            state.finished = True
        st.rerun()
    if c3.button("End session", key=f"cand_iv_end_{state.rounds}"):
        state.finished = True
        st.rerun()


# ── Recruiter verification guide ───────────────────────────────────────────

def render_recruiter_verification_panel(result: Any) -> None:
    from src.engine.access_control import get_recruiter_view

    guide = build_recruiter_verification_guide(get_recruiter_view(result.payload))

    section_header(
        "Verification Interview",
        f"{guide.role_title} · {humanize_seniority(guide.seniority)}",
    )
    notice(
        "Structured, evidence-based verification guide for manual evaluation. "
        "Decision-support only — the recruiter judges the answers.",
        "info",
    )

    if not guide.questions:
        st.caption("No verification questions generated for this analysis.")
        return

    for i, q in enumerate(guide.questions, start=1):
        with st.expander(f"{i}. {q.question}", expanded=(i <= 2)):
            st.markdown(
                badge(q.importance.replace("_", " ").title(),
                      _IMPORTANCE_KIND.get(q.importance, "neutral")),
                unsafe_allow_html=True,
            )
            st.markdown("**A strong answer should contain**")
            for s in q.strong_answer_contains:
                st.markdown(f"- {s}")
            st.markdown("**Weak / unclear answers may indicate**")
            for w in q.weak_answer_indicates:
                st.markdown(f"- {w}")
            st.markdown("**Suggested follow-ups**")
            for f in q.suggested_followups:
                st.markdown(f"- {f}")
