# tests/test_ui_imports.py
#
# Import-only smoke tests for the UI layer. Streamlit is NOT launched; we only
# verify the modules import and expose their render entrypoints. No data/raw,
# no LLM, no network.

import importlib

import pytest

pytest.importorskip("streamlit")

_UI_MODULES = [
    "src.ui.components.score_cards",
    "src.ui.components.skill_tables",
    "src.ui.components.governance_panel",
    "src.ui.components.cv_quality_panel",
    "src.ui.components.ui_kit",
    "src.ui.components.candidate_pool_panel",
    "src.ui.components.interview_panel",
    "src.ui.components.quiz_panel",
    "src.ui.components.ranking_panel",
    "src.ui.components.data_ingest_panel",
    "src.ui.components.skill_depth_panel",
    "src.ui.components.jd_version_panel",
    "src.ui.components.utility_bar",
    "src.ui.components.summary_builders",
    "src.ui.components.export_panel",
    "src.ui.app_gates",
    "src.ui.upload_utils",
    "src.ui.tabs.tab_input",
    "src.ui.tabs.tab_shared_analysis",
    "src.ui.tabs.tab_candidate_room",
    "src.ui.tabs.tab_recruiter_room",
    "src.ui.modes.mode_admin",
    "src.ui.modes.mode_candidate",
    "src.ui.modes.mode_recruiter",
    "streamlit_app",
]


@pytest.mark.parametrize("module_name", _UI_MODULES)
def test_ui_module_imports(module_name):
    importlib.import_module(module_name)


def test_render_entrypoints_exist():
    from src.ui.components.ui_kit import progress_row
    from src.ui.components.candidate_pool_panel import render_candidate_pool_section
    from src.ui.components.data_ingest_panel import render_data_ingest_panel
    from src.ui.components.skill_depth_panel import render_candidate_skill_depth
    from src.ui.components.jd_version_panel import render_jd_version_panel
    from src.ui.components.utility_bar import render_utility_bar, is_focus_mode
    from src.ui.components.export_panel import render_export_panel
    from src.ui.components.ui_kit import inject_presentation_css
    from src.ui.components.score_cards import render_score_cards
    from src.ui.tabs.tab_candidate_room import render_candidate_room
    from src.ui.tabs.tab_input import render_input_tab
    from src.ui.tabs.tab_recruiter_room import render_recruiter_room
    from src.ui.tabs.tab_shared_analysis import render_shared_analysis_tab
    from src.ui.modes.mode_admin import render_admin_mode
    from src.ui.modes.mode_candidate import render_candidate_mode
    from src.ui.modes.mode_recruiter import render_recruiter_mode
    import streamlit_app

    for fn in (
        render_score_cards, render_input_tab, render_shared_analysis_tab,
        render_candidate_room, render_recruiter_room,
        render_admin_mode, render_candidate_mode, render_recruiter_mode,
        progress_row, render_candidate_pool_section, render_data_ingest_panel,
        render_candidate_skill_depth, render_jd_version_panel, render_utility_bar,
        render_export_panel, is_focus_mode, inject_presentation_css,
        streamlit_app.main,
    ):
        assert callable(fn)


def test_humanize_seniority_labels():
    from src.ui.components.ui_kit import humanize_label, humanize_seniority

    assert humanize_seniority("senior") == "senior-level"
    assert humanize_seniority("mid") == "mid-level"
    assert humanize_seniority("intern") == "intern-level"
    # Tolerates enum-like objects exposing `.value`.
    class _E:
        value = "lead"
    assert humanize_seniority(_E()) == "lead-level"
    assert humanize_label("strong_yes") == "Strong Yes"


def test_low_score_messaging():
    from src.ui.components.ui_kit import (
        candidate_low_score_message,
        is_low_score,
        is_very_low_score,
        recruiter_low_score_message,
    )

    assert is_very_low_score(0.0) is True
    assert is_low_score(10.0) is True
    assert is_low_score(80.0) is False
    # Zero-score wording must not sound positive.
    msg = candidate_low_score_message(0.0).lower()
    assert "not provide enough evidence" in msg
    assert "viable path" not in msg
    rmsg = recruiter_low_score_message(0.0).lower()
    assert "insufficient cv evidence" in rmsg
