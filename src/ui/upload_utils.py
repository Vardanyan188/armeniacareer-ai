# src/ui/upload_utils.py
#
# Bridges Streamlit uploads (in-memory bytes) to the path-based pipeline.
#
# Privacy contract:
#   - Uploaded content is written ONLY to the system temp directory, never to
#     data/raw, and is deleted as soon as the context manager exits.
#   - No network calls. No LLM. No persistence beyond the temp file lifetime.
#
# The helpers accept any object exposing `.name` (str) and `.getvalue()`
# (bytes/str), which matches Streamlit's UploadedFile and the test fakes.

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterator, Optional


def _safe_unlink(path: Any) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:  # pragma: no cover - best-effort cleanup
        pass


def _write_temp(data: bytes, suffix: str) -> Path:
    """Writes bytes to a uniquely named temp file and returns its path."""
    fd, name = tempfile.mkstemp(suffix=suffix, prefix="acai_upload_")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
    except Exception:
        _safe_unlink(name)
        raise
    return Path(name)


def _suffix_of(filename: str) -> str:
    return Path(filename or "").suffix.lower() or ".txt"


def _as_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return bytes(value)


# ---------------------------------------------------------------------------
# Save helpers
# ---------------------------------------------------------------------------

def save_upload_to_temp(uploaded_file: Any) -> Path:
    """Writes an uploaded resume/file to a temp file, preserving its extension."""
    return _write_temp(_as_bytes(uploaded_file.getvalue()), _suffix_of(uploaded_file.name))


def build_jd_dict(
    raw_text: str,
    role_title: Optional[str] = None,
    industry: Optional[str] = None,
) -> dict:
    """Wraps free-form JD text into the minimal JD-JSON structure the loader expects."""
    return {
        "role_title": role_title or "Target Role",
        "industry": industry or "technology",
        "required_experience_years": 0.0,
        "raw_text": raw_text,
        "meta": {},
    }


def save_jd_text_to_temp(
    raw_text: str,
    role_title: Optional[str] = None,
    industry: Optional[str] = None,
) -> Path:
    """Writes pasted JD text as a temp JD-JSON file."""
    payload = build_jd_dict(raw_text, role_title, industry)
    return _write_temp(json.dumps(payload, ensure_ascii=False).encode("utf-8"), ".json")


def save_jd_upload_to_temp(
    uploaded_file: Any,
    role_title: Optional[str] = None,
    industry: Optional[str] = None,
) -> Path:
    """
    Writes an uploaded JD to a temp file. A .json upload is used as-is; a text
    upload (.txt/.md) is wrapped into JD-JSON.
    """
    suffix = _suffix_of(uploaded_file.name)
    data = _as_bytes(uploaded_file.getvalue())
    if suffix == ".json":
        return _write_temp(data, ".json")
    text = data.decode("utf-8", errors="replace")
    return save_jd_text_to_temp(text, role_title, industry)


# ---------------------------------------------------------------------------
# Context managers (auto-cleanup)
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def temp_path(path: Any) -> Iterator[Path]:
    """Yields an existing temp path and deletes it on exit."""
    try:
        yield Path(path)
    finally:
        _safe_unlink(path)


@contextlib.contextmanager
def temp_upload(uploaded_file: Any) -> Iterator[Path]:
    p = save_upload_to_temp(uploaded_file)
    try:
        yield p
    finally:
        _safe_unlink(p)


@contextlib.contextmanager
def temp_jd_text(
    raw_text: str,
    role_title: Optional[str] = None,
    industry: Optional[str] = None,
) -> Iterator[Path]:
    p = save_jd_text_to_temp(raw_text, role_title, industry)
    try:
        yield p
    finally:
        _safe_unlink(p)


@contextlib.contextmanager
def temp_jd_upload(
    uploaded_file: Any,
    role_title: Optional[str] = None,
    industry: Optional[str] = None,
) -> Iterator[Path]:
    p = save_jd_upload_to_temp(uploaded_file, role_title, industry)
    try:
        yield p
    finally:
        _safe_unlink(p)
