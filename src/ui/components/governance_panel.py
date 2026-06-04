# src/ui/components/governance_panel.py
#
# Governance / fallback status panel. Reads the AnalysisRunResult and the
# payload's governance layer. No LLM, no PII.

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from src.engine.audit_log import sanitize_error
from src.ui.app_gates import is_debug_enabled


def _label(value: Any) -> str:
    return str(getattr(value, "value", value))


_MODEL_ACCESS_HINTS = (
    "model", "access", "permission", "not found", "embedding", "401", "403",
    "unauthorized", "forbidden", "does not have access", "project",
)


def _looks_like_model_access_error(message: str) -> bool:
    low = (message or "").lower()
    return any(hint in low for hint in _MODEL_ACCESS_HINTS)


def _llm_status(result: Any) -> str:
    """
    Infers LLM usage without changing the orchestrator:
      - succeeded → "Used"
      - errors recorded → it was attempted but fell back
      - otherwise → deterministic fallback (not attempted, e.g. no API key)
    """
    if getattr(result, "llm_used", False):
        return "Used (live agents)"
    if getattr(result, "agent_errors", None):
        return "Attempted, fell back"
    return "Not attempted (deterministic fallback)"


def render_governance_panel(result: Any) -> None:
    payload = result.payload
    gov = payload.governance

    c1, c2, c3 = st.columns(3)
    c1.metric("LLM", _llm_status(result))
    input_passed = result.input_guardrail.passed if result.input_guardrail else True
    c2.metric("Input guardrail", "Passed" if input_passed else "Rejected")
    output_passed = result.output_guardrail.passed if result.output_guardrail else gov.guardrail_output_passed
    c3.metric("Output guardrail", "Passed" if output_passed else "Flagged")

    st.markdown("**Phase 1 agent status**")
    phase1 = {k: _label(v) for k, v in gov.phase1_agent_status.items()}
    st.dataframe(
        pd.DataFrame({"status": list(phase1.values())}, index=list(phase1.keys())),
        use_container_width=True,
    )
    st.markdown(f"**Phase 2 (bias & safety) status:** {_label(gov.phase2_agent_status)}")

    # ── Fallback diagnostics ───────────────────────────────────────────────
    fell_back = [name for name, status in phase1.items() if status == "fallback"]
    if _label(gov.phase2_agent_status) == "fallback":
        fell_back.append("bias_safety (phase 2)")
    if fell_back:
        st.markdown("**Phases on fallback:** " + ", ".join(fell_back))

    agent_errors = getattr(result, "agent_errors", None) or {}
    provider_status = getattr(result, "provider_status", None) or {}
    sem_provider = provider_status.get("semantic_alignment")
    sem_err = agent_errors.get("semantic_alignment")
    sem_google_err = agent_errors.get("semantic_alignment_google")

    # Clean, provider-aware semantic-alignment summary.
    if sem_provider == "openai":
        st.success("Semantic alignment: OpenAI embeddings used.")
    elif sem_provider == "google":
        st.info(
            "Semantic alignment: OpenAI embeddings unavailable — alternate provider "
            "(Google) was used."
        )
    elif sem_provider == "deterministic" or phase1.get("semantic_alignment") == "fallback":
        if sem_err and _looks_like_model_access_error(sem_err):
            st.info(
                "Semantic alignment: OpenAI embedding model unavailable for this API "
                "project; deterministic semantic fallback was used."
            )
        elif sem_err or sem_google_err:
            st.info("Semantic alignment: deterministic fallback was used.")
        else:
            st.info(
                "Semantic alignment: deterministic fallback was used "
                "(no live provider was attempted)."
            )
    # Technical details are SANITIZED to a category and shown only in debug
    # (local/dev or ACAI_DEBUG=1) — never raw provider strings/paths/secrets.
    _semantic_keys = {"semantic_alignment", "semantic_alignment_google"}
    other_errors = {k: v for k, v in agent_errors.items() if k not in _semantic_keys}
    if is_debug_enabled():
        if sem_err or sem_google_err:
            with st.expander("Technical details (debug)"):
                if sem_err:
                    st.caption(f"Semantic (OpenAI): {sanitize_error(sem_err)}")
                if sem_google_err:
                    st.caption(f"Semantic (Google): {sanitize_error(sem_google_err)}")
        if other_errors:
            with st.expander("Other agent issues (debug)"):
                for agent, message in other_errors.items():
                    st.caption(f"• {agent}: {sanitize_error(message)}")
    elif sem_err or sem_google_err or other_errors:
        st.caption("Some steps used a fallback. Technical details are hidden in this environment.")
    elif fell_back and not agent_errors:
        st.caption(
            "Fallback was deterministic (no live models attempted, "
            "e.g. no API key configured)."
        )

    flags = list(gov.guardrail_output_flags or [])
    halluc = list(gov.hallucination_flags or [])
    st.markdown(f"**Output / fallback flags:** {', '.join(flags) if flags else 'none'}")
    st.markdown(f"**Hallucination flags:** {', '.join(halluc) if halluc else 'none'}")

    st.markdown(
        f"**Analysis completeness:** {payload.analysis_completeness_score:.2f} "
        f"| **Overall confidence:** {payload.overall_analysis_confidence:.2f}"
    )

    if gov.total_processing_time_ms is not None:
        st.caption(f"Assembly processing time: {gov.total_processing_time_ms} ms")

    from src.ui.components.export_panel import render_governance_export
    render_governance_export(result)
