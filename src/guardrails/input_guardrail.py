# src/guardrails/input_guardrail.py
#
# Input guardrail — runs BEFORE any LLM call.
#
# Responsibilities (all deterministic, no LLM, no file I/O):
#   1. PII masking: emails, phone numbers, and obvious LinkedIn/GitHub URLs are
#      replaced with redaction placeholders before text reaches any model.
#   2. Prompt-injection detection: flags known control-hijack phrases. Only a
#      SEVERE subset causes the input to be rejected; lighter matches are flagged
#      but allowed through (HR text legitimately contains words like "system").
#
# The module exposes both a class (InputGuardrail) and free functions
# (validate_input, mask_pii, detect_prompt_injection) for convenience.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# PII patterns
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/[^\s,;]+", re.IGNORECASE)
_GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[^\s,;]+", re.IGNORECASE)
# Phones: an international +-prefixed run, or grouped 3-3-x digits with separators.
_PHONE_INTL_RE = re.compile(r"\+\d[\d\s().\-]{7,}\d")
_PHONE_GROUPED_RE = re.compile(r"\(?\d{3}\)?[\s\-]\d{3}[\s\-]?\d{2,4}")

# ---------------------------------------------------------------------------
# Prompt-injection phrases
# ---------------------------------------------------------------------------

# Unambiguous control-hijack / secret-exfiltration / role-bypass attempts.
# These are both detected AND severe (rejected). Bare ambiguous terms like
# "system prompt" remain soft (flag-only), since HR text legitimately uses them.
EXFILTRATION_PHRASES: List[str] = [
    # prompt / instruction extraction
    "reveal the system prompt", "reveal system prompt", "show the system prompt",
    "show your system prompt", "print the system prompt", "print your system prompt",
    "print your hidden prompt", "print the hidden prompt", "reveal hidden prompt",
    "show hidden instructions", "reveal your instructions", "show your instructions",
    "prompt template", "chain of thought", "chain-of-thought",
    # secrets / env / keys
    "show environment variables", "show env variables", "print environment variables",
    "reveal your api key", "show your api key", "print your api key", "reveal api key",
    # data / path exfiltration
    "return raw cv", "return the raw cv", "return raw cv text",
    "return data/private", "data/private file paths", "return private file paths",
    "export private data", "export all private data",
    # destructive / role / score tampering
    "delete files", "delete all files", "remove all files",
    "change score to", "set score to", "change the score to",
    "show recruiter-only", "show recruiter only", "show candidate coaching",
    "ignore all instructions", "disregard all instructions",
]

# All phrases that are flagged when present (lowercase match).
INJECTION_PHRASES: List[str] = [
    "ignore previous instructions",
    "ignore all previous instructions",
    "disregard previous instructions",
    "ignore above",
    "system prompt",
    "developer message",
    "jailbreak",
    "you are now",
    "reveal hidden",
    "override instructions",
] + EXFILTRATION_PHRASES

# Phrases severe enough to REJECT the input outright.
SEVERE_INJECTION_PHRASES = {
    "ignore previous instructions",
    "ignore all previous instructions",
    "disregard previous instructions",
    "ignore above",
    "jailbreak",
    "reveal hidden",
    "override instructions",
    *EXFILTRATION_PHRASES,
}


@dataclass
class InputGuardrailResult:
    passed: bool
    rejection_reason: Optional[str]
    masked_cv_text: str
    masked_jd_text: str
    pii_fields_masked: List[str] = field(default_factory=list)
    injection_flags: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Free functions
# ---------------------------------------------------------------------------

def mask_pii(text: str) -> Tuple[str, List[str]]:
    """
    Masks emails, LinkedIn/GitHub URLs, and phone numbers in `text`.
    Returns (masked_text, list_of_field_labels_masked). Order of operations
    matters: URLs and emails are masked before phone patterns so digits inside
    those tokens are not mistaken for phone numbers.
    """
    if not text:
        return text or "", []

    masked = text
    fields: List[str] = []

    def _sub(pattern: re.Pattern, placeholder: str, label: str) -> None:
        nonlocal masked
        if pattern.search(masked):
            masked = pattern.sub(placeholder, masked)
            if label not in fields:
                fields.append(label)

    _sub(_EMAIL_RE, "[EMAIL_REDACTED]", "email")
    _sub(_LINKEDIN_RE, "[LINKEDIN_REDACTED]", "linkedin_url")
    _sub(_GITHUB_RE, "[GITHUB_REDACTED]", "github_url")
    _sub(_PHONE_INTL_RE, "[PHONE_REDACTED]", "phone")
    _sub(_PHONE_GROUPED_RE, "[PHONE_REDACTED]", "phone")

    return masked, fields


def detect_prompt_injection(text: str) -> List[str]:
    """
    Returns the list of known injection phrases present in `text`
    (case-insensitive). Empty list means no injection patterns were found.
    """
    if not text:
        return []
    low = text.lower()
    return [phrase for phrase in INJECTION_PHRASES if phrase in low]


# ---------------------------------------------------------------------------
# Guardrail class
# ---------------------------------------------------------------------------

class InputGuardrail:
    """Deterministic input guardrail: PII masking + prompt-injection screening."""

    def mask(self, text: str) -> Tuple[str, List[str]]:
        return mask_pii(text)

    def detect(self, text: str) -> List[str]:
        return detect_prompt_injection(text)

    def validate(self, cv_text: str, jd_text: str) -> InputGuardrailResult:
        cv_flags = detect_prompt_injection(cv_text)
        jd_flags = detect_prompt_injection(jd_text)
        all_flags: List[str] = []
        for f in cv_flags + jd_flags:
            if f not in all_flags:
                all_flags.append(f)

        masked_cv, cv_fields = mask_pii(cv_text)
        masked_jd, jd_fields = mask_pii(jd_text)
        pii_fields: List[str] = []
        for f in cv_fields + jd_fields:
            if f not in pii_fields:
                pii_fields.append(f)

        severe = [f for f in all_flags if f in SEVERE_INJECTION_PHRASES]
        if severe:
            passed = False
            reason = f"Severe prompt-injection pattern(s) detected: {severe}"
        else:
            passed = True
            reason = None

        return InputGuardrailResult(
            passed=passed,
            rejection_reason=reason,
            masked_cv_text=masked_cv,
            masked_jd_text=masked_jd,
            pii_fields_masked=pii_fields,
            injection_flags=all_flags,
        )


def validate_input(cv_text: str, jd_text: str) -> InputGuardrailResult:
    """Module-level convenience wrapper around InputGuardrail.validate()."""
    return InputGuardrail().validate(cv_text, jd_text)
