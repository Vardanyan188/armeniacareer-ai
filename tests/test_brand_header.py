# tests/test_brand_header.py
#
# Phase 24.3A — brand lockup + app header builders. Pure HTML strings.

import re

from src.ui.components.ui_kit import (
    app_header_html,
    brand_lockup_html,
    brand_mark_svg,
)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def _safe(html: str) -> None:
    assert "@" not in html or not _EMAIL_RE.search(html)
    low = html.lower()
    assert "data/private" not in low and "sk-" not in low


def test_brand_mark_svg_is_valid_and_safe():
    svg = brand_mark_svg(28)
    assert svg.startswith("<svg") and "</svg>" in svg
    assert "width='28'" in svg
    _safe(svg)


def test_brand_lockup_shows_full_name_and_tagline():
    html = brand_lockup_html("ArmeniaCareer AI", "Career Intelligence")
    assert "ArmeniaCareer AI" in html
    assert "Career Intelligence" in html
    assert "<svg" in html                      # mark present
    _safe(html)


def test_brand_lockup_escapes_injection():
    html = brand_lockup_html("<script>x</script>", "tag")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_app_header_shows_brand_and_mode():
    html = app_header_html("ArmeniaCareer AI", "Candidate", "Analyze your CV.",
                           badge_text="", icon="◆")
    assert "ArmeniaCareer AI" in html
    assert "Candidate" in html and "Analyze your CV." in html
    _safe(html)


def test_app_header_admin_badge():
    html = app_header_html("ArmeniaCareer AI", "Admin · Demo", "Internal demo.",
                           badge_text="Internal Demo Mode", icon="▣")
    assert "Internal Demo Mode" in html


def test_ui_kit_exports_all_names_streamlit_app_needs():
    # Regression guard for the public ImportError: streamlit_app imports these
    # exact names from ui_kit — they must all exist.
    import importlib
    ui_kit = importlib.import_module("src.ui.components.ui_kit")
    for name in ("brand_mark_svg", "brand_lockup_html", "app_header_html",
                 "inject_global_style", "inject_presentation_css", "df_width_kwargs"):
        assert hasattr(ui_kit, name), f"ui_kit is missing required export: {name}"


def test_streamlit_app_imports_cleanly():
    import streamlit_app
    assert callable(streamlit_app.main)


def test_inject_global_style_has_top_padding():
    # The header-spacing fix lives in inject_global_style — verify the rule shape.
    import inspect
    from src.ui.components import ui_kit
    src = inspect.getsource(ui_kit.inject_global_style)
    assert "padding-top:2.4rem" in src or "padding-top: 2.4rem" in src
    assert "block-container" in src
