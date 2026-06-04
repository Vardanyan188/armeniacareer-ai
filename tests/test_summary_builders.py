# tests/test_summary_builders.py
#
# Privacy-boundary tests for Phase 21.2 export summary builders. Pure builders,
# fed only role-safe selector output. No LLM, no network, no API keys.

import re

import pytest

from src.engine.access_control import (
    get_candidate_view,
    get_recruiter_view,
    get_shared_view,
    get_skill_depth_view,
)
from src.engine.jd_versioning.diff import diff_versions
from src.engine.jd_versioning.models import create_jd_version
from src.engine.ranking.models import (
    AnalysisStatus,
    BulkRankingResult,
    RankBucket,
    RankedCandidate,
)
from src.schemas.canonical_payload import JDEntities, SkillCategory, SkillEntry
from src.ui.components.summary_builders import (
    build_admin_demo_markdown_summary,
    build_bulk_ranking_markdown_summary,
    build_candidate_markdown_summary,
    build_governance_markdown_summary,
    build_jd_diff_markdown_summary,
    build_recruiter_markdown_summary,
)

from tests._payload_factory import MOTIVATION_TEXT, RED_FLAG_TEXT, make_payload

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL_RE = re.compile(r"https?://|www\.")
_PHONE_RE = re.compile(r"\(?\+?\d[\d\s().\-]{7,}\d\)?")


def _assert_no_pii(md: str) -> None:
    assert not _EMAIL_RE.search(md), "email leaked"
    assert not _URL_RE.search(md), "url leaked"
    assert not _PHONE_RE.search(md), "phone leaked"


def _assert_no_private_paths(md: str) -> None:
    low = md.lower()
    assert "data/private" not in low and "data\\private" not in low
    assert "candidate_pool" not in low
    assert "real_resumes" not in low and "company_private" not in low


# ---------------------------------------------------------------------------
# Candidate export — excludes recruiter-only content
# ---------------------------------------------------------------------------

def test_candidate_summary_excludes_recruiter_only_fields():
    payload = make_payload()
    md = build_candidate_markdown_summary(
        get_candidate_view(payload), get_shared_view(payload), get_skill_depth_view(payload),
    )
    assert RED_FLAG_TEXT not in md
    assert "hire" not in md.lower()
    assert "verification" not in md.lower()
    assert "# Candidate Match Summary" in md
    _assert_no_pii(md)
    _assert_no_private_paths(md)


def test_candidate_summary_includes_coaching_but_no_recruiter_risk():
    payload = make_payload()
    md = build_candidate_markdown_summary(get_candidate_view(payload))
    # Candidate keeps their own motivational/coaching content.
    assert "Strengths" in md or "coaching" in md.lower()
    assert RED_FLAG_TEXT not in md


# ---------------------------------------------------------------------------
# Recruiter export — excludes candidate-only coaching/motivation
# ---------------------------------------------------------------------------

def test_recruiter_summary_excludes_candidate_motivation():
    payload = make_payload()
    md = build_recruiter_markdown_summary(
        get_recruiter_view(payload), get_shared_view(payload), get_skill_depth_view(payload),
    )
    assert MOTIVATION_TEXT not in md
    assert "# Recruiter Screening Summary" in md
    # Recruiter-safe screening content is present.
    assert "Recommendation" in md
    _assert_no_pii(md)
    _assert_no_private_paths(md)


# ---------------------------------------------------------------------------
# PII scrub
# ---------------------------------------------------------------------------

def test_scrub_redacts_injected_pii_in_narrative():
    payload = make_payload(
        candidate_strength="Reach me at john.doe@example.com or +374 99 123456 https://x.io",
    )
    md = build_candidate_markdown_summary(get_candidate_view(payload))
    assert "[redacted]" in md and "[link removed]" in md
    _assert_no_pii(md)


# ---------------------------------------------------------------------------
# Governance / JD diff / ranking
# ---------------------------------------------------------------------------

def test_governance_summary_is_neutral_and_keyless():
    class _R:
        payload = make_payload()
        provider_status = {"semantic_alignment": "deterministic"}
        llm_used = False
        agent_errors = {}
        input_guardrail = None
        output_guardrail = None
    md = build_governance_markdown_summary(_R())
    assert "# Governance & Fallback Summary" in md
    assert "sk-" not in md  # no API keys
    _assert_no_pii(md)
    _assert_no_private_paths(md)


def _sk(name):
    return SkillEntry(raw_name=name, canonical_name=name, category=SkillCategory.TECHNICAL)


def test_jd_diff_summary_headings():
    old = create_jd_version(raw_text="a", jd_entities=JDEntities(
        role_title="X", required_skills=[_sk("Python")]), source_type="generated")
    new = create_jd_version(raw_text="b", jd_entities=JDEntities(
        role_title="X", required_skills=[_sk("Python"), _sk("Docker")]), source_type="generated")
    md = build_jd_diff_markdown_summary(diff_versions(old, new))
    assert "# JD Requirement Change Summary" in md
    assert "Docker" in md
    _assert_no_pii(md)


def test_bulk_ranking_summary_omits_source_filename():
    rc = RankedCandidate(
        candidate_id="abc123", label="Candidate 1",
        source_filename="John_Doe_CV_+37499123456.pdf",   # must NOT appear
        status=AnalysisStatus.SUCCESS, bucket=RankBucket.STRONG_FIT,
        priority_label="Interview first", composite_pct=82.0,
        matched_count=5, missing_critical_count=1, rank=1,
    )
    bulk = BulkRankingResult(candidates=[rc], total=1, analyzed=1, failed=0)
    md = build_bulk_ranking_markdown_summary(bulk)
    assert "John_Doe_CV" not in md
    assert "Candidate 1" in md and "abc123" in md
    assert "# Candidate Ranking Summary" in md
    _assert_no_pii(md)


# ---------------------------------------------------------------------------
# Admin stamp + determinism + no-keys
# ---------------------------------------------------------------------------

def test_admin_export_is_stamped_internal():
    payload = make_payload()
    md = build_admin_demo_markdown_summary(
        get_candidate_view(payload), get_recruiter_view(payload), get_shared_view(payload),
    )
    assert "INTERNAL DEMO — decision-support only — not a hiring decision." in md
    _assert_no_pii(md)
    _assert_no_private_paths(md)


def test_builders_are_deterministic():
    payload = make_payload()
    cv = get_candidate_view(payload)
    assert build_candidate_markdown_summary(cv) == build_candidate_markdown_summary(cv)


def test_builders_need_no_api_keys(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    payload = make_payload()
    assert build_candidate_markdown_summary(get_candidate_view(payload)).startswith("# Candidate")


def test_disclaimer_present_in_all():
    payload = make_payload()
    cmd = build_candidate_markdown_summary(get_candidate_view(payload))
    rmd = build_recruiter_markdown_summary(get_recruiter_view(payload))
    assert "Decision-support only" in cmd and "Decision-support only" in rmd
