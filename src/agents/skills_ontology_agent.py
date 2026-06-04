# src/agents/skills_ontology_agent.py
#
# SkillsOntologyAgent — Phase 1 Parallel Agent
#
# Architectural position:
#   Executed concurrently with SemanticAlignmentAgent and DocumentIntelligenceAgent
#   via asyncio.gather in node_phase1_parallel (src/engine/orchestrator.py).
#
# Input contract:
#   - parsed_cv: ParsedCVOutput — validated structured CV entity object.
#     The agent operates exclusively on parsed_cv.skills (List[ParsedSkillEntry]).
#   - jd_entities: JDEntities — validated job description entity object.
#     The agent uses jd_entities.required_skills and jd_entities.preferred_skills
#     (both List[SkillEntry]).
#
# Three-Stage Matching Pipeline:
#
#   STAGE 1 — Exact Canonical Match (deterministic, no LLM)
#     For each JD skill, check if its canonical_name exists verbatim in the CV
#     skill pool (case-insensitive). This is the lowest-cost, highest-confidence
#     match type.
#
#   STAGE 2 — Functional Equivalence Group Match (deterministic, no LLM)
#     For each JD skill not resolved in Stage 1, check if it belongs to a
#     functional equivalence group that also contains any CV skill. Groups
#     represent clusters of technologies with substantial functional overlap
#     (e.g., all relational SQL databases, all Python web frameworks).
#     Transfer confidence is pre-assigned per group at group-definition time.
#
#   STAGE 3 — LLM Transferability Assessment (only for Stage 1+2 residuals)
#     Only unresolved JD skills reach this stage. The LLM receives the
#     unresolved skill names and the full CV canonical skill pool and assesses
#     non-obvious functional transferability. The LLM never re-assesses
#     skills resolved in Stages 1 or 2.
#
# Gap Classification Logic:
#   After all three stages, JD required skills fall into one of four buckets:
#     matched:           Resolved in Stage 1 (exact match)
#     transferable:      Resolved in Stage 2 (synonym) or Stage 3 (LLM, confidence ≥ 0.55)
#     missing_critical:  Required skill, not resolved in any stage
#     missing_preferred: Preferred skill, not resolved in any stage
#
# Coverage ratio:
#   = (matched + transferable weighted by transfer_confidence) / total_required
#   Note: "matched" skills contribute 1.0 to the numerator. Transferable skills
#   contribute their transfer_confidence (0.55–1.0). This weighted formulation
#   more accurately represents the candidate's actual readiness level than a
#   binary matched/unmatched count.

from __future__ import annotations

import json
import logging
import time
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, field_validator, model_validator

