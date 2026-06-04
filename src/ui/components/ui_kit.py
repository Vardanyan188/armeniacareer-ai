# src/ui/components/ui_kit.py
#
# Premium dark-theme UI primitives + shared display helpers.
# Minimal, contained inline CSS (no external frameworks). All dynamic text is
# HTML-escaped before render.

from __future__ import annotations

import html
from typing import Any, Iterable, Optional

import streamlit as st

# ── Dark palette ───────────────────────────────────────────────────────────
_BG = "#0e1117"
_SURFACE = "#161b22"
_SURFACE_ALT = "#1b2230"
_BORDER = "#262c37"
_TEXT = "#e6e8eb"
_TEXT_LABEL = "#c7ccd4"
_TEXT_MUTED = "#8b929e"
_BAR_TRACK = "#2a2f3a"

_BADGE_KINDS = {
    "neutral": ("#1b2230", "#c7ccd4"),
    "good": ("#15301f", "#7fd1a3"),
    "warn": ("#2e2410", "#e0b766"),
    "bad": ("#2e1616", "#e09a9a"),
    "info": ("#14233f", "#8fb6f0"),
}

# ── Low-score thresholds + wording ─────────────────────────────────────────
LOW_SCORE_THRESHOLD = 25.0
VERY_LOW_THRESHOLD = 5.0

_SENIORITY_LABELS = {
    "intern": "intern-level",
    "junior": "junior-level",
    "mid": "mid-level",
    "senior": "senior-level",
    "lead": "lead-level",
    "principal": "principal-level",
    "executive": "executive-level",
}


def _bar_color(pct: float) -> str:
    if pct >= 70:
        return "#4f9d77"
    if pct >= 40:
        return "#c9a14a"
    return "#c2766a"


# ── Enum / label humanization ──────────────────────────────────────────────

def humanize_seniority(value: Any) -> str:
    """Maps a SeniorityLevel (enum or string) to 'mid-level', 'senior-level', …"""
    raw = str(getattr(value, "value", value)).strip().lower()
    return _SENIORITY_LABELS.get(raw, raw.replace("_", " ") or "unspecified")


def humanize_label(value: Any) -> str:
    """Maps an enum/string like 'strong_yes' → 'Strong Yes'."""
    raw = str(getattr(value, "value", value)).strip()
    return raw.replace("_", " ").title() if raw else ""


# ── Low-score messaging ────────────────────────────────────────────────────

def is_low_score(pct: float) -> bool:
    return pct < LOW_SCORE_THRESHOLD


def is_very_low_score(pct: float) -> bool:
    return pct < VERY_LOW_THRESHOLD


def candidate_low_score_message(pct: float) -> str:
    if pct < VERY_LOW_THRESHOLD:
        return (
            "The current CV does not provide enough evidence for this role. The "
            "match is weak based on the extracted CV evidence. Strengthen your CV "
            "with concrete projects, tools, and measurable experience before applying."
        )
    return (
        "The match is currently weak based on the extracted CV evidence. Focus on "
        "the gaps below and add concrete, measurable experience to improve your fit."
    )


def recruiter_low_score_message(pct: float) -> str:
    if pct < VERY_LOW_THRESHOLD:
        return (
            "Insufficient CV evidence to assess fit for this role. Treat as "
            "inconclusive and verify qualifications directly before proceeding."
        )
    return (
        "Weak match based on the extracted CV evidence. Interpret conservatively and "
        "verify core competencies directly."
    )


# ── Global theme ───────────────────────────────────────────────────────────

