# src/ui/components/summary_builders.py
#
# Phase 21.2 — pure, role-safe Markdown summary builders for Export / Copy.
#
# HARD RULES (enforced by construction + tests):
#   - Built ONLY from role-safe access-control views / already-neutral objects.
#   - Explicit field allowlists; no raw CV/JD text; no PII; no private paths.
#   - Defensive scrub of emails / phones / URLs on every free-text field.
#   - No file reads, no API calls, no Streamlit session, no scoring/logic.
#   - Ranking exports omit source_filename (no name leakage).
#   - Every document carries a decision-support / human-review disclaimer.

from __future__ import annotations

import re
from typing import Any, List, Optional

from src.engine.audit_log import scrub_text as _scrub_secrets
from src.engine.skill_depth.models import DepthMatchType

DISCLAIMER = "_Decision-support only — human review required. Not an automated hiring decision._"
_INTERNAL_STAMP = "INTERNAL DEMO — decision-support only — not a hiring decision."

# Dimension display order/labels (keys match the canonical dimensional fields).
_DIMENSIONS = [
    ("technical_skills_match", "Technical skills"),
    ("experience_depth_alignment", "Experience depth"),
    ("educational_relevance", "Education relevance"),
    ("domain_knowledge", "Domain knowledge"),
    ("soft_skills_signals", "Soft-skill signals"),
    ("seniority_trajectory", "Seniority trajectory"),
    ("semantic_contextual_alignment", "Semantic alignment"),
]

_DEPTH_GAP_TYPES = {
    DepthMatchType.PARTIAL_DEPTH_MATCH,
    DepthMatchType.MENTIONED_ONLY,
    DepthMatchType.MISSING_SKILL,
}

# Defensive scrub patterns (applied to free-text narrative fields only).
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL_RE = re.compile(r"(https?://\S+|www\.\S+)", re.IGNORECASE)
_PHONE_RE = re.compile(r"\(?\+?\d[\d\s().\-]{7,}\d\)?")


def _scrub(text: Any) -> str:
    """
    Masks emails / URLs / phone-like sequences, then masks any leaked secrets /
    env names / source-or-private paths / prompt markers (defense-in-depth).
    """
    s = str(text or "")
    s = _EMAIL_RE.sub("[redacted]", s)
    s = _URL_RE.sub("[link removed]", s)
    s = _PHONE_RE.sub("[redacted]", s)
    s = _scrub_secrets(s)            # keys / env vars / paths / prompt markers
    return s.strip()


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _pct(value: Any) -> str:
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "—"


def _names(entries: Any) -> List[str]:
    out: List[str] = []
    for e in entries or []:
        name = str(getattr(e, "canonical_name", None) or getattr(e, "skill_name", "") or "").strip()
        if name:
            out.append(name)
    return out


def _name_line(label: str, entries: Any) -> str:
    names = _names(entries)
    return f"- **{label}:** {', '.join(names) if names else 'none'}"


def _dimension_lines(scores: Any) -> List[str]:
    """Accepts a {key: raw} dict (candidate view) or a DimensionalAnalysis object."""
    lines: List[str] = []
    for key, label in _DIMENSIONS:
        if isinstance(scores, dict):
            raw = scores.get(key)
        else:
            dim = getattr(scores, key, None)
            raw = getattr(dim, "raw_score", None)
        if raw is None:
            continue
        lines.append(f"- {label}: {_pct(float(raw) * 100)}")
    return lines


def _depth_lines(skill_depth: Any, *, recruiter: bool) -> List[str]:
    if skill_depth is None:
        return []
    lines: List[str] = []
    for e in getattr(skill_depth, "entries", []) or []:
        if e.match_type not in _DEPTH_GAP_TYPES:
            continue
        if recruiter:
            evid = ", ".join(e.evidence_labels) if e.evidence_labels else "—"
            lines.append(
                f"- **{e.skill}** — observed {e.candidate_depth_label} / needed "
                f"{e.required_depth_label}; evidence: {evid}; verify: {_scrub(e.verification_prompt)}"
            )
        else:
            lines.append(
                f"- **{e.skill}** — your {e.candidate_depth_label} / needed "
                f"{e.required_depth_label}: {_scrub(e.recommendation)}"
            )
    return lines


def _join(lines: List[str]) -> str:
    return "\n".join(line for line in lines if line is not None)


# ---------------------------------------------------------------------------
# Candidate
# ---------------------------------------------------------------------------

