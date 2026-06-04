# src/engine/jd_versioning/store.py
#
# Deterministic filesystem store for JD version history (Phase 20).
#
# Layout (sibling of the scanned JD dirs, so document_loader is untouched and
# snapshots NEVER appear in the JD selectors):
#   data/raw/jd_version_history/       demo-safe (generated/public) versions
#     ├─ index.json                    list[version metadata]
#     └─ <jd_id>/<version_id>.json     per-version snapshot
#   data/private/jd_version_history/   private / recruiter "current" JD versions
#     ├─ index.json
#     └─ <jd_id>/<version_id>.json
#
# Hard rules:
#   - A private-source version is NEVER written to the raw (demo) history.
#   - No writes under data/raw/job_descriptions/** or data/private/job_descriptions/**.
#   - No network, no LLM. Pure filesystem.
#
# Every function accepts an optional `base_dir` so tests target a temp dir; under
# `base_dir` the two roots become `<base_dir>/raw` and `<base_dir>/private`.

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Union

from src.engine.jd_versioning.models import (
    DEMO_SAFE_SOURCE_TYPES,
    JDEntitiesSnapshot,
    JDVersion,
)

PathLike = Union[str, Path]

RAW_HISTORY_DIR = "data/raw/jd_version_history"
PRIVATE_HISTORY_DIR = "data/private/jd_version_history"
_INDEX_FILENAME = "index.json"


class PrivateJDMisroutingError(Exception):
    """Raised when a private-source JD version would be written to the demo (raw) history."""


def is_private_source(source_type: str) -> bool:
    return source_type not in DEMO_SAFE_SOURCE_TYPES


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def history_root(private: bool, base_dir: Optional[PathLike] = None) -> Path:
    if base_dir is not None:
        return Path(base_dir) / ("private" if private else "raw")
    return Path(PRIVATE_HISTORY_DIR if private else RAW_HISTORY_DIR)


def _index_path(private: bool, base_dir: Optional[PathLike] = None) -> Path:
    return history_root(private, base_dir) / _INDEX_FILENAME


# ---------------------------------------------------------------------------
# Index I/O
# ---------------------------------------------------------------------------

def _load_index(private: bool, base_dir: Optional[PathLike] = None) -> List[dict]:
    path = _index_path(private, base_dir)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_index(records: List[dict], private: bool, base_dir: Optional[PathLike] = None) -> None:
    root = history_root(private, base_dir)
    root.mkdir(parents=True, exist_ok=True)
    _index_path(private, base_dir).write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def next_version_number(jd_id: str, *, private: bool, base_dir: Optional[PathLike] = None) -> int:
    """Next 1-based version number for a jd_id within a given history root."""
    existing = [r for r in _load_index(private, base_dir) if r.get("jd_id") == jd_id]
    return 1 + max((int(r.get("version_number", 0)) for r in existing), default=0)


def save_jd_version(
    version: JDVersion,
    *,
    base_dir: Optional[PathLike] = None,
    to_private: Optional[bool] = None,
) -> Path:
    """
    Persists a JDVersion snapshot + updates the index.

    Routing: a private-source version always goes to the private history. The
    optional `to_private` lets a caller request a target explicitly; requesting
    the raw (demo) history for a private source raises PrivateJDMisroutingError.
    """
    src_private = is_private_source(version.source_type)
    target_private = src_private if to_private is None else bool(to_private)

    if src_private and not target_private:
        raise PrivateJDMisroutingError(
            f"Source type '{version.source_type}' is private and must not be "
            "written to the demo (raw) version history."
        )

    root = history_root(target_private, base_dir)
    jd_dir = root / version.jd_id
    jd_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = jd_dir / f"{version.version_id}.json"
    snapshot_path.write_text(
        json.dumps(version.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    index = _load_index(target_private, base_dir)
    index.append({
        "jd_id": version.jd_id,
        "version_id": version.version_id,
        "version_number": version.version_number,
        "created_at": version.created_at,
        "source_type": version.source_type,
        "original_filename": version.original_filename,
        "raw_text_hash": version.raw_text_hash,
        "notes": version.notes,
        "snapshot": f"{version.jd_id}/{version.version_id}.json",
    })
    _save_index(index, target_private, base_dir)
    return snapshot_path


def _to_version(data: dict) -> JDVersion:
    ent = data.get("entities") or {}
    known = {f: ent.get(f) for f in JDEntitiesSnapshot.__dataclass_fields__}
    snapshot = JDEntitiesSnapshot(**{k: v for k, v in known.items() if v is not None})
    fields = {f: data.get(f) for f in JDVersion.__dataclass_fields__}
    fields["entities"] = snapshot
    fields["required_depth"] = data.get("required_depth") or {}
    fields["notes"] = data.get("notes") or ""
    return JDVersion(**fields)


def list_versions(
    jd_id: Optional[str] = None, *, private: bool, base_dir: Optional[PathLike] = None,
) -> List[JDVersion]:
    """Loads stored versions (optionally filtered by jd_id), ordered by version_number."""
    root = history_root(private, base_dir)
    out: List[JDVersion] = []
    for rec in _load_index(private, base_dir):
        if jd_id is not None and rec.get("jd_id") != jd_id:
            continue
        snap = root / str(rec.get("snapshot", ""))
        if not snap.is_file():
            continue
        try:
            out.append(_to_version(json.loads(snap.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, OSError, TypeError):
            continue
    return sorted(out, key=lambda v: (v.jd_id, v.version_number))


def list_jd_ids(*, private: bool, base_dir: Optional[PathLike] = None) -> List[str]:
    return sorted({r.get("jd_id", "") for r in _load_index(private, base_dir) if r.get("jd_id")})
