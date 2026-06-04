# tests/test_upload_utils.py
#
# Temp-file bridge tests. Uses a fake uploaded-file object (matching Streamlit's
# UploadedFile surface: .name + .getvalue()). No data/raw, no network.

from pathlib import Path

from src.preprocessing.document_loader import load_jd_json
from src.ui.upload_utils import (
    build_jd_dict,
    save_jd_text_to_temp,
    save_upload_to_temp,
    temp_jd_text,
    temp_jd_upload,
    temp_upload,
)


class _FakeUpload:
    def __init__(self, name: str, data):
        self.name = name
        self._data = data

    def getvalue(self):
        return self._data


def _assert_not_in_data_raw(path: Path):
    s = str(path).replace("\\", "/").lower()
    assert "data/raw" not in s


# ---------------------------------------------------------------------------
# Resume upload
# ---------------------------------------------------------------------------

def test_save_upload_to_temp_preserves_extension_and_content():
    up = _FakeUpload("resume.txt", b"hello cv")
    p = save_upload_to_temp(up)
    try:
        assert p.suffix == ".txt"
        assert p.read_bytes() == b"hello cv"
        _assert_not_in_data_raw(p)
    finally:
        p.unlink(missing_ok=True)


def test_temp_upload_cleans_up():
    up = _FakeUpload("resume.md", "string content")
    with temp_upload(up) as p:
        assert p.exists()
        captured = p
    assert not captured.exists()  # deleted on exit


# ---------------------------------------------------------------------------
# JD text → temp JSON
# ---------------------------------------------------------------------------

def test_build_jd_dict_shape():
    d = build_jd_dict("some jd text", role_title="Analyst", industry="fintech")
    assert d["role_title"] == "Analyst"
    assert d["industry"] == "fintech"
    assert d["raw_text"] == "some jd text"


def test_save_jd_text_to_temp_is_loadable():
    p = save_jd_text_to_temp("Python and SQL required", role_title="Data Analyst")
    try:
        jd = load_jd_json(p)
        assert jd["raw_text"] == "Python and SQL required"
        assert jd["role_title"] == "Data Analyst"
        _assert_not_in_data_raw(p)
    finally:
        p.unlink(missing_ok=True)


def test_temp_jd_text_cleans_up():
    with temp_jd_text("jd text here") as p:
        assert p.exists()
        captured = p
    assert not captured.exists()


# ---------------------------------------------------------------------------
# JD upload (.json vs text)
# ---------------------------------------------------------------------------

def test_temp_jd_upload_json_used_as_is():
    up = _FakeUpload("jd.json", b'{"role_title": "X", "raw_text": "verbatim"}')
    with temp_jd_upload(up) as p:
        jd = load_jd_json(p)
        assert jd["raw_text"] == "verbatim"
        assert jd["role_title"] == "X"


def test_temp_jd_upload_text_is_wrapped():
    up = _FakeUpload("jd.txt", "Plain JD text with Python")
    with temp_jd_upload(up, role_title="Engineer") as p:
        jd = load_jd_json(p)
        assert jd["raw_text"] == "Plain JD text with Python"
        assert jd["role_title"] == "Engineer"
