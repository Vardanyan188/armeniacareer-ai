# tests/test_candidate_pool.py
#
# Candidate pool storage tests against a tmp_path pool (never data/raw, no network).

import json

import pytest

from src.engine.candidate_pool import (
    ConsentRequiredError,
    DuplicateCandidateError,
    add_candidate,
    compute_file_hash,
    is_duplicate,
    list_candidates,
    pool_base_dir,
)


def _add(base, data=b"My CV: Python, Docker", name="cv.txt", score=0.8, consent=True):
    return add_candidate(
        data=data,
        original_filename=name,
        quality_score=score,
        detected_skills=["Python", "Docker"],
        role_families=["Backend Engineer"],
        consent=consent,
        base_dir=base,
    )


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def test_compute_file_hash_is_deterministic():
    assert compute_file_hash(b"abc") == compute_file_hash(b"abc")
    assert compute_file_hash(b"abc") != compute_file_hash(b"abd")


# ---------------------------------------------------------------------------
# Add + persistence
# ---------------------------------------------------------------------------

def test_add_candidate_persists_file_and_metadata(tmp_path):
    rec = _add(tmp_path)
    assert rec.consent is True
    assert rec.file_hash == compute_file_hash(b"My CV: Python, Docker")
    assert rec.recommended_role_families == ["Backend Engineer"]

    stored = pool_base_dir(tmp_path) / "files" / rec.stored_filename
    assert stored.is_file()
    assert stored.read_bytes() == b"My CV: Python, Docker"

    index = json.loads((pool_base_dir(tmp_path) / "index.json").read_text(encoding="utf-8"))
    assert len(index) == 1
    assert index[0]["candidate_id"] == rec.candidate_id
    assert index[0]["quality_score"] == 0.8


def test_list_candidates_returns_records(tmp_path):
    _add(tmp_path, data=b"cv one", name="a.txt")
    _add(tmp_path, data=b"cv two", name="b.txt")
    records = list_candidates(tmp_path)
    assert len(records) == 2
    assert {r.original_filename for r in records} == {"a.txt", "b.txt"}


# ---------------------------------------------------------------------------
# Consent + duplicate rules
# ---------------------------------------------------------------------------

def test_add_candidate_requires_consent(tmp_path):
    with pytest.raises(ConsentRequiredError):
        _add(tmp_path, consent=False)
    assert list_candidates(tmp_path) == []


def test_duplicate_hash_is_rejected(tmp_path):
    _add(tmp_path, data=b"same bytes")
    assert is_duplicate(compute_file_hash(b"same bytes"), tmp_path) is True
    with pytest.raises(DuplicateCandidateError):
        _add(tmp_path, data=b"same bytes", name="other.txt")
    assert len(list_candidates(tmp_path)) == 1


# ---------------------------------------------------------------------------
# Storage location safety
# ---------------------------------------------------------------------------

def test_storage_never_under_data_raw(tmp_path):
    rec = _add(tmp_path)
    stored = pool_base_dir(tmp_path) / "files" / rec.stored_filename
    s = str(stored).replace("\\", "/").lower()
    assert "data/raw" not in s


def test_empty_pool_lists_nothing(tmp_path):
    assert list_candidates(tmp_path) == []
    assert is_duplicate("deadbeef", tmp_path) is False