def inject_global_style() -> None:
    """
    Injects contained structural refinements that complement the dark base theme
    (.streamlit/config.toml). Base colors/text are driven by the theme; this only
    tunes layout width and surface treatment so the UI feels premium and calm.
    """
    st.markdown(
        f"""
<style>
.block-container {{ max-width:1120px; padding-top:1.4rem; padding-bottom:3rem; }}
h1,h2,h3,h4,h5 {{ font-weight:650; letter-spacing:0.2px; }}
section[data-testid="stSidebar"] {{ border-right:1px solid {_BORDER}; }}
[data-testid="stMetric"] {{
  background:{_SURFACE}; border:1px solid {_BORDER}; border-radius:12px;
  padding:12px 16px; transition:border-color .18s ease, box-shadow .18s ease;
}}
[data-testid="stMetric"]:hover {{ border-color:#3a4554; box-shadow:0 1px 10px rgba(0,0,0,0.25); }}
[data-testid="stMetricLabel"] p {{ color:{_TEXT_MUTED}; font-size:0.8rem; }}
button[data-baseweb="tab"][aria-selected="true"] {{ font-weight:600; }}
[data-testid="stExpander"] {{
  border:1px solid {_BORDER}; border-radius:10px;
  transition:border-color .18s ease;
}}
[data-testid="stExpander"]:hover {{ border-color:#33404f; }}
div[data-testid="stDataFrame"] {{ border:1px solid {_BORDER}; border-radius:10px; }}
.stButton > button {{
  border:1px solid {_BORDER}; border-radius:8px;
  transition:border-color .15s ease, transform .08s ease, box-shadow .15s ease;
}}
.stButton > button:hover {{
  border-color:#43a07e; box-shadow:0 0 0 1px rgba(79,157,119,0.25);
}}
.stButton > button:active {{ transform:translateY(1px); }}
.acai-card {{ transition:border-color .18s ease, box-shadow .18s ease; }}
.acai-card:hover {{ border-color:#3a4554; box-shadow:0 1px 14px rgba(0,0,0,0.30); }}
hr {{ border-color:{_BORDER}; }}
</style>
""",
        unsafe_allow_html=True,
    )


# ── Cards / badges / bars ──────────────────────────────────────────────────

def section_header(title: str, subtitle: Optional[str] = None) -> None:
    st.markdown(f"#### {html.escape(title)}")
    if subtitle:
        st.markdown(
            f"<div style='color:{_TEXT_MUTED};margin-top:-8px;font-size:0.88rem'>"
            f"{html.escape(subtitle)}</div>",
            unsafe_allow_html=True,
        )


def badge(text: str, kind: str = "neutral") -> str:
    bg, fg = _BADGE_KINDS.get(kind, _BADGE_KINDS["neutral"])
    safe = html.escape(str(text))
    return (
        f"<span style='background:{bg};color:{fg};padding:2px 10px;border-radius:10px;"
        f"font-size:0.78rem;margin:0 6px 6px 0;display:inline-block;"
        f"border:1px solid {_BORDER}'>{safe}</span>"
    )


def badges(items: Iterable[str], kind: str = "neutral") -> None:
    items = list(items)
    if not items:
        st.caption("None")
        return
    st.markdown("".join(badge(i, kind) for i in items), unsafe_allow_html=True)


def notice(text: str, kind: str = "info") -> None:
    """A contained dark notice banner."""
    bg, fg = _BADGE_KINDS.get(kind, _BADGE_KINDS["info"])
    st.markdown(
        f"<div class='acai-surface' style='background:{bg};border:1px solid {_BORDER};"
        f"border-radius:10px;padding:12px 16px;margin:6px 0;color:{fg};font-size:0.9rem'>"
        f"{html.escape(text)}</div>",
        unsafe_allow_html=True,
    )


def progress_row(label: str, pct: float, show_value: bool = True) -> None:
    """One calm, contained dark score row: label | short bar | value."""
    pct = max(0.0, min(100.0, float(pct)))
    color = _bar_color(pct)
    safe_label = html.escape(str(label))
    value_txt = f"{pct:.0f}%" if show_value else ""
    st.markdown(
        f"""
<div style='display:grid;grid-template-columns:175px minmax(0,300px) 40px;
            align-items:center;gap:12px;margin:5px 0'>
  <span style='font-size:0.85rem;color:{_TEXT_LABEL}'>{safe_label}</span>
  <div style='background:{_BAR_TRACK};border-radius:5px;height:7px;width:100%'>
    <div style='background:{color};width:{pct:.0f}%;height:7px;border-radius:5px'></div>
  </div>
  <span style='font-size:0.8rem;color:{_TEXT_MUTED};text-align:right'>{value_txt}</span>
</div>
""",
        unsafe_allow_html=True,
    )


