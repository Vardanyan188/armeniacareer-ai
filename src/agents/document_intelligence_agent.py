# src/agents/document_intelligence.py
#
# Document Intelligence Agent — Phase 1 of the Shared Analysis Engine.
#
# Orchestration pattern: instructor.from_openai() with Mode.TOOLS.
# instructor patches the OpenAI client to inject a tool_call definition
# derived directly from the Pydantic model's JSON schema, then validates
# the response against the model before returning it. This eliminates the
# need for a separate output parser and provides retry logic at the
# LLM-response level, not the application level.
#
# Fallback chain:
#   Attempt 1: V3 prompt (few-shot)   — production quality
#   Attempt 2: V2 prompt (structured) — if V3 fails Pydantic validation twice
#   Fallback:  create_fallback_cv_entities() — empty-safe defaults
#
# The agent is intentionally narrow: it extracts ONLY CVEntities and JDEntities.
# Scoring, semantic analysis, and ontology resolution are delegated to
# downstream agents. No scoring logic exists here.

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, Tuple

import instructor
from instructor.exceptions import InstructorRetryException
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.schemas.cv_parsing_schema import ParsedCVOutput
from src.preprocessing.cv_preprocessor import CVTextPreprocessor, format_budget_report
from src.prompts.document_intelligence.v3_fewshot import (
    SYSTEM_PROMPT as V3_SYSTEM,
    USER_TEMPLATE as V3_USER,
    FEW_SHOT_EXAMPLES as V3_EXAMPLES,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Agent Configuration
# ---------------------------------------------------------------------------

# Model identifiers
_EXTRACTION_MODEL = "gpt-4.1-mini"

# instructor retry configuration:
# Max retries that instructor internally attempts before raising InstructorRetryException.
# Each retry re-calls the LLM with the validation error appended to the context,
# allowing the model to self-correct its JSON output.
_INSTRUCTOR_MAX_RETRIES = 3

# Application-level retry: wraps the entire agent invocation on API errors.
_API_RETRY_MAX_ATTEMPTS = 2
_API_RETRY_WAIT_MIN_SECONDS = 1
_API_RETRY_WAIT_MAX_SECONDS = 4

# Token budget for the extraction prompt
# System + examples ≈ 2,200 tokens; CV text budget: 4,000 tokens; output: ~1,800 tokens
# Total: stays within 8,000 tokens → well within gpt-4.1-mini 128k context
_MAX_COMPLETION_TOKENS = 2_500


# ---------------------------------------------------------------------------
# Agent Output Container
# ---------------------------------------------------------------------------

class DocumentIntelligenceOutput(BaseModel):
    """
    Container for the Document Intelligence Agent's extraction results.
    Bundles the parsed CV with preprocessing metadata for downstream use
    in the PayloadAssembler and Evaluation Tab.
    """
    parsed_cv: ParsedCVOutput
    preprocessing_report: str     # Human-readable budget/anomaly report
    preprocessing_confidence: float
    prompt_version_used: str
    extraction_latency_ms: int
    instructor_retry_count: int   # Number of internal instructor retries consumed


# ---------------------------------------------------------------------------
# Fallback Factory
# ---------------------------------------------------------------------------

def create_fallback_cv_output(session_id: str, reason: str) -> ParsedCVOutput:
    """
    Returns a structurally valid but empty ParsedCVOutput for use when
    the Document Intelligence Agent fails all retry attempts.
    Annotates format_quality.extraction_anomalies with the failure reason.
    """
    from src.schemas.cv_parsing_schema import (
        CVFormatQualitySignals, SeniorityLevel, CVFormatType, ScriptType
    )
    logger.error(
        "DocumentIntelligenceAgent fallback activated for session %s. Reason: %s",
        session_id, reason,
    )
    return ParsedCVOutput(
        masked_identifier="[CANDIDATE]",
        contact_info_present=False,
        work_history=[],
        education=[],
        skills=[],
        language_proficiencies=[],
        certifications=[],
        projects=[],
        total_years_experience=0.0,
        inferred_seniority=SeniorityLevel.JUNIOR,
        career_domain_signals=[],
        professional_summary=None,
        format_quality=CVFormatQualitySignals(
            detected_format_type=CVFormatType.UNKNOWN,
            primary_script=ScriptType.UNKNOWN,
            detected_languages=[],
            section_headers_found=[],
            has_experience_section=False,
            has_education_section=False,
            has_skills_section=False,
            extraction_anomalies=[f"agent_failure:{reason[:80]}"],
            preprocessing_confidence=0.0,
        ),
        section_extraction_confidence={
            k: 0.0 for k in
            ["work_history", "education", "skills", "languages", "certifications", "projects"]
        },
        extraction_notes=[f"Fallback activated: {reason[:200]}"],
    )


# ---------------------------------------------------------------------------
# Core Agent
# ---------------------------------------------------------------------------

class DocumentIntelligenceAgent:
    """
    Extracts structured CV entities from preprocessed text using instructor-backed
    tool-calling against gpt-4.1-mini. Produces a ParsedCVOutput Pydantic object.

    The agent maintains a single AsyncOpenAI client and a single instructor-patched
    client as instance attributes, making it safe to reuse across Streamlit reruns
    within the same server process (clients are not per-session).
    """

    def __init__(self, prompt_version: str = "v3"):
        self._raw_client = AsyncOpenAI()
        # Patch the raw client with instructor in TOOLS mode.
        # Mode.TOOLS uses OpenAI's function/tool calling interface rather than
        # JSON mode, which provides more reliable schema adherence because the
        # model's function-call decoder enforces structure independently of the
        # generation sampler.
        self._client = instructor.from_openai(
            self._raw_client,
            mode=instructor.Mode.TOOLS,
        )
        self._preprocessor = CVTextPreprocessor()
        self._prompt_version = prompt_version

    # -----------------------------------------------------------------------
    # Public Async Interface
    # -----------------------------------------------------------------------

    async def arun(
        self,
        cv_text: str,
        session_id: str,
    ) -> DocumentIntelligenceOutput:
        """
        Full pipeline: preprocess → extract → validate → return.

        Args:
            cv_text: Raw (but PII-masked) CV text from the guardrail agent.
            session_id: Session identifier for audit logging.

        Returns:
            DocumentIntelligenceOutput with parsed_cv and extraction metadata.

        Raises:
            Exception: Only if both prompt versions fail AND fallback is disabled.
            In normal operation, always returns a result (using fallback if necessary).
        """
        start_ms = int(time.monotonic() * 1000)

        # Pass 1: Preprocess
        preprocessing_result = await self._preprocessor.preprocess_async(cv_text)
        budget_report = format_budget_report(preprocessing_result)

        logger.info(
            "[%s] Preprocessing complete: %d→%d chars, script=%s, languages=%s, "
            "confidence=%.2f, anomalies=%s",
            session_id,
            preprocessing_result.total_input_chars,
            preprocessing_result.total_output_chars,
            preprocessing_result.primary_script,
            preprocessing_result.detected_languages,
            preprocessing_result.preprocessing_confidence,
            preprocessing_result.anomalies,
        )

        # Pass 2: LLM Extraction with retry cascade
        parsed_cv, used_version, retry_count = await self._extract_with_retry_cascade(
            cleaned_cv_text=preprocessing_result.cleaned_text,
            session_id=session_id,
        )

        # Pass 3: Backfill preprocessing metadata into format_quality
        # (Some format_quality fields require only regex analysis — done in preprocessor.
        #  Others require semantic understanding — done by LLM. We merge here.)
        parsed_cv = self._merge_preprocessing_signals(parsed_cv, preprocessing_result)

        end_ms = int(time.monotonic() * 1000)

        return DocumentIntelligenceOutput(
            parsed_cv=parsed_cv,
            preprocessing_report=budget_report,
            preprocessing_confidence=preprocessing_result.preprocessing_confidence,
            prompt_version_used=used_version,
            extraction_latency_ms=end_ms - start_ms,
            instructor_retry_count=retry_count,
        )

    # -----------------------------------------------------------------------
    # Extraction with Retry Cascade
    # -----------------------------------------------------------------------

    async def _extract_with_retry_cascade(
        self,
        cleaned_cv_text: str,
        session_id: str,
    ) -> Tuple[ParsedCVOutput, str, int]:
        """
        Attempts extraction with V3 (production) prompt first.
        Falls back to V2 (structured) if V3 fails instructor validation.
        Returns (parsed_output, version_used, total_retry_count).
        """
        # Attempt 1: V3 few-shot prompt
        try:
            result, retry_count = await self._call_instructor(
                system_prompt=self._build_system_prompt("v3"),
                user_message=self._build_user_message(cleaned_cv_text, "v3"),
                session_id=session_id,
            )
            return result, "v3", retry_count

        except InstructorRetryException as e:
            logger.warning(
                "[%s] V3 prompt failed instructor validation after %d retries. "
                "Falling back to V2. Last error: %s",
                session_id, _INSTRUCTOR_MAX_RETRIES, str(e)[:200],
            )

        # Attempt 2: V2 structured prompt
        try:
            result, retry_count = await self._call_instructor(
                system_prompt=self._build_system_prompt("v2"),
                user_message=self._build_user_message(cleaned_cv_text, "v2"),
                session_id=session_id,
            )
            return result, "v2", _INSTRUCTOR_MAX_RETRIES + retry_count

        except InstructorRetryException as e:
            logger.error(
                "[%s] V2 prompt also failed. Activating fallback. Error: %s",
                session_id, str(e)[:200],
            )

        # Fallback: empty-safe defaults
        fallback = create_fallback_cv_output(session_id, "all_prompt_versions_failed")
        return fallback, "fallback", _INSTRUCTOR_MAX_RETRIES * 2

    # -----------------------------------------------------------------------
    # instructor Client Call
    # -----------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type((TimeoutError, ConnectionError)),
        stop=stop_after_attempt(_API_RETRY_MAX_ATTEMPTS),
        wait=wait_exponential(
            min=_API_RETRY_WAIT_MIN_SECONDS,
            max=_API_RETRY_WAIT_MAX_SECONDS,
        ),
        reraise=True,
    )
    async def _call_instructor(
        self,
        system_prompt: str,
        user_message: str,
        session_id: str,
    ) -> Tuple[ParsedCVOutput, int]:
        """
        Calls the instructor-patched OpenAI client.

        instructor.client.chat.completions.create_with_completion() returns
        a (model_instance, raw_completion) tuple. The model_instance is the
        Pydantic-validated ParsedCVOutput. If validation fails, instructor
        automatically retries up to _INSTRUCTOR_MAX_RETRIES times, each time
        appending the ValidationError message to the conversation so the LLM
        can correct its output. If all retries are exhausted, InstructorRetryException
        is raised and caught by the retry cascade in _extract_with_retry_cascade.

        The retry_count is extracted from the raw completion's usage metadata
        to give the Evaluation Tab precise iteration tracking.
        """
        parsed_output, completion = await self._client.chat.completions.create_with_completion(
            model=_EXTRACTION_MODEL,
            response_model=ParsedCVOutput,
            max_retries=_INSTRUCTOR_MAX_RETRIES,
            max_tokens=_MAX_COMPLETION_TOKENS,
            temperature=0.0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
        )

        # Extract retry count from instructor's internal tracking
        # (instructor adds a 'n_retries' attribute to the completion object)
        retry_count = getattr(completion, "n_retries", 0)

        logger.debug(
            "[%s] instructor extraction complete. "
            "Prompt tokens: %d, Completion tokens: %d, Retries: %d",
            session_id,
            completion.usage.prompt_tokens if completion.usage else 0,
            completion.usage.completion_tokens if completion.usage else 0,
            retry_count,
        )

        return parsed_output, retry_count

    # -----------------------------------------------------------------------
    # Prompt Construction
    # -----------------------------------------------------------------------

    def _build_system_prompt(self, version: str) -> str:
        """Returns the system prompt for the specified version."""
        if version == "v3":
            return V3_SYSTEM
        elif version == "v2":
            return self._get_v2_system_prompt()
        return V3_SYSTEM

    def _build_user_message(self, cv_text: str, version: str) -> str:
        """
        Constructs the user message for the specified prompt version.
        For V3, the few-shot examples are embedded in the user message
        (not the system prompt) to maximize the model's attention on them
        as grounding context for the extraction task at hand.
        """
        if version == "v3":
            # For V3, format_instructions is handled by instructor automatically
            # (instructor injects the tool schema, so we don't need PydanticOutputParser).
            # The {format_instructions} placeholder in USER_TEMPLATE is replaced with
            # a concise instruction referencing the tool schema instructor already provides.
            format_note = (
                "Use the ParsedCVOutput tool schema provided to structure your extraction. "
                "The schema defines all required and optional fields."
            )
            user_msg = V3_USER.format(
                format_instructions=format_note,
                cv_text=cv_text,
            )
            # Prepend few-shot examples
            return V3_EXAMPLES + "\n\n" + user_msg

        elif version == "v2":
            return self._get_v2_user_message(cv_text)

        return self._get_v2_user_message(cv_text)

    # -----------------------------------------------------------------------
    # Preprocessing Metadata Merge
    # -----------------------------------------------------------------------

    @staticmethod
    def _merge_preprocessing_signals(
        parsed_cv: ParsedCVOutput,
        preprocess_result,
    ) -> ParsedCVOutput:
        """
        Backfills the preprocessor's signal data into the LLM-extracted output.
        The LLM fills format_quality fields that require semantic understanding.
        The preprocessor fills structural/statistical fields. This merge
        ensures the format_quality object contains data from both sources.

        Preprocessor-authoritative fields (overwrite LLM values):
          - extraction_anomalies (LLM cannot know what the preprocessor detected)
          - preprocessing_confidence (computed from anomaly count)
          - estimated_ats_compliance (computed from structural signals)

        LLM-authoritative fields (LLM knows the semantics):
          - detected_format_type, primary_script, detected_languages, section_headers_found
        """
        fq = parsed_cv.format_quality

        # Overwrite preprocessor-authoritative fields
        fq.extraction_anomalies = preprocess_result.anomalies
        fq.preprocessing_confidence = preprocess_result.preprocessing_confidence
        fq.section_headers_found = preprocess_result.section_headers_found

        # Backfill structural flags from preprocessor's section detection
        detected_sections = {sec.label for sec in preprocess_result.sections}
        fq.has_experience_section = "work_experience" in detected_sections
        fq.has_education_section = "education" in detected_sections
        fq.has_skills_section = "skills" in detected_sections
        fq.has_contact_section = "contact" in detected_sections
        fq.has_summary_section = "summary" in detected_sections

        # ATS compliance heuristic
        # Score: +0.20 for each of 5 structural section types present (max 1.0)
        # Penalty: -0.15 per severe anomaly (encoding_artifacts, garbled_armenian)
        ats_score = sum([
            0.20 if fq.has_experience_section else 0.0,
            0.20 if fq.has_education_section else 0.0,
            0.20 if fq.has_skills_section else 0.0,
            0.15 if fq.has_contact_section else 0.0,
            0.10 if fq.has_summary_section else 0.0,
        ])
        severe_anomaly_count = sum(
            1 for a in fq.extraction_anomalies
            if a in {"encoding_artifacts", "garbled_armenian", "mixed_rtl_ltr"}
        )
        ats_score = max(0.0, ats_score - severe_anomaly_count * 0.15)
        fq.estimated_ats_compliance = round(ats_score, 2)

        return parsed_cv

    # -----------------------------------------------------------------------
    # V2 Prompt (Fallback)
    # -----------------------------------------------------------------------

    @staticmethod
    def _get_v2_system_prompt() -> str:
        return (
            "You are a precision document parser for HR materials in the Armenian and CIS "
            "technology job market. Extract structured entity data exactly as specified by "
            "the ParsedCVOutput schema. Do not hallucinate. Do not infer absent information. "
            "Preserve original language in raw fields. Normalize to English in canonical fields. "
            "Report null for all absent fields."
        )

    @staticmethod
    def _get_v2_user_message(cv_text: str) -> str:
        return (
            "Use the ParsedCVOutput tool schema to extract all entities from the CV below.\n\n"
            "EXTRACTION RULES:\n"
            "1. total_years_experience: set to 0.0 (computed externally)\n"
            "2. duration_months: set to null in all entries (computed externally)\n"
            "3. Skills: deduplicate by canonical_name + category pair\n"
            "4. PII: replace any unmasked name/email/phone with [REDACTED]\n"
            "5. section_extraction_confidence: score below 1.0 for ambiguous sections\n\n"
            f"CV TEXT:\n{cv_text}"
        )
