# tests/test_bulk_ranker.py
#
# Deterministic bulk-ranking tests. No LLM, no network, no data/raw.

from src.engine.orchestrator import AnalysisRunResult
from src.engine.ranking.bulk_ranker import (
    bucket_for,
    build_bulk_result,
    rank_candidates,
    to_candidate_record,
)
from src.engine.ranking.models import (
    PRIORITY_LABELS,
    AnalysisStatus,
    RankBucket,
    RankedCandidate,
)

from tests._payload_factory import MOTIVATION_TEXT, make_payload


def _mk(label, composite, matched, missing, status=AnalysisStatus.SUCCESS, bucket=None):
    bucket = bucket or bucket_for(composite, matched, status)
    return RankedCandidate(
        candidate_id=label.lower(), label=label, source_filename=f"{label}.txt",
        status=status, bucket=bucket, priority_label=PRIORITY_LABELS[bucket],
        composite_pct=composite, matched_count=matched, missing_critical_count=missing,
    )


# ── Buckets ─────────────────────────────────────────────────────────────────

def test_bucket_thresholds():
    assert bucket_for(85, 3, AnalysisStatus.SUCCESS) == RankBucket.STRONG_FIT
    assert bucket_for(70, 1, AnalysisStatus.SUCCESS) == RankBucket.STRONG_FIT
    assert bucket_for(60, 2, AnalysisStatus.SUCCESS) == RankBucket.REVIEW_CLOSELY
    assert bucket_for(49, 2, AnalysisStatus.SUCCESS) == RankBucket.WEAK_FIT
    assert bucket_for(49, 0, AnalysisStatus.SUCCESS) == RankBucket.INSUFFICIENT_EVIDENCE
    assert bucket_for(99, 9, AnalysisStatus.FAILED) == RankBucket.FAILED


# ── Sorting ─────────────────────────────────────────────────────────────────

def test_deterministic_sorting_and_ranks():
    recs = [
        _mk("A", 40, 2, 1),
        _mk("B", 80, 3, 0),
        _mk("C", 60, 2, 1),
        _mk("D", 10, 0, 3),
        _mk("E", 0, 0, 0, status=AnalysisStatus.FAILED, bucket=RankBucket.FAILED),
    ]
    ranked = rank_candidates(recs)
    assert [c.label for c in ranked] == ["B", "C", "A", "D", "E"]
    assert ranked[0].rank == 1 and ranked[-1].rank == 5


def test_failed_always_last():
    recs = [
        _mk("F", 0, 0, 0, status=AnalysisStatus.FAILED, bucket=RankBucket.FAILED),
        _mk("G", 5, 0, 4),          # insufficient but successful
    ]
    ranked = rank_candidates(recs)
    assert ranked[0].label == "G"
    assert ranked[-1].status == AnalysisStatus.FAILED


def test_tie_break_by_matched_then_missing():
    recs = [_mk("X", 60, 1, 2), _mk("Y", 60, 3, 0)]
    ranked = rank_candidates(recs)
    assert [c.label for c in ranked] == ["Y", "X"]   # same score → more matched first


def test_build_bulk_result_counts():
    recs = [
        _mk("A", 80, 3, 0),
        _mk("B", 0, 0, 0, status=AnalysisStatus.FAILED, bucket=RankBucket.FAILED),
    ]
    bulk = build_bulk_result(recs)
    assert bulk.total == 2 and bulk.analyzed == 1 and bulk.failed == 1
    assert bulk.candidates[0].rank == 1


# ── Recruiter-safe extraction ───────────────────────────────────────────────

def test_to_candidate_record_success_is_recruiter_safe():
    res = AnalysisRunResult(success=True, payload=make_payload(), session_id="s1")
    rec = to_candidate_record(res, label="Candidate 1", candidate_id="abc12345",
                              source_filename="resume.txt")
    assert rec.status == AnalysisStatus.SUCCESS
    assert rec.composite_pct == 62.0
    assert rec.matched_count == 2
    assert rec.missing_critical_count == 1
    assert rec.bucket == RankBucket.REVIEW_CLOSELY

    # The ranking record's own fields carry no coaching/motivational content.
    record_text = " ".join([
        rec.label, rec.source_filename, rec.bucket.value,
        rec.priority_label, rec.candidate_id, str(rec.composite_pct),
        rec.failure_reason or "",
    ])
    assert MOTIVATION_TEXT not in record_text


def test_to_candidate_record_failed_result():
    res = AnalysisRunResult(success=False, failure_reason="bad pdf")
    rec = to_candidate_record(res, label="Candidate 2", candidate_id="def",
                              source_filename="broken.pdf")
    assert rec.status == AnalysisStatus.FAILED
    assert rec.bucket == RankBucket.FAILED
    assert rec.priority_label == "Re-upload"
    assert rec.failure_reason == "bad pdf"


def test_to_candidate_record_none_result():
    rec = to_candidate_record(None, label="Candidate 3", candidate_id="ghi",
                              source_filename="x.txt")
    assert rec.status == AnalysisStatus.FAILED
    assert rec.failure_reason
