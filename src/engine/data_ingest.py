# src/engine/data_ingest.py
#
# Admin-only PRIVATE data ingest backend (Phase 17.3).
#
# Purpose:
#   Provide an explicit, opt-in way to persist an uploaded CV/JD into the local
#   PRIVATE dataset for internal testing — and nothing else. This is a separate
#   store from the consent-gated Candidate Pool (src/engine/candidate_pool.py).
#
# Storage layout (all git-ignored under data/private/):
#   data/private/
#     ├─ ingest_manifest.json                 # list[IngestRecord as dict] — audit/dedup
#     ├─ real_resumes/<record_id><ext>        # ingested CV bytes
#     └─ job_descriptions/company_private/<record_id><ext>   # ingested private JD bytes
#
# Hard rules:
#   - Writes ONLY under data/private/. Never data/raw, never the Candidate Pool.
#   - A file is saved only with an explicit authorization flag (authorized=True).
#   - Stored filenames are <record_id><original_extension> — NEVER a human name.
#     The original filename is kept ONLY in the manifest metadata.
#   - Duplicate files (identical SHA-256) are not written a second time.
#   - No network, no LLM. Pure deterministic filesystem logic.
#   - Private ingest never affects Admin/Demo listing: document_loader excludes
#     `private` path segments, so ingested files stay out of the demo selectors.
#
# Every function accepts an optional `base_dir` so tests can target a temp dir.

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Union

PathLike = Union[str, Path]

# Root of the private dataset (everything here is git-ignored).
PRIVATE_BASE_DIR = "data/private"
_MANIFEST_FILENAME = "ingest_manifest.json"

# Supported data types and their private destinations (relative to base_dir).
DATA_TYPE_RESUME = "resume"
DATA_TYPE_JD = "job_description"

# Destination constants are kept LOCAL to this module on purpose (Phase 17.3
# decision: do not extend dataset_registry.py). raw/demo destinations are
# intentionally NOT writable — raw/demo import is deferred to a later phase.
_DESTINATIONS = {
    DATA_TYPE_RESUME: "real_resumes",
    DATA_TYPE_JD: "job_descriptions/company_private",
}

# Allowed upload extensions per data type (defensive; the UI also filters).
_ALLOWED_EXTENSIONS = {
    DATA_TYPE_RESUME: {".pdf", ".docx", ".txt", ".md"},
    DATA_TYPE_JD: {".json", ".txt", ".md"},
}

_CREATED_BY_CONTEXT = "admin_ingest"
_DEFAULT_SOURCE_CATEGORY = "private"
_DEFAULT_SENSITIVITY = "high"


# Env flag that gates the entire ingest UI. Admin mode is only a sidebar role
# (not real auth), so the persistence surface stays hidden unless this is set.
_INGEST_ENV_VAR = "ACAI_ENABLE_INGEST"


def ingest_enabled() -> bool:
    """True only when ACAI_ENABLE_INGEST is explicitly truthy ('1'/'true'/'yes')."""
    return os.environ.get(_INGEST_ENV_VAR, "").strip().lower() in {"1", "true", "yes", "on"}


class AuthorizationRequiredError(Exception):
    """Raised when a private save is attempted without the authorization flag."""


class DuplicateIngestError(Exception):
    """Raised when a file with an identical SHA-256 hash is already ingested."""


class UnsupportedDestinationError(Exception):
    """Raised for an unknown data type / a non-private (raw/demo) destination."""


@dataclass
class IngestRecord:
    record_id: str
    original_filename: str
    stored_filename: str
    file_hash: str
    data_type: str
    destination: str
    source_category: str
    sensitivity: str
    uploaded_at: str
    notes: str = ""
    consent_or_authorization_flag: bool = False
    created_by_context: str = _CREATED_BY_CONTEXT

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def private_base_dir(base_dir: Optional[PathLike] = None) -> Path:
    return Path(base_dir) if base_dir is not None else Path(PRIVATE_BASE_DIR)


def manifest_path(base_dir: Optional[PathLike] = None) -> Path:
    return private_base_dir(base_dir) / _MANIFEST_FILENAME


