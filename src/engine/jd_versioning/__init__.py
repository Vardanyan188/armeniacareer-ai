# src/engine/jd_versioning/__init__.py
#
# Deterministic JD Refresh / Requirement Versioning (Phase 20).
# Explanatory/comparison layer only — never feeds scoring or ranking.

from src.engine.jd_versioning.diff import DepthChange, JDVersionDiff, diff_versions
from src.engine.jd_versioning.models import (
    DEMO_SAFE_SOURCE_TYPES,
    JDEntitiesSnapshot,
    JDVersion,
    create_jd_version,
    default_jd_id,
    compute_raw_text_hash,
)
from src.engine.jd_versioning.store import (
    PrivateJDMisroutingError,
    is_private_source,
    list_versions,
    next_version_number,
    save_jd_version,
)

__all__ = [
    "JDVersion",
    "JDEntitiesSnapshot",
    "JDVersionDiff",
    "DepthChange",
    "create_jd_version",
    "diff_versions",
    "default_jd_id",
    "compute_raw_text_hash",
    "save_jd_version",
    "list_versions",
    "next_version_number",
    "is_private_source",
    "PrivateJDMisroutingError",
    "DEMO_SAFE_SOURCE_TYPES",
]
