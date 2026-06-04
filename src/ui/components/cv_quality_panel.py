# src/ui/components/cv_quality_panel.py
#
# Renders a CVQualityReport with clean score cards, progress bars, and simple
# tables. No zoom-heavy charts. No raw CV text is displayed.

from __future__ import annotations

from typing import Any

import streamlit as st

_SECTION_LABELS = {
    "experience": "Work Experience",
    "education": "Education",
    "skills": "Skills",
    "summary": "Summary",
}


def render_cv_quality(report: Any) -> None:
    st.markdown("### CV intelligence report")

    band = getattr(report, "extraction_quality_band", "good")
    if getattr(report, "is_probably_scanned", False):
        st.error(
            "Low extraction quality — this looks like a scanned/image PDF with no "
            "text layer. Please upload a text-based PDF or DOCX for an accurate "
            "analysis."
        )
    elif band == "low":
        st.warning(
            "Low extraction quality — very little readable text was found. Results "
            "may be unreliable."
        )
    elif band == "partial":
        st.info("Partial extraction — some sections may not have been detected.")

    c1, c2, c3 = st.columns(3)
    c1.metric("CV quality score", f"{report.quality_score * 100:.0f}%")
    c2.metric("Skills detected", report.skill_count)
    c3.metric("Word count", report.word_count)
    st.progress(min(max(report.quality_score, 0.0), 1.0))

    st.divider()
    st.markdown("#### Sections")
    cols = st.columns(len(_SECTION_LABELS) + 1)
    cols[0].metric("Contact info", "Yes" if report.contact_info_present else "Missing")
    for i, (key, label) in enumerate(_SECTION_LABELS.items(), start=1):
        present = report.sections_present.get(key, False)
        cols[i].metric(label, "Yes" if present else "Missing")

    st.divider()
    st.markdown("#### Detected skills")
    if report.detected_skills:
        st.write(", ".join(report.detected_skills))
    else:
        st.caption("No recognised technical skills detected. Add a clear Skills section.")

    if report.languages:
        st.markdown("**Languages:** " + ", ".join(report.languages))

    st.divider()
    st.markdown("#### Possible role directions")
    for role in report.role_suggestions:
        st.markdown(f"- {role}")

    st.divider()
    st.markdown("#### Improvement suggestions")
    if report.improvement_suggestions:
        for tip in report.improvement_suggestions:
            st.markdown(f"- {tip}")
    else:
        st.success("No major structural issues detected. Strong CV foundation.")
