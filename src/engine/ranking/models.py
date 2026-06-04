# src/engine/ranking/models.py
#
# Data models for deterministic Recruiter Bulk Ranking (no LLM, no network).

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional

MAX_BATCH = 10


class AnalysisStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


class RankBucket(str, Enum):
    STRONG_FIT = "Strong fit"
    REVIEW_CLOSELY = "Review closely"
    WEAK_FIT = "Weak fit"
    INSUFFICIENT_EVIDENCE = "Insufficient evidence"
    FAILED = "Failed"


# Interview-priority label per bucket.
PRIORITY_LABELS = {
    RankBucket.STRONG_FIT: "Interview first",
    RankBucket.REVIEW_CLOSELY: "Interview",
    RankBucket.WEAK_FIT: "Backup",
    RankBucket.INSUFFICIENT_EVIDENCE: "Re-screen / better CV",
    RankBucket.FAILED: "Re-upload",
}


@dataclass
class RankedCandidate:
    candidate_id: str                       # short content hash (no PII)
    label: str                              # "Candidate N" (upload order)
    source_filename: str                    # recruiter-provided filename (their own file)
    status: AnalysisStatus
    bucket: RankBucket
    priority_label: str
    composite_pct: float = 0.0
    matched_count: int = 0
    missing_critical_count: int = 0
    failure_reason: Optional[str] = None
    rank: int = 0                           # assigned after sorting (1-based)
    # The recruiter-safe result is held only for the detail view; never serialized.
    result: Any = None


@dataclass
class BulkRankingResult:
    candidates: List[RankedCandidate] = field(default_factory=list)
    total: int = 0
    analyzed: int = 0
    failed: int = 0
