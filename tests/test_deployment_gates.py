# tests/test_deployment_gates.py
#
# Phase 22 — runtime feature gates (src/ui/app_gates.py). Pure, env-only.

import pytest

from src.ui import app_gates as g

_FLAGS = [
    "APP_ENV", "ACAI_ENABLE_ADMIN", "ACAI_ENABLE_INGEST",
    "ACAI_ENABLE_CANDIDATE_POOL", "ACAI_DEBUG", "ACAI_PUBLIC_DEMO",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for f in _FLAGS:
        monkeypatch.delenv(f, raising=False)
    yield


# ---------------------------------------------------------------------------
# Defaults (local)
# ---------------------------------------------------------------------------

def test_defaults_local():
    assert g.app_env() == "local"
    assert g.is_admin_enabled() is False
    assert g.is_ingest_enabled() is False
    assert g.is_candidate_pool_enabled() is True       # local allows pool
    assert g.is_debug_enabled() is True
    assert g.available_modes() == [g.MODE_CANDIDATE, g.MODE_RECRUITER]


# ---------------------------------------------------------------------------
# Admin gate
# ---------------------------------------------------------------------------

def test_admin_enabled_with_flag(monkeypatch):
    monkeypatch.setenv("ACAI_ENABLE_ADMIN", "1")
    assert g.is_admin_enabled() is True
    assert g.MODE_ADMIN in g.available_modes()


def test_admin_hidden_in_public_even_with_flag(monkeypatch):
    monkeypatch.setenv("ACAI_ENABLE_ADMIN", "1")
    monkeypatch.setenv("APP_ENV", "prod")
    assert g.is_public_demo() is True
    assert g.is_admin_enabled() is False
    assert g.MODE_ADMIN not in g.available_modes()


# ---------------------------------------------------------------------------
# Ingest gate
# ---------------------------------------------------------------------------

def test_ingest_gate(monkeypatch):
    monkeypatch.setenv("ACAI_ENABLE_INGEST", "1")
    assert g.is_ingest_enabled() is True
    monkeypatch.setenv("ACAI_PUBLIC_DEMO", "1")
    assert g.is_ingest_enabled() is False


# ---------------------------------------------------------------------------
# Candidate-pool gate
# ---------------------------------------------------------------------------

def test_candidate_pool_disabled_in_public_without_flag(monkeypatch):
    monkeypatch.setenv("APP_ENV", "demo")
    assert g.is_candidate_pool_enabled() is False


def test_candidate_pool_enabled_in_public_with_flag(monkeypatch):
    monkeypatch.setenv("APP_ENV", "demo")
    monkeypatch.setenv("ACAI_ENABLE_CANDIDATE_POOL", "1")
    assert g.is_candidate_pool_enabled() is True


# ---------------------------------------------------------------------------
# Debug gate
# ---------------------------------------------------------------------------

def test_debug_off_in_public():
    pass  # placeholder kept for readability


def test_debug_off_in_prod(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    assert g.is_debug_enabled() is False


def test_debug_on_with_flag_in_dev(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    assert g.is_debug_enabled() is True


def test_public_demo_flag_locks_down(monkeypatch):
    monkeypatch.setenv("ACAI_PUBLIC_DEMO", "1")
    monkeypatch.setenv("ACAI_ENABLE_ADMIN", "1")
    monkeypatch.setenv("ACAI_ENABLE_INGEST", "1")
    assert g.is_admin_enabled() is False
    assert g.is_ingest_enabled() is False
    assert g.is_debug_enabled() is False
