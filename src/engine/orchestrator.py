# src/engine/orchestrator.py
#
# MVP orchestration layer. Wires the existing backbone together:
#
#   document_loader → input_guardrail → adapters → (optional agents / fallbacks)
#                   → PayloadAssembler → output_guardrail → CanonicalAnalysisPayload
#
# Design contracts honoured here:
#   - Heavy agents are NEVER imported at module load. They are lazily imported
#     inside try/except blocks so a missing instructor/langchain/openai install
#     can never break `import src.engine.orchestrator`.
#   - No LLM call is attempted unless OPENAI_API_KEY is present (auto-detected),
#     and any agent import/dependency/API failure degrades to a deterministic
#     fallback rather than raising.
#   - The existing PayloadAssembler is used as-is (its NarrativeGenerator already
#     falls back deterministically when Gemini/langchain is unavailable), so no
#     change to payload_assembler.py or scoring.py is required.

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.engine.adapters import (
    MVP_SKILL_ALIASES,
    infer_seniority_from_years,
    jd_json_to_jd_entities,
    parsed_cv_to_cv_entities,
    semantic_output_to_canonical,
    skills_output_to_canonical,
)
from src.engine.payload_assembler import PayloadAssembler
from src.guardrails.input_guardrail import InputGuardrail, InputGuardrailResult, mask_pii
from src.guardrails.output_guardrail import OutputGuardrailResult, validate_payload
from src.preprocessing.document_loader import (
    jd_json_to_raw_text,
    load_jd_json,
    load_resume_text,
)
from src.schemas.canonical_payload import (
    AgentExecutionStatus,
    BiasAuditResult,
    CanonicalAnalysisPayload,
    CVEntities,
    EvaluationIntegrityRisk,
    GapSeverity,
    JDEntities,
    SemanticAnalysis,
    SkillCategory,
    SkillEntry,
    SkillMatchEntry,
    SkillMatchType,
    SkillsOntologyResult,
)

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]

# Google/Gemini embedding model for the alternate semantic provider.
# Configurable via GOOGLE_EMBEDDING_MODEL; defaults to the current text-only
# embedding model. The langchain-google client expects a "models/" prefix.
_DEFAULT_GOOGLE_EMBEDDING_MODEL = "gemini-embedding-001"


def google_embedding_model() -> str:
    """Resolves the Google embedding model name (env-overridable, prefixed)."""
    name = (os.environ.get("GOOGLE_EMBEDDING_MODEL") or _DEFAULT_GOOGLE_EMBEDDING_MODEL).strip()
    return name if name.startswith("models/") else f"models/{name}"

# Boundary-guarded patterns for the MVP skill list (reused for CV fallback).
_SKILL_PATTERNS = {
    canonical: [
        re.compile(r"(?<![a-z0-9])" + re.escape(alias.lower()) + r"(?![a-z0-9])")
        for alias in aliases
    ]
    for canonical, aliases in MVP_SKILL_ALIASES.items()
}

# Obvious natural-language keyword cues (English / Armenian / Russian).
_LANGUAGE_KEYWORDS = {
    "English": ["english", "անգլերեն", "английск"],
    "Armenian": ["armenian", "հայերեն", "армянск"],
    "Russian": ["russian", "ռուսերեն", "русск"],
    "French": ["french", "ֆրանսերեն", "французск"],
    "German": ["german", "գերմաներեն", "немецк"],
    "Spanish": ["spanish", "испанск"],
}

# Obvious domain cues → canonical domain slug.
_DOMAIN_KEYWORDS = {
    "fintech": ["fintech", "banking", "payments", "financial services"],
    "igaming": ["igaming", "betting", "gambling", "casino", "odds", "sportsbook"],
    "ecommerce": ["ecommerce", "e-commerce", "marketplace"],
    "healthcare": ["healthcare", "medtech", "clinical", "pharma"],
    "saas": ["saas", "b2b software", "cloud platform"],
    "data_analytics": ["data analytics", "business intelligence", "machine learning", "data science"],
    "telecom": ["telecom", "telecommunication"],
}

_EMAIL_OR_PHONE_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}|\+?\d[\d\s().\-]{6,}\d"
)


# ===========================================================================
# Public dataclasses
# ===========================================================================

@dataclass
class AnalysisRequest:
    cv_path: PathLike
    jd_path: PathLike
    language: str = "hy"
    seniority_context: str = "junior"