def build_candidate_markdown_summary(
    candidate_view: Any, shared_view: Any = None, skill_depth: Any = None,
) -> str:
    cp = candidate_view.get("candidate_perspective")
    lines: List[str] = [
        "# Candidate Match Summary",
        "",
        f"**Role:** {_scrub(candidate_view.get('role_title', ''))}  ",
        f"**Required level:** {candidate_view.get('required_seniority', '')}  ",
        f"**Composite match:** {_pct(candidate_view.get('composite_score_percentage'))}  ",
        f"**Overall confidence:** {_pct(float(candidate_view.get('overall_confidence', 0)) * 100)}",
        "",
        "## Dimension scores",
        *_dimension_lines(candidate_view.get("dimensional_scores")),
        "",
        "## Skills",
        _name_line("Matched", candidate_view.get("matched_skills")),
        _name_line("Missing critical", candidate_view.get("missing_critical")),
        _name_line("Missing preferred", candidate_view.get("missing_preferred")),
        _name_line("Transferable", candidate_view.get("transferable")),
    ]

    depth_lines = _depth_lines(skill_depth, recruiter=False)
    if depth_lines:
        lines += ["", "## Skill-depth gaps & what to strengthen", *depth_lines]

    if cp is not None:
        strength = _scrub(getattr(cp, "strength_narrative", ""))
        focus = _scrub(getattr(cp, "interview_preparation_focus", ""))
        roadmap = getattr(cp, "gap_closure_roadmap", []) or []
        lines += ["", "## Your coaching summary"]
        if strength:
            lines.append(f"- **Strengths:** {strength}")
        if focus:
            lines.append(f"- **Interview focus:** {focus}")
        for item in roadmap[:5]:
            gap = _scrub(getattr(item, "skill_or_gap", ""))
            target = _scrub(getattr(item, "target_state_description", ""))
            if gap:
                lines.append(f"- **Improve {gap}:** {target}")

    lines += [
        "",
        "## Analysis status",
        "- Deterministic-safe analysis; decision-support only.",
        "",
        DISCLAIMER,
    ]
    return _join(lines)


# ---------------------------------------------------------------------------
# Recruiter
# ---------------------------------------------------------------------------

def build_recruiter_markdown_summary(
    recruiter_view: Any, shared_view: Any = None, skill_depth: Any = None,
    ranked_candidate: Any = None,
) -> str:
    rp = recruiter_view.get("recruiter_perspective")
    skills = recruiter_view.get("skills_ontology")
    lines: List[str] = [
        "# Recruiter Screening Summary",
        "",
        f"**Composite match:** {_pct(recruiter_view.get('composite_score_percentage'))}  ",
        f"**Integrity risk:** {recruiter_view.get('evaluation_integrity_risk', '')}",
        "",
        "## Dimension scores",
        *_dimension_lines(recruiter_view.get("dimensional_analysis")),
    ]

    if rp is not None:
        lines += [
            "",
            "## Screening",
            f"- **Summary:** {_scrub(getattr(rp, 'screening_summary', ''))}",
            f"- **Recommendation:** {getattr(rp, 'hire_recommendation', '')}",
            f"- **Rationale:** {_scrub(getattr(rp, 'hire_recommendation_rationale', ''))}",
        ]
        red = _scrub(getattr(rp, "red_flag_summary", "") or "")
        if red:
            lines.append(f"- **Caution:** {red}")
        vpoints = getattr(rp, "verification_points", []) or []
        if vpoints:
            lines += ["", "## Verification questions"]
            for vp in vpoints[:6]:
                topic = _scrub(getattr(vp, "topic", ""))
                q = _scrub(getattr(vp, "suggested_interview_question", ""))
                lines.append(f"- **{topic}:** {q}")

    if skills is not None:
        lines += [
            "",
            "## Skills",
            _name_line("Matched", getattr(skills, "matched_skills", [])),
            _name_line("Missing critical", getattr(skills, "missing_critical", [])),
        ]

    depth_lines = _depth_lines(skill_depth, recruiter=True)
    if depth_lines:
        lines += ["", "## Requirement-depth evidence", *depth_lines]

    if ranked_candidate is not None:
        # NOTE: source_filename is intentionally omitted (no name leakage).
        rc = ranked_candidate
        lines += [
            "",
            "## Ranking",
            f"- **{getattr(rc, 'label', 'Candidate')}** (id {getattr(rc, 'candidate_id', '')}) — "
            f"rank {getattr(rc, 'rank', '—')}, {getattr(getattr(rc, 'bucket', None), 'value', '')}, "
            f"{getattr(rc, 'priority_label', '')}, composite {_pct(getattr(rc, 'composite_pct', 0))}",
        ]

    lines += [
        "",
        "## Analysis status",
        "- Deterministic-safe analysis; decision-support only.",
        "",
        DISCLAIMER,
    ]
    return _join(lines)


# ---------------------------------------------------------------------------
# Governance
# ---------------------------------------------------------------------------