from src.schemas.canonical_payload import (
    GapSeverity,
    JDEntities,
    SkillCategory,
    SkillEntry,
    SkillMatchEntry,
    SkillMatchType,
    SkillsOntologyResult,
)
from src.schemas.cv_parsing_schema import ParsedCVOutput, ParsedSkillEntry
from src.prompts.skills_ontology.v3_fewshot import (
    SYSTEM_PROMPT,
    FEW_SHOT_EXAMPLES,
    USER_TEMPLATE,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Functional Equivalence Groups
#
# Each group is a frozenset of canonical skill names that share substantial
# functional overlap. The group_transfer_confidence is the default transfer
# confidence assigned when a JD skill is matched via this group.
#
# Groups are ordered from highest to lowest inter-group similarity
# (same-paradigm first, cross-paradigm last within similar domains).
#
# Maintenance note: add new technologies to the correct group as the CIS
# tech market evolves. Do not create single-element groups — they provide
# no classification value over exact matching.
# ─────────────────────────────────────────────────────────────────────────────

class _EquivalenceGroup:
    __slots__ = ("members", "transfer_confidence", "rationale_template")

    def __init__(
        self,
        members: FrozenSet[str],
        transfer_confidence: float,
        rationale_template: str,
    ) -> None:
        self.members = members
        self.transfer_confidence = transfer_confidence
        self.rationale_template = rationale_template


_EQUIVALENCE_GROUPS: List[_EquivalenceGroup] = [
    # ── Relational / OLTP databases ──────────────────────────────────────────
    _EquivalenceGroup(
        members=frozenset({
            "PostgreSQL", "MySQL", "MariaDB", "SQLite",
            "MSSQL", "SQL Server", "OracleDB", "Oracle Database",
        }),
        transfer_confidence=0.82,
        rationale_template=(
            "Both are relational SQL databases with compatible query paradigms; "
            "schema design and query optimization skills transfer directly."
        ),
    ),
    # ── Analytical / columnar stores ─────────────────────────────────────────
    _EquivalenceGroup(
        members=frozenset({
            "ClickHouse", "Redshift", "BigQuery", "Snowflake",
            "DuckDB", "Vertica", "Apache Hive", "Druid",
        }),
        transfer_confidence=0.71,
        rationale_template=(
            "Both are columnar analytical stores with SQL interfaces; "
            "aggregation query patterns and denormalized schema designs transfer, "
            "though storage engine internals differ."
        ),
    ),
    # ── NoSQL document stores ─────────────────────────────────────────────────
    _EquivalenceGroup(
        members=frozenset({
            "MongoDB", "CouchDB", "Firestore", "RavenDB", "Couchbase",
        }),
        transfer_confidence=0.76,
        rationale_template=(
            "Both are document-oriented NoSQL stores; JSON document modeling, "
            "indexing strategy, and aggregation pipeline concepts transfer."
        ),
    ),
    # ── Key-value / in-memory stores ──────────────────────────────────────────
    _EquivalenceGroup(
        members=frozenset({
            "Redis", "Memcached", "KeyDB", "Valkey",
        }),
        transfer_confidence=0.80,
        rationale_template=(
            "Both are in-memory key-value caches; TTL management, eviction policies, "
            "and client library usage patterns transfer directly."
        ),
    ),
    # ── Python web frameworks ────────────────────────────────────────────────
    _EquivalenceGroup(
        members=frozenset({
            "FastAPI", "Flask", "Django", "Tornado", "Sanic", "Litestar", "Starlette",
        }),
        transfer_confidence=0.78,
        rationale_template=(
            "Both are Python web frameworks; routing, middleware, ORM integration, "
            "and request/response lifecycle concepts transfer across frameworks."
        ),
    ),
    # ── JavaScript / TypeScript frontend frameworks ───────────────────────────
    _EquivalenceGroup(
        members=frozenset({
            "React", "React.js", "ReactJS",
            "Vue", "Vue.js", "VueJS",
            "Angular", "AngularJS",
            "Svelte", "SolidJS",
        }),
        transfer_confidence=0.68,
        rationale_template=(
            "Both are component-based frontend frameworks; component lifecycle, "
            "state management patterns, and virtual DOM concepts transfer, "
            "though framework-specific API syntax requires ramp-up."
        ),
    ),
    # ── Python deep learning frameworks ──────────────────────────────────────
    _EquivalenceGroup(
        members=frozenset({
            "TensorFlow", "PyTorch", "Keras", "JAX", "MXNet", "PaddlePaddle",
        }),
        transfer_confidence=0.79,
        rationale_template=(
            "Both are autodifferentiation-based deep learning frameworks; "
            "tensor operations, model training loops, and loss optimization "
            "concepts transfer directly."
        ),
    ),
    # ── Gradient boosting / classical ML ─────────────────────────────────────
    _EquivalenceGroup(
        members=frozenset({
            "scikit-learn", "sklearn", "XGBoost", "LightGBM", "CatBoost",
            "H2O", "Weka",
        }),
        transfer_confidence=0.77,
        rationale_template=(
            "Both are supervised ML libraries with scikit-learn-compatible APIs; "
            "model training, cross-validation, and feature engineering patterns "
            "transfer with minimal ramp-up."
        ),
    ),
    # ── BI and dashboard tools ────────────────────────────────────────────────
    _EquivalenceGroup(
        members=frozenset({
            "Power BI", "PowerBI", "Tableau", "Looker", "Metabase",
            "Apache Superset", "Grafana", "Redash", "Mode",
        }),
        transfer_confidence=0.70,
        rationale_template=(
            "Both are visual BI/analytics tools; data connection setup, "
            "dimensional modeling, and dashboard design concepts transfer, "
            "though UI paradigms differ."
        ),
    ),
    # ── Python data manipulation ──────────────────────────────────────────────
    _EquivalenceGroup(
        members=frozenset({
            "pandas", "polars", "dask", "modin", "cuDF",
        }),
        transfer_confidence=0.74,
        rationale_template=(
            "Both are DataFrame-based data manipulation libraries; "
            "indexing, groupby, merge, and reshape operations transfer directly, "
            "though lazy vs eager execution models may differ."
        ),
    ),
    # ── Container runtimes ────────────────────────────────────────────────────
    _EquivalenceGroup(
        members=frozenset({
            "Docker", "Podman", "containerd", "Docker Compose",
        }),
        transfer_confidence=0.85,
        rationale_template=(
            "Both are OCI-compatible container runtimes; Dockerfile syntax, "
            "container lifecycle, networking, and volume management transfer directly."
        ),
    ),
    # ── Container orchestration ───────────────────────────────────────────────
    _EquivalenceGroup(
        members=frozenset({
            "Kubernetes", "K8s", "Docker Swarm", "Nomad", "Amazon ECS",
        }),
        transfer_confidence=0.68,
        rationale_template=(
            "Both are container orchestration systems; workload scheduling, "
            "service discovery, and rolling deployment concepts transfer, "
            "though API surface and complexity differ substantially."
        ),
    ),
    # ── Message queues / event streaming ─────────────────────────────────────
    _EquivalenceGroup(
        members=frozenset({
            "Apache Kafka", "Kafka", "RabbitMQ", "AWS SQS", "Google Pub/Sub",
            "NATS", "Apache Pulsar", "Amazon Kinesis", "Azure Service Bus",
        }),
        transfer_confidence=0.65,
        rationale_template=(
            "Both are message-passing systems; producer/consumer patterns, "
            "at-least-once delivery semantics, and topic/queue modeling transfer, "
            "though throughput characteristics and exactly-once guarantees differ."
        ),
    ),
    # ── Data pipeline orchestrators ───────────────────────────────────────────
    _EquivalenceGroup(
        members=frozenset({
            "Apache Airflow", "Airflow", "Prefect", "Dagster", "Luigi",
            "Mage", "Kedro", "Flyte",
        }),
        transfer_confidence=0.72,
        rationale_template=(
            "Both are DAG-based pipeline orchestrators; dependency declaration, "
            "scheduling, retry logic, and sensor patterns transfer across tools."
        ),
    ),
    # ── Cloud platforms (high-level) ──────────────────────────────────────────
    _EquivalenceGroup(
        members=frozenset({
            "AWS", "Amazon Web Services",
            "GCP", "Google Cloud Platform",
            "Azure", "Microsoft Azure",
            "Yandex Cloud", "Alibaba Cloud",
        }),
        transfer_confidence=0.65,
        rationale_template=(
            "Both are hyperscaler cloud platforms; IaaS/PaaS service categories, "
            "IAM, networking, and storage concepts transfer, though service naming "
            "and console UX differ."
        ),
    ),
    # ── Version control platforms ─────────────────────────────────────────────
    _EquivalenceGroup(
        members=frozenset({
            "Git", "GitHub", "GitLab", "Bitbucket",
        }),
        transfer_confidence=0.88,
        rationale_template=(
            "All are Git-based version control platforms; branching strategy, "
            "merge/rebase workflows, and code review processes transfer directly."
        ),
    ),
    # ── CI/CD platforms ───────────────────────────────────────────────────────
    _EquivalenceGroup(
        members=frozenset({
            "GitHub Actions", "GitLab CI", "Jenkins", "CircleCI",
            "Travis CI", "TeamCity", "Buildkite", "Azure Pipelines",
        }),
        transfer_confidence=0.70,
        rationale_template=(
            "Both are CI/CD pipeline platforms; pipeline-as-code, artifact management, "
            "and environment promotion patterns transfer, though DSL syntax differs."
        ),
    ),
    # ── Infrastructure-as-code ────────────────────────────────────────────────
    _EquivalenceGroup(
        members=frozenset({
            "Terraform", "OpenTofu", "Pulumi", "AWS CloudFormation",
            "AWS CDK", "Ansible",
        }),
        transfer_confidence=0.67,
        rationale_template=(
            "Both are infrastructure-as-code tools; declarative resource definition, "
            "state management, and idempotent apply operations transfer, "
            "though provider ecosystems and HCL vs YAML syntax differ."
        ),
    ),
    # ── Python visualization ──────────────────────────────────────────────────
    _EquivalenceGroup(
        members=frozenset({
            "Matplotlib", "Seaborn", "Plotly", "Bokeh", "Altair", "Plotly Dash",
        }),
        transfer_confidence=0.73,
        rationale_template=(
            "Both are Python data visualization libraries; figure/axes API patterns, "
            "color mapping, and data-binding concepts transfer across libraries."
        ),
    ),
    # ── SQL transformation tools ──────────────────────────────────────────────
    _EquivalenceGroup(
        members=frozenset({
            "dbt", "dbt Core", "SQLMesh", "Looker LookML",
        }),
        transfer_confidence=0.68,
        rationale_template=(
            "Both are SQL-based data transformation and modeling tools; "
            "ref() dependency graphs, model testing, and lineage documentation "
            "concepts transfer."
        ),
    ),
    # ── Spark ecosystem ───────────────────────────────────────────────────────
    _EquivalenceGroup(
        members=frozenset({
            "Apache Spark", "Spark", "PySpark", "Spark SQL",
            "Apache Flink", "Beam",
        }),
        transfer_confidence=0.71,
        rationale_template=(
            "Both are distributed data processing frameworks; partition-level "
            "execution, lazy evaluation, and join strategies transfer, "
            "though streaming vs batch semantics differ."
        ),
    ),
]


def _build_synonym_lookup(
    groups: List[_EquivalenceGroup],
) -> Dict[str, _EquivalenceGroup]:
    """
    Builds a flat dict: lowercase(canonical_name) → _EquivalenceGroup.
    Enables O(1) group membership lookup per skill name.
    Skills appearing in multiple groups (schema error) raise ValueError at startup.
    """
    lookup: Dict[str, _EquivalenceGroup] = {}
    for group in groups:
        for member in group.members:
            key = member.lower()
            if key in lookup:
                raise ValueError(
                    f"Skill '{member}' appears in multiple equivalence groups. "
                    "Equivalence groups must be mutually exclusive."
                )
            lookup[key] = group
    return lookup


# Module-level lookup table — built once at import time
_SYNONYM_LOOKUP: Dict[str, _EquivalenceGroup] = _build_synonym_lookup(_EQUIVALENCE_GROUPS)


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Output Models
# ─────────────────────────────────────────────────────────────────────────────

class TransferabilityAssessment(BaseModel):
    """
    LLM assessment result for a single unresolved JD skill.
    Produced only for skills that failed Stage 1 (exact) and Stage 2 (synonym) matching.
    """
    jd_skill_canonical: str = Field(
        ...,
        description="The JD skill being assessed. Verbatim from the unresolved input list.",
    )
    is_critical: bool = Field(
        ...,
        description="True if this skill is from required_skills; False if preferred.",
    )
    has_transferable_cv_skill: bool = Field(
        ...,
        description=(
            "True only if a CV skill with transfer_confidence ≥ 0.55 was identified. "
            "False means this skill is a genuine gap (critical or preferred)."
        ),
    )
    cv_skill_canonical: Optional[str] = Field(
        None,
        description=(
            "The canonical name of the CV skill providing transferable competency. "
            "Must be copied verbatim from the provided FULL_CV_SKILL_POOL list. "
            "Null if has_transferable_cv_skill is false."
        ),
    )
    transfer_confidence: Optional[float] = Field(
        None,
        ge=0.55,
        le=1.0,
        description=(
            "Confidence in the transferability claim. Null if has_transferable = false. "
            "Minimum reported value: 0.55 (below this, set has_transferable = false)."
        ),
    )
    transfer_rationale: Optional[str] = Field(
        None,
        description=(
            "One-sentence rationale for the transferability claim. ≤25 words. "
            "Focus on the functional overlap mechanism. Null if has_transferable = false."
        ),
        max_length=200,
    )

    @model_validator(mode="after")
    def validate_conditional_fields(self) -> "TransferabilityAssessment":
        if self.has_transferable_cv_skill:
            if self.cv_skill_canonical is None:
                raise ValueError(
                    "cv_skill_canonical must be provided when has_transferable_cv_skill is true."
                )
            if self.transfer_confidence is None:
                raise ValueError(
                    "transfer_confidence must be provided when has_transferable_cv_skill is true."
                )
        else:
            # Normalize to null when no transfer found
            self.cv_skill_canonical = None
            self.transfer_confidence = None
            self.transfer_rationale = None
        return self


class LLMTransferabilityOutput(BaseModel):
    """Root LLM output for the transferability assessment batch."""
    assessments: List[TransferabilityAssessment] = Field(
        ...,
        description="One assessment per unresolved JD skill. No omissions permitted.",
    )
    assessment_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="LLM's overall confidence in the batch of assessments.",
    )

    @field_validator("assessments", mode="after")
    @classmethod
    def no_empty_assessments(cls, v: List[TransferabilityAssessment]) -> List[TransferabilityAssessment]:
        if not v:
            raise ValueError(
                "LLMTransferabilityOutput.assessments must contain at least one entry. "
                "If no skills were sent to LLM, this model should not be instantiated."
            )
        return v