@dataclass
class AnalysisRunResult:
    success: bool
    payload: Optional[CanonicalAnalysisPayload] = None
    failure_reason: Optional[str] = None
    session_id: str = ""
    llm_used: bool = False
    phase1_statuses: Dict[str, str] = field(default_factory=dict)
    phase2_status: str = AgentExecutionStatus.FALLBACK.value
    agent_errors: Dict[str, str] = field(default_factory=dict)
    input_guardrail: Optional[InputGuardrailResult] = None
    output_guardrail: Optional[OutputGuardrailResult] = None
    # Which provider produced each signal: "openai" | "google" | "deterministic".
    provider_status: Dict[str, str] = field(default_factory=dict)


# ===========================================================================
# Orchestrator
# ===========================================================================

class AnalysisOrchestrator:
    """
    Drives one end-to-end analysis. LLM usage is opt-in and auto-detected from
    OPENAI_API_KEY unless `enable_llm` is set explicitly (tests force it False).
    """

    def __init__(self, enable_llm: Optional[bool] = None) -> None:
        if enable_llm is None:
            enable_llm = bool(os.environ.get("OPENAI_API_KEY"))
        self._llm_enabled = enable_llm

    # ── Sync / async entrypoints ───────────────────────────────────────────

    def run(self, request: AnalysisRequest) -> AnalysisRunResult:
        """Synchronous entrypoint. Drives the async core via asyncio.run."""
        return asyncio.run(self.arun(request))

    async def arun(self, request: AnalysisRequest) -> AnalysisRunResult:
        session_id = str(uuid.uuid4())
        start_ms = int(time.monotonic() * 1000)

        # ── Load inputs ────────────────────────────────────────────────────
        try:
            cv_text = load_resume_text(request.cv_path)
            jd_raw = load_jd_json(request.jd_path)
        except Exception as exc:  # FileNotFoundError, ValueError, JSON errors
            logger.error("Input loading failed: %s", exc)
            return AnalysisRunResult(
                success=False,
                failure_reason=f"Input loading failed: {exc}",
                session_id=session_id,
            )

        jd_text = jd_json_to_raw_text(jd_raw)

        # ── Input guardrail ────────────────────────────────────────────────
        ig = InputGuardrail().validate(cv_text, jd_text)
        if not ig.passed:
            return AnalysisRunResult(
                success=False,
                failure_reason=ig.rejection_reason,
                session_id=session_id,
                input_guardrail=ig,
            )

        masked_cv = ig.masked_cv_text
        masked_jd = ig.masked_jd_text

        # ── JD → JDEntities (deterministic, no LLM) ────────────────────────
        jd_for_adapter = {**jd_raw, "raw_text": masked_jd}
        jd_entities = jd_json_to_jd_entities(jd_for_adapter)

        # ── Phase 1 (agents if available, else deterministic fallbacks) ────
        statuses: Dict[str, AgentExecutionStatus] = {}
        errors: Dict[str, str] = {}
        provider_status: Dict[str, str] = {}

        cv_entities, parsed_cv = await self._resolve_cv(masked_cv, cv_text, session_id, statuses, errors)
        semantic = await self._resolve_semantic(
            parsed_cv, jd_entities, cv_entities, session_id, statuses, errors, provider_status,
        )
        skills = await self._resolve_skills(parsed_cv, jd_entities, cv_entities, session_id, statuses, errors)

        bias_audit = self._fallback_bias_audit()

        # ── Assemble payload via the existing PayloadAssembler ─────────────
        state: Dict[str, Any] = {
            "cv_text": masked_cv,
            "jd_text": masked_jd,
            "session_id": session_id,
            "language": request.language,
            "seniority_context": request.seniority_context,
            "analysis_start_time_ms": start_ms,
            "cv_entities": cv_entities,
            "jd_entities": jd_entities,
            "semantic_result": semantic,
            "skills_result": skills,
            "bias_audit_result": bias_audit,
            "phase1_statuses": statuses,
            "phase2_status": AgentExecutionStatus.FALLBACK,
            "agent_errors": errors,
            # Kill-switch: when False, the assembler must not call Gemini narratives.
            "enable_llm": self._llm_enabled,
        }

        try:
            payload = await PayloadAssembler().assemble(state)
        except Exception as exc:
            logger.exception("PayloadAssembler failed.")
            return AnalysisRunResult(
                success=False,
                failure_reason=f"Payload assembly failed: {exc}",
                session_id=session_id,
                llm_used=any(s == AgentExecutionStatus.SUCCESS for s in statuses.values()),
                phase1_statuses={k: v.value for k, v in statuses.items()},
                agent_errors=errors,
                input_guardrail=ig,
                provider_status=provider_status,
            )

        # ── Output guardrail ───────────────────────────────────────────────
        og = validate_payload(payload)
        self._reflect_output_guardrail(payload, og)

        return AnalysisRunResult(
            success=og.passed,
            payload=payload,
            failure_reason=None if og.passed else f"Output guardrail flags: {og.flags}",
            session_id=session_id,
            llm_used=any(s == AgentExecutionStatus.SUCCESS for s in statuses.values()),
            phase1_statuses={k: v.value for k, v in statuses.items()},
            phase2_status=AgentExecutionStatus.FALLBACK.value,
            agent_errors=errors,
            input_guardrail=ig,
            output_guardrail=og,
            provider_status=provider_status,
        )

    # ── Phase-1 resolvers ──────────────────────────────────────────────────

    async def _resolve_cv(
        self,
        masked_cv: str,
        original_cv: str,
        session_id: str,
        statuses: Dict[str, AgentExecutionStatus],
        errors: Dict[str, str],
    ):
        """Returns (cv_entities, parsed_cv_or_None)."""
        if self._llm_enabled:
            try:
                from src.agents.document_intelligence_agent import DocumentIntelligenceAgent
                agent = DocumentIntelligenceAgent()
                output = await agent.arun(masked_cv, session_id)
                parsed_cv = output.parsed_cv
                cv_entities = parsed_cv_to_cv_entities(parsed_cv)
                statuses["document_intelligence"] = AgentExecutionStatus.SUCCESS
                return cv_entities, parsed_cv
            except Exception as exc:
                logger.warning("DocumentIntelligenceAgent unavailable/failed (%s). Using fallback.", exc)
                errors["document_intelligence"] = str(exc)

        statuses["document_intelligence"] = AgentExecutionStatus.FALLBACK
        return self._fallback_cv_entities(masked_cv, original_cv), None

    async def _resolve_semantic(
        self, parsed_cv, jd_entities, cv_entities, session_id, statuses, errors, provider_status,
    ) -> SemanticAnalysis:
        """
        Provider fallback chain for semantic alignment:
          1) OpenAI embeddings (SemanticAlignmentAgent),
          2) Google/Gemini embeddings (if configured),
          3) deterministic skill-overlap fallback.
        Each step is gated/lazy so missing keys or libraries never raise.
        """
        # 1) OpenAI path (requires OPENAI_API_KEY + a parsed CV from the doc agent).
        if self._llm_enabled and parsed_cv is not None:
            try:
                from src.agents.semantic_alignment_agent import SemanticAlignmentAgent
                output = await SemanticAlignmentAgent().arun(parsed_cv, jd_entities, session_id)
                statuses["semantic_alignment"] = AgentExecutionStatus.SUCCESS
                provider_status["semantic_alignment"] = "openai"
                return semantic_output_to_canonical(output)
            except Exception as exc:
                logger.warning("OpenAI semantic alignment failed (%s). Trying alternates.", exc)
                errors["semantic_alignment"] = str(exc)

        # 2) Google/Gemini embedding path — ONLY when LLM use is enabled. With
        #    enable_llm=False this is skipped even if GOOGLE_API_KEY is present
        #    (deterministic kill-switch: no external provider calls in tests/demo).
        if self._llm_enabled:
            try:
                google_sem = await self._google_semantic(jd_entities, cv_entities)
                if google_sem is not None:
                    statuses["semantic_alignment"] = AgentExecutionStatus.SUCCESS
                    provider_status["semantic_alignment"] = "google"
                    return google_sem
            except Exception as exc:  # pragma: no cover - network/provider dependent
                logger.warning("Google semantic alignment failed (%s). Using deterministic fallback.", exc)
                errors["semantic_alignment_google"] = str(exc)

        # 3) Deterministic fallback.
        statuses["semantic_alignment"] = AgentExecutionStatus.FALLBACK
        provider_status["semantic_alignment"] = "deterministic"
        return self._fallback_semantic(cv_entities, jd_entities)

    async def _google_semantic(self, jd_entities, cv_entities) -> Optional[SemanticAnalysis]:
        """
        Best-effort semantic alignment via Google embeddings. Returns None when
        GOOGLE_API_KEY or the langchain-google library is unavailable (so the
        caller falls through to the deterministic path). Never makes a network
        call without an API key.
        """
        if not os.environ.get("GOOGLE_API_KEY"):
            return None
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            import numpy as np
        except Exception:
            return None

        cv_text = ", ".join(s.canonical_name for s in cv_entities.raw_skills) or "general technology"
        jd_text = ", ".join(
            s.canonical_name for s in (jd_entities.required_skills + jd_entities.preferred_skills)
        ) or "general technology"

        embedder = GoogleGenerativeAIEmbeddings(model=google_embedding_model())
        vectors = await asyncio.to_thread(embedder.embed_documents, [cv_text, jd_text])
        a, b = np.array(vectors[0]), np.array(vectors[1])
        denom = float(np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
        cosine = round(max(0.0, min(1.0, float(np.dot(a, b) / denom))), 4)

        base = self._fallback_semantic(cv_entities, jd_entities)
        return SemanticAnalysis(
            embedding_cosine_similarity=cosine,
            key_phrase_overlap_ratio=base.key_phrase_overlap_ratio,
            cv_unique_key_phrases=base.cv_unique_key_phrases,
            jd_unique_key_phrases=base.jd_unique_key_phrases,
            shared_key_phrases=base.shared_key_phrases,
            contextual_domain_alignment=base.contextual_domain_alignment,
        )

    async def _resolve_skills(
        self, parsed_cv, jd_entities, cv_entities, session_id, statuses, errors,
    ) -> SkillsOntologyResult:
        if self._llm_enabled and parsed_cv is not None:
            try:
                from src.agents.skills_ontology_agent import SkillsOntologyAgent
                output = await SkillsOntologyAgent().arun(parsed_cv, jd_entities, session_id)
                statuses["skills_ontology"] = AgentExecutionStatus.SUCCESS
                return skills_output_to_canonical(output)
            except Exception as exc:
                logger.warning("SkillsOntologyAgent unavailable/failed (%s). Using fallback.", exc)
                errors["skills_ontology"] = str(exc)

        statuses["skills_ontology"] = AgentExecutionStatus.FALLBACK
        return self._fallback_skills_result(cv_entities, jd_entities)

    # ── Deterministic fallbacks ────────────────────────────────────────────

    @staticmethod
    def _match_skill_names(text: str) -> List[str]:
        low = text.lower()
        found: List[str] = []
        for canonical, patterns in _SKILL_PATTERNS.items():
            if any(p.search(low) for p in patterns):
                found.append(canonical)
        return found

    def _fallback_cv_entities(self, masked_cv: str, original_cv: str) -> CVEntities:
        """Minimal-but-valid CVEntities built from the raw CV text, no LLM."""
        contact_present = bool(_EMAIL_OR_PHONE_RE.search(original_cv or ""))

        raw_skills = [
            SkillEntry(raw_name=name, canonical_name=name, category=SkillCategory.TECHNICAL)
            for name in self._match_skill_names(masked_cv)
        ]

        low = masked_cv.lower()
        languages = [
            lang for lang, cues in _LANGUAGE_KEYWORDS.items()
            if any(c in low for c in cues)
        ]
        domain_signals = [
            slug for slug, cues in _DOMAIN_KEYWORDS.items()
            if any(c in low for c in cues)
        ][:5]

        return CVEntities(
            masked_identifier="[CANDIDATE]",
            contact_info_present=contact_present,
            work_history=[],
            education=[],
            raw_skills=raw_skills,
            languages=languages,
            certifications=[],
            total_years_experience=0.0,
            inferred_seniority=infer_seniority_from_years(0.0, None),
            career_domain_signals=domain_signals,
        )

    @staticmethod
    def _fallback_semantic(cv_entities: CVEntities, jd_entities: JDEntities) -> SemanticAnalysis:
        cv_names = {s.canonical_name for s in cv_entities.raw_skills}
        jd_names = {s.canonical_name for s in jd_entities.required_skills}
        jd_names |= {s.canonical_name for s in jd_entities.preferred_skills}

        shared = cv_names & jd_names
        union = cv_names | jd_names
        overlap_ratio = round(len(shared) / max(len(jd_names), 1), 4)
        jaccard = round(len(shared) / len(union), 4) if union else 0.0

        jd_industry = (jd_entities.industry or "").lower().replace(" ", "_")
        cv_domains = {d.lower().replace(" ", "_") for d in cv_entities.career_domain_signals}
        if jd_industry and jd_industry in cv_domains:
            domain_alignment = 0.7
        elif cv_domains:
            domain_alignment = 0.4
        else:
            domain_alignment = 0.3

        return SemanticAnalysis(
            embedding_cosine_similarity=jaccard,
            key_phrase_overlap_ratio=overlap_ratio,
            cv_unique_key_phrases=sorted(cv_names - jd_names)[:10],
            jd_unique_key_phrases=sorted(jd_names - cv_names)[:10],
            shared_key_phrases=sorted(shared)[:10],
            contextual_domain_alignment=domain_alignment,
        )

    @staticmethod
    def _fallback_skills_result(cv_entities: CVEntities, jd_entities: JDEntities) -> SkillsOntologyResult:
        cv_names = {s.canonical_name.lower() for s in cv_entities.raw_skills}

        matched: List[SkillMatchEntry] = []
        missing_critical: List[SkillMatchEntry] = []
        for jd_skill in jd_entities.required_skills:
            if jd_skill.canonical_name.lower() in cv_names:
                matched.append(SkillMatchEntry(
                    skill_name=jd_skill.raw_name,
                    canonical_name=jd_skill.canonical_name,
                    match_type=SkillMatchType.MATCHED,
                    is_critical=True,
                ))
            else:
                missing_critical.append(SkillMatchEntry(
                    skill_name=jd_skill.raw_name,
                    canonical_name=jd_skill.canonical_name,
                    match_type=SkillMatchType.MISSING_CRITICAL,
                    is_critical=True,
                ))

        missing_preferred: List[SkillMatchEntry] = [
            SkillMatchEntry(
                skill_name=jd_skill.raw_name,
                canonical_name=jd_skill.canonical_name,
                match_type=SkillMatchType.MISSING_PREFERRED,
                is_critical=False,
            )
            for jd_skill in jd_entities.preferred_skills
            if jd_skill.canonical_name.lower() not in cv_names
        ]

        total_required = len(jd_entities.required_skills)
        matched_count = len(matched)
        critical_gap_count = len(missing_critical)
        coverage_ratio = round(matched_count / total_required, 4) if total_required > 0 else 0.0

        if total_required == 0:
            gap_severity = GapSeverity.NONE
        elif critical_gap_count >= 3:
            gap_severity = GapSeverity.CRITICAL
        elif critical_gap_count >= 1:
            gap_severity = GapSeverity.MODERATE
        else:
            gap_severity = GapSeverity.MINOR

        return SkillsOntologyResult(
            matched_skills=matched,
            missing_critical=missing_critical,
            missing_preferred=missing_preferred,
            transferable=[],
            total_required_skills=total_required,
            matched_count=matched_count,
            critical_gap_count=critical_gap_count,
            coverage_ratio=coverage_ratio,
            gap_severity=gap_severity,
        )

    @staticmethod
    def _fallback_bias_audit() -> BiasAuditResult:
        return BiasAuditResult(
            evaluation_integrity_risk=EvaluationIntegrityRisk.LOW,
            risk_rationale=(
                "MVP fallback audit: no automated high-risk bias indicators were "
                "evaluated in this phase."
            ),
            structured_interview_recommendations=[
                "Use the same structured rubric and scoring scale for every candidate.",
                "Ask identical core competency questions across all interviews.",
                "Base every assessment on job-relevant evidence only, not background signals.",
            ],
            emergent_scoring_bias_detected=False,
            jd_exclusionary_language_flagged=False,
        )

    @staticmethod
    def _reflect_output_guardrail(
        payload: CanonicalAnalysisPayload, og: OutputGuardrailResult,
    ) -> None:
        """Records the output-guardrail outcome into governance (best-effort)."""
        try:
            payload.governance.guardrail_output_passed = og.passed
            if og.flags:
                payload.governance.guardrail_output_flags = (
                    list(payload.governance.guardrail_output_flags) + og.flags
                )
            payload.governance.hallucination_flags = list(og.hallucination_flags)
        except Exception:  # pragma: no cover - never let bookkeeping break a run
            logger.debug("Could not reflect output guardrail into governance.", exc_info=True)


# ===========================================================================
# Module-level convenience
# ===========================================================================

def run_analysis(
    cv_path: PathLike,
    jd_path: PathLike,
    language: str = "hy",
    seniority_context: str = "junior",
) -> AnalysisRunResult:
    """Convenience wrapper: builds an orchestrator (LLM auto-detected) and runs."""
    request = AnalysisRequest(
        cv_path=cv_path,
        jd_path=jd_path,
        language=language,
        seniority_context=seniority_context,
    )
    return AnalysisOrchestrator().run(request)
