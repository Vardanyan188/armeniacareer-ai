# src/engine/ranking/bulk_ranker.py
#
# Deterministic ranking logic for Recruiter Bulk Ranking (no LLM, no network).
#
# Reads ONLY recruiter-safe / neutral data (get_shared_view), so candidate
# coaching roadmap and motivational framing can never enter a ranking record.
# Wraps the existing run_analysis results; does NOT modify scoring.

from __future__ import annotations

from typing import Any, List, Optional

from src.engine.access_control import get_shared_view
from src.engine.ranking.models import (
    PRIORITY_LABELS,
    AnalysisStatus,
    BulkRankingResult,
    RankBucket,
    RankedCandidate,
)

_STRONG_MIN = 70.0
_REVIEW_MIN = 50.0


def bucket_for(
    composite_pct: float,
    matched_count: int,
    status: AnalysisStatus,
) -> RankBucket:
    """Deterministic bucket from composite score + evidence + status."""
    if status == AnalysisStatus.FAILED:
        return RankBucket.FAILED
    if composite_pct >= _STRONG_MIN:
        return RankBucket.STRONG_FIT
    if composite_pct >= _REVIEW_MIN:
        return RankBucket.REVIEW_CLOSELY
    if matched_count >= 1:
        return RankBucket.WEAK_FIT
    return RankBucket.INSUFFICIENT_EVIDENCE


def to_candidate_record(
    result: Any,
    *,
    label: str,
    candidate_id: str,
    source_filename: str,
) -> RankedCandidate:
    """
    Builds a recruiter-safe ranking record from an AnalysisRunResult.
    A None / unsuccessful result becomes a FAILED record (kept in the table).
    """
    if result is None or not getattr(result, "success", False) or result.payload is None:
        reason = getattr(result, "failure_reason", None) if result is not None else "analysis error"
        return RankedCandidate(
            candidate_id=candidate_id,
            label=label,
            source_filename=source_filename,
            status=AnalysisStatus.FAILED,
            bucket=RankBucket.FAILED,
            priority_label=PRIORITY_LABELS[RankBucket.FAILED],
            failure_reason=reason or "analysis error",
            result=result,
        )

    shared = get_shared_view(result.payload)
    composite = float(shared["composite_score_percentage"])
    summary = shared["skills_ontology_summary"]
    matched = int(summary.get("matched_count", 0))
    missing_critical = int(summary.get("critical_gap_count", 0))

    bucket = bucket_for(composite, matched, AnalysisStatus.SUCCESS)
    return RankedCandidate(
        candidate_id=candidate_id,
        label=label,
        source_filename=source_filename,
        status=AnalysisStatus.SUCCESS,
        bucket=bucket,
        priority_label=PRIORITY_LABELS[bucket],
        composite_pct=round(composite, 1),
        matched_count=matched,
        missing_critical_count=missing_critical,
        result=result,
    )


def _sort_key(c: RankedCandidate):
    status_rank = 0 if c.status == AnalysisStatus.SUCCESS else 1
    return (
        status_rank,                 # successes first, failures last
        -c.composite_pct,            # higher score first
        -c.matched_count,            # more matched skills first
        c.missing_critical_count,    # fewer critical gaps first
        c.label,                     # stable tie-breaker
        c.candidate_id,
    )


def rank_candidates(records: List[RankedCandidate]) -> List[RankedCandidate]:
    """Sorts records deterministically and assigns 1-based ranks in place."""
    ordered = sorted(records, key=_sort_key)
    for i, c in enumerate(ordered, start=1):
        c.rank = i
    return ordered


def build_bulk_result(records: List[RankedCandidate]) -> BulkRankingResult:
    """Sorts records and packages totals for the UI."""
    ordered = rank_candidates(records)
    failed = sum(1 for c in ordered if c.status == AnalysisStatus.FAILED)
    return BulkRankingResult(
        candidates=ordered,
        total=len(ordered),
        analyzed=len(ordered) - failed,
        failed=failed,
    )
