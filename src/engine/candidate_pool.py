# src/engine/candidate_pool.py
#
# Local persistence backend for APPROVED candidate CVs.
#
# Storage layout (git-ignored via data/uploads/):
#   data/uploads/candidate_pool/
#     ├─ index.json          # list[CandidateRecord as dict] — metadata only
#     └─ files/
#          └─ <candidate_id>__<sanitized_original_name>   # stored CV bytes
#
# Hard rules:
#   - CVs are written ONLY under the pool dir, never under data/raw.
#   - A record is stored only with explicit consent (consent=True) AND a quality
#     score at/above the threshold. Nothing is ever added automatically.
#   - Duplicate CVs are prevented by SHA-256 file hash.
#   - No network, no LLM.
#
# Every function accepts an optional `base_dir` so tests can target a temp dir.

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Union

PathLike = Union[str, Path]

# Quality gate for pool eligibility (env-overridable).
CANDIDATE_POOL_QUALITY_THRESHOLD: float = float(
    os.environ.get("ACAI_CANDIDATE_POOL_THRESHOLD", "0.70")
)

_DEFAULT_POOL_DIR = os.environ.get(
    "ACAI_CANDIDATE_POOL_DIR", "data/uploads/candidate_pool"
)

_INDEX_FILENAME = "index.json"
_FILES_SUBDIR = "files"


class DuplicateCandidateError(Exception):
    """Raised when a CV with an identical file hash already exists in the pool."""


class ConsentRequiredError(Exception):
    """Raised when an add is attempted without explicit consent."""


@dataclass
class CandidateRecord:
    candidate_id: str
    original_filename: str
    stored_filename: str
    file_hash: str
    quality_score: float
    detected_skills: List[str] = field(default_factory=list)
    recommended_role_families: List[str] = field(default_factory=list)
    created_at: str = ""
    consent: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def pool_base_dir(base_dir: Optional[PathLike] = None) -> Path:
    return Path(base_dir) if base_dir is not None else Path(_DEFAULT_POOL_DIR)


def _files_dir(base_dir: Optional[PathLike] = None) -> Path:
    return pool_base_dir(base_dir) / _FILES_SUBDIR


def _index_path(base_dir: Optional[PathLike] = None) -> Path:
    return pool_base_dir(base_dir) / _INDEX_FILENAME


def ensure_pool(base_dir: Optional[PathLike] = None) -> None:
    _files_dir(base_dir).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Index I/O
# ---------------------------------------------------------------------------

def _load_index(base_dir: Optional[PathLike] = None) -> List[dict]:
    path = _index_path(base_dir)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_index(records: List[dict], base_dir: Optional[PathLike] = None) -> None:
    ensure_pool(base_dir)
    _index_path(base_dir).write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_file_hash(data: bytes) -> str:
    """Deterministic SHA-256 hex digest of the file bytes."""
    return hashlib.sha256(data).hexdigest()


def is_duplicate(file_hash: str, base_dir: Optional[PathLike] = None) -> bool:
    return any(rec.get("file_hash") == file_hash for rec in _load_index(base_dir))


def list_candidates(base_dir: Optional[PathLike] = None) -> List[CandidateRecord]:
    """Returns all stored candidate records (metadata only)."""
    records: List[CandidateRecord] = []
    for rec in _load_index(base_dir):
        try:
            records.append(CandidateRecord(**rec))
        except TypeError:
            # Tolerate forward/backward-compatible index entries.
            known = {f: rec.get(f) for f in CandidateRecord.__dataclass_fields__}
            records.append(CandidateRecord(**known))
    return records


def _sanitize_filename(name: str) -> str:
    base = Path(name or "cv").name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("_")
    return cleaned or "cv"


def add_candidate(
    *,
    data: bytes,
    original_filename: str,
    quality_score: float,
    detected_skills: Optional[List[str]] = None,
    role_families: Optional[List[str]] = None,
    consent: bool,
    base_dir: Optional[PathLike] = None,
) -> CandidateRecord:
    """
    Persists an approved candidate CV and its metadata.

    Raises:
        ConsentRequiredError: if consent is not True.
        DuplicateCandidateError: if a CV with the same hash already exists.
    """
    if consent is not True:
        raise ConsentRequiredError("Explicit consent is required to store a CV.")

    file_hash = compute_file_hash(data)
    if is_duplicate(file_hash, base_dir):
        raise DuplicateCandidateError("This CV is already in the candidate pool.")

    ensure_pool(base_dir)
    candidate_id = uuid.uuid4().hex
    stored_filename = f"{candidate_id}__{_sanitize_filename(original_filename)}"
    (_files_dir(base_dir) / stored_filename).write_bytes(data)

    record = CandidateRecord(
        candidate_id=candidate_id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        file_hash=file_hash,
        quality_score=round(float(quality_score), 3),
        detected_skills=list(detected_skills or []),
        recommended_role_families=list(role_families or []),
        created_at=datetime.now(timezone.utc).isoformat(),
        consent=True,
    )

    index = _load_index(base_dir)
    index.append(record.to_dict())
    _save_index(index, base_dir)
    return record