class SkillsOntologyOutput(BaseModel):
    """
    Root output model for SkillsOntologyAgent.

    Superset of the canonical SkillsOntologyResult defined in
    src/schemas/canonical_payload.py. All SkillsOntologyResult fields are
    present and populated. Additional fields provide matching-stage provenance
    (exact_match_count, synonym_match_count, etc.) consumed by the PayloadAssembler
    for analysis_completeness_score computation.

    ACCESS PATTERN:
      - For CanonicalAnalysisPayload: call to_canonical_skills_result()
      - For UI skills bridge visualization: read all four skill buckets directly
      - For Evaluation Tab metrics: read matching statistics fields
    """

    # ── SkillsOntologyResult core fields ─────────────────────────────────────
    matched_skills: List[SkillMatchEntry] = Field(default_factory=list)
    missing_critical: List[SkillMatchEntry] = Field(default_factory=list)
    missing_preferred: List[SkillMatchEntry] = Field(default_factory=list)
    transferable: List[SkillMatchEntry] = Field(default_factory=list)
    total_required_skills: int = 0
    matched_count: int = 0
    critical_gap_count: int = 0
    coverage_ratio: float = Field(0.0, ge=0.0, le=1.0)
    gap_severity: GapSeverity = GapSeverity.MODERATE

    # ── Weighted coverage (extended) ──────────────────────────────────────────
    weighted_coverage_ratio: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Coverage ratio where transferable skills are weighted by transfer_confidence "
            "rather than counted as binary matches. More accurate readiness indicator."
        ),
    )

    # ── Stage provenance counters ─────────────────────────────────────────────
    exact_match_count: int = Field(
        0,
        description="Skills resolved via Stage 1 exact canonical-name matching.",
    )
    synonym_match_count: int = Field(
        0,
        description="Skills resolved via Stage 2 functional equivalence group matching.",
    )
    llm_transferable_count: int = Field(
        0,
        description="Skills assessed as transferable in Stage 3 (LLM).",
    )
    llm_invoked: bool = Field(
        False,
        description="True if Stage 3 was executed (any unresolved skills reached LLM).",
    )
    unresolved_to_gap_count: int = Field(
        0,
        description="Skills that remained unresolved after all three stages (genuine gaps).",
    )

    # ── Agent metadata ────────────────────────────────────────────────────────
    agent_session_id: str = ""
    llm_assessment_confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Set from LLMTransferabilityOutput.assessment_confidence. 0.5 on fallback.",
    )
    processing_latency_ms: Optional[int] = None

    def to_canonical_skills_result(self) -> SkillsOntologyResult:
        """
        Extracts the SkillsOntologyResult subset for insertion into CanonicalAnalysisPayload.
        This is the only sanctioned method for canonical-payload insertion.
        """
        return SkillsOntologyResult(
            matched_skills=self.matched_skills,
            missing_critical=self.missing_critical,
            missing_preferred=self.missing_preferred,
            transferable=self.transferable,
            total_required_skills=self.total_required_skills,
            matched_count=self.matched_count,
            critical_gap_count=self.critical_gap_count,
            coverage_ratio=self.coverage_ratio,
            gap_severity=self.gap_severity,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Agent Implementation
# ─────────────────────────────────────────────────────────────────────────────

class SkillsOntologyAgent:
    """
    Phase 1 parallel agent responsible for skills gap analysis.

    Consumes ParsedCVOutput and JDEntities (structured, validated objects).
    Applies a three-stage matching pipeline (exact → synonym → LLM).
    Produces SkillsOntologyOutput with full gap classification and metrics.
    """

    def __init__(self) -> None:
        self._llm = ChatOpenAI(
            model="gpt-4.1-mini",
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        self._parser = PydanticOutputParser(pydantic_object=LLMTransferabilityOutput)
        self._chain = self._build_chain()

    def _build_chain(self):
        """Constructs the LangChain RunnableSequence for transferability assessment."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", USER_TEMPLATE),
        ])
        return prompt | self._llm | self._parser

    # ─────────────────────────────────────────────────────────────────────────
    # Static Utility Methods
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _classify_gap_severity(
        critical_gap_count: int,
        total_required: int,
        has_must_have_tool_gap: bool = False,
    ) -> GapSeverity:
        """
        Classifies overall gap severity using the business rules defined in
        the Skills Ontology Agent V3 prompt specification.

        Rules (applied in order, first matching rule wins):
          CRITICAL: critical_gap_count ≥ 3, OR has_must_have_tool_gap is True
          MODERATE: 1 ≤ critical_gap_count ≤ 2
          MINOR:    critical_gap_count = 0, preferred gaps exist
          NONE:     zero total gaps
        """
        if total_required == 0:
            return GapSeverity.NONE
        if critical_gap_count >= 3 or has_must_have_tool_gap:
            return GapSeverity.CRITICAL
        if critical_gap_count >= 1:
            return GapSeverity.MODERATE
        return GapSeverity.MINOR

    @staticmethod
    def _compute_weighted_coverage(
        matched_skills: List[SkillMatchEntry],
        transferable_skills: List[SkillMatchEntry],
        total_required: int,
    ) -> Tuple[float, float]:
        """
        Computes both binary and weighted coverage ratios.

        Binary coverage:
          = exact_match_count / total_required
          (transferable skills are NOT counted in binary coverage)

        Weighted coverage:
          = (exact_match_count + Σ transfer_confidence_i) / total_required
          where the sum runs over all transferable skills.

        Returns (binary_ratio, weighted_ratio). Both clamped to [0.0, 1.0].
        """
        if total_required == 0:
            return (0.0, 0.0)

        binary_numerator = float(len(matched_skills))
        weighted_numerator = binary_numerator + sum(
            (s.transfer_confidence or 0.0) for s in transferable_skills
        )

        binary_ratio = round(min(binary_numerator / total_required, 1.0), 4)
        weighted_ratio = round(min(weighted_numerator / total_required, 1.0), 4)
        return (binary_ratio, weighted_ratio)

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 1: Exact Canonical Name Matching
    # ─────────────────────────────────────────────────────────────────────────

    def _build_cv_skill_index(
        self, parsed_cv: ParsedCVOutput
    ) -> Dict[str, ParsedSkillEntry]:
        """
        Builds a lowercase canonical name → ParsedSkillEntry lookup dict.
        Used for O(1) Stage 1 exact-match lookups.
        If the same canonical name appears multiple times (deduplication validator
        in ParsedCVOutput should prevent this, but we handle it defensively),
        the entry with the richer proficiency signal is retained.
        """
        index: Dict[str, ParsedSkillEntry] = {}
        for skill in parsed_cv.skills:
            key = skill.canonical_name.lower().strip()
            if key not in index:
                index[key] = skill
            else:
                # Keep the entry with explicit proficiency signal
                existing = index[key]
                if skill.proficiency_signal and not existing.proficiency_signal:
                    index[key] = skill
        return index

    def _stage1_exact_match(
        self,
        jd_skill: SkillEntry,
        cv_index: Dict[str, ParsedSkillEntry],
        is_critical: bool,
    ) -> Optional[SkillMatchEntry]:
        """
        Attempts exact canonical-name match for one JD skill.
        Returns a SkillMatchEntry (MATCHED) if found; None otherwise.
        """
        key = jd_skill.canonical_name.lower().strip()
        cv_skill = cv_index.get(key)
        if cv_skill is None:
            return None
        return SkillMatchEntry(
            skill_name=jd_skill.raw_name,
            canonical_name=jd_skill.canonical_name,
            match_type=SkillMatchType.MATCHED,
            transfer_confidence=None,
            transfer_rationale=None,
            is_critical=is_critical,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 2: Functional Equivalence Group Matching
    # ─────────────────────────────────────────────────────────────────────────

    def _stage2_synonym_match(
        self,
        jd_skill: SkillEntry,
        cv_index: Dict[str, ParsedSkillEntry],
        is_critical: bool,
    ) -> Optional[SkillMatchEntry]:
        """
        Checks if the JD skill and any CV skill share a functional equivalence group.

        Lookup: jd_skill.canonical_name → group (if group exists for this skill).
        If the group is found, scan all group members against the CV index.
        If any group member is in the CV index, a TRANSFERABLE match is created
        with the group's pre-assigned transfer_confidence and rationale.

        Returns a SkillMatchEntry (TRANSFERABLE) if synonym match found; None otherwise.
        """
        jd_key = jd_skill.canonical_name.lower().strip()
        jd_group = _SYNONYM_LOOKUP.get(jd_key)
        if jd_group is None:
            return None  # JD skill not in any group

        # Find a CV skill in the same group
        matched_cv_canonical: Optional[str] = None
        for member in jd_group.members:
            if member.lower() in cv_index:
                matched_cv_canonical = member
                break

        if matched_cv_canonical is None:
            return None  # No CV skill in this group

        return SkillMatchEntry(
            skill_name=jd_skill.raw_name,
            canonical_name=jd_skill.canonical_name,
            match_type=SkillMatchType.TRANSFERABLE,
            transfer_confidence=round(jd_group.transfer_confidence, 4),
            transfer_rationale=(
                f"Matched via functional equivalence group. "
                f"CV skill '{matched_cv_canonical}': "
                f"{jd_group.rationale_template}"
            ),
            is_critical=is_critical,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 3: LLM Transferability Assessment
    # ─────────────────────────────────────────────────────────────────────────

    async def _stage3_llm_transferability(
        self,
        unresolved_required: List[SkillEntry],
        unresolved_preferred: List[SkillEntry],
        cv_index: Dict[str, ParsedSkillEntry],
    ) -> Tuple[LLMTransferabilityOutput, float]:
        """
        Sends unresolved JD skills to the LLM for transferability assessment.
        Returns (LLMTransferabilityOutput, llm_confidence).
        llm_confidence is 0.5 if fallback was activated.

        The LLM receives:
          - The full CV canonical skill pool (all skills, not just unresolved ones)
          - The unresolved required and preferred skill lists
        It does NOT receive any resolved skills (Stage 1+2 results).
        """
        cv_pool = sorted(cv_index.keys())  # Alphabetical order for deterministic prompting
        cv_pool_proper = [cv_index[k].canonical_name for k in cv_pool]  # Restore proper casing

        unresolved_req_names = [s.canonical_name for s in unresolved_required]
        unresolved_pref_names = [s.canonical_name for s in unresolved_preferred]

        invoke_vars = {
            "format_instructions": self._parser.get_format_instructions(),
            "few_shot_examples": FEW_SHOT_EXAMPLES,
            "cv_skill_pool_json": json.dumps(cv_pool_proper, ensure_ascii=False, indent=2),
            "unresolved_required_json": json.dumps(unresolved_req_names, ensure_ascii=False),
            "unresolved_preferred_json": json.dumps(unresolved_pref_names, ensure_ascii=False),
        }

        try:
            result: LLMTransferabilityOutput = await self._chain.ainvoke(invoke_vars)
            logger.debug(
                "SkillsOntologyAgent Stage 3 LLM: %d assessments, confidence=%.2f",
                len(result.assessments),
                result.assessment_confidence,
            )
            return result, result.assessment_confidence
        except Exception as exc:
            logger.error(
                "SkillsOntologyAgent Stage 3 LLM failed: %s. Activating fallback: "
                "all unresolved skills classified as gaps.",
                exc,
            )
            # Fallback: classify all unresolved as non-transferable
            fallback_assessments = [
                TransferabilityAssessment(
                    jd_skill_canonical=s.canonical_name,
                    is_critical=True,
                    has_transferable_cv_skill=False,
                )
                for s in unresolved_required
            ] + [
                TransferabilityAssessment(
                    jd_skill_canonical=s.canonical_name,
                    is_critical=False,
                    has_transferable_cv_skill=False,
                )
                for s in unresolved_preferred
            ]
            # Ensure at least one entry (model validator requirement)
            if not fallback_assessments:
                fallback_assessments = [
                    TransferabilityAssessment(
                        jd_skill_canonical="__fallback_placeholder__",
                        is_critical=False,
                        has_transferable_cv_skill=False,
                    )
                ]
            return LLMTransferabilityOutput(
                assessments=fallback_assessments,
                assessment_confidence=0.5,
            ), 0.5

    def _convert_llm_assessment_to_match_entry(
        self,
        assessment: TransferabilityAssessment,
    ) -> Optional[SkillMatchEntry]:
        """
        Converts a TransferabilityAssessment to a SkillMatchEntry.
        Returns None if the assessment reports no transferable match
        (caller handles gap classification).
        """
        if not assessment.has_transferable_cv_skill:
            return None
        return SkillMatchEntry(
            skill_name=assessment.jd_skill_canonical,
            canonical_name=assessment.jd_skill_canonical,
            match_type=SkillMatchType.TRANSFERABLE,
            transfer_confidence=assessment.transfer_confidence,
            transfer_rationale=assessment.transfer_rationale,
            is_critical=assessment.is_critical,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Primary Entry Point
    # ─────────────────────────────────────────────────────────────────────────

    async def arun(
        self,
        parsed_cv: ParsedCVOutput,
        jd_entities: JDEntities,
        session_id: str,
    ) -> SkillsOntologyOutput:
        """
        Main async execution method.

        Executes the three-stage matching pipeline sequentially:
          Stage 1 (exact) and Stage 2 (synonym) are synchronous and CPU-bound.
          Stage 3 (LLM) is async I/O-bound and invoked only if needed.

        The method returns a fully populated SkillsOntologyOutput.

        Raises: Pydantic ValidationError if output assembly fails structural invariants.
                The caller (node_phase1_parallel) handles this via return_exceptions=True.
        """
        start_ms = int(time.monotonic() * 1000)
        logger.info("SkillsOntologyAgent.arun started. session_id=%s", session_id)

        # ── Build CV skill index ──────────────────────────────────────────────
        cv_index = self._build_cv_skill_index(parsed_cv)

        # ── Initialize result buckets ─────────────────────────────────────────
        matched_skills: List[SkillMatchEntry] = []
        transferable_skills: List[SkillMatchEntry] = []
        missing_critical: List[SkillMatchEntry] = []
        missing_preferred: List[SkillMatchEntry] = []

        stage_counters = {
            "exact": 0,
            "synonym": 0,
            "llm": 0,
        }

        # ── Stage 1 + 2: Process all required skills ──────────────────────────
        unresolved_required: List[SkillEntry] = []

        for jd_skill in jd_entities.required_skills:
            # Stage 1: exact match
            match = self._stage1_exact_match(jd_skill, cv_index, is_critical=True)
            if match:
                matched_skills.append(match)
                stage_counters["exact"] += 1
                continue

            # Stage 2: synonym / equivalence group match
            match = self._stage2_synonym_match(jd_skill, cv_index, is_critical=True)
            if match:
                transferable_skills.append(match)
                stage_counters["synonym"] += 1
                continue

            # Unresolved: mark for Stage 3
            unresolved_required.append(jd_skill)

        # ── Stage 1 + 2: Process all preferred skills ────────────────────────
        unresolved_preferred: List[SkillEntry] = []

        for jd_skill in jd_entities.preferred_skills:
            # Stage 1: exact match
            match = self._stage1_exact_match(jd_skill, cv_index, is_critical=False)
            if match:
                matched_skills.append(match)
                stage_counters["exact"] += 1
                continue

            # Stage 2: synonym match
            match = self._stage2_synonym_match(jd_skill, cv_index, is_critical=False)
            if match:
                transferable_skills.append(match)
                stage_counters["synonym"] += 1
                continue

            unresolved_preferred.append(jd_skill)

        # ── Stage 3: LLM transferability (only if unresolved skills remain) ───
        llm_invoked = False
        llm_confidence = 1.0
        unresolved_to_gap_count = 0

        if unresolved_required or unresolved_preferred:
            llm_invoked = True
            llm_output, llm_confidence = await self._stage3_llm_transferability(
                unresolved_required=unresolved_required,
                unresolved_preferred=unresolved_preferred,
                cv_index=cv_index,
            )

            # Build lookup from LLM assessments for quick access
            assessment_map: Dict[str, TransferabilityAssessment] = {
                a.jd_skill_canonical: a for a in llm_output.assessments
                if a.jd_skill_canonical != "__fallback_placeholder__"
            }

            # Process unresolved required skills via LLM assessments
            for jd_skill in unresolved_required:
                assessment = assessment_map.get(jd_skill.canonical_name)
                if assessment and assessment.has_transferable_cv_skill:
                    entry = self._convert_llm_assessment_to_match_entry(assessment)
                    if entry:
                        transferable_skills.append(entry)
                        stage_counters["llm"] += 1
                        continue
                # No transferable match found: genuine critical gap
                missing_critical.append(SkillMatchEntry(
                    skill_name=jd_skill.raw_name,
                    canonical_name=jd_skill.canonical_name,
                    match_type=SkillMatchType.MISSING_CRITICAL,
                    transfer_confidence=None,
                    transfer_rationale=None,
                    is_critical=True,
                ))
                unresolved_to_gap_count += 1

            # Process unresolved preferred skills via LLM assessments
            for jd_skill in unresolved_preferred:
                assessment = assessment_map.get(jd_skill.canonical_name)
                if assessment and assessment.has_transferable_cv_skill:
                    entry = self._convert_llm_assessment_to_match_entry(assessment)
                    if entry:
                        transferable_skills.append(entry)
                        stage_counters["llm"] += 1
                        continue
                # No transferable match: preferred gap (lower severity than critical)
                missing_preferred.append(SkillMatchEntry(
                    skill_name=jd_skill.raw_name,
                    canonical_name=jd_skill.canonical_name,
                    match_type=SkillMatchType.MISSING_PREFERRED,
                    transfer_confidence=None,
                    transfer_rationale=None,
                    is_critical=False,
                ))
                unresolved_to_gap_count += 1
        else:
            # No unresolved skills: LLM not needed
            logger.debug(
                "SkillsOntologyAgent: all skills resolved in Stage 1+2. LLM not invoked."
            )

        # ── Compute metrics ───────────────────────────────────────────────────
        total_required = len(jd_entities.required_skills)
        matched_count = len(matched_skills)
        critical_gap_count = len(missing_critical)

        binary_coverage, weighted_coverage = self._compute_weighted_coverage(
            matched_skills=matched_skills,
            transferable_skills=transferable_skills,
            total_required=total_required,
        )

        # Detect if any must-have tool (is_critical=True, commonly used primary tool)
        # has a direct gap — used to elevate gap severity to CRITICAL
        # Heuristic: a "must-have tool" is a required skill that appears in
        # required_qualifications prose AND is missing from CV.
        must_have_gaps = {mc.canonical_name.lower() for mc in missing_critical}
        required_qual_text = " ".join(jd_entities.required_qualifications).lower()
        has_must_have_tool_gap = any(
            gap in required_qual_text for gap in must_have_gaps
        )

        gap_severity = self._classify_gap_severity(
            critical_gap_count=critical_gap_count,
            total_required=total_required,
            has_must_have_tool_gap=has_must_have_tool_gap,
        )

        end_ms = int(time.monotonic() * 1000)
        latency_ms = end_ms - start_ms

        logger.info(
            "SkillsOntologyAgent.arun completed. session_id=%s latency_ms=%d "
            "matched=%d transferable=%d critical_gaps=%d preferred_gaps=%d "
            "binary_coverage=%.3f weighted_coverage=%.3f gap_severity=%s",
            session_id, latency_ms,
            matched_count, len(transferable_skills), critical_gap_count,
            len(missing_preferred), binary_coverage, weighted_coverage, gap_severity.value,
        )

        return SkillsOntologyOutput(
            # Core SkillsOntologyResult fields
            matched_skills=matched_skills,
            missing_critical=missing_critical,
            missing_preferred=missing_preferred,
            transferable=transferable_skills,
            total_required_skills=total_required,
            matched_count=matched_count,
            critical_gap_count=critical_gap_count,
            coverage_ratio=binary_coverage,
            gap_severity=gap_severity,
            # Extended fields
            weighted_coverage_ratio=weighted_coverage,
            exact_match_count=stage_counters["exact"],
            synonym_match_count=stage_counters["synonym"],
            llm_transferable_count=stage_counters["llm"],
            llm_invoked=llm_invoked,
            unresolved_to_gap_count=unresolved_to_gap_count,
            # Metadata
            agent_session_id=session_id,
            llm_assessment_confidence=llm_confidence,
            processing_latency_ms=latency_ms,
        )
