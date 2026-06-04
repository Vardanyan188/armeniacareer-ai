# src/engine/audit_log.py
#
# Phase 22 — privacy-safe audit logging + shared sanitization primitives.
#
# Two append-only JSONL streams (off by default; enabled via ACAI_ENABLE_AUDIT_LOG):
#   - workflow_events.jsonl  : what the system did (steps/labels/counts only)
#   - security_events.jsonl  : sanitized security/issue events
#
# HARD RULES:
#   - Every event is sanitized + field-allowlisted before writing.
#   - NEVER write raw CV/JD text, prompts, secrets, env values, PII, paths,
#     original filenames, stack traces, or raw provider error dumps.
#   - Logging must never crash the app: all writes are best-effort.
#   - Pure helpers (scrub_text / build_* / sanitize_error) are unit-testable.
#
# This module also hosts the shared scrubbers used by guardrails, exports, and
# the governance panel (single source of truth; stdlib-only, no heavy deps).

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

PathLike = Union[str, Path]

# ---------------------------------------------------------------------------
# Sanitization patterns (shared)
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_URL_RE = re.compile(r"(https?://\S+|www\.\S+)", re.IGNORECASE)
_PHONE_RE = re.compile(r"\(?\+?\d[\d\s().\-]{7,}\d\)?")

# API-key-like tokens (specific prefixes + generic long opaque tokens).
_APIKEY_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_\-]{8,}|AIza[0-9A-Za-z_\-]{10,}|ghp_[A-Za-z0-9]{10,}|"
    r"xox[baprs]-[A-Za-z0-9\-]{8,})\b"
)
_LONG_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_\-]{40,}\b")

# Environment-variable NAMES (and obvious secret-ish names).
_ENVVAR_RE = re.compile(
    r"\b(?:OPENAI|GOOGLE|GEMINI|ANTHROPIC|AWS|AZURE)_[A-Z0-9_]*"
    r"|\bACAI_[A-Z0-9_]+\b|\bAPP_ENV\b"
    r"|\b[A-Z][A-Z0-9_]{2,}_(?:KEY|TOKEN|SECRET|PASSWORD)\b"
)

# Source / data / absolute paths.
_PATH_RE = re.compile(
    r"(?:[A-Za-z]:\\[^\s'\"]+"
    r"|/(?:home|Users|var|etc|opt|tmp)/[^\s'\"]+"
    r"|(?:\.{0,2}[\\/])?(?:src|data|tests|docs)[\\/][^\s'\"]*)"
)

# Internal prompt / instruction markers.
_PROMPT_MARKER_RE = re.compile(
    r"(?i)\b(system prompt|developer (?:message|prompt)|hidden instructions?|"
    r"chain[\s\-]of[\s\-]thought|prompt template|few[\s\-]?shot)\b"
)

# Categories a scanner can report (order = scrub order).
_LEAK_RULES = [
    ("email", _EMAIL_RE, "[EMAIL_REDACTED]"),
    ("url", _URL_RE, "[URL_REDACTED]"),
    ("api_key", _APIKEY_RE, "[KEY_REDACTED]"),
    ("env_var", _ENVVAR_RE, "[ENV_REDACTED]"),
    ("path", _PATH_RE, "[PATH_REDACTED]"),
    ("prompt_marker", _PROMPT_MARKER_RE, "[REDACTED]"),
    ("long_token", _LONG_TOKEN_RE, "[REDACTED]"),
    ("phone", _PHONE_RE, "[PHONE_REDACTED]"),
]


def scrub_text(text: Any) -> str:
    """Masks emails/URLs/keys/env/paths/prompt-markers/phones in a string."""
    s = str(text if text is not None else "")
    for _name, pattern, repl in _LEAK_RULES:
        s = pattern.sub(repl, s)
    return s


def find_leaks(text: Any) -> List[str]:
    """Returns the leak categories present in `text` (before scrubbing)."""
    s = str(text if text is not None else "")
    found: List[str] = []
    for name, pattern, _repl in _LEAK_RULES:
        if pattern.search(s):
            found.append(name)
    return found


def contains_sensitive(text: Any) -> bool:
    return bool(find_leaks(text))


