# tests/test_document_loader.py
#
# Lightweight tests for the document loading layer. They rely only on temporary
# files created at runtime — no real (private) CV data is required or committed.
# PDF/DOCX extraction is exercised only if the optional parsers are installed.

import json

import pytest

from src.preprocessing.document_loader import (
    JD_EXTENSIONS,
    RESUME_EXTENSIONS,
    extract_docx_text,
    extract_pdf_text,
    jd_json_to_raw_text,
    list_jd_files,
    list_resume_files,
    load_jd_json,
    load_resume_text,
    load_text_file,
)


# ---------------------------------------------------------------------------
# Plain text + resume dispatch
# ---------------------------------------------------------------------------

def test_load_text_file_reads_utf8(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("Բարև Hello", encoding="utf-8")
    assert load_text_file(f) == "Բարև Hello"


def test_load_resume_text_dispatches_txt_and_md(tmp_path):
    txt = tmp_path / "cv.txt"
    txt.write_text("plain cv", encoding="utf-8")
    md = tmp_path / "cv.md"
    md.write_text("# markdown cv", encoding="utf-8")
    assert load_resume_text(txt) == "plain cv"
    assert load_resume_text(md) == "# markdown cv"


def test_load_resume_text_rejects_unsupported_extension(tmp_path):
    bad = tmp_path / "cv.doc"
    bad.write_text("legacy word", encoding="utf-8")
    with pytest.raises(ValueError):
        load_resume_text(bad)


def test_load_resume_text_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_resume_text(tmp_path / "nope.pdf")


# ---------------------------------------------------------------------------
# JD JSON
# ---------------------------------------------------------------------------

def test_load_jd_json_roundtrip(tmp_path):
    payload = {"jd_id": "JD_TEST_001", "role_title": "Mathematician", "raw_text": "full text"}
    f = tmp_path / "jd.json"
    f.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    assert load_jd_json(f) == payload


def test_load_jd_json_rejects_non_json(tmp_path):
    f = tmp_path / "jd.txt"
    f.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_jd_json(f)


def test_load_jd_json_rejects_non_object(tmp_path):
    f = tmp_path / "jd.json"
    f.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(ValueError):
        load_jd_json(f)


def test_jd_json_to_raw_text_prefers_raw_text():
    jd = {"role_title": "X", "raw_text": "verbatim description"}
    assert jd_json_to_raw_text(jd) == "verbatim description"


def test_jd_json_to_raw_text_composes_fallback():
    jd = {"role_title": "Mathematician", "company_name": "SoftConstruct", "industry": "iGaming"}
    out = jd_json_to_raw_text(jd)
    assert "Mathematician" in out
    assert "SoftConstruct" in out
    assert "iGaming" in out


def test_jd_json_to_raw_text_empty_raw_text_falls_back():
    jd = {"role_title": "Analyst", "raw_text": "   "}
    out = jd_json_to_raw_text(jd)
    assert "Analyst" in out


# ---------------------------------------------------------------------------
# Directory listing
# ---------------------------------------------------------------------------

def test_list_resume_files_filters_and_sorts(tmp_path):
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    (tmp_path / "ignore.csv").write_text("x", encoding="utf-8")
    names = [p.name for p in list_resume_files(tmp_path)]
    assert names == ["a.md", "b.txt"]


def test_list_jd_files_filters_json(tmp_path):
    (tmp_path / "one.json").write_text("{}", encoding="utf-8")
    (tmp_path / "two.txt").write_text("x", encoding="utf-8")
    names = [p.name for p in list_jd_files(tmp_path)]
    assert names == ["one.json"]


def test_list_helpers_missing_dir_returns_empty(tmp_path):
    missing = tmp_path / "does_not_exist"
    assert list_resume_files(missing) == []
    assert list_jd_files(missing) == []


def test_list_resume_files_recurses_subfolders(tmp_path):
    (tmp_path / "generated_samples").mkdir()
    (tmp_path / "linkedin_profiles").mkdir()
    (tmp_path / "generated_samples" / "a.pdf").write_text("a", encoding="utf-8")
    (tmp_path / "linkedin_profiles" / "b.txt").write_text("b", encoding="utf-8")
    names = {p.name for p in list_resume_files(tmp_path)}
    assert names == {"a.pdf", "b.txt"}


def test_list_resume_files_excludes_private_and_uploads(tmp_path):
    (tmp_path / "generated_samples").mkdir()
    (tmp_path / "generated_samples" / "ok.pdf").write_text("ok", encoding="utf-8")
    (tmp_path / "private").mkdir()
    (tmp_path / "private" / "secret.pdf").write_text("x", encoding="utf-8")
    (tmp_path / "uploads" / "candidate_pool").mkdir(parents=True)
    (tmp_path / "uploads" / "candidate_pool" / "pool.pdf").write_text("x", encoding="utf-8")
    names = {p.name for p in list_resume_files(tmp_path)}
    assert names == {"ok.pdf"}            # private + candidate_pool excluded


def test_list_jd_files_recurses_and_excludes_private(tmp_path):
    (tmp_path / "generated_samples" / "international").mkdir(parents=True)
    (tmp_path / "generated_samples" / "international" / "jd.json").write_text("{}", encoding="utf-8")
    (tmp_path / "private").mkdir()
    (tmp_path / "private" / "company.json").write_text("{}", encoding="utf-8")
    names = {p.name for p in list_jd_files(tmp_path)}
    assert names == {"jd.json"}


# ---------------------------------------------------------------------------
# Optional binary parsers (skipped when the package is not installed)
# ---------------------------------------------------------------------------

def test_extract_docx_text_if_available(tmp_path):
    docx = pytest.importorskip("docx")  # python-docx
    path = tmp_path / "cv.docx"
    document = docx.Document()
    document.add_paragraph("Hello from docx")
    document.save(str(path))
    assert "Hello from docx" in extract_docx_text(path)


def test_extract_pdf_text_requires_pypdf(tmp_path):
    pytest.importorskip("pypdf")
    # Construction of a real PDF is out of scope; we only assert a missing file raises.
    with pytest.raises(FileNotFoundError):
        extract_pdf_text(tmp_path / "missing.pdf")


def test_format_extension_constants():
    assert ".pdf" in RESUME_EXTENSIONS and ".docx" in RESUME_EXTENSIONS
    assert JD_EXTENSIONS == {".json"}
