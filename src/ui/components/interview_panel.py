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
from src.engine.interview.localizer import (
    localize_band,
    localize_candidate_question,
    localize_followup,
    localize_verification,
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
from src.ui.i18n import current_lang, t

_IMPORTANCE_LABEL_KEY = {
    "must_ask": "interview.must_ask",
    "recommended": "interview.recommended",
    "optional": "interview.optional",
}

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


def _render_evaluation(ev: Any, lang: str) -> None:
    st.markdown(
        badge(localize_band(ev.band, lang), _BAND_KIND.get(ev.band, "neutral")),
        unsafe_allow_html=True,
    )
    progress_row("Structure", ev.structure * 10)
    progress_row("Relevance", ev.relevance * 10)
    progress_row("Specificity", ev.specificity * 10)
    st.write(ev.feedback)
    for tip in ev.improvement_tips:
        st.markdown(f"- {tip}")


def render_candidate_interview_panel(result: Any) -> None:
    lang = current_lang()
    state = _get_candidate_state(result)

    section_header(
        t("interview.practice_title", lang),
        f"{state.role_title} · {humanize_seniority(state.seniority)}",
    )
    notice(t("interview.practice_notice", lang), "info")

    # ── Progress visibility ────────────────────────────────────────────────
    total = len(state.queue)
    answered = len(state.history)
    current_no = min(state.index + 1, total) if not state.finished else total
    avg = (round(sum(t["evaluation"].overall_pct for t in state.history) / answered, 1)
           if answered else None)
    stat_chips([
        (t("interview.question", lang), f"{current_no} / {total}"),
        (t("interview.answered", lang), str(answered)),
        (t("interview.avg_score", lang), f"{avg:.0f}%" if avg is not None else "—"),
        (t("interview.target", lang), f"{_PASS_THRESHOLD}%"),
    ])
    progress_row(t("interview.session_progress", lang), (answered / total * 100) if total else 0.0)
    if avg is not None:
        meets = avg >= _PASS_THRESHOLD
        st.caption(t("interview.on_track", lang) if meets else t("interview.keep_going", lang))
    st.divider()

    # History of completed turns (prompts shown as recorded; band localized).
    answer_prefix = t("interview.your_answer_prefix", lang)
    for i, turn in enumerate(state.history, start=1):
        st.markdown(f"**Q{i}.** {turn['prompt_shown']}")
        st.caption(f"{answer_prefix}: {turn['answer'][:300]}")
        _render_evaluation(turn["evaluation"], lang)
        if not turn["follow_up"].advances and turn["follow_up"].text:
            st.caption(f"{t('interview.followup', lang)}: "
                       f"{localize_followup(turn['follow_up'].text, '', lang)}")
        st.divider()

    prompt = current_prompt(state)
    if state.finished or prompt is None:
        st.success(t("interview.complete", lang))
        if state.history:
            avg = round(sum(t["evaluation"].overall_pct for t in state.history) / len(state.history), 1)
            st.metric(t("interview.avg_answer_score", lang), f"{avg:.0f}%")
        if st.button(t("interview.restart", lang), key="cand_iv_restart"):
            st.session_state.pop(_STATE_KEY, None)
            st.rerun()
        return

    # Localize the current prompt (a follow-up, or the queued question).
    q = state.current_question()
    if state.active_followup:
        shown = localize_followup(state.active_followup, getattr(q, "target", ""), lang)
    else:
        shown = localize_candidate_question(q, lang) if q is not None else prompt

    st.markdown("### " + t("interview.current_question", lang))
    st.markdown(shown)
    answer_key = f"cand_iv_answer_{state.rounds}"
    answer = st.text_area(t("interview.your_answer", lang), key=answer_key, height=140)

    c1, c2, c3 = st.columns(3)
    if c1.button(t("interview.submit", lang), type="primary", key=f"cand_iv_submit_{state.rounds}"):
        if answer.strip():
            submit_answer(state, answer)
            st.rerun()
        else:
            st.warning(t("interview.write_answer", lang))
    if c2.button(t("interview.skip", lang), key=f"cand_iv_skip_{state.rounds}"):
        state.active_followup = None
        state.index += 1
        state.rounds += 1
        if state.index >= len(state.queue) or state.rounds >= state.max_rounds:
            state.finished = True
        st.rerun()
    if c3.button(t("interview.end", lang), key=f"cand_iv_end_{state.rounds}"):
        state.finished = True
        st.rerun()


# ── Recruiter verification guide ───────────────────────────────────────────

def render_recruiter_verification_panel(result: Any) -> None:
    from src.engine.access_control import get_recruiter_view

    lang = current_lang()
    guide = build_recruiter_verification_guide(get_recruiter_view(result.payload))

    section_header(
        t("interview.verify_title", lang),
        f"{guide.role_title} · {humanize_seniority(guide.seniority)}",
    )
    notice(t("interview.verify_notice", lang), "info")

    if not guide.questions:
        st.caption(t("interview.no_questions", lang))
        return

    for i, q in enumerate(guide.questions, start=1):
        loc = localize_verification(q, lang)
        with st.expander(f"{i}. {loc['question']}", expanded=(i <= 2)):
            importance_label = t(_IMPORTANCE_LABEL_KEY.get(loc["importance"], "interview.recommended"), lang)
            st.markdown(
                badge(importance_label, _IMPORTANCE_KIND.get(loc["importance"], "neutral")),
                unsafe_allow_html=True,
            )
            st.markdown("**" + t("interview.strong_header", lang) + "**")
            for s in loc["strong"]:
                st.markdown(f"- {s}")
            st.markdown("**" + t("interview.weak_header", lang) + "**")
            for w in loc["weak"]:
                st.markdown(f"- {w}")
            st.markdown("**" + t("interview.followups_header", lang) + "**")
            for f in loc["followups"]:
                st.markdown(f"- {f}")