def score_card(label: str, pct: float) -> None:
    """Compact premium dark headline score card with a contained bar."""
    pct = max(0.0, min(100.0, float(pct)))
    color = _bar_color(pct)
    safe_label = html.escape(str(label))
    st.markdown(
        f"""
<div class='acai-card' style='border:1px solid {_BORDER};border-radius:14px;padding:16px 20px;
            margin-bottom:10px;max-width:420px;background:{_SURFACE}'>
  <div style='color:{_TEXT_MUTED};font-size:0.82rem'>{safe_label}</div>
  <div style='font-size:2.0rem;font-weight:680;color:{color};line-height:1.15'>{pct:.1f}%</div>
  <div style='background:{_BAR_TRACK};border-radius:5px;height:7px;width:100%;margin-top:10px'>
    <div style='background:{color};width:{pct:.0f}%;height:7px;border-radius:5px'></div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def stat_chips(items) -> None:
    """Renders a compact row of KPI chips: items = [(label, value), ...]."""
    inner = "".join(
        f"<div class='acai-card' style='flex:1;min-width:96px;background:{_SURFACE};"
        f"border:1px solid {_BORDER};border-radius:10px;padding:8px 12px'>"
        f"<div style='color:{_TEXT_MUTED};font-size:0.72rem'>{html.escape(str(label))}</div>"
        f"<div style='color:{_TEXT};font-weight:650;font-size:1.05rem'>{html.escape(str(value))}</div>"
        f"</div>"
        for label, value in items
    )
    st.markdown(
        f"<div style='display:flex;gap:10px;flex-wrap:wrap;margin:6px 0 8px'>{inner}</div>",
        unsafe_allow_html=True,
    )


def step_header(step: str, title: str) -> None:
    """A numbered 'workspace step' header for a cleaner analysis flow."""
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:10px;margin:4px 0 6px'>"
        f"<span style='background:{_SURFACE_ALT};border:1px solid {_BORDER};color:{_TEXT};"
        f"width:24px;height:24px;border-radius:7px;display:inline-flex;align-items:center;"
        f"justify-content:center;font-size:0.8rem;font-weight:650'>{html.escape(step)}</span>"
        f"<span style='font-weight:650;color:{_TEXT}'>{html.escape(title)}</span></div>",
        unsafe_allow_html=True,
    )


# ── Phase 21.1: product-comfort primitives (visual only) ────────────────────
#
# Each primitive has a PURE `*_html` builder (returns an escaped HTML string,
# unit-testable without a Streamlit runtime) plus a thin render wrapper. None of
# these carry business logic, raw CV/JD text, or PII.

# Standard, safe trust labels shown across the app.
DEFAULT_TRUST_LABELS = [
    "Offline-ready",
    "Deterministic fallback",
    "Private data excluded",
    "Decision-support only",
    "No auto-hiring",
]


def empty_state_html(icon: str, title: str, hint: str = "") -> str:
    """Pure builder for a calm, premium empty-state card."""
    safe_icon = html.escape(str(icon or "•"))
    safe_title = html.escape(str(title or ""))
    safe_hint = html.escape(str(hint or ""))
    hint_block = (
        f"<div style='color:{_TEXT_MUTED};font-size:0.85rem;margin-top:4px'>{safe_hint}</div>"
        if safe_hint else ""
    )
    return (
        f"<div class='acai-card acai-surface' style='background:{_SURFACE};border:1px dashed {_BORDER};"
        f"border-radius:14px;padding:26px 22px;text-align:center;margin:8px 0'>"
        f"<div style='font-size:1.6rem;line-height:1;margin-bottom:8px'>{safe_icon}</div>"
        f"<div style='color:{_TEXT};font-weight:640;font-size:0.98rem'>{safe_title}</div>"
        f"{hint_block}</div>"
    )


def empty_state(icon: str, title: str, hint: str = "") -> None:
    st.markdown(empty_state_html(icon, title, hint), unsafe_allow_html=True)


def confidence_label(value) -> str:
    """Maps a 0–1 score (or a string) to a calm confidence label."""
    if isinstance(value, (int, float)):
        v = float(value)
        if v >= 0.75:
            return "High confidence"
        if v >= 0.5:
            return "Medium confidence"
        return "Low confidence"
    return str(value or "").strip() or "Unrated"


def confidence_chip(value) -> str:
    """Pure builder: a confidence badge. Returns an HTML chip string."""
    label = confidence_label(value)
    kind = "good" if label.startswith("High") else "warn" if label.startswith("Medium") else "bad"
    if label in ("Unrated",) or not isinstance(value, (int, float)) and label not in (
        "High confidence", "Medium confidence", "Low confidence"
    ):
        kind = "neutral"
    return badge(label, kind)


def trust_badges(labels=None, kind: str = "neutral") -> None:
    """Renders a compact row of standard trust chips."""
    badges(list(labels) if labels is not None else DEFAULT_TRUST_LABELS, kind)


def stepper_html(steps, active=None) -> str:
    """
    Pure builder for a compact horizontal stepper. `active` is a 1-based index or
    a step label; it is highlighted. Purely visual — no routing.
    """
    steps = [str(s) for s in (steps or [])]
    active_idx = None
    if isinstance(active, int):
        active_idx = active
    elif isinstance(active, str):
        for i, s in enumerate(steps, start=1):
            if s.lower() == active.lower():
                active_idx = i
                break

    chips = []
    for i, label in enumerate(steps, start=1):
        is_active = active_idx is not None and i == active_idx
        bg = _SURFACE_ALT if is_active else "transparent"
        border = "#43a07e" if is_active else _BORDER
        fg = _TEXT if is_active else _TEXT_MUTED
        chips.append(
            f"<span style='display:inline-flex;align-items:center;gap:6px;background:{bg};"
            f"border:1px solid {border};border-radius:9px;padding:4px 10px;font-size:0.78rem;"
            f"color:{fg}'>"
            f"<span style='opacity:0.7'>{i}</span>{html.escape(label)}</span>"
        )
    return (
        "<div style='display:flex;gap:8px;flex-wrap:wrap;margin:2px 0 10px'>"
        + "".join(chips) + "</div>"
    )


def stepper(steps, active=None) -> None:
    st.markdown(stepper_html(steps, active), unsafe_allow_html=True)


def hero_panel_html(title: str, subtitle: str = "", icon: str = "") -> str:
    """Pure builder for a small workspace hero panel (no result data)."""
    safe_title = html.escape(str(title or ""))
    safe_sub = html.escape(str(subtitle or ""))
    icon_block = (
        f"<span style='font-size:1.2rem;margin-right:10px'>{html.escape(str(icon))}</span>"
        if icon else ""
    )
    sub_block = (
        f"<div style='color:{_TEXT_MUTED};font-size:0.9rem;margin-top:3px'>{safe_sub}</div>"
        if safe_sub else ""
    )
    return (
        f"<div class='acai-surface' style='background:{_SURFACE};border:1px solid {_BORDER};"
        f"border-radius:14px;padding:16px 20px;margin-bottom:12px'>"
        f"<div style='display:flex;align-items:center'>{icon_block}"
        f"<span style='font-size:1.12rem;font-weight:660;color:{_TEXT}'>{safe_title}</span></div>"
        f"{sub_block}</div>"
    )


def hero_panel(title: str, subtitle: str = "", icon: str = "") -> None:
    st.markdown(hero_panel_html(title, subtitle, icon), unsafe_allow_html=True)


def status_chip_html(label: str, kind: str = "neutral") -> str:
    """Alias builder for a single status chip (reuses the badge styling)."""
    return badge(label, kind)


# ── Phase 21.3: Focus / Presentation mode + Print comfort (CSS only) ─────────
#
# Pure string builders (unit-testable). They tune layout/print chrome only — no
# business logic, no access-control change. Focus mode never blanket-hides
# st.caption (governance/directional disclaimers are captions and must stay).

def focus_mode_css() -> str:
    """CSS applied ONLY when focus/presentation mode is enabled."""
    return """
<style id='acai-focus'>
.block-container { max-width:1320px !important; padding-top:1rem !important; }
/* Trim the decorative sidebar "How it works" steps; keep workspace switch + status. */
section[data-testid="stSidebar"] .acai-sidebar-steps { display:none !important; }
.acai-card, .acai-surface { box-shadow:0 1px 14px rgba(0,0,0,0.30); }
</style>
"""


def print_css() -> str:
    """@media print CSS — always injected so browser printing is comfortable."""
    return """
<style id='acai-print'>
@media print {
  section[data-testid="stSidebar"], header, [data-testid="stHeader"],
  [data-testid="stToolbar"], .stButton, [data-testid="stFileUploader"],
  [data-testid="stFileUploaderDropzone"], [data-testid="stDownloadButton"] {
    display:none !important;
  }
  html, body, .stApp, .block-container {
    background:#ffffff !important; color:#111111 !important;
  }
  .block-container { max-width:100% !important; padding-top:0 !important; }
  .acai-card, .acai-surface {
    background:#ffffff !important; color:#111111 !important;
    border:1px solid #cccccc !important; box-shadow:none !important;
    break-inside: avoid; page-break-inside: avoid;
  }
  h1, h2, h3, h4, h5 { color:#111111 !important; }
}
</style>
"""


def presentation_css(focus: bool) -> str:
    """Print CSS is always included; focus CSS only when `focus` is True."""
    css = print_css()
    if focus:
        css += focus_mode_css()
    return css


def inject_presentation_css(focus: bool) -> None:
    st.markdown(presentation_css(focus), unsafe_allow_html=True)
