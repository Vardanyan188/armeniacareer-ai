# tests/test_data_ingest.py
#
# Deterministic tests for the Admin-only PRIVATE data ingest backend.
# No LLM, no network. All writes target a pytest tmp_path — never the real
# data/private tree.

import json

import pytest

from src.engine.data_ingest import (
    DATA_TYPE_JD,
    DATA_TYPE_RESUME,
    AuthorizationRequiredError,
    DuplicateIngestError,
    IngestRecord,
    UnsupportedDestinationError,
    compute_file_hash,
    ingest_enabled,
    is_duplicate_ingest,
    list_ingested,
    manifest_path,
    save_private_file,
)
from src.preprocessing.document_loader import list_jd_files, list_resume_files

_CV_BYTES = b"John Doe - Senior Engineer - Python, SQL"
_CV_NAME = "John_Doe_Resume.pdf"


# ---------------------------------------------------------------------------
# Authorization gate
# ---------------------------------------------------------------------------

def test_save_requires_authorization(tmp_path):
    with pytest.raises(AuthorizationRequiredError):
        save_private_file(
            data=_CV_BYTES, original_filename=_CV_NAME,
            data_type=DATA_TYPE_RESUME, authorized=False, base_dir=tmp_path,
        )
    # Nothing should have been written.
    assert not manifest_path(tmp_path).exists()


# ---------------------------------------------------------------------------
# Destination safety
# ---------------------------------------------------------------------------

def test_saved_file_lands_only_under_private_base(tmp_path):
    record = save_private_file(
        data=_CV_BYTES, original_filename=_CV_NAME,
        data_type=DATA_TYPE_RESUME, authorized=True, base_dir=tmp_path,
    )
    stored = tmp_path / "real_resumes" / record.stored_filename
    assert stored.is_file()
    assert stored.read_bytes() == _CV_BYTES
    # Destination metadata points at the private tree, not data/raw.
    assert record.destination == "data/private/real_resumes"
    assert "raw" not in record.destination


def test_private_jd_destination(tmp_path):
    record = save_private_file(
        data=b'{"role_title": "X"}', original_filename="company_jd.json",
        data_type=DATA_TYPE_JD, authorized=True, base_dir=tmp_path,
    )
    assert record.destination == "data/private/job_descriptions/company_private"
    assert (tmp_path / "job_descriptions" / "company_private" / record.stored_filename).is_file()


def test_raw_demo_destination_rejected(tmp_path):
    # Unknown / non-private data types must be refused.
    with pytest.raises(UnsupportedDestinationError):
        save_private_file(
            data=_CV_BYTES, original_filename=_CV_NAME,
            data_type="raw_demo", authorized=True, base_dir=tmp_path,
        )
    with pytest.raises(UnsupportedDestinationError):
        save_private_file(
            data=_CV_BYTES, original_filename=_CV_NAME,
            data_type="generated_samples", authorized=True, base_dir=tmp_path,
        )


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def test_duplicate_hash_not_written_twice(tmp_path):
    save_private_file(
        data=_CV_BYTES, original_filename=_CV_NAME,
        data_type=DATA_TYPE_RESUME, authorized=True, base_dir=tmp_path,
    )
    assert is_duplicate_ingest(compute_file_hash(_CV_BYTES), base_dir=tmp_path)

    with pytest.raises(DuplicateIngestError):
        save_private_file(
            data=_CV_BYTES, original_filename="different_name.pdf",
            data_type=DATA_TYPE_RESUME, authorized=True, base_dir=tmp_path,
        )

    # Exactly one stored file and one manifest entry.
    stored_files = list((tmp_path / "real_resumes").iterdir())
    assert len(stored_files) == 1
    assert len(list_ingested(tmp_path)) == 1


# ---------------------------------------------------------------------------
# Filename privacy
# ---------------------------------------------------------------------------