def destination_subdir(data_type: str) -> str:
    """Returns the private sub-path for a data type, or raises for unknown types."""
    try:
        return _DESTINATIONS[data_type]
    except KeyError as exc:
        raise UnsupportedDestinationError(
            f"Unsupported data type '{data_type}'. "
            f"Allowed: {sorted(_DESTINATIONS)} (private destinations only)."
        ) from exc


def destination_dir(data_type: str, base_dir: Optional[PathLike] = None) -> Path:
    return private_base_dir(base_dir) / destination_subdir(data_type)


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def compute_file_hash(data: bytes) -> str:
    """Deterministic SHA-256 hex digest of the file bytes."""
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Manifest I/O
# ---------------------------------------------------------------------------

def _load_manifest(base_dir: Optional[PathLike] = None) -> List[dict]:
    path = manifest_path(base_dir)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_manifest(records: List[dict], base_dir: Optional[PathLike] = None) -> None:
    base = private_base_dir(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    manifest_path(base_dir).write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def list_ingested(base_dir: Optional[PathLike] = None) -> List[IngestRecord]:
    """Returns all ingested records (metadata only)."""
    records: List[IngestRecord] = []
    for rec in _load_manifest(base_dir):
        known = {f: rec.get(f) for f in IngestRecord.__dataclass_fields__}
        records.append(IngestRecord(**known))
    return records


def is_duplicate_ingest(file_hash: str, base_dir: Optional[PathLike] = None) -> bool:
    return any(rec.get("file_hash") == file_hash for rec in _load_manifest(base_dir))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _safe_extension(original_filename: str, data_type: str) -> str:
    """Returns a lowercase, allowed extension for the data type (defaults sensibly)."""
    ext = Path(original_filename or "").suffix.lower()
    allowed = _ALLOWED_EXTENSIONS[data_type]
    if ext in allowed:
        return ext
    # Fall back to a benign default rather than trusting an odd extension on disk.
    return ".json" if data_type == DATA_TYPE_JD else ".txt"


def save_private_file(
    *,
    data: bytes,
    original_filename: str,
    data_type: str,
    authorized: bool,
    notes: str = "",
    source_category: str = _DEFAULT_SOURCE_CATEGORY,
    sensitivity: str = _DEFAULT_SENSITIVITY,
    base_dir: Optional[PathLike] = None,
) -> IngestRecord:
    """
    Persists an uploaded file into the PRIVATE local dataset and records an audit
    entry in data/private/ingest_manifest.json.

    Raises:
        AuthorizationRequiredError: if `authorized` is not True.
        UnsupportedDestinationError: for an unknown / non-private data type.
        DuplicateIngestError: if an identical file (by SHA-256) is already stored.
    """
    if authorized is not True:
        raise AuthorizationRequiredError(
            "Explicit authorization is required to store a file privately."
        )

    # Validates the data type (raises UnsupportedDestinationError for raw/demo).
    subdir = destination_subdir(data_type)

    file_hash = compute_file_hash(data)
    if is_duplicate_ingest(file_hash, base_dir):
        raise DuplicateIngestError("This file is already ingested (identical hash).")

    record_id = uuid.uuid4().hex
    extension = _safe_extension(original_filename, data_type)
    stored_filename = f"{record_id}{extension}"            # no human name on disk

    dest_dir = destination_dir(data_type, base_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / stored_filename).write_bytes(data)

    record = IngestRecord(
        record_id=record_id,
        original_filename=original_filename,             # metadata only
        stored_filename=stored_filename,
        file_hash=file_hash,
        data_type=data_type,
        destination=f"{PRIVATE_BASE_DIR}/{subdir}",
        source_category=source_category,
        sensitivity=sensitivity,
        uploaded_at=datetime.now(timezone.utc).isoformat(),
        notes=notes or "",
        consent_or_authorization_flag=True,
        created_by_context=_CREATED_BY_CONTEXT,
    )

    manifest = _load_manifest(base_dir)
    manifest.append(record.to_dict())
    _save_manifest(manifest, base_dir)
    return record
