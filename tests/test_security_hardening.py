# tests/test_security_hardening.py
#
# Phase 22 — output-guardrail leak scanning + redaction, export hardening,
# and governance sanitization. No network, no API keys.

from src.engine.access_control import get_candidate_view, get_recruiter_view, get_shared_view
from src.guardrails.output_guardrail import (
    redact_text_for_display,
    scan_payload_for_leaks,
    validate_payload,
)
from src.ui.components.summary_builders import (
    build_candidate_markdown_summary,
    build_governance_markdown_summary,
    build_recruiter_markdown_summary,
)

from tests._payload_factory import MOTIVATION_TEXT, RED_FLAG_TEXT, make_payload

_LEAK = (
    "Internal: system prompt at src/prompts/v3_fewshot.py, OPENAI_API_KEY=sk-ABCDEF0123456789, "
    "private file data/private/real_resumes/cv.pdf"
)


# ---------------------------------------------------------------------------
# Output guardrail leak scan (flag, do not fail)
# ---------------------------------------------------------------------------

def test_output_guardrail_flags_leaks_without_failing():
    payload = make_payload(candidate_strength=_LEAK)
    res = validate_payload(payload)
    assert res.passed is True                      # structural pass unchanged
    assert res.leak_flags                          # leaks detected
    assert {"path", "env_var", "api_key", "prompt_marker"} & set(res.leak_flags)


def test_clean_payload_has_no_leak_flags():
    assert validate_payload(make_payload()).leak_flags == []


def test_redact_text_for_display_scrubs():
    out = redact_text_for_display(_LEAK)
    assert "sk-ABCDEF0123456789" not in out
    assert "OPENAI_API_KEY" not in out
    assert "src/prompts" not in out
    assert "data/private" not in out


def test_scan_payload_for_leaks_categories():
    cats = scan_payload_for_leaks(make_payload(recruiter_summary=_LEAK))
    assert "api_key" in cats and "path" in cats


# ---------------------------------------------------------------------------
# Export hardening — secrets/paths/env never survive into exports
# ---------------------------------------------------------------------------

def test_candidate_export_scrubs_secrets_and_paths():
    payload = make_payload(candidate_strength=_LEAK)
    md = build_candidate_markdown_summary(get_candidate_view(payload), get_shared_view(payload))
    assert "sk-ABCDEF0123456789" not in md
    assert "OPENAI_API_KEY" not in md
    assert "src/prompts" not in md
    assert "data/private" not in md
    # And still no recruiter-only content.
    assert RED_FLAG_TEXT not in md


def test_recruiter_export_scrubs_secrets_and_excludes_coaching():
    payload = make_payload(recruiter_summary=_LEAK)
    md = build_recruiter_markdown_summary(get_recruiter_view(payload))
    assert "sk-ABCDEF0123456789" not in md
    assert "data/private" not in md
    assert MOTIVATION_TEXT not in md


# ---------------------------------------------------------------------------
# Governance summary — neutral, no secrets/keys
# ---------------------------------------------------------------------------

def test_governance_summary_no_keys_or_paths():
    class _R:
        payload = make_payload()
        provider_status = {"semantic_alignment": "deterministic"}
        llm_used = False
        agent_errors = {"semantic_alignment": "boom at src/agents/x.py sk-zzzzzzzzzz12345678"}
        input_guardrail = None
        output_guardrail = None
    md = build_governance_markdown_summary(_R())
    assert "sk-" not in md
    assert "src/agents" not in md
    assert "boom at" not in md                      # raw error string not echoed
