# src/guardrails/output_guardrail.py
#
# Output guardrail — thin, deterministic validation of an assembled payload.
#
# This is intentionally minimal for the MVP. It does NOT mutate the payload and
# does NOT call an LLM. It performs structural sanity checks:
#   - composite score / percentage are within range,
#   - all required payload sections are present,
#   - candidate and recruiter perspectives carry non-empty core narratives.
#
# Structural problems are recorded in `flags` and fail the guardrail.
# Content-quality concerns (e.g. an empty narrative) are recorded in
# `hallucination_flags`, which are surfaced but do not by themselves fail it.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from src.engine.audit_log import find_leaks, scrub_text
from src.schemas.canonical_payload import CanonicalAnalysisPayload

# Sections that must be present on every payload.
_REQUIRED_SECTIONS = [
    "cv_entities",
    "jd_entities",
    "dimensional_analysis",
    "skills_ontology",
    "semantic_analysis",
    "governance",
    "candidate_perspective",
    "recruiter_perspective",
]


# Narrative fields scanned for leaked prompts/secrets/paths before display/export.
_SCANNED_TEXT_PATHS = [
    ("candidate_perspective", ["strength_narrative", "interview_preparation_focus",
                               "salary_positioning_context", "motivational_framing"]),
    ("recruiter_perspective", ["screening_summary", "hire_recommendation_rationale",
                               "comparative_profile_summary", "red_flag_summary"]),
]


@dataclass
class OutputGuardrailResult:
    passed: bool
    flags: List[str] = field(default_factory=list)
    hallucination_flags: List[str] = field(default_factory=list)
    # Sensitive/internal content categories detected in narratives (info only;
    # does not fail the guardrail). Redaction happens at display/export time.
    leak_flags: List[str] = field(default_factory=list)


def scan_payload_for_leaks(payload: CanonicalAnalysisPayload) -> List[str]:
    """Returns leak categories found in any narrative field (deduped)."""
    found: List[str] = []
    for section, attrs in _SCANNED_TEXT_PATHS:
        obj = getattr(payload, section, None)
        if obj is None:
            continue
        for attr in attrs:
            for category in find_leaks(getattr(obj, attr, "") or ""):
                if category not in found:
                    found.append(category)
    return found


def redact_text_for_display(text: str) -> str:
    """Redacts prompts/secrets/paths/PII from a narrative before display/export."""
    return scrub_text(text)


class OutputGuardrail:
    """Thin structural validator for a CanonicalAnalysisPayload."""

    def validate(self, payload: CanonicalAnalysisPayload) -> OutputGuardrailResult:
        flags: List[str] = []
        hallucination_flags: List[str] = []

        # 1. Required sections present.
        for name in _REQUIRED_SECTIONS:
            if getattr(payload, name, None) is None:
                flags.append(f"missing_section:{name}")

        # 2. Composite score ranges (defensive; schema already constrains these).
        da = getattr(payload, "dimensional_analysis", None)
        if da is not None:
            if not (0.0 <= da.composite_score <= 1.0):
                flags.append("composite_score_out_of_range")
            if not (0.0 <= da.composite_score_percentage <= 100.0):
                flags.append("composite_percentage_out_of_range")

        # 3. Perspective narratives present and non-empty.
        cp = getattr(payload, "candidate_perspective", None)
        if cp is None:
            flags.append("missing_section:candidate_perspective")
        elif not (cp.strength_narrative or "").strip():
            hallucination_flags.append("empty_candidate_strength_narrative")

        rp = getattr(payload, "recruiter_perspective", None)
        if rp is None:
            flags.append("missing_section:recruiter_perspective")
        elif not (rp.screening_summary or "").strip():
            hallucination_flags.append("empty_recruiter_screening_summary")

        # 4. Leak scan of narratives (informational; never the cause of failure).
        leak_flags = scan_payload_for_leaks(payload)

        passed = len(flags) == 0
        return OutputGuardrailResult(
            passed=passed,
            flags=flags,
            hallucination_flags=hallucination_flags,
            leak_flags=leak_flags,
        )


def validate_payload(payload: CanonicalAnalysisPayload) -> OutputGuardrailResult:
    """Module-level convenience wrapper around OutputGuardrail.validate()."""
    return OutputGuardrail().validate(payload)
