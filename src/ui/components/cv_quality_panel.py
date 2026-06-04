# src/ui/components/cv_quality_panel.py
#
# Renders a CVQualityReport with clean score cards, progress bars, and simple
# tables. No zoom-heavy charts. No raw CV text is displayed.

from __future__ import annotations

from typing import Any

import streamlit as st

from src.ui.i18n import current_lang, t

_SECTION_KEYS = [
    ("experience", "cv.report.work_experience"),
    ("education", "cv.report.education"),
    ("skills", "cv.report.skills"),
    ("summary", "cv.report.summary"),
]


def render_cv_quality(report: Any) -> None:
    lang = current_lang()
    yes, missing = t("cv.report.present", lang), t("cv.report.missing", lang)

    st.markdown("### " + t("cv.report.title", lang))

    band = getattr(report, "extraction_quality_band", "good")
    if getattr(report, "is_probably_scanned", False):
        st.error(t("cv.report.scanned_warning", lang))
    elif band == "low":
        st.warning(t("cv.report.low_warning", lang))
    elif band == "partial":
        st.info(t("cv.report.partial_warning", lang))

    c1, c2, c3 = st.columns(3)
    c1.metric(t("cv.report.quality_score", lang), f"{report.quality_score * 100:.0f}%")
    c2.metric(t("cv.report.skills_detected", lang), report.skill_count)
    c3.metric(t("cv.report.word_count", lang), report.word_count)
    st.progress(min(max(report.quality_score, 0.0), 1.0))

    st.divider()
    st.markdown("#### " + t("cv.report.sections", lang))
    cols = st.columns(len(_SECTION_KEYS) + 1)
    cols[0].metric(
        t("cv.report.contact_info", lang), yes if report.contact_info_present else missing
    )
    for i, (key, label_key) in enumerate(_SECTION_KEYS, start=1):
        present = report.sections_present.get(key, False)
        cols[i].metric(t(label_key, lang), yes if present else missing)

    st.divider()
    st.markdown("#### " + t("cv.report.detected_skills", lang))
    if report.detected_skills:
        st.write(", ".join(report.detected_skills))
    else:
        st.caption(t("cv.report.no_skills", lang))

    if report.languages:
        st.markdown(f"**{t('cv.report.languages', lang)}:** " + ", ".join(report.languages))

    # Layout & readability advisory (safe, localized; shown only when relevant).
    layout_warnings = (getattr(report, "diagnostics", {}) or {}).get("layout_warnings", [])
    if layout_warnings:
        st.divider()
        st.markdown("#### " + t("cv.layout.title", lang))
        for key in layout_warnings:
            st.info(t(key, lang))

    st.divider()
    st.markdown("#### " + t("cv.report.role_directions", lang))
    for role in report.role_suggestions:
        st.markdown(f"- {role}")

    st.divider()
    st.markdown("#### " + t("cv.report.improvement", lang))
    if report.improvement_suggestions:
        for tip in report.improvement_suggestions:
            st.markdown(f"- {tip}")
    else:
        st.success(t("cv.report.no_issues", lang))