def build_governance_markdown_summary(result: Any) -> str:
    payload = getattr(result, "payload", None)
    gov = getattr(payload, "governance", None)
    provider_status = getattr(result, "provider_status", None) or {}
    sem = provider_status.get("semantic_alignment") if isinstance(provider_status, dict) else None
    provider = {
        "openai": "OpenAI embeddings",
        "google": "Google (alternate) embeddings",
        "deterministic": "Deterministic fallback",
    }.get(sem, "Deterministic-ready")

    llm = "Used (live agents)" if getattr(result, "llm_used", False) else (
        "Attempted, fell back" if getattr(result, "agent_errors", None)
        else "Not attempted (deterministic fallback)"
    )
    input_passed = getattr(getattr(result, "input_guardrail", None), "passed", True)
    output_passed = getattr(getattr(result, "output_guardrail", None), "passed", True)
    flags = list(getattr(gov, "guardrail_output_flags", []) or []) if gov else []

    lines = [
        "# Governance & Fallback Summary",
        "",
        f"- **Provider:** {provider}",
        f"- **LLM:** {llm}",
        f"- **Input guardrail:** {'Passed' if input_passed else 'Rejected'}",
        f"- **Output guardrail:** {'Passed' if output_passed else 'Flagged'}",
        f"- **Output/fallback flags:** {', '.join(flags) if flags else 'none'}",
    ]
    if payload is not None:
        lines += [
            f"- **Analysis completeness:** {getattr(payload, 'analysis_completeness_score', 0):.2f}",
            f"- **Overall confidence:** {getattr(payload, 'overall_analysis_confidence', 0):.2f}",
        ]
    lines += ["", DISCLAIMER]
    return _join(lines)


# ---------------------------------------------------------------------------
# JD diff
# ---------------------------------------------------------------------------

def build_jd_diff_markdown_summary(diff: Any) -> str:
    lines = [
        "# JD Requirement Change Summary",
        "",
        f"_{_scrub(getattr(diff, 'summary', ''))}_",
        "",
    ]
    if getattr(diff, "role_title_changed", False):
        lines.append(f"- **Role title:** {_scrub(diff.old_role_title)} → {_scrub(diff.new_role_title)}")
    if getattr(diff, "seniority_changed", False):
        lines.append(f"- **Seniority:** {diff.old_seniority} → {diff.new_seniority}")
    if getattr(diff, "required_experience_changed", False):
        lines.append(
            f"- **Experience:** {diff.old_required_experience_years:g}y → "
            f"{diff.new_required_experience_years:g}y"
        )
    lines += [
        f"- **Added required skills:** {', '.join(diff.added_required_skills) or 'none'}",
        f"- **Removed required skills:** {', '.join(diff.removed_required_skills) or 'none'}",
        f"- **Added preferred skills:** {', '.join(diff.added_preferred_skills) or 'none'}",
        f"- **Removed preferred skills:** {', '.join(diff.removed_preferred_skills) or 'none'}",
    ]
    depth = getattr(diff, "required_depth_changed", []) or []
    if depth:
        lines.append("- **Required-depth changes:** " + "; ".join(
            f"{c.skill}: {c.old_depth or '—'}→{c.new_depth or '—'}" for c in depth
        ))
    gaps = getattr(diff, "newly_required_depth_gaps", []) or []
    if gaps:
        lines.append(f"- **Newly deeper requirements:** {', '.join(gaps)}")
    lines += ["", DISCLAIMER]
    return _join(lines)


# ---------------------------------------------------------------------------
# Bulk ranking
# ---------------------------------------------------------------------------

def build_bulk_ranking_markdown_summary(bulk_result: Any) -> str:
    lines = [
        "# Candidate Ranking Summary",
        "",
        f"Candidates: {getattr(bulk_result, 'total', 0)} · "
        f"Analyzed: {getattr(bulk_result, 'analyzed', 0)} · "
        f"Failed: {getattr(bulk_result, 'failed', 0)}",
        "",
        "| Rank | Candidate | ID | Composite | Bucket | Priority | Matched | Missing critical | Status |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for c in getattr(bulk_result, "candidates", []) or []:
        # source_filename intentionally omitted.
        lines.append(
            f"| {getattr(c, 'rank', '—')} | {getattr(c, 'label', '')} | "
            f"{getattr(c, 'candidate_id', '')} | {_pct(getattr(c, 'composite_pct', 0))} | "
            f"{getattr(getattr(c, 'bucket', None), 'value', '')} | {getattr(c, 'priority_label', '')} | "
            f"{getattr(c, 'matched_count', 0)} | {getattr(c, 'missing_critical_count', 0)} | "
            f"{getattr(getattr(c, 'status', None), 'value', '')} |"
        )
    lines += ["", DISCLAIMER]
    return _join(lines)


# ---------------------------------------------------------------------------
# Admin / Demo (single stamped document)
# ---------------------------------------------------------------------------

def build_admin_demo_markdown_summary(
    candidate_view: Any, recruiter_view: Any, shared_view: Any = None,
) -> str:
    lines = [
        f"# {_INTERNAL_STAMP}",
        "",
        "> This document is for internal demo inspection only.",
        "",
        "---",
        "",
        build_candidate_markdown_summary(candidate_view, shared_view),
        "",
        "---",
        "",
        build_recruiter_markdown_summary(recruiter_view, shared_view),
    ]
    return _join(lines)