# Error categories for sanitized user/log messages.
def sanitize_error(error: Any) -> str:
    """
    Maps an exception/message to a SAFE, category-style string. Never returns
    raw paths, secrets, or stack traces.
    """
    msg = str(error or "")
    low = msg.lower()
    if any(h in low for h in ("permission", "denied", "unauthorized", "forbidden", "401", "403")):
        return "Access/permission error"
    if any(h in low for h in ("not found", "no such file", "missing", "filenotfound", "404")):
        return "Resource not found"
    if any(h in low for h in ("timeout", "timed out", "connection", "network", "unreachable")):
        return "Connection/timeout error"
    if any(h in low for h in ("model", "embedding", "quota", "rate limit", "api")):
        return "Model/provider error"
    if any(h in low for h in ("json", "decode", "parse", "value", "format")):
        return "Input parsing error"
    return "Unexpected error"


# ---------------------------------------------------------------------------
# Env / config
# ---------------------------------------------------------------------------

def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def app_env() -> str:
    env = _env("APP_ENV").lower()
    return env if env in {"local", "dev", "demo", "prod"} else "local"


def audit_enabled() -> bool:
    """True only when ACAI_ENABLE_AUDIT_LOG is explicitly enabled."""
    return _env("ACAI_ENABLE_AUDIT_LOG").lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Event field allowlists (anything else is dropped)
# ---------------------------------------------------------------------------

_WORKFLOW_FIELDS = {
    "mode", "step", "action", "status", "success", "duration_ms",
    "provider", "provider_status", "fallback_used", "input_type", "file_type",
    "cv_count", "jd_count", "matched_skill_count", "missing_critical_count",
    "quality_band", "score_bucket", "bucket", "count",
}
_SECURITY_FIELDS = {
    "mode", "action", "success", "status", "severity", "category",
    "error_category", "blocked_reason", "provider_status",
}

_WORKFLOW_FILENAME = "workflow_events.jsonl"
_SECURITY_FILENAME = "security_events.jsonl"
_DEFAULT_DIR = "data/reports/audit_logs"


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, (list, tuple)):
        return [_scrub_value(v) for v in value]
    return value


def _sanitize_event(fields: Dict[str, Any], allowed: set, *, app_env_value: str) -> Dict[str, Any]:
    """Keeps only allowlisted keys, scrubs every string value, stamps metadata."""
    event: Dict[str, Any] = {
        "event_id": uuid.uuid4().hex,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "app_env": app_env_value,
    }
    for key, value in (fields or {}).items():
        if key in allowed and value is not None:
            event[key] = _scrub_value(value)
    event["privacy_safe"] = True
    return event


def build_workflow_event(action: str, **fields: Any) -> Dict[str, Any]:
    """Pure builder for a sanitized workflow event (no write)."""
    fields = dict(fields)
    fields["action"] = action
    return _sanitize_event(fields, _WORKFLOW_FIELDS | {"action"}, app_env_value=app_env())


def build_security_event(action: str, *, severity: str = "info", **fields: Any) -> Dict[str, Any]:
    """Pure builder for a sanitized security event (no write)."""
    fields = dict(fields)
    fields["action"] = action
    fields["severity"] = severity if severity in {"info", "warning", "blocked", "error"} else "info"
    return _sanitize_event(fields, _SECURITY_FIELDS | {"action"}, app_env_value=app_env())


# ---------------------------------------------------------------------------
# Writing (best-effort, never raises)
# ---------------------------------------------------------------------------

def _log_dir(base_dir: Optional[PathLike] = None) -> Path:
    return Path(base_dir) if base_dir is not None else Path(_DEFAULT_DIR)


def _write_jsonl(filename: str, event: Dict[str, Any], base_dir: Optional[PathLike]) -> bool:
    try:
        directory = _log_dir(base_dir)
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / filename).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        return True
    except Exception:  # pragma: no cover - logging must never crash the app
        return False


def log_workflow_event(
    action: str, *, base_dir: Optional[PathLike] = None,
    enabled: Optional[bool] = None, **fields: Any,
) -> Optional[Dict[str, Any]]:
    """Sanitizes + appends a workflow event. No-op unless audit logging is on."""
    if not (enabled if enabled is not None else audit_enabled()):
        return None
    event = build_workflow_event(action, **fields)
    _write_jsonl(_WORKFLOW_FILENAME, event, base_dir)
    return event


def log_security_event(
    action: str, *, severity: str = "info", base_dir: Optional[PathLike] = None,
    enabled: Optional[bool] = None, **fields: Any,
) -> Optional[Dict[str, Any]]:
    """Sanitizes + appends a security event. No-op unless audit logging is on."""
    if not (enabled if enabled is not None else audit_enabled()):
        return None
    event = build_security_event(action, severity=severity, **fields)
    _write_jsonl(_SECURITY_FILENAME, event, base_dir)
    return event
