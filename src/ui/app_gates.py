# src/ui/app_gates.py
#
# Phase 22 — runtime feature gates for public/demo safety.
#
# Single source of truth for which surfaces are available, driven by env:
#   APP_ENV               local | dev | demo | prod          (default: local)
#   ACAI_ENABLE_ADMIN     show Admin/Demo mode
#   ACAI_ENABLE_INGEST    show Private Data Ingest (also checked by data_ingest)
#   ACAI_ENABLE_CANDIDATE_POOL   allow Candidate Pool persistence
#   ACAI_DEBUG            show raw technical details
#   ACAI_PUBLIC_DEMO      hard public lockdown (admin/ingest/pool off)
#
# Pure, env-only, no Streamlit dependency → unit-testable.

from __future__ import annotations

import os

_TRUTHY = {"1", "true", "yes", "on"}
_VALID_ENVS = {"local", "dev", "demo", "prod"}

# Canonical mode labels (must match streamlit_app).
MODE_CANDIDATE = "Candidate"
MODE_RECRUITER = "Recruiter / HR"
MODE_ADMIN = "Admin · Demo"


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def app_env() -> str:
    env = os.environ.get("APP_ENV", "").strip().lower()
    return env if env in _VALID_ENVS else "local"


def is_public_demo() -> bool:
    """Hard public lockdown: explicit flag, or a demo/prod environment."""
    return _flag("ACAI_PUBLIC_DEMO") or app_env() in {"demo", "prod"}


def is_local_or_dev() -> bool:
    return app_env() in {"local", "dev"} and not _flag("ACAI_PUBLIC_DEMO")


# ---------------------------------------------------------------------------
# Feature gates
# ---------------------------------------------------------------------------

def is_admin_enabled() -> bool:
    """Admin/Demo is hidden unless explicitly enabled and not in public lockdown."""
    return _flag("ACAI_ENABLE_ADMIN") and not is_public_demo()


def is_ingest_enabled() -> bool:
    """Private ingest requires its flag and is never on in public lockdown."""
    return _flag("ACAI_ENABLE_INGEST") and not is_public_demo()


def is_candidate_pool_enabled() -> bool:
    """
    Candidate Pool persistence: explicit flag enables it; otherwise allowed only
    in local/dev. Disabled in public/demo/prod unless the flag is set.
    """
    if is_public_demo():
        return _flag("ACAI_ENABLE_CANDIDATE_POOL")
    if _flag("ACAI_ENABLE_CANDIDATE_POOL"):
        return True
    return is_local_or_dev()


def is_debug_enabled() -> bool:
    """Raw technical details only in local/dev or with ACAI_DEBUG=1 (never public)."""
    if is_public_demo():
        return False
    return is_local_or_dev() or _flag("ACAI_DEBUG")


def available_modes() -> list:
    """Modes to show in the workspace switcher."""
    modes = [MODE_CANDIDATE, MODE_RECRUITER]
    if is_admin_enabled():
        modes.append(MODE_ADMIN)
    return modes
