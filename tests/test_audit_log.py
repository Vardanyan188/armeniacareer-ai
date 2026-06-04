# tests/test_audit_log.py
#
# Phase 22 — privacy-safe audit logging. Pure builders + best-effort JSONL
# writes to tmp_path. No network, no real data/reports access.

import json

from src.engine.audit_log import (
    build_security_event,
    build_workflow_event,
    contains_sensitive,
    find_leaks,
    log_security_event,
    log_workflow_event,
    sanitize_error,
    scrub_text,
)

_SECRET_BLOB = (
    "key sk-ABCDEF0123456789 OPENAI_API_KEY=x path data/private/real_resumes/cv.pdf "
    "email a@b.com phone +374 99 123456 url https://x.io system prompt here"
)


# ---------------------------------------------------------------------------
# Scrubbing
# ---------------------------------------------------------------------------

def test_scrub_text_masks_all_categories():
    s = scrub_text(_SECRET_BLOB)
    assert "sk-ABCDEF0123456789" not in s
    assert "OPENAI_API_KEY" not in s
    assert "data/private" not in s
    assert "a@b.com" not in s
    assert "https://x.io" not in s
    assert "+374 99 123456" not in s
    assert "system prompt" not in s.lower()


def test_find_leaks_and_contains_sensitive():
    cats = find_leaks(_SECRET_BLOB)
    for expected in ("email", "url", "api_key", "env_var", "path", "prompt_marker", "phone"):
        assert expected in cats
    assert contains_sensitive(_SECRET_BLOB) is True
    assert contains_sensitive("Python, SQL, mid-level") is False


def test_sanitize_error_is_categorical():
    assert sanitize_error("PermissionError: /home/u/.env 403") == "Access/permission error"
    assert sanitize_error("FileNotFoundError: data/private/x") == "Resource not found"
    msg = sanitize_error("Traceback ... sk-secret at C:\\app\\main.py")
    assert "sk-secret" not in msg and "C:\\app" not in msg


# ---------------------------------------------------------------------------
# Event builders (pure) — allowlist + sanitize
# ---------------------------------------------------------------------------

def test_build_workflow_event_allowlists_and_stamps():
    ev = build_workflow_event(
        "analysis_completed", mode="Candidate", provider="deterministic",
        cv_count=1, quality_band="good",
        cv_text="RAW CV TEXT", original_filename="John_Doe.pdf",   # forbidden → dropped
    )
    assert ev["action"] == "analysis_completed"
    assert ev["mode"] == "Candidate" and ev["cv_count"] == 1
    assert "cv_text" not in ev and "original_filename" not in ev
    assert ev["privacy_safe"] is True
    assert ev["event_id"] and ev["timestamp"] and ev["app_env"]


def test_build_security_event_scrubs_string_values():
    ev = build_security_event(
        "output_leak_redacted", severity="blocked",
        blocked_reason="leaked sk-ABCDEF0123456789 at data/private/x.pdf",
        error_category="Model/provider error",
    )
    assert ev["severity"] == "blocked"
    assert "sk-ABCDEF0123456789" not in ev["blocked_reason"]
    assert "data/private" not in ev["blocked_reason"]


def test_build_security_event_clamps_severity():
    assert build_security_event("x", severity="nope")["severity"] == "info"


# ---------------------------------------------------------------------------
# Writing (best-effort JSONL)
# ---------------------------------------------------------------------------

def test_log_workflow_event_writes_jsonl_when_enabled(tmp_path):
    ev = log_workflow_event("cv_uploaded", enabled=True, base_dir=tmp_path, file_type="pdf")
    path = tmp_path / "workflow_events.jsonl"
    assert path.is_file()
    line = path.read_text(encoding="utf-8").strip()
    loaded = json.loads(line)
    assert loaded["action"] == "cv_uploaded" and loaded["file_type"] == "pdf"
    assert loaded == ev


def test_log_security_event_writes_separate_stream(tmp_path):
    log_security_event("prompt_injection_detected", enabled=True, base_dir=tmp_path,
                       severity="blocked")
    assert (tmp_path / "security_events.jsonl").is_file()
    assert not (tmp_path / "workflow_events.jsonl").exists()


def test_logging_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("ACAI_ENABLE_AUDIT_LOG", raising=False)
    assert log_workflow_event("app_started", base_dir=tmp_path) is None
    assert not (tmp_path / "workflow_events.jsonl").exists()


def test_logging_never_crashes_on_bad_path(tmp_path):
    # base_dir whose parent is a FILE → mkdir fails, but logging must not raise.
    bad_parent = tmp_path / "afile"
    bad_parent.write_text("x", encoding="utf-8")
    ev = log_workflow_event("app_started", enabled=True, base_dir=bad_parent / "sub")
    assert isinstance(ev, dict)            # returned, no exception


def test_written_events_never_contain_private_paths(tmp_path):
    log_workflow_event(
        "analysis_completed", enabled=True, base_dir=tmp_path,
        status="data/private/real_resumes/cv.pdf",   # scrubbed
    )
    text = (tmp_path / "workflow_events.jsonl").read_text(encoding="utf-8")
    assert "data/private" not in text and "candidate_pool" not in text
    assert "@" not in text
