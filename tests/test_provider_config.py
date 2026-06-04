# tests/test_provider_config.py
#
# Local AI provider configuration / stability. Pure env + mocked provider paths.
# NO real API calls, NO network, NO real keys (placeholders only).

import json

import pytest

from src.engine.orchestrator import (
    AnalysisOrchestrator,
    AnalysisRequest,
    gemini_api_key,
    is_public_demo,
    openai_api_key,
    preferred_provider,
    provider_availability,
    provider_error_category,
    resolve_llm_enabled,
    safe_provider_status,
)

# Placeholder (clearly fake) key values — never real secrets.
_FAKE = "test-not-a-real-key"

_PROVIDER_FLAGS = [
    "APP_ENV", "ACAI_PUBLIC_DEMO", "ACAI_ENABLE_LLM", "ACAI_LLM_PROVIDER",
    "OPENAI_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for f in _PROVIDER_FLAGS:
        monkeypatch.delenv(f, raising=False)
    yield


def _write_inputs(tmp_path):
    cv = tmp_path / "cv.txt"
    cv.write_text(
        "Software engineer experienced in Python and Docker. "
        "English speaker. Contact: dev@example.com",
        encoding="utf-8",
    )
    jd = tmp_path / "jd.json"
    jd.write_text(json.dumps({
        "jd_id": "JD_TEST_PROV",
        "role_title": "Backend Engineer",
        "company_name": "Acme",
        "industry": "fintech",
        "geography": "Armenia",
        "required_experience_years": 3.0,
        "required_education_level": "Bachelor",
        "meta": {"employment_type": "Full-time"},
        "raw_text": "Necessary skills:\nPython, Docker and PostgreSQL are required.\n",
    }, ensure_ascii=False), encoding="utf-8")
    return str(cv), str(jd)


# ---------------------------------------------------------------------------
# 1) local mode + no keys → deterministic fallback
# ---------------------------------------------------------------------------

def test_local_no_keys_disables_llm(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("ACAI_ENABLE_LLM", "1")  # opted in, but no keys
    assert resolve_llm_enabled() is False
    assert provider_availability() == {"gemini": False, "openai": False}


def test_local_enable_flag_unset_disables_llm(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("GOOGLE_API_KEY", _FAKE)  # key present but not opted in
    assert resolve_llm_enabled() is False


# ---------------------------------------------------------------------------
# 2) local + GOOGLE_API_KEY → Gemini availability detected
# ---------------------------------------------------------------------------

def test_local_google_key_enables_gemini(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("ACAI_ENABLE_LLM", "1")
    monkeypatch.setenv("GOOGLE_API_KEY", _FAKE)
    assert resolve_llm_enabled() is True
    assert provider_availability()["gemini"] is True
    assert gemini_api_key() == _FAKE


# ---------------------------------------------------------------------------
# 3) local + GEMINI_API_KEY → Gemini availability detected (alias support)
# ---------------------------------------------------------------------------

def test_local_gemini_key_alias_enables_gemini(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("ACAI_ENABLE_LLM", "1")
    monkeypatch.setenv("GEMINI_API_KEY", _FAKE)
    assert resolve_llm_enabled() is True
    assert provider_availability()["gemini"] is True
    assert gemini_api_key() == _FAKE


# ---------------------------------------------------------------------------
# 4) local + OPENAI_API_KEY → OpenAI availability detected
# ---------------------------------------------------------------------------

def test_local_openai_key_enables_openai(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("ACAI_ENABLE_LLM", "1")
    monkeypatch.setenv("OPENAI_API_KEY", _FAKE)
    assert resolve_llm_enabled() is True
    assert provider_availability()["openai"] is True
    assert openai_api_key() == _FAKE


# ---------------------------------------------------------------------------
# 5) demo mode + keys present → provider disabled (keys ignored)
# ---------------------------------------------------------------------------

def test_public_demo_ignores_keys(monkeypatch):
    monkeypatch.setenv("ACAI_PUBLIC_DEMO", "1")
    monkeypatch.setenv("ACAI_ENABLE_LLM", "1")
    monkeypatch.setenv("GOOGLE_API_KEY", _FAKE)
    monkeypatch.setenv("OPENAI_API_KEY", _FAKE)
    assert is_public_demo() is True
    assert resolve_llm_enabled() is False
    assert provider_availability() == {"gemini": False, "openai": False}
    status = safe_provider_status()
    assert status["enabled"] is False
    assert status["error_category"] == "disabled_by_public_demo"


def test_demo_env_value_locks_down(monkeypatch):
    monkeypatch.setenv("APP_ENV", "demo")
    monkeypatch.setenv("ACAI_ENABLE_LLM", "1")
    monkeypatch.setenv("GEMINI_API_KEY", _FAKE)
    assert resolve_llm_enabled() is False


# ---------------------------------------------------------------------------
# Provider preference (ACAI_LLM_PROVIDER)
# ---------------------------------------------------------------------------

def test_preferred_provider_default_and_values(monkeypatch):
    assert preferred_provider() == "auto"
    monkeypatch.setenv("ACAI_LLM_PROVIDER", "gemini")
    assert preferred_provider() == "gemini"
    monkeypatch.setenv("ACAI_LLM_PROVIDER", "openai")
    assert preferred_provider() == "openai"
    monkeypatch.setenv("ACAI_LLM_PROVIDER", "nonsense")
    assert preferred_provider() == "auto"


def test_gemini_preference_skips_openai_agents(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("ACAI_ENABLE_LLM", "1")
    monkeypatch.setenv("ACAI_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("OPENAI_API_KEY", _FAKE)
    monkeypatch.setenv("GOOGLE_API_KEY", _FAKE)
    orch = AnalysisOrchestrator()  # resolver enables LLM
    assert orch._openai_active() is False   # deselected by preference
    assert orch._gemini_active() is True


# ---------------------------------------------------------------------------
# 6) provider exception → safe fallback (no crash)
# ---------------------------------------------------------------------------

def test_provider_exception_falls_back_safely(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("ACAI_ENABLE_LLM", "1")
    monkeypatch.setenv("ACAI_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", _FAKE)

    async def _boom(self, jd_entities, cv_entities):
        raise RuntimeError("quota exceeded for project (429)")

    monkeypatch.setattr(AnalysisOrchestrator, "_google_semantic", _boom)

    cv, jd = _write_inputs(tmp_path)
    res = AnalysisOrchestrator().run(AnalysisRequest(cv, jd))
    assert res.success is True                       # no crash
    assert res.provider_status.get("semantic_alignment") == "deterministic"


def test_enable_llm_without_keys_does_not_crash(monkeypatch, tmp_path):
    # Forcing enable_llm=True with no keys must still produce a deterministic run.
    cv, jd = _write_inputs(tmp_path)
    res = AnalysisOrchestrator(enable_llm=True).run(AnalysisRequest(cv, jd))
    assert res.success is True
    assert res.provider_status.get("semantic_alignment") == "deterministic"


# ---------------------------------------------------------------------------
# 7-9) sanitized status: no raw error leak, no key leak, category tokens only
# ---------------------------------------------------------------------------

_VALID_CATEGORIES = {
    "missing_key", "auth_failed", "quota_or_rate_limit", "timeout",
    "provider_error", "disabled_by_public_demo", None,
}


def test_error_category_tokens():
    assert provider_error_category("Missing API key") == "missing_key"
    assert provider_error_category("429 quota exceeded / rate limit") == "quota_or_rate_limit"
    assert provider_error_category("401 Unauthorized: invalid api key") in {"auth_failed", "missing_key"}
    assert provider_error_category("Connection timed out") == "timeout"
    assert provider_error_category("something odd happened") == "provider_error"


def test_safe_provider_status_does_not_leak_raw_error_or_key(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("ACAI_ENABLE_LLM", "1")
    monkeypatch.setenv("GOOGLE_API_KEY", _FAKE)

    class _Result:
        provider_status = {"semantic_alignment": "deterministic"}
        agent_errors = {
            "semantic_alignment_google": f"401 Unauthorized using key {_FAKE} at /home/u/.env",
        }

    status = safe_provider_status(_Result())
    blob = json.dumps(status)
    assert _FAKE not in blob                 # no key leak
    assert "/home/u/.env" not in blob        # no path leak
    assert "401" not in blob                 # no raw error leak
    assert status["error_category"] in _VALID_CATEGORIES
    assert status["fallback_active"] is True


def test_safe_provider_status_reports_selected_provider():
    class _Result:
        provider_status = {"semantic_alignment": "google"}
        agent_errors = {}

    status = safe_provider_status(_Result())
    assert status["selected"] == "gemini"
    assert status["fallback_active"] is False
    assert status["error_category"] is None


# ---------------------------------------------------------------------------
# 10) full app import works
# ---------------------------------------------------------------------------

def test_streamlit_app_imports_cleanly():
    import importlib
    import streamlit_app
    importlib.reload(streamlit_app)
    assert streamlit_app is not None
