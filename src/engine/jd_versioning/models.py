# src/engine/jd_versioning/models.py
#
# Plain-dataclass models for deterministic JD Refresh / Requirement Versioning
# (Phase 20). Separate from the pydantic canonical payload — the payload schema
# is never modified by this feature.
#
# A JDVersion is an immutable, PII-light snapshot of a job description's
# requirements at a point in time: parsed entity snapshot + a raw-text hash +
# the reused Phase-19 required-depth map. No LLM, no network.

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Source types that may persist to the demo (data/raw) version history. Anything
# else (pasted / uploaded / private / recruiter "current" JDs) is treated as
# private and may persist only under data/private.
DEMO_SAFE_SOURCE_TYPES = {"generated", "public"}


# ---------------------------------------------------------------------------
# Snapshot models
# ---------------------------------------------------------------------------

@dataclass
class JDEntitiesSnapshot:
    role_title: str
    required_skills: List[str] = field(default_factory=list)      # canonical names
    preferred_skills: List[str] = field(default_factory=list)
    responsibilities: List[str] = field(default_factory=list)
    required_qualifications: List[str] = field(default_factory=list)
    required_seniority: str = "mid"
    required_experience_years: float = 0.0
    industry: str = "technology"


@dataclass
class JDVersion:
    jd_id: str
    version_id: str
    version_number: int
    created_at: str
    source_type: str
    original_filename: Optional[str]
    raw_text_hash: str
    entities: JDEntitiesSnapshot
    required_depth: Dict[str, str] = field(default_factory=dict)   # skill -> depth label
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def is_private_source(self) -> bool:
        return self.source_type not in DEMO_SAFE_SOURCE_TYPES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def normalize_raw_text(text: str) -> str:
    """Deterministic normalization for hashing: lowercase + collapsed whitespace."""
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def compute_raw_text_hash(text: str) -> str:
    """SHA-256 of the normalized raw text."""
    return hashlib.sha256(normalize_raw_text(text).encode("utf-8")).hexdigest()


def _slug(value: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return s or "jd"


def default_jd_id(role_title: str, raw_text_hash: str) -> str:
    """Stable default id seeded from role title + a short hash (operator-editable)."""
    return f"{_slug(role_title)}-{raw_text_hash[:8]}"


def _names(skill_entries: Any) -> List[str]:
    out: List[str] = []
    seen: set = set()
    for entry in skill_entries or []:
        name = str(getattr(entry, "canonical_name", None) or getattr(entry, "raw_name", "")).strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out


def snapshot_from_entities(jd_entities: Any) -> JDEntitiesSnapshot:
    return JDEntitiesSnapshot(
        role_title=str(getattr(jd_entities, "role_title", "") or ""),
        required_skills=_names(getattr(jd_entities, "required_skills", [])),
        preferred_skills=_names(getattr(jd_entities, "preferred_skills", [])),
        responsibilities=list(getattr(jd_entities, "responsibilities", []) or []),
        required_qualifications=list(getattr(jd_entities, "required_qualifications", []) or []),
        required_seniority=_enum_value(getattr(jd_entities, "required_seniority", "mid")),
        required_experience_years=float(getattr(jd_entities, "required_experience_years", 0.0) or 0.0),
        industry=str(getattr(jd_entities, "industry", "technology") or "technology"),
    )


def required_depth_snapshot(jd_entities: Any) -> Dict[str, str]:
    """
    Reuses the Phase-19 skill-depth engine READ-ONLY: an empty CV yields each
    required skill's required_depth, with no candidate inference. skill_depth/
    is not modified.
    """
    from src.engine.skill_depth.analyzer import analyze_skill_depth
    from src.schemas.canonical_payload import CVEntities

    analysis = analyze_skill_depth(CVEntities(), jd_entities)
    return {e.skill: e.required_depth.label for e in analysis.entries}


def create_jd_version(
    *,
    raw_text: str,
    jd_entities: Any,
    source_type: str,
    jd_id: Optional[str] = None,
    version_number: int = 1,
    original_filename: Optional[str] = None,
    notes: str = "",
    created_at: Optional[str] = None,
) -> JDVersion:
    """
    Builds a deterministic JDVersion from raw text + parsed JDEntities.
    `jd_id` defaults to a stable, operator-editable slug from role title + hash.
    """
    raw_hash = compute_raw_text_hash(raw_text)
    snapshot = snapshot_from_entities(jd_entities)
    resolved_id = (jd_id or "").strip() or default_jd_id(snapshot.role_title, raw_hash)
    return JDVersion(
        jd_id=resolved_id,
        version_id=uuid.uuid4().hex,
        version_number=int(version_number),
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
        source_type=source_type,
        original_filename=original_filename,
        raw_text_hash=raw_hash,
        entities=snapshot,
        required_depth=required_depth_snapshot(jd_entities),
        notes=notes or "",
    )