def test_stored_filename_has_no_human_name(tmp_path):
    record = save_private_file(
        data=_CV_BYTES, original_filename=_CV_NAME,
        data_type=DATA_TYPE_RESUME, authorized=True, base_dir=tmp_path,
    )
    assert "John" not in record.stored_filename
    assert "Doe" not in record.stored_filename
    # <record_id><ext> shape.
    assert record.stored_filename == f"{record.record_id}.pdf"


def test_original_filename_only_in_manifest_metadata(tmp_path):
    record = save_private_file(
        data=_CV_BYTES, original_filename=_CV_NAME,
        data_type=DATA_TYPE_RESUME, authorized=True, base_dir=tmp_path,
    )
    # On disk: no human name.
    on_disk = [p.name for p in (tmp_path / "real_resumes").iterdir()]
    assert all("John_Doe" not in name for name in on_disk)
    # In manifest: original filename preserved.
    manifest = json.loads(manifest_path(tmp_path).read_text(encoding="utf-8"))
    assert manifest[0]["original_filename"] == _CV_NAME
    assert record.original_filename == _CV_NAME


# ---------------------------------------------------------------------------
# Manifest shape
# ---------------------------------------------------------------------------

def test_manifest_record_shape(tmp_path):
    save_private_file(
        data=_CV_BYTES, original_filename=_CV_NAME, data_type=DATA_TYPE_RESUME,
        authorized=True, notes="internal test", base_dir=tmp_path,
    )
    manifest = json.loads(manifest_path(tmp_path).read_text(encoding="utf-8"))
    assert isinstance(manifest, list) and len(manifest) == 1
    rec = manifest[0]
    expected_keys = set(IngestRecord.__dataclass_fields__)
    assert set(rec.keys()) == expected_keys
    assert rec["created_by_context"] == "admin_ingest"
    assert rec["consent_or_authorization_flag"] is True
    assert rec["data_type"] == DATA_TYPE_RESUME
    assert rec["source_category"] == "private"
    assert rec["sensitivity"] == "high"
    assert rec["notes"] == "internal test"
    assert rec["file_hash"] == compute_file_hash(_CV_BYTES)


# ---------------------------------------------------------------------------
# Loader isolation — private ingest never appears in demo listings
# ---------------------------------------------------------------------------

def test_ingested_files_excluded_from_demo_loaders(tmp_path):
    # Simulate the real layout: a 'private' subtree plus a demo-safe folder.
    private_root = tmp_path / "private"
    save_private_file(
        data=_CV_BYTES, original_filename=_CV_NAME,
        data_type=DATA_TYPE_RESUME, authorized=True, base_dir=private_root,
    )
    save_private_file(
        data=b'{"role_title": "X"}', original_filename="jd.json",
        data_type=DATA_TYPE_JD, authorized=True, base_dir=private_root,
    )
    # A demo-safe file at the same root.
    (tmp_path / "generated_samples").mkdir()
    (tmp_path / "generated_samples" / "demo.pdf").write_text("ok", encoding="utf-8")
    (tmp_path / "generated_samples" / "demo.json").write_text("{}", encoding="utf-8")

    resume_names = {p.name for p in list_resume_files(tmp_path)}
    jd_names = {p.name for p in list_jd_files(tmp_path)}
    # Demo file present; nothing from the private subtree leaks through.
    assert "demo.pdf" in resume_names
    assert all("private" not in str(p) for p in list_resume_files(tmp_path))
    assert all("private" not in str(p) for p in list_jd_files(tmp_path))
    assert jd_names == {"demo.json"}


# ---------------------------------------------------------------------------
# Env gate
# ---------------------------------------------------------------------------

def test_ingest_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ACAI_ENABLE_INGEST", raising=False)
    assert ingest_enabled() is False


def test_ingest_enabled_with_flag(monkeypatch):
    monkeypatch.setenv("ACAI_ENABLE_INGEST", "1")
    assert ingest_enabled() is True
    monkeypatch.setenv("ACAI_ENABLE_INGEST", "0")
    assert ingest_enabled() is False
