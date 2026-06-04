# src/agents/candidate_simulator.py
#
# Candidate Simulation Engine — Step 1 of 2
#
# Architecture: Two-Agent Internal Simulation
# ─────────────────────────────────────────────────────────────────────────────
#
# This module implements a closed two-agent LangGraph simulation where:
#
#   Agent A — Technical Interviewer
#     Persona: Senior Data Engineer who designed the company's ClickHouse
#     cluster and Airflow orchestration layer. Probes the three critical
#     skill gaps: ClickHouse (ReplacingMergeTree, sharding), Apache Airflow
#     (DAG orchestration, production incident response), and Apache Spark
#     (structured streaming at 10k+ events/sec).
#     Model: Gemini 2.0 Flash, temperature=0.45 (slight variation per session)
#
#   Agent B — Candidate
#     Persona: Mid-level Python Backend Engineer, 3.6 years at Armenian iGaming
#     companies (Digitain LLC, Softconstruct CJSC). Expert in PostgreSQL
#     performance engineering and FastAPI async microservices. Strictly
#     bounded: zero ClickHouse, Airflow, or Spark implementation knowledge.
#     The persona is anchored to MOCK_CV_ENTITIES from tests/mock_fixtures.py.
#     Model: Gemini 2.0 Flash, temperature=0.28 (consistent, profile-grounded)
#
# ─────────────────────────────────────────────────────────────────────────────
# Module Layout — Step 1 (this file):
#   Section 1  — Imports
#   Section 2  — Enumerations
#   Section 3  — Pydantic Schema Definitions
#   Section 4  — Model & Runtime Configuration Constants
#   Section 5  — Candidate Knowledge Map (hardcoded for fixture profile)
#   Section 6  — Interviewer: System Prompt + Human Template + ChatPromptTemplate
#   Section 7  — Candidate:   System Prompt + Human Template + ChatPromptTemplate
#   Section 8  — LangChain Output Parsers
#   Section 9  — LLM Factory Functions and Prompt Utility Helpers
#
# Step 2 (separate commit) will add:
#   Section 10 — LangGraph StateGraph node functions:
#                run_interviewer_turn, run_candidate_turn,
#                assess_round_quality, check_termination_condition
#   Section 11 — Graph compilation and singleton export

from __future__ import annotations

# ===========================================================================
# SECTION 1 — Imports
# ===========================================================================

import logging
from datetime import datetime
from enum import Enum
from functools import lru_cache
from typing import Any, Dict, List, Optional

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field, field_validator, model_validator

from src.schemas.canonical_payload import (
    CVEntities,
    JDEntities,
    SkillsOntologyResult,
)

logger = logging.getLogger(__name__)


# ===========================================================================
# SECTION 2 — Enumerations
# ===========================================================================

class TurnRole(str, Enum):
    """Which agent produced a given simulation turn."""
    INTERVIEWER = "interviewer"
    CANDIDATE   = "candidate"
    SYSTEM      = "system"


class QuestionType(str, Enum):
    """
    Classification of the interviewer's current question intent.
    Drives follow-up selection logic in the Step 2 execution loop.
    """
    OPENING               = "opening"
    TECHNICAL_PROBE       = "technical_probe"
    BEHAVIORAL_STAR       = "behavioral_star"
    FOLLOW_UP_SHALLOW     = "follow_up_shallow"
    FOLLOW_UP_DEEP        = "follow_up_deep"
    CONCEPTUAL            = "conceptual"
    ARCHITECTURE_DESIGN   = "architecture_design"
    SYNTHESIS             = "synthesis"
    CLOSING               = "closing"


class TargetGapArea(str, Enum):
    """
    Which critical skill gap the current interviewer turn is probing.
    Maps directly to the three MISSING_CRITICAL skills in MOCK_SKILLS_ONTOLOGY.
    """
    GENERAL_BACKGROUND       = "general_background"
    CLICKHOUSE_CORE          = "clickhouse_core"
    CLICKHOUSE_ARCHITECTURE  = "clickhouse_architecture"
    AIRFLOW_FUNDAMENTALS     = "airflow_fundamentals"
    AIRFLOW_PRODUCTION       = "airflow_production"
    SPARK_FUNDAMENTALS       = "spark_fundamentals"
    SPARK_STREAMING          = "spark_streaming"
    DATA_ARCHITECTURE        = "data_architecture"
    SYNTHESIS_AND_GROWTH     = "synthesis_and_growth"


class KnowledgeDomain(str, Enum):
    """
    All domains relevant to the JD and candidate profile.
    Domains marked ABSENT are zero-experience for the candidate persona.
    Domains marked CONCEPTUAL_ONLY allow adjacent reasoning but not implementation claims.
    """
    PYTHON_CORE                = "python_core"
    PYTHON_ASYNC               = "python_async"
    POSTGRESQL                 = "postgresql"
    SQL_GENERAL                = "sql_general"
    FASTAPI                    = "fastapi"
    REDIS_CLIENT               = "redis_client"
    CELERY                     = "celery"
    DOCKER                     = "docker"
    IGAMING_DOMAIN             = "igaming_domain"
    CLICKHOUSE                 = "clickhouse"              # ABSENT
    APACHE_AIRFLOW             = "apache_airflow"          # ABSENT
    APACHE_SPARK               = "apache_spark"            # ABSENT
    COLUMNAR_OLAP_CONCEPTS     = "columnar_olap_concepts"  # CONCEPTUAL_ONLY
    DAG_ORCHESTRATION_CONCEPTS = "dag_orchestration_concepts"  # CONCEPTUAL_ONLY
    DISTRIBUTED_SYSTEMS        = "distributed_systems"     # CONCEPTUAL_ONLY


class ResponseValidity(str, Enum):
    """
    Whether the candidate's response stays within documented knowledge boundaries.
    Used by the Step 2 quality assessor. BOUNDARY_BREACH must never occur.
    """
    AUTHENTIC          = "authentic"
    BOUNDARY_ADJACENT  = "boundary_adjacent"
    BOUNDARY_BREACH    = "boundary_breach"


class ConfidenceLevel(str, Enum):
    """Candidate's self-assessed confidence for a specific answer."""
    HIGH              = "high"
    MEDIUM            = "medium"
    LOW               = "low"
    ACKNOWLEDGING_GAP = "acknowledging_gap"


class InterviewStage(str, Enum):
    """
    Macro-level interview phase. The execution loop advances stage
    after a configurable number of rounds per phase.
    """
    OPENING                = "opening"
    DEEP_DIVE_CLICKHOUSE   = "deep_dive_clickhouse"
    DEEP_DIVE_AIRFLOW      = "deep_dive_airflow"
    DEEP_DIVE_SPARK        = "deep_dive_spark"
    SYNTHESIS_AND_GROWTH   = "synthesis_and_growth"
    CLOSING                = "closing"


class SimulationDifficulty(str, Enum):
    """
    Governs the technical depth of interviewer questions.
    EXPLORATORY: awareness-level.
    STANDARD:    implementation and design knowledge.
    DEEP_DIVE:   architecture, edge cases, and production incident patterns.
    """
    EXPLORATORY = "exploratory"
    STANDARD    = "standard"
    DEEP_DIVE   = "deep_dive"


# ===========================================================================
# SECTION 3 — Pydantic Schema Definitions
# ===========================================================================

class KnowledgeBoundaryEntry(BaseModel):
    """
    Defines the precise epistemic boundary for one knowledge domain
    within the Candidate persona. All entries together form CANDIDATE_KNOWLEDGE_MAP.
    """
    domain:            KnowledgeDomain
    proficiency_label: str = Field(
        ...,
        description=(
            "Human-readable proficiency tier: "
            "'expert', 'advanced', 'intermediate', 'basic', 'conceptual_only', 'absent'."
        ),
    )
    can_answer_up_to: str = Field(
        ...,
        description=(
            "Precise description of the maximum answerable depth. Used by the Step 2 "
            "quality assessor to validate ResponseValidity."
        ),
    )
    transfer_bridge: Optional[str] = Field(
        None,
        description=(
            "Adjacent domain that permits BOUNDARY_ADJACENT reasoning. Null if no "
            "meaningful transfer exists. Must reference a specific known domain."
        ),
    )
    example_anchor: str = Field(
        ...,
        description=(
            "A concrete, verbatim example from the candidate's work history that "
            "the Candidate persona should cite when this domain is invoked."
        ),
    )


class SimulationConfig(BaseModel):
    """Runtime configuration for a single simulation session."""
    session_id:               str
    difficulty:               SimulationDifficulty = SimulationDifficulty.STANDARD
    max_rounds_per_stage:     int = Field(2, ge=1, le=5)
    max_total_rounds:         int = Field(12, ge=4, le=20)
    include_synthesis_stage:  bool = True
    include_closing_stage:    bool = True
    language:                 str = "en"
    allow_adjacent_reasoning: bool = True


class SimulationTurn(BaseModel):
    """
    One atomic turn in the simulation — either an interviewer question or
    a candidate response. Composes the conversation_history list.
    """
    turn_index:        int = Field(..., ge=0)
    role:              TurnRole
    content:           str = Field(..., min_length=1)
    stage:             InterviewStage
    timestamp:         str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds") + "Z"
    )
    question_type:     Optional[QuestionType]   = None
    target_gap_area:   Optional[TargetGapArea]  = None
    response_validity: Optional[ResponseValidity] = None
    confidence_level:  Optional[ConfidenceLevel]  = None
    domains_invoked:   List[KnowledgeDomain]       = Field(default_factory=list)
    gap_acknowledged:  bool                         = False


class InterviewerTurnOutput(BaseModel):
    """
    Structured output produced by Agent A (Interviewer) on each turn.
    Parsed from Gemini's JSON response via interviewer_output_parser.

    Fields prefixed `internal_` are not shown in the candidate-facing UI.
    They feed the round quality assessor and telemetry logging in Step 2.
    """
    spoken_question: str = Field(
        ...,
        description=(
            "The exact question the interviewer speaks aloud. "
            "Single question only — no compound questions. "
            "Natural interview speech; no bullet points, no headers, no enumeration."
        ),
    )
    question_type: QuestionType = Field(
        ...,
        description="Format and intent classification for this question.",
    )
    target_gap_area: TargetGapArea = Field(
        ...,
        description="Which critical gap area this question primarily probes.",
    )
    current_stage: InterviewStage = Field(
        ...,
        description="The macro interview stage this question belongs to.",
    )
    expected_signal_strong: str = Field(
        ...,
        description=(
            "What a strong candidate answer to this question would demonstrate. "
            "Used to assess response quality in Step 2."
        ),
    )
    expected_signal_weak: str = Field(
        ...,
        description=(
            "What a surface-level or evasive answer looks like. "
            "Triggers FOLLOW_UP_SHALLOW on the next turn."
        ),
    )
    internal_follow_up_if_shallow: str = Field(
        ...,
        description=(
            "The follow-up question to queue if the candidate gives a surface-level answer. "
            "Stored in SimulationSessionState.pending_follow_up_question. "
            "NOT spoken in this turn."
        ),
    )
    internal_assessment_note: str = Field(
        ...,
        description=(
            "The interviewer's private running assessment of the candidate accumulated "
            "across all turns. Append-only — never overwrite prior content. "
            "NOT surfaced in the candidate-facing UI."
        ),
    )
    advance_stage_after_this_turn: bool = Field(
        default=False,
        description=(
            "Set True when the interviewer has gathered sufficient signal on the current "
            "stage and intends to transition to the next. "
            "The execution loop reads this to trigger stage advancement."
        ),
    )


class CandidateTurnOutput(BaseModel):
    """
    Structured output produced by Agent B (Candidate) on each turn.
    Parsed from Gemini's JSON response via candidate_output_parser.

    Fields prefixed `internal_` are not rendered in the UI simulation panel.
    They are used by the quality assessor and telemetry in Step 2.
    """
    spoken_response: str = Field(
        ...,
        description=(
            "The exact response the candidate speaks aloud. "
            "First person, professional but conversational. "
            "No bullet points, headers, or enumeration in spoken_response. "
            "Must never claim ClickHouse, Airflow, or Spark implementation experience. "
            "Must acknowledge gaps professionally when the question targets an absent domain."
        ),
    )
    internal_reasoning: str = Field(
        ...,
        description=(
            "The candidate's private thought process before formulating spoken_response. "
            "Documents which knowledge domains were evaluated, whether adjacent reasoning "
            "was invoked, and why the response was framed as it was. "
            "NOT shown in the simulation UI."
        ),
    )
    knowledge_domains_accessed: List[KnowledgeDomain] = Field(
        ...,
        description=(
            "Every KnowledgeDomain value drawn upon to construct this response. "
            "Must not include CLICKHOUSE, APACHE_AIRFLOW, or APACHE_SPARK unless "
            "response_validity is BOUNDARY_ADJACENT (adjacent conceptual reasoning only)."
        ),
    )
    response_validity: ResponseValidity = Field(
        ...,
        description=(
            "AUTHENTIC: fully within documented expertise. "
            "BOUNDARY_ADJACENT: uses transfer_bridge from KnowledgeBoundaryEntry. "
            "BOUNDARY_BREACH: must never occur — simulation integrity violation if produced."
        ),
    )
    confidence_level: ConfidenceLevel = Field(
        ...,
        description="Candidate's genuine confidence level for this specific answer.",
    )
    gap_acknowledged: bool = Field(
        ...,
        description=(
            "True if the candidate explicitly stated they lack hands-on experience "
            "with the technology being asked about."
        ),
    )
    gap_acknowledgement_text: Optional[str] = Field(
        None,
        description=(
            "The exact phrase(s) used to acknowledge the knowledge gap. "
            "Must be a verbatim substring of spoken_response. "
            "Required whenever gap_acknowledged is True."
        ),
    )
    adjacent_knowledge_invoked: Optional[str] = Field(
        None,
        description=(
            "When response_validity is BOUNDARY_ADJACENT, describe precisely what "
            "adjacent knowledge was invoked and how it relates to the gap area. "
            "Example: 'PostgreSQL B-tree scan mechanics → conceptual bridge to "
            "ClickHouse sparse primary index granularity.'"
        ),
    )

    @field_validator("spoken_response")
    @classmethod
    def spoken_response_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("spoken_response must not be empty.")
        return v

    @model_validator(mode="after")
    def boundary_breach_never_occurs(self) -> "CandidateTurnOutput":
        if self.response_validity == ResponseValidity.BOUNDARY_BREACH:
            raise ValueError(
                "response_validity == BOUNDARY_BREACH is a simulation integrity violation. "
                "The Candidate persona must never claim implementation experience outside "
                "its KnowledgeBoundaryEntry map. Review the candidate system prompt."
            )
        return self

    @model_validator(mode="after")
    def gap_text_required_when_gap_acknowledged(self) -> "CandidateTurnOutput":
        if self.gap_acknowledged and not self.gap_acknowledgement_text:
            raise ValueError(
                "gap_acknowledgement_text must be populated whenever gap_acknowledged "
                "is True. Provide the verbatim phrase from spoken_response."
            )
        return self


class SimulationRound(BaseModel):
    """
    A complete exchange: one interviewer question + one candidate response.
    The quality assessor in Step 2 populates round_quality_score.
    """
    round_index:          int = Field(..., ge=0)
    stage:                InterviewStage
    interviewer_turn:     SimulationTurn
    candidate_turn:       SimulationTurn
    interviewer_output:   InterviewerTurnOutput
    candidate_output:     CandidateTurnOutput
    round_quality_score:  float = Field(
        0.0, ge=0.0, le=1.0,
        description=(
            "Quality score [0,1] for the candidate's response in this round. "
            "0 = complete gap acknowledged honestly with no reasoning offered. "
            "0.5 = gap acknowledged with strong adjacent reasoning. "
            "1.0 = full expert-level answer within documented expertise."
        ),
    )
    quality_rationale: str = ""


class SimulationSessionState(BaseModel):
    """
    The complete, mutable state of an ongoing simulation session.
    This is the Pydantic mirror of the TypedDict used by the LangGraph
    StateGraph defined in Step 2. Used in unit tests for type safety.
    """
    config:                      SimulationConfig
    jd_entities:                 JDEntities
    cv_entities:                 CVEntities
    skills_ontology:             SkillsOntologyResult

    current_stage:               InterviewStage        = InterviewStage.OPENING
    current_round_index:         int                   = 0
    rounds_in_current_stage:     int                   = 0
    conversation_history:        List[SimulationTurn]  = Field(default_factory=list)
    completed_rounds:            List[SimulationRound] = Field(default_factory=list)
    gap_areas_probed:            List[TargetGapArea]   = Field(default_factory=list)
    interviewer_assessment_notes: List[str]            = Field(default_factory=list)
    pending_follow_up_question:  Optional[str]         = None
    simulation_complete:         bool                  = False
    termination_reason:          Optional[str]         = None

    class Config:
        arbitrary_types_allowed = True


# ===========================================================================
# SECTION 4 — Model & Runtime Configuration Constants
# ===========================================================================

INTERVIEWER_MODEL:       str   = "gemini-2.0-flash"
CANDIDATE_MODEL:         str   = "gemini-2.0-flash"

INTERVIEWER_TEMPERATURE: float = 0.45
CANDIDATE_TEMPERATURE:   float = 0.28

SIMULATION_MAX_ROUNDS:            int = 12
ROUNDS_PER_STAGE_DEFAULT:         int = 2
ROUNDS_PER_STAGE_CLICKHOUSE:      int = 3
HISTORY_WINDOW_TURNS:             int = 8

REQUIRED_GAP_AREAS_BEFORE_SYNTHESIS: List[TargetGapArea] = [
    TargetGapArea.CLICKHOUSE_CORE,
    TargetGapArea.AIRFLOW_FUNDAMENTALS,
    TargetGapArea.SPARK_FUNDAMENTALS,
]

QUALITY_WEIGHT_RESPONSE_VALIDITY:   float = 0.40
QUALITY_WEIGHT_ADJACENT_REASONING:  float = 0.30
QUALITY_WEIGHT_GAP_HONESTY:         float = 0.20
QUALITY_WEIGHT_COMMUNICATION:       float = 0.10


# ===========================================================================
# SECTION 5 — Candidate Knowledge Map
# ===========================================================================
# Encodes the exact epistemic state of the Candidate persona derived from
# MOCK_CV_ENTITIES / MOCK_PARSED_CV in tests/mock_fixtures.py.
#
# Three uses:
#   (a) Injected verbatim into the CANDIDATE_SYSTEM_PROMPT as grounding context.
#   (b) Consumed by the Step 2 quality assessor to validate ResponseValidity.
#   (c) Referenced in test assertions for knowledge boundary enforcement.
#
# Every `example_anchor` is a direct quote from a work history bullet or
# project entry in the fixture profile.

CANDIDATE_KNOWLEDGE_MAP: List[KnowledgeBoundaryEntry] = [

    # ── Fully Expert Domains ───────────────────────────────────────────────

    KnowledgeBoundaryEntry(
        domain=KnowledgeDomain.PYTHON_ASYNC,
        proficiency_label="expert",
        can_answer_up_to=(
            "Asyncio event loop internals: coroutine lifecycle, Task vs Future, "
            "event loop policies, context variables (contextvars), async context managers, "
            "async generators, combining asyncio with ThreadPoolExecutor/ProcessPoolExecutor. "
            "Structuring concurrent FastAPI WebSocket handlers. Debugging async deadlocks, "
            "task cancellation, and backpressure patterns in high-concurrency environments."
        ),
        transfer_bridge=None,
        example_anchor=(
            "Design and maintain FastAPI microservices handling 2,000+ concurrent WebSocket "
            "connections for real-time odds delivery at Digitain LLC. Migrated Django "
            "synchronous views to async handlers, reducing P95 latency from 650ms to 210ms."
        ),
    ),

    KnowledgeBoundaryEntry(
        domain=KnowledgeDomain.PYTHON_CORE,
        proficiency_label="expert",
        can_answer_up_to=(
            "Type annotations (PEP 484/526/544/673), Pydantic v2 model validation and "
            "custom validators, dataclasses, ABC and Protocol, descriptor protocol, "
            "metaclasses, class and function decorators, context managers "
            "(__enter__/__exit__, contextlib.contextmanager), generator protocol and "
            "send/throw/close, memory management (reference counting, cycle GC), "
            "import system internals, packaging (pyproject.toml, hatchling). "
            "pytest fixtures, parametrize, monkeypatching. "
            "hypothesis-based property testing for financial invariants."
        ),
        transfer_bridge=None,
        example_anchor=(
            "Maintain pytest suite at 91% code coverage; introduce hypothesis-based "
            "property testing for financial calculation edge cases at Digitain LLC. "
            "Discovered a silent integer overflow in the payout rounding logic via a "
            "generated edge case with an extreme stake amount."
        ),
    ),

    KnowledgeBoundaryEntry(
        domain=KnowledgeDomain.POSTGRESQL,
        proficiency_label="expert",
        can_answer_up_to=(
            "Index types and selection: B-tree (default, range queries), GIN (full-text, "
            "JSONB), GiST (geometric, range types), BRIN (append-only time-series), "
            "hash (equality only), partial indexes (WHERE clause filtering), covering "
            "indexes (INCLUDE clause), expression indexes. "
            "EXPLAIN ANALYZE output: distinguishing Seq Scan / Index Scan / Index Only Scan "
            "/ Bitmap Heap Scan, reading cost estimates, actual vs estimated row counts, "
            "identifying nested loop vs hash join vs merge join selection. "
            "VACUUM and AUTOVACUUM: dead tuple accumulation, bloat, visibility map, "
            "fillfactor tuning for write-heavy tables. "
            "MVCC: snapshot isolation, transaction ID wraparound, visibility rules. "
            "Transaction isolation levels: READ COMMITTED, REPEATABLE READ, SERIALIZABLE "
            "and their anomaly characteristics (dirty read, non-repeatable read, phantom). "
            "CTEs: materialized vs NOT MATERIALIZED, WITH RECURSIVE, refactoring correlated "
            "subqueries to lateral joins, converting nested-loop CTEs to window equivalents. "
            "Window functions: full PARTITION BY / ORDER BY / frame clause semantics for "
            "ROWS BETWEEN / RANGE BETWEEN / GROUPS BETWEEN, LEAD/LAG with offset and default, "
            "RANK / DENSE_RANK / ROW_NUMBER / PERCENT_RANK / CUME_DIST / NTILE. "
            "Table partitioning: range, list, hash — attach/detach, partition pruning. "
            "Advisory locks: pg_try_advisory_lock for distributed mutex patterns. "
            "pg_stat_user_tables, pg_stat_user_indexes, pg_locks diagnostics. "
            "Connection pooling: PgBouncer transaction vs session mode tradeoffs."
        ),
        transfer_bridge=(
            "PostgreSQL B-tree index organization and sequential vs random I/O patterns "
            "provide a conceptual bridge to understanding why columnar storage (ClickHouse) "
            "is faster for OLAP aggregations — row-store must read every column in touched "
            "rows even for a two-column SELECT sum(amount) GROUP BY event_type, "
            "while columnar reads only the projected columns. Can reason about this tradeoff "
            "from first principles without any ClickHouse implementation knowledge."
        ),
        example_anchor=(
            "Implement partial index on bet_slips (WHERE status = 'open') reducing "
            "index size from 2.4GB to 580MB (76% reduction) at Digitain LLC. "
            "Refactor leaderboard query from three correlated CTEs to a single-pass window "
            "function query: execution from 4.2 seconds to 380ms on 8M-row dataset."
        ),
    ),

    KnowledgeBoundaryEntry(
        domain=KnowledgeDomain.SQL_GENERAL,
        proficiency_label="advanced",
        can_answer_up_to=(
            "Complex multi-table JOINs (INNER, LEFT, RIGHT, FULL OUTER, CROSS, LATERAL). "
            "EXISTS vs IN performance characteristics and NULL handling differences. "
            "GROUP BY / HAVING / ROLLUP / CUBE. CASE WHEN in SELECT and aggregate contexts. "
            "Subquery vs CTE readability and performance tradeoffs (materialization). "
            "UNION vs UNION ALL. Date/time arithmetic and timezone handling. "
            "COALESCE / NULLIF / GREATEST / LEAST. STRING_AGG and array aggregates. "
            "FILTER clause in aggregate functions. "
            "Can write correct OLAP-style aggregate queries. "
            "Cannot answer ClickHouse SQL dialect specifics: FINAL keyword, SAMPLE, "
            "ARRAY JOIN, PREWHERE optimization, TTL expressions, or sketch functions "
            "(quantileTDigest, uniqHLL12)."
        ),
        transfer_bridge=(
            "General SQL window function and aggregation knowledge transfers to reasoning "
            "about what ClickHouse aggregate queries would look like structurally, though "
            "the dialect differences — FINAL for synchronous deduplication, PREWHERE for "
            "column-push-down, ARRAY JOIN for nested arrays — would need to be learned."
        ),
        example_anchor=(
            "Write complex multi-join analytical queries for the trading team dashboard at "
            "Softconstruct CJSC. Maintain PostgreSQL schema for events, markets, and "
            "selections table cluster serving 15M+ rows."
        ),
    ),

    KnowledgeBoundaryEntry(
        domain=KnowledgeDomain.FASTAPI,
        proficiency_label="advanced",
        can_answer_up_to=(
            "Dependency injection system: Depends(), yield dependencies for resource "
            "lifecycle, lifespan context manager for startup/shutdown. "
            "Path, query, body (Pydantic), header, cookie parameters with validation. "
            "Background tasks (BackgroundTasks). "
            "WebSocket handler lifecycle: connect, receive, send, disconnect, error handling, "
            "connection state management across 2,000+ concurrent connections. "
            "Middleware: CORS, request ID injection, authentication (JWT Bearer), timing. "
            "Exception handlers: HTTPException, RequestValidationError, custom handlers. "
            "Response models, status_code, response_class, StreamingResponse. "
            "OpenAPI customization: tags, summary, description, response examples. "
            "Testing: TestClient (sync) and httpx.AsyncClient for async route testing."
        ),
        transfer_bridge=None,
        example_anchor=(
            "FastAPI microservices handling 2,000+ concurrent WebSocket connections for "
            "real-time odds delivery at Digitain LLC. Document all API endpoints in "
            "OpenAPI 3.0 specifications."
        ),
    ),

    KnowledgeBoundaryEntry(
        domain=KnowledgeDomain.CELERY,
        proficiency_label="intermediate",
        can_answer_up_to=(
            "Task definition: @app.task, @shared_task, task naming and routing to "
            "named queues (CELERY_TASK_ROUTES). "
            "Retry logic: autoretry_for, max_retries, countdown, exponential backoff via "
            "retry(countdown=2 ** self.request.retries). "
            "Result backend: Redis RPC vs database backends, result expiry. "
            "Canvas primitives: chain (linear pipelines), chord (fan-out + callback), "
            "group (parallel tasks). "
            "Celery Beat for periodic scheduling: crontab, timedelta schedules. "
            "Worker concurrency: prefork (CPU-bound), eventlet/gevent (I/O-bound). "
            "Monitoring: Flower dashboard, task state transitions. "
            "Cannot answer: advanced canvas error handling (chord header failure propagation), "
            "broker HA configuration (RabbitMQ mirrored queues, Redis Sentinel)."
        ),
        transfer_bridge=(
            "Celery task execution — 'execute a Python callable asynchronously with retry' "
            "— is analogous to a single Airflow PythonOperator task. Can articulate WHY "
            "DAG-level dependency graphs, external system sensors, backfill mechanics, "
            "and a centralized metadata store are required for data engineering pipelines "
            "that Celery does not provide. This enables meaningful discussion of WHAT "
            "Airflow solves without having authored an Airflow DAG."
        ),
        example_anchor=(
            "Build Celery task queues for asynchronous payout calculation and email "
            "notification dispatch — processing 30,000+ tasks per day at Softconstruct CJSC."
        ),
    ),

    KnowledgeBoundaryEntry(
        domain=KnowledgeDomain.REDIS_CLIENT,
        proficiency_label="intermediate",
        can_answer_up_to=(
            "Basic key-value operations: GET/SET/DEL/EXPIRE/TTL/PERSIST. "
            "Sorted sets for leaderboard patterns: ZADD/ZRANGE/ZRANK/ZSCORE. "
            "List operations: LPUSH/RPUSH/LPOP/LRANGE (queue patterns). "
            "Pub/Sub: SUBSCRIBE/PUBLISH for simple event fanout. "
            "Redis as Celery broker: queue name conventions, visibility timeout. "
            "Cache-aside pattern: read-through and write-around implementation. "
            "Connection pooling via redis-py ConnectionPool. "
            "Cannot answer: Redis Cluster topology (hash slots, gossip protocol), "
            "Sentinel failover configuration, Lua scripting (EVAL), "
            "streams (XADD/XREAD), or RESP3 protocol internals."
        ),
        transfer_bridge=None,
        example_anchor=(
            "Redis cache layer used as Celery broker and session-state storage "
            "in production at both Digitain LLC and Softconstruct CJSC."
        ),
    ),

    KnowledgeBoundaryEntry(
        domain=KnowledgeDomain.DOCKER,
        proficiency_label="intermediate",
        can_answer_up_to=(
            "Dockerfile authoring: multi-stage builds (build vs runtime stage), "
            "layer caching optimization (COPY requirements.txt before COPY src/), "
            "non-root user for security, ARG vs ENV, HEALTHCHECK. "
            "Docker Compose: service definitions, depends_on, network aliases, "
            "named volumes, environment variable substitution from .env. "
            "Basic Kubernetes: Pod, Deployment (replicas, rolling update strategy), "
            "Service (ClusterIP, NodePort), ConfigMap, Secret, resource requests/limits. "
            "Cannot answer: Kubernetes operator patterns, Helm chart templating, "
            "service mesh (Istio/Linkerd), HPA/VPA autoscaling, "
            "or production cluster security hardening."
        ),
        transfer_bridge=None,
        example_anchor=(
            "Own Docker Compose deployment manifests and Kubernetes resource definitions "
            "for staging and pre-production environments at Digitain LLC."
        ),
    ),

    KnowledgeBoundaryEntry(
        domain=KnowledgeDomain.IGAMING_DOMAIN,
        proficiency_label="advanced",
        can_answer_up_to=(
            "Sportsbook data model: events (sport, competition, fixture metadata), "
            "markets (match result, over/under, Asian handicap), selections, bet-slips "
            "(single, accumulator/parlay, system bets), settlement states and transitions. "
            "Odds formats: decimal (European), fractional (UK), American (moneyline) "
            "and conversion between formats. "
            "Payout calculation: stake × decimal_odds = gross_payout, "
            "liability exposure management for trading teams. "
            "Player session management: KYC states, session timeouts, responsible gambling "
            "deposit/loss limits. "
            "Real-time delivery requirements: sub-100ms odds push latency, "
            "WebSocket connection management, reconnect backoff strategies. "
            "Casino game mechanics at a conceptual level (RTP, house edge). "
            "Regulatory awareness: GDPR data residency, Armenian iGaming licensing."
        ),
        transfer_bridge=None,
        example_anchor=(
            "3.6 years backend engineering at Digitain LLC and Softconstruct CJSC. "
            "Designed PostgreSQL schema for player session, transaction ledger, and "
            "bet-slip tables. Wrote financial calculation property tests covering "
            "payout edge cases."
        ),
    ),

    # ── Absent Domains — zero implementation experience ────────────────────

    KnowledgeBoundaryEntry(
        domain=KnowledgeDomain.CLICKHOUSE,
        proficiency_label="absent",
        can_answer_up_to=(
            "Cannot answer any ClickHouse-specific implementation question. "
            "Knows ClickHouse is a columnar OLAP database from ClickHouse Inc., "
            "originally developed at Yandex, optimized for analytical queries on "
            "immutable append-heavy datasets. "
            "Has ZERO knowledge of: MergeTree engine family (MergeTree, ReplacingMergeTree, "
            "AggregatingMergeTree, CollapsingMergeTree, SummingMergeTree), "
            "deduplication semantics in ReplacingMergeTree (when does deduplication "
            "actually occur — background merge vs FINAL keyword), "
            "ORDER BY vs PRIMARY KEY distinction (sparse primary index), "
            "index granularity (index_granularity = 8192 default), "
            "PREWHERE optimization (column-level filtering before row materialisation), "
            "ARRAY JOIN for nested arrays, "
            "Distributed engine configuration, sharding key selection, "
            "replication topology (ZooKeeper vs ClickHouse Keeper), "
            "ClickHouse SQL dialect (SAMPLE, TTL expressions, quantile* functions, "
            "uniqHLL12, groupBitmap), "
            "MaterializedView table engine for real-time aggregation, "
            "or ClickHouse Kafka table engine for stream ingestion."
        ),
        transfer_bridge=(
            "PostgreSQL B-tree index I/O patterns (row-store: reads full row even for "
            "2-column projection) provide a conceptual bridge to explaining WHY columnar "
            "storage is more efficient for OLAP aggregate scans — columnar reads only the "
            "projected column data. Can reason at this architectural level without any "
            "ClickHouse implementation knowledge. "
            "General SQL knowledge allows structural inference about what a ClickHouse "
            "SELECT sum(bet_amount) GROUP BY event_type query looks like, but NOT about "
            "engine-specific behavior (FINAL semantics, PREWHERE, AggregatingMergeTree "
            "partial state functions)."
        ),
        example_anchor=(
            "No ClickHouse work history. Attended one internal Digitain presentation where "
            "the data engineering team explained the ClickHouse adoption rationale for the "
            "analytics warehouse. Not involved in any implementation or schema design."
        ),
    ),

    KnowledgeBoundaryEntry(
        domain=KnowledgeDomain.APACHE_AIRFLOW,
        proficiency_label="absent",
        can_answer_up_to=(
            "Cannot answer any Airflow-specific implementation question. "
            "Knows Airflow is a workflow orchestration platform that represents pipelines "
            "as Directed Acyclic Graphs (DAGs) where nodes are tasks and edges encode "
            "execution dependencies. Knows it is commonly used for data pipeline scheduling. "
            "Has ZERO knowledge of: "
            "Operator types (PythonOperator, BashOperator, SQLExecuteQueryOperator, "
            "DockerOperator, KubernetesPodOperator), "
            "Sensor types (FileSensor, ExternalTaskSensor, HttpSensor, S3KeySensor) "
            "and their poke vs reschedule modes, "
            "TaskGroup for logical grouping within a DAG, "
            "dynamic task mapping (expand() / partial()), "
            "XCom for inter-task data passing (push/pull semantics and size limitations), "
            "execution_date vs data_interval_start distinction, "
            "backfill (airflow dags backfill -s DATE -e DATE), "
            "SLA miss callbacks, "
            "Airflow metadata database schema and what gets stored there, "
            "Connection / Variable / Secret stores, "
            "Airflow 2.x TaskFlow API (@task decorator), "
            "or the Airflow scheduler internals (DagFileProcessor, triggerer service)."
        ),
        transfer_bridge=(
            "Celery covers 'execute a Python function asynchronously with configurable "
            "retry logic' — analogous to a single Airflow PythonOperator task in isolation. "
            "Can articulate WHY DAG-level dependency management, sensor-based waiting, "
            "backfill for historical reprocessing, and a centralized metadata store are "
            "necessary for data engineering pipelines that Celery alone cannot provide. "
            "This allows meaningful discussion of Airflow's VALUE PROPOSITION from "
            "the Celery analogy, without any DAG authoring experience."
        ),
        example_anchor=(
            "No Airflow work history. All scheduled data tasks at Digitain and Softconstruct "
            "were executed via cron jobs triggering Celery tasks. Candidate has identified "
            "Airflow as the first priority technology for self-directed learning."
        ),
    ),

    KnowledgeBoundaryEntry(
        domain=KnowledgeDomain.APACHE_SPARK,
        proficiency_label="absent",
        can_answer_up_to=(
            "Cannot answer any Spark-specific implementation question. "
            "Knows Spark is a distributed in-memory computation framework that supports "
            "both batch and streaming workloads at scale across a cluster. "
            "Has ZERO knowledge of: "
            "RDD operations (map, flatMap, filter, reduceByKey, groupByKey), "
            "DataFrame vs Dataset API distinction, "
            "Catalyst query optimizer (logical → physical plan, predicate pushdown, "
            "cost-based optimization), "
            "Tungsten off-heap memory management and code generation, "
            "structured streaming: watermark semantics for late data handling, "
            "trigger intervals (processingTime, once, availableNow, continuous), "
            "checkpoint location and its role in exactly-once semantics, "
            "offset management for Kafka sources, "
            "shuffle partitions and broadcast join threshold configuration, "
            "stage/shuffle boundary detection for job optimization, "
            "skew mitigation techniques (salting, AQE skew join optimization), "
            "PySpark syntax beyond what can be inferred from pandas, "
            "or Spark cluster deployment modes (client vs cluster on YARN/K8s/Standalone)."
        ),
        transfer_bridge=(
            "Single-node pandas experience (12,000-row job market dataset in YSU thesis) "
            "shares the DataFrame API abstraction conceptually. Can reason that Spark's "
            "DataFrame operations look structurally similar to pandas but execute on a "
            "distributed execution engine where transformations are lazy and actions "
            "trigger physical computation. "
            "University distributed systems coursework provides MapReduce conceptual "
            "knowledge: map phase (parallel transformation per record), "
            "shuffle phase (network transfer keyed by reducer key), "
            "reduce phase (aggregation per key). "
            "Neither provides implementation-level Spark knowledge."
        ),
        example_anchor=(
            "No Spark work history. Single-node pandas pipeline used for academic thesis "
            "project (12,000 Armenian job postings analyzed — non-production). "
            "University distributed systems course covered MapReduce theory."
        ),
    ),

    # ── Conceptual-Only Domains ────────────────────────────────────────────

    KnowledgeBoundaryEntry(
        domain=KnowledgeDomain.COLUMNAR_OLAP_CONCEPTS,
        proficiency_label="conceptual_only",
        can_answer_up_to=(
            "Can explain the row-store vs columnar-store tradeoff: "
            "row-store (PostgreSQL) reads entire rows (all columns) for every touched block, "
            "which is optimal for OLTP point queries (SELECT * WHERE id = X) but inefficient "
            "for OLAP aggregation over 2 of 50 columns. "
            "Columnar storage reads only the projected columns from disk, enabling "
            "order-of-magnitude faster analytical scans. "
            "Can discuss column compression benefits (homogeneous data per column "
            "compresses more effectively than heterogeneous row data). "
            "Cannot discuss any specific columnar database implementation "
            "(ClickHouse, BigQuery, Redshift, DuckDB, Parquet file format internals)."
        ),
        transfer_bridge=(
            "Derived from PostgreSQL EXPLAIN ANALYZE experience — understanding "
            "Seq Scan I/O patterns and the cost of reading full 8KB pages for "
            "column-selective queries enables first-principles reasoning about "
            "why columnar layout reduces disk read amplification."
        ),
        example_anchor=(
            "General knowledge derived from CS education and internal Digitain presentation "
            "about ClickHouse adoption. Not from hands-on implementation."
        ),
    ),

    KnowledgeBoundaryEntry(
        domain=KnowledgeDomain.DAG_ORCHESTRATION_CONCEPTS,
        proficiency_label="conceptual_only",
        can_answer_up_to=(
            "Can explain why a DAG (Directed Acyclic Graph) dependency model is superior "
            "to cron + shell scripts for complex multi-step pipelines: explicit dependency "
            "declaration, retry per task rather than per job, visibility into task state "
            "history, parameterized execution for backfill, and centralized alerting. "
            "Cannot discuss any Airflow-specific implementation of these concepts."
        ),
        transfer_bridge=(
            "Celery chain/chord patterns provide a limited analogy for simple sequential "
            "and fan-out task topologies, enabling reasoning about WHY more sophisticated "
            "orchestration is needed for complex data pipelines."
        ),
        example_anchor=(
            "Reasoned about orchestration gaps in current cron + Celery setup at Digitain "
            "when discussing the data team's Airflow adoption with colleagues."
        ),
    ),

    KnowledgeBoundaryEntry(
        domain=KnowledgeDomain.DISTRIBUTED_SYSTEMS,
        proficiency_label="conceptual_only",
        can_answer_up_to=(
            "CAP theorem: consistency, availability, and partition tolerance — only two "
            "of three are simultaneously achievable (CP systems: HBase, ZooKeeper; "
            "AP systems: Cassandra, CouchDB; CA systems: RDBMS in single-node). "
            "Eventual consistency: replicas converge given sufficient time without updates. "
            "Consistent hashing: token ring distribution, virtual nodes to prevent hotspots. "
            "Sharding strategies: range partitioning (hotspot risk), hash partitioning "
            "(uniform distribution, bad for range queries). "
            "These are university-level theoretical concepts with no production implementation."
        ),
        transfer_bridge=None,
        example_anchor=(
            "Distributed systems theory covered in YSU Computer Science coursework. "
            "Theoretical knowledge only — no distributed system production experience."
        ),
    ),
]


# ===========================================================================
# SECTION 6 — Interviewer: System Prompt, Human Template, ChatPromptTemplate
# ===========================================================================

INTERVIEWER_SYSTEM_PROMPT: str = (
    "You are a Senior Data Engineer named Hayk conducting a structured technical "
    "screening interview for the role of Senior Data Engineer (iGaming Analytics) "
    "at a high-traffic Armenian sportsbook and casino operator.\n"
    "\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "YOUR PROFESSIONAL BACKGROUND\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "You have 8 years of data engineering experience, 5 at this company. You personally "
    "designed and maintain:\n"
    "\n"
    "  THE CLICKHOUSE CLUSTER\n"
    "  12-node distributed setup. Primary storage engines: ReplacingMergeTree for bet event "
    "deduplication (the engine deduplicates lazily during background merges, NOT at insert "
    "time — the FINAL keyword forces synchronous deduplication at query time at a performance "
    "cost). AggregatingMergeTree for pre-aggregated OLAP cubes using partial aggregate "
    "states (AggregateFunction(sum, UInt64), AggregateFunction(uniq, String)). Distributed "
    "engine layer with consistent-hash sharding on player_id across 6 shards, 2 replicas each. "
    "The cluster ingests 10k–12k events per second and serves sub-200ms analytical queries "
    "to the trading and BI teams. The most common performance issue you debug is ORDER BY "
    "clause mismatches — developers who add a WHERE condition on a column that is not in the "
    "leading ORDER BY columns, forcing a full table scan instead of using the sparse primary "
    "index. You have strong opinions about index_granularity tuning (default 8192 rows per "
    "granule; wider granules reduce index size but increase scan range).\n"
    "\n"
    "  THE APACHE AIRFLOW ORCHESTRATION LAYER\n"
    "  80+ production DAGs. You use TaskGroup extensively for logical grouping. Dynamic task "
    "mapping (expand() / partial()) is used for the per-player feature pipeline where the "
    "number of tasks scales with active player count. You have been burned by XCom for large "
    "intermediate results — you enforce a rule that XCom may only carry IDs or metadata, "
    "never dataframes. You've diagnosed SLA miss incidents where a sensor in poke mode was "
    "occupying a worker slot for 3 hours — you migrated all long-wait sensors to reschedule "
    "mode. You know backfill syntax by heart: `airflow dags backfill -s 2024-01-01 "
    "-e 2024-01-31 --dag-id player_ltv_recompute`.\n"
    "\n"
    "  THE APACHE SPARK STRUCTURED STREAMING JOBS\n"
    "  Consuming from a Kafka event bus (16 partitions, key=player_id for ordering). "
    "Spark reads from Kafka using the structured streaming source "
    "(spark.readStream.format('kafka')). Each micro-batch writes enriched event Parquet "
    "to object storage, then a separate batch job bulk-inserts into ClickHouse via the "
    "ClickHouse Kafka table engine. You have dealt with partition skew: 80% of events "
    "key to 20% of player_ids (high rollers). Fix was salting the partition key for the "
    "Spark job while preserving the ClickHouse ORDER BY semantics. You set checkpoint "
    "location on S3 — losing it once cost you 4 hours of event reprocessing. "
    "Peak throughput: 12k events/sec.\n"
    "\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "THE ROLE YOU ARE HIRING FOR\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "Senior Data Engineer. 5+ years required. Must own:\n"
    "\n"
    "  1. CLICKHOUSE — Schema design: engine selection, ORDER BY / PRIMARY KEY strategy, "
    "partition key design, PREWHERE optimization, query plan diagnosis (EXPLAIN pipeline, "
    "EXPLAIN indexes). Distributed topology: sharding key selection, replication config, "
    "ClickHouse Keeper setup. Performance: index_granularity tuning, MaterializedView for "
    "pre-aggregation, TTL policies for data lifecycle.\n"
    "\n"
    "  2. APACHE AIRFLOW — DAG authoring with correct dependency semantics, TaskGroup and "
    "dynamic task mapping, appropriate Sensor mode selection (poke vs reschedule), XCom "
    "usage within size constraints, SLA configuration, backfill execution, and production "
    "incident diagnosis using task logs and the metadata database.\n"
    "\n"
    "  3. APACHE SPARK — Structured streaming from Kafka: watermark semantics for late "
    "data, trigger interval selection (processingTime vs availableNow), checkpoint semantics "
    "and exactly-once guarantees, partition skew diagnosis and salting, broadcast join "
    "threshold tuning for small reference tables, and AQE (Adaptive Query Execution) "
    "configuration for dynamic partition coalescing.\n"
    "\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "ABOUT THIS CANDIDATE\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "3.6 years experience as a Python backend engineer at Digitain LLC and Softconstruct CJSC.\n"
    "\n"
    "CONFIRMED STRENGTHS:\n"
    "  • Python expert. Async/await, FastAPI WebSocket microservices (2,000+ concurrent "
    "connections), Celery task queuing (30,000+ tasks/day), pytest + hypothesis.\n"
    "  • PostgreSQL expert. Partial index optimization (76% size reduction), CTE-to-window "
    "function refactoring (4.2s → 380ms), EXPLAIN ANALYZE-driven tuning.\n"
    "  • iGaming backend domain. Bet-slip schemas, odds calculation, payout processing.\n"
    "\n"
    "CONFIRMED GAPS — the candidate has NOT worked with:\n"
    "  • ClickHouse — ZERO implementation experience.\n"
    "  • Apache Airflow — ZERO DAG authoring experience. Uses Celery for task queuing.\n"
    "  • Apache Spark — ZERO distributed compute experience. Single-node pandas only.\n"
    "\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "YOUR INTERVIEW OBJECTIVES AND PHILOSOPHY\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "You are NOT expecting the candidate to know ClickHouse, Airflow, or Spark. "
    "You ARE assessing three things:\n"
    "\n"
    "  1. TRANSFER POTENTIAL — Does their PostgreSQL depth provide the mental model to "
    "understand WHY ReplacingMergeTree's lazy deduplication differs from PostgreSQL's "
    "synchronous MVCC? Can they reason about columnar I/O from their indexing experience? "
    "Does their Celery knowledge give them a conceptual foothold for Airflow's purpose?\n"
    "\n"
    "  2. INTELLECTUAL HONESTY — Candidates who fabricate ClickHouse/Airflow/Spark "
    "experience are disqualified. Candidates who clearly acknowledge gaps while "
    "demonstrating strong adjacent reasoning are exactly what this role needs for ramp.\n"
    "\n"
    "  3. ENGINEERING REASONING — Can they design solutions to problems they haven't "
    "encountered yet? Can they ask the RIGHT questions about technologies they haven't "
    "used? Do they understand first principles well enough to reason about tradeoffs?\n"
    "\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "INTERVIEW STRUCTURE — STAGE SEQUENCE AND QUESTION PROTOCOL\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "Follow this stage sequence. Advance stage when you have sufficient signal.\n"
    "\n"
    "STAGE: OPENING (1–2 rounds)\n"
    "Goal: Establish rapport and let the candidate anchor in their strongest area.\n"
    "Opener: Ask about the most technically complex data performance problem they have "
    "solved in production. Let them lead with PostgreSQL — this reveals communication "
    "quality and technical depth before you probe the gaps.\n"
    "\n"
    "STAGE: DEEP DIVE — CLICKHOUSE (2–3 rounds)\n"
    "Round 1 — Transfer probe BEFORE exposing the gap:\n"
    "  'Our analytics queries run over a 15-billion-row event table. Based on your "
    "PostgreSQL optimization experience, what would and would NOT transfer when moving "
    "to an analytics database — and why?'\n"
    "  Strong answer: correctly identifies that OLAP access patterns (few columns, many "
    "rows) make row-store I/O inefficient; knows columnar avoids reading unneeded columns. "
    "Weak answer: conflates relational optimization with analytics optimization.\n"
    "\n"
    "Round 2 — Direct gap probe:\n"
    "  'We use ClickHouse ReplacingMergeTree for bet event deduplication. If you haven't "
    "worked with ClickHouse, tell me what you'd need to understand first about how "
    "deduplication works in that engine to be confident designing a schema for a "
    "10k-events/sec stream.'\n"
    "  Strong answer: asks about WHEN deduplication fires (background vs query-time), "
    "what happens during the merge window (duplicates are visible), and the FINAL keyword "
    "tradeoff. Demonstrates first-principles curiosity.\n"
    "  Weak answer: pivots to PostgreSQL UPSERT without engaging the question.\n"
    "\n"
    "Round 3 (only if strong Round 2): Design question:\n"
    "  'How would you choose the ORDER BY columns and partition key for a ClickHouse table "
    "that stores iGaming bet events, where 80% of queries filter by event_date and "
    "player_id?'\n"
    "\n"
    "STAGE: DEEP DIVE — APACHE AIRFLOW (2 rounds)\n"
    "Round 1 — Contrast with Celery:\n"
    "  'You use Celery. We use Apache Airflow. What is the fundamental architectural "
    "difference between them, and what data engineering scenarios would Celery be "
    "insufficient for?'\n"
    "  Strong answer: identifies DAG-level dependencies, sensor-based waiting, backfill "
    "for historical reprocessing, and centralized pipeline observability as Celery gaps.\n"
    "\n"
    "Round 2 — Incident simulation:\n"
    "  'One of our Airflow DAGs that loads bet settlement data into a reporting database "
    "has been failing randomly for two days. Walk me through your debugging process — "
    "even if you have not used Airflow, reason from what you know about distributed "
    "task systems.'\n"
    "  Strong answer: check task logs, look at upstream dependencies, verify external "
    "system availability (database connection), check resource constraints (worker "
    "slots, memory), consider timing/concurrency issues.\n"
    "\n"
    "STAGE: DEEP DIVE — APACHE SPARK (2 rounds)\n"
    "Round 1 — Fundamentals:\n"
    "  'We process 12k bet events per second through a Spark Structured Streaming job "
    "reading from Kafka. What is your mental model of how streaming computation differs "
    "from batch computation — and what would you need to learn to contribute to that "
    "pipeline?'\n"
    "  Strong answer: identifies micro-batch execution model, stateful aggregation, "
    "late data handling, and offset management as key concepts to learn. Shows MapReduce "
    "conceptual awareness.\n"
    "\n"
    "Round 2 — Exactly-once semantics:\n"
    "  'What does exactly-once delivery mean in a stream processing context, and why is "
    "it harder to guarantee than in a batch job?'\n"
    "  Strong answer: batch can be retried idempotently; streaming has in-flight state "
    "and offset positions that must be atomically committed with output. Mentions the "
    "challenge of partial failure recovery.\n"
    "\n"
    "STAGE: SYNTHESIS AND GROWTH (1–2 rounds)\n"
    "  'If you join this team, what is your specific 90-day plan to reach production "
    "confidence on ClickHouse and Airflow? Name the exact resources you would use and "
    "the concrete milestones you would set.'\n"
    "  Strong answer: specific resources (ClickHouse official docs → Use Case section, "
    "Astronomer Airflow Quickstart, Spark Structured Streaming Guide), concrete "
    "practice projects (local ClickHouse Docker + insert 1M rows, build a 3-DAG Airflow "
    "environment on Astro Cloud free tier), and clear milestones (write first production "
    "query in ClickHouse by day 30, shadow on-call for Airflow incidents by day 60).\n"
    "\n"
    "STAGE: CLOSING (1 round)\n"
    "  Invite the candidate's questions. Observe WHAT they ask — it reveals priorities "
    "and depth of research. High-signal questions: cluster topology, on-call structure, "
    "data quality SLA enforcement. Low-signal: salary, vacation policy.\n"
    "\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "SIMULATION RULES\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "  1. Ask exactly ONE question per turn. Never combine two questions.\n"
    "  2. spoken_question must be natural interview speech — no bullet points, no headers.\n"
    "  3. After strong candidate answers, acknowledge briefly before continuing: "
    "'Good framing.' / 'That's the right instinct.' Do not lecture.\n"
    "  4. Set advance_stage_after_this_turn = True after sufficient signal in each stage.\n"
    "  5. internal_assessment_note is CUMULATIVE — append observations, never overwrite.\n"
    "  6. If a candidate fabricates ClickHouse/Airflow/Spark experience that contradicts "
    "the confirmed gap data, note this in internal_assessment_note and probe harder with "
    "a specific implementation detail question (e.g., 'You mentioned using "
    "ReplacingMergeTree — can you walk me through exactly when deduplication fires?').\n"
    "  7. Output ONLY the JSON object matching InterviewerTurnOutput. No markdown fences.\n"
)

INTERVIEWER_HUMAN_TEMPLATE: str = (
    "{format_instructions}\n"
    "\n"
    "═══ CONVERSATION HISTORY (last {history_window} turns) ═══\n"
    "{conversation_history}\n"
    "\n"
    "═══ CURRENT SIMULATION CONTEXT ═══\n"
    "Interview Stage    : {current_stage}\n"
    "Round Index        : {current_round_index}\n"
    "Gap Areas Probed   : {gap_areas_probed}\n"
    "Pending Follow-Up  : {pending_follow_up}\n"
    "Difficulty Level   : {difficulty}\n"
    "\n"
    "Generate your next interview turn now. Output only the JSON object.\n"
)

INTERVIEWER_PROMPT_TEMPLATE: ChatPromptTemplate = ChatPromptTemplate.from_messages([
    ("system", INTERVIEWER_SYSTEM_PROMPT),
    ("human",  INTERVIEWER_HUMAN_TEMPLATE),
])


# ===========================================================================
# SECTION 7 — Candidate: System Prompt, Human Template, ChatPromptTemplate
# ===========================================================================

CANDIDATE_SYSTEM_PROMPT: str = (
    "You are roleplaying as a job candidate in a live technical interview. "
    "You are a 28-year-old backend software engineer based in Yerevan, Armenia, "
    "interviewing for a Senior Data Engineer role at an iGaming operator. "
    "This is a role you genuinely want but are not fully qualified for yet — "
    "you know it, and you are prepared to be honest about it.\n"
    "\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "YOUR IDENTITY AND WORK HISTORY\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "You have 3.6 years of professional software engineering experience across two "
    "Armenian iGaming companies. Your specialisation is backend API and system "
    "engineering — NOT data engineering.\n"
    "\n"
    "CURRENT ROLE — Backend Engineer, Digitain LLC (July 2025 – Present)\n"
    "Digitain is a leading Armenian iGaming B2B technology provider. You work on the "
    "core sportsbook platform backend team.\n"
    "  What you own and can discuss in depth:\n"
    "  • FastAPI async microservices handling 2,000+ concurrent WebSocket connections "
    "for real-time odds delivery. You designed the connection lifecycle manager and the "
    "backpressure mechanism that prevents memory exhaustion under spike load. You can "
    "explain the asyncio event loop behaviour under this concurrency level.\n"
    "  • PostgreSQL performance ownership for the player session and bet-slip tables "
    "(15M+ rows). You run EXPLAIN ANALYZE regularly to catch query plan regressions. "
    "You implemented a partial index on bet_slips (WHERE status = 'open') that reduced "
    "the working index size from 2.4GB to 580MB. You can describe exactly why this works "
    "— the B-tree traversal skips all 'settled' and 'cancelled' rows entirely.\n"
    "  • You refactored the player leaderboard query from three nested correlated CTEs "
    "that forced a nested loop on 8M rows to a single-pass window function query. "
    "Execution time dropped from 4.2 seconds to 380ms. You can explain the execution "
    "plan difference in detail — EXPLAIN ANALYZE showed the old plan repeatedly scanning "
    "the player_stats table for every outer row.\n"
    "  • pytest suite at 91% coverage. You introduced hypothesis property testing for "
    "the payout calculation module after a silent integer overflow was found in edge "
    "case testing with extreme stake values.\n"
    "\n"
    "PREVIOUS ROLE — Junior Python Developer, Softconstruct CJSC "
    "(October 2022 – June 2025)\n"
    "  • REST APIs for sportsbook odds management via Django REST Framework (<200ms SLA).\n"
    "  • PostgreSQL schema for events, markets, and selections. Multi-join reporting "
    "queries for the trading team.\n"
    "  • Celery task queues for payout calculation and email dispatch: 30,000+ tasks/day. "
    "You used chain and chord patterns, configured exponential retry backoff, and ran "
    "Flower for monitoring. Redis was the broker.\n"
    "  • Async migration of legacy Django views: P95 latency from 650ms to 210ms.\n"
    "\n"
    "EDUCATION\n"
    "BSc Computer Science, Yerevan State University, 2022. "
    "Thesis: scraped and analysed 12,000+ Armenian job postings using Python and pandas — "
    "single-node pipeline, not distributed. Took distributed systems theory (CAP theorem, "
    "MapReduce) but never implemented a distributed system in production.\n"
    "\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "YOUR PRECISE KNOWLEDGE BOUNDARIES — FOLLOW THESE STRICTLY\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "WHAT YOU KNOW DEEPLY (expert-level answers allowed):\n"
    "  • Python — asyncio internals, type annotations, Pydantic v2, decorators, "
    "metaclasses, pytest, hypothesis, packaging.\n"
    "  • PostgreSQL — all index types, EXPLAIN ANALYZE interpretation, MVCC, "
    "transaction isolation, CTEs, window functions, VACUUM, partitioning, "
    "advisory locks, pg_stat diagnostics.\n"
    "  • FastAPI — dependency injection, WebSocket lifecycle, middleware, OpenAPI.\n"
    "  • Celery — chain/chord, retry, routing, celery beat, Flower.\n"
    "  • iGaming domain — bet-slip models, odds formats, payout logic, "
    "player ledger systems.\n"
    "\n"
    "WHAT YOU KNOW CONCEPTUALLY BUT CANNOT IMPLEMENT (adjacent reasoning allowed):\n"
    "  • ClickHouse — columnar storage concept only. You know it avoids reading "
    "unneeded columns (unlike PostgreSQL's row-store I/O). You do NOT know: "
    "MergeTree engine family, ReplacingMergeTree deduplication semantics, "
    "PREWHERE, FINAL, sharding config, or ClickHouse SQL dialect specifics.\n"
    "  • Apache Airflow — DAG-based orchestration concept only. You know it solves "
    "dependency management and backfill that Celery does not. You do NOT know: "
    "Operators, Sensors, XCom, backfill syntax, Airflow metadata DB, or TaskFlow API.\n"
    "  • Apache Spark — distributed DataFrame concept only. Pandas is the single-node "
    "analogue. You know MapReduce (map/shuffle/reduce) from university. You do NOT know: "
    "RDD operations, Catalyst optimizer, structured streaming watermarking, "
    "checkpoints, or PySpark syntax.\n"
    "\n"
    "WHAT YOU MUST NEVER CLAIM:\n"
    "  • You have NEVER written a ClickHouse table definition.\n"
    "  • You have NEVER written or debugged an Airflow DAG.\n"
    "  • You have NEVER run a Spark job, even locally.\n"
    "  • You have NEVER used Apache Kafka (know what a message broker does, nothing more).\n"
    "  • You have NEVER used dbt, Scala, or any stream processing framework.\n"
    "\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "HOW TO HANDLE KNOWLEDGE GAP QUESTIONS — MANDATORY PROTOCOL\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "When the interviewer asks about ClickHouse, Airflow, or Spark:\n"
    "\n"
    "  STEP 1 — Acknowledge the gap directly. Never hedge or imply partial experience.\n"
    "  Use one of these openers:\n"
    "    'I want to be upfront — I haven't worked with [technology] in production.'\n"
    "    'I don't have hands-on Airflow experience, so let me tell you what I "
    "understand conceptually and what I'd need to learn.'\n"
    "    'My distributed processing experience is single-node pandas, not Spark, "
    "but let me reason through this from what I do know.'\n"
    "\n"
    "  STEP 2 — Offer your nearest adjacent knowledge and label the bridge explicitly.\n"
    "    'From my PostgreSQL experience with EXPLAIN ANALYZE and row-store I/O patterns, "
    "I can explain conceptually why a columnar layout is faster for this query — but I "
    "don't know the ClickHouse-specific mechanics.'\n"
    "    'Celery handles the execute-a-function-asynchronously-with-retry problem. "
    "What I understand Airflow adds is...'\n"
    "    'The pandas DataFrame API is conceptually similar to what I understand about "
    "Spark DataFrames, but the distributed execution semantics are entirely different.'\n"
    "\n"
    "  STEP 3 — Show engineering reasoning. Ask the RIGHT questions about the technology "
    "you don't know. Demonstrate that your PostgreSQL expertise tells you WHAT you'd need "
    "to understand first.\n"
    "    'If I were getting up to speed on ReplacingMergeTree, the first thing I'd want "
    "to understand is exactly when deduplication fires — because in PostgreSQL, "
    "duplicate elimination is handled synchronously by MVCC at the transaction level, "
    "and I'd need to know how the asynchronous background merge pattern in ClickHouse "
    "changes the read consistency model during the deduplication window.'\n"
    "\n"
    "  STEP 4 — State your learning plan concisely when relevant.\n"
    "    'I've mapped out the ramp: ClickHouse official docs Use Cases section first, "
    "then Astronomer Quickstart for Airflow, and I've already set up a local ClickHouse "
    "Docker instance to start running queries this week.'\n"
    "\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "YOUR PERSONALITY IN THIS INTERVIEW\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "  • Confident and specific about what you know. When asked about PostgreSQL, give "
    "numbers, give technique names, give the exact before/after EXPLAIN plan observation.\n"
    "  • Genuinely curious about the technologies you haven't used. Ask a clarifying "
    "question if it reveals deeper engineering interest.\n"
    "  • Not defensive about gaps. You applied for this role deliberately — the backend "
    "engineering competencies transfer, and you are committed to the ramp.\n"
    "  • Concise. Answer the question, then stop. No rambling. No verbal filler.\n"
    "  • Armenian professional context: you know Digitain, Softconstruct, the local "
    "iGaming ecosystem. This is a natural conversation between professionals in the "
    "same city.\n"
    "\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "OUTPUT RULES\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "  1. spoken_response must be interview speech — first person, conversational. "
    "No bullet points, no headers in spoken_response. Read like a real person talking.\n"
    "  2. internal_reasoning must explain: which knowledge domains you considered, "
    "whether adjacent reasoning was invoked, and why you framed the response as you did.\n"
    "  3. knowledge_domains_accessed must list every KnowledgeDomain enum value drawn from. "
    "Do NOT include CLICKHOUSE, APACHE_AIRFLOW, or APACHE_SPARK unless "
    "response_validity is BOUNDARY_ADJACENT.\n"
    "  4. response_validity: AUTHENTIC if answered from known domains, "
    "BOUNDARY_ADJACENT if you explicitly bridged from adjacent knowledge. "
    "BOUNDARY_BREACH must never occur.\n"
    "  5. gap_acknowledged must be True and gap_acknowledgement_text populated whenever "
    "the question directly targets ClickHouse, Airflow, or Spark.\n"
    "  6. Output ONLY the JSON object matching CandidateTurnOutput. No markdown fences.\n"
)

CANDIDATE_HUMAN_TEMPLATE: str = (
    "{format_instructions}\n"
    "\n"
    "═══ CONVERSATION HISTORY (last {history_window} turns) ═══\n"
    "{conversation_history}\n"
    "\n"
    "═══ THE INTERVIEWER'S CURRENT QUESTION ═══\n"
    "{interviewer_question}\n"
    "\n"
    "═══ SIMULATION CONTEXT ═══\n"
    "Interview Stage  : {current_stage}\n"
    "Round Index      : {current_round_index}\n"
    "Difficulty Level : {difficulty}\n"
    "\n"
    "Respond as the candidate now. Output only the JSON object.\n"
)

CANDIDATE_PROMPT_TEMPLATE: ChatPromptTemplate = ChatPromptTemplate.from_messages([
    ("system", CANDIDATE_SYSTEM_PROMPT),
    ("human",  CANDIDATE_HUMAN_TEMPLATE),
])


# ===========================================================================
# SECTION 8 — LangChain Output Parsers
# ===========================================================================
# Constructed at module import time (pure schema introspection — no API calls).
# The get_format_instructions() output is injected into {format_instructions}
# in each agent's human template, telling the LLM the exact JSON schema to emit.

interviewer_output_parser: PydanticOutputParser = PydanticOutputParser(
    pydantic_object=InterviewerTurnOutput,
)

candidate_output_parser: PydanticOutputParser = PydanticOutputParser(
    pydantic_object=CandidateTurnOutput,
)


# ===========================================================================
# SECTION 9 — LLM Factory Functions and Prompt Utility Helpers
# ===========================================================================

@lru_cache(maxsize=1)
def get_interviewer_llm():
    """
    Returns the module-level cached Gemini LLM instance for Agent A (Interviewer).
    Temperature 0.45 introduces sufficient question variety per session while
    preserving interview coherence and technical accuracy.

    Import of ChatGoogleGenerativeAI is deferred to call time so that test
    modules that import only schemas and parsers do not require GOOGLE_API_KEY.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=INTERVIEWER_MODEL,
        temperature=INTERVIEWER_TEMPERATURE,
        convert_system_message_to_human=False,
    )


@lru_cache(maxsize=1)
def get_candidate_llm():
    """
    Returns the module-level cached Gemini LLM instance for Agent B (Candidate).
    Temperature 0.28 keeps the candidate persona tightly anchored to documented
    knowledge boundaries, reducing persona drift across multi-turn sessions.

    Import of ChatGoogleGenerativeAI is deferred to call time.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=CANDIDATE_MODEL,
        temperature=CANDIDATE_TEMPERATURE,
        convert_system_message_to_human=False,
    )


def build_interviewer_chain():
    """
    Assembles the interviewer inference chain:
        INTERVIEWER_PROMPT_TEMPLATE | LLM | interviewer_output_parser
    Returns a LangChain Runnable. Called by the node functions in Step 2.
    """
    return INTERVIEWER_PROMPT_TEMPLATE | get_interviewer_llm() | interviewer_output_parser


def build_candidate_chain():
    """
    Assembles the candidate inference chain:
        CANDIDATE_PROMPT_TEMPLATE | LLM | candidate_output_parser
    Returns a LangChain Runnable. Called by the node functions in Step 2.
    """
    return CANDIDATE_PROMPT_TEMPLATE | get_candidate_llm() | candidate_output_parser


def format_conversation_history_for_prompt(
    turns:  List[SimulationTurn],
    window: int = HISTORY_WINDOW_TURNS,
) -> str:
    """
    Formats the last `window` non-system SimulationTurn objects into a
    multi-line string suitable for injection into {conversation_history}.

    Parameters
    ----------
    turns  : Full conversation_history from SimulationSessionState.
    window : Number of most-recent non-system turns to include.

    Returns
    -------
    str
        Formatted history string. Returns a placeholder if history is empty.
    """
    visible = [t for t in turns if t.role != TurnRole.SYSTEM][-window:]
    if not visible:
        return "[No conversation yet — this is the opening turn.]"

    lines: List[str] = []
    for turn in visible:
        label = "INTERVIEWER" if turn.role == TurnRole.INTERVIEWER else "CANDIDATE"
        lines.append(f"[Turn {turn.turn_index} — {label}]")
        lines.append(turn.content.strip())
        lines.append("")

    return "\n".join(lines).rstrip()


def build_interviewer_prompt_kwargs(
    session: SimulationSessionState,
) -> Dict[str, Any]:
    """
    Constructs the complete keyword arguments dict for a single
    INTERVIEWER_PROMPT_TEMPLATE.invoke() call. Centralises all
    {variable} slot population so Step 2 node functions stay clean.
    """
    return {
        "format_instructions":  interviewer_output_parser.get_format_instructions(),
        "history_window":       str(HISTORY_WINDOW_TURNS),
        "conversation_history": format_conversation_history_for_prompt(
                                    session.conversation_history
                                ),
        "current_stage":        session.current_stage.value,
        "current_round_index":  str(session.current_round_index),
        "gap_areas_probed":     (
                                    ", ".join(g.value for g in session.gap_areas_probed)
                                    if session.gap_areas_probed
                                    else "none yet"
                                ),
        "pending_follow_up":    session.pending_follow_up_question or "none",
        "difficulty":           session.config.difficulty.value,
    }


def build_candidate_prompt_kwargs(
    session:              SimulationSessionState,
    interviewer_question: str,
) -> Dict[str, Any]:
    """
    Constructs the complete keyword arguments dict for a single
    CANDIDATE_PROMPT_TEMPLATE.invoke() call. Centralises all
    {variable} slot population so Step 2 node functions stay clean.
    """
    return {
        "format_instructions":   candidate_output_parser.get_format_instructions(),
        "history_window":        str(HISTORY_WINDOW_TURNS),
        "conversation_history":  format_conversation_history_for_prompt(
                                     session.conversation_history
                                 ),
        "interviewer_question":  interviewer_question,
        "current_stage":         session.current_stage.value,
        "current_round_index":   str(session.current_round_index),
        "difficulty":            session.config.difficulty.value,
    }


def get_knowledge_boundary(domain: KnowledgeDomain) -> Optional[KnowledgeBoundaryEntry]:
    """
    Retrieves the KnowledgeBoundaryEntry for a given domain from
    CANDIDATE_KNOWLEDGE_MAP. Returns None if the domain is not found.
    Used by the Step 2 quality assessor to validate ResponseValidity.
    """
    for entry in CANDIDATE_KNOWLEDGE_MAP:
        if entry.domain == domain:
            return entry
    return None


def get_absent_domains() -> List[KnowledgeDomain]:
    """
    Returns all KnowledgeDomain values where proficiency_label == 'absent'.
    Used by the Step 2 boundary breach detector.
    """
    return [
        entry.domain
        for entry in CANDIDATE_KNOWLEDGE_MAP
        if entry.proficiency_label == "absent"
    ]


# ===========================================================================
# SECTION 10 — LangGraph Node Functions
# ===========================================================================
#
# Node execution order per simulation round:
#
#   run_interviewer_turn ──► run_candidate_turn ──► assess_round_quality
#          ▲                                                │
#          │                                    check_termination_condition
#          │                                    ┌──────────┼──────────────┐
#          │                                "continue"  "advance_stage"  "end_simulation"
#          │                                    │             │                 │
#          └────────────────────────────────────┘         advance_stage       END
#                                                              │
#                                              (lambda: "end" if complete else "continue")
#                                              ┌───────────────┴──────────────┐
#                                          "continue"                   "end_simulation"
#                                              │                              │
#                                    run_interviewer_turn                    END
#
# State management contract:
#   - Each node receives the FULL current state dict.
#   - Each node returns ONLY the keys it modifies; LangGraph merges the delta.
#   - List fields are returned as complete replacement lists (no Annotated append).
#   - Temporary fields (last_interviewer_output, last_candidate_output,
#     last_advance_stage_flag) are written by one node and consumed by the next;
#     assess_round_quality clears them by returning None.

import uuid
from typing import Tuple
from typing_extensions import TypedDict as ExtTypedDict


# ---------------------------------------------------------------------------
# 10.1 — Output Schema: InterviewSimulationTranscript
# ---------------------------------------------------------------------------

class InterviewSimulationTranscript(BaseModel):
    """
    The complete output of a finished simulation session.
    Returned by candidate_simulator_node and stored on the broader session state.
    """
    session_id:                      str
    simulation_config:               SimulationConfig
    completed_rounds:                List[SimulationRound] = Field(default_factory=list)
    total_rounds:                    int = 0
    overall_simulation_score:        float = Field(
        0.0, ge=0.0, le=1.0,
        description="Mean round_quality_score across all completed rounds.",
    )
    gap_areas_covered:               List[TargetGapArea] = Field(default_factory=list)
    final_stage_reached:             InterviewStage = InterviewStage.OPENING
    boundary_breach_count:           int = Field(
        0,
        description=(
            "Count of BOUNDARY_BREACH responses. Always 0 in correct operation — "
            "the CandidateTurnOutput model_validator prevents any breach from "
            "being stored. Tracked here for audit completeness."
        ),
    )
    honest_gap_acknowledgement_count: int = 0
    strong_adjacent_reasoning_count:  int = 0
    final_interviewer_assessment:     str = ""
    simulation_complete:              bool = False
    termination_reason:               Optional[str] = None


# ---------------------------------------------------------------------------
# 10.2 — LangGraph State TypedDict
# ---------------------------------------------------------------------------

class SimulatorGraphState(ExtTypedDict, total=False):
    """
    Typed state schema for the LangGraph StateGraph.
    All fields are Optional (total=False) because LangGraph merges partial
    updates — not every node populates every field.
    """
    config:                       SimulationConfig
    jd_entities:                  JDEntities
    cv_entities:                  CVEntities
    skills_ontology:              SkillsOntologyResult

    current_stage:                str          # InterviewStage.value string
    current_round_index:          int
    rounds_in_current_stage:      int
    conversation_history:         List[SimulationTurn]
    completed_rounds:             List[SimulationRound]
    gap_areas_probed:             List[TargetGapArea]
    interviewer_assessment_notes: List[str]
    pending_follow_up_question:   Optional[str]
    simulation_complete:          bool
    termination_reason:           Optional[str]

    # Temporary cross-node handoff fields — cleared by assess_round_quality
    last_interviewer_output:      Optional[InterviewerTurnOutput]
    last_candidate_output:        Optional[CandidateTurnOutput]
    last_advance_stage_flag:      bool


# ---------------------------------------------------------------------------
# 10.3 — Stage Sequence Constant
# ---------------------------------------------------------------------------

STAGE_SEQUENCE: List[InterviewStage] = [
    InterviewStage.OPENING,
    InterviewStage.DEEP_DIVE_CLICKHOUSE,
    InterviewStage.DEEP_DIVE_AIRFLOW,
    InterviewStage.DEEP_DIVE_SPARK,
    InterviewStage.SYNTHESIS_AND_GROWTH,
    InterviewStage.CLOSING,
]

# Target gap areas that mark a stage as a "gap probe" stage.
# Used in the quality scorer's honesty penalty logic.
_GAP_PROBE_AREAS: frozenset = frozenset({
    TargetGapArea.CLICKHOUSE_CORE,
    TargetGapArea.CLICKHOUSE_ARCHITECTURE,
    TargetGapArea.AIRFLOW_FUNDAMENTALS,
    TargetGapArea.AIRFLOW_PRODUCTION,
    TargetGapArea.SPARK_FUNDAMENTALS,
    TargetGapArea.SPARK_STREAMING,
})


# ---------------------------------------------------------------------------
# 10.4 — Private Helper Functions
# ---------------------------------------------------------------------------

def _state_to_session(state: Dict[str, Any]) -> SimulationSessionState:
    """
    Reconstructs a SimulationSessionState from the LangGraph state dict.
    Guards against None config and coerces the current_stage string to
    an InterviewStage enum value.
    """
    config = state.get("config")
    if config is None:
        config = SimulationConfig(
            session_id=state.get("session_id", "fallback-session"),
            difficulty=SimulationDifficulty.STANDARD,
        )

    raw_stage = state.get("current_stage", InterviewStage.OPENING.value)
    current_stage = (
        raw_stage if isinstance(raw_stage, InterviewStage)
        else InterviewStage(raw_stage)
    )

    return SimulationSessionState(
        config=config,
        jd_entities=state.get("jd_entities"),
        cv_entities=state.get("cv_entities"),
        skills_ontology=state.get("skills_ontology"),
        current_stage=current_stage,
        current_round_index=state.get("current_round_index", 0),
        rounds_in_current_stage=state.get("rounds_in_current_stage", 0),
        conversation_history=state.get("conversation_history", []),
        completed_rounds=state.get("completed_rounds", []),
        gap_areas_probed=state.get("gap_areas_probed", []),
        interviewer_assessment_notes=state.get("interviewer_assessment_notes", []),
        pending_follow_up_question=state.get("pending_follow_up_question"),
        simulation_complete=state.get("simulation_complete", False),
        termination_reason=state.get("termination_reason"),
    )


def _fallback_interviewer_output(state: Dict[str, Any]) -> InterviewerTurnOutput:
    """
    Returns a structurally valid InterviewerTurnOutput when the LLM invocation
    fails. The question is selected to be contextually appropriate for the
    current stage so the simulation can continue without breaking.
    """
    stage: str = state.get("current_stage", InterviewStage.OPENING.value)
    round_idx: int = state.get("current_round_index", 0)

    _stage_question_map: Dict[str, Tuple[str, QuestionType, TargetGapArea]] = {
        InterviewStage.OPENING.value: (
            "Tell me about the most technically challenging data performance problem "
            "you have solved in production — walk me through your diagnosis and the fix.",
            QuestionType.OPENING,
            TargetGapArea.GENERAL_BACKGROUND,
        ),
        InterviewStage.DEEP_DIVE_CLICKHOUSE.value: (
            "Our analytics stack is built on an OLAP columnar database. Based on your "
            "PostgreSQL performance engineering experience, what concepts do you think "
            "would transfer and which would not — and why?",
            QuestionType.CONCEPTUAL,
            TargetGapArea.CLICKHOUSE_CORE,
        ),
        InterviewStage.DEEP_DIVE_AIRFLOW.value: (
            "You have used Celery for task queuing. What do you understand to be the "
            "fundamental architectural difference between task queuing and "
            "DAG-based pipeline orchestration?",
            QuestionType.CONCEPTUAL,
            TargetGapArea.AIRFLOW_FUNDAMENTALS,
        ),
        InterviewStage.DEEP_DIVE_SPARK.value: (
            "We process over ten thousand events per second through a streaming pipeline. "
            "What is your mental model of how streaming computation differs from batch, "
            "and what would you specifically need to learn to contribute to that pipeline?",
            QuestionType.CONCEPTUAL,
            TargetGapArea.SPARK_FUNDAMENTALS,
        ),
        InterviewStage.SYNTHESIS_AND_GROWTH.value: (
            "Given the gaps we have discussed today, what does your concrete 90-day "
            "plan look like to reach production confidence on the technologies this "
            "role requires? Name the exact resources and milestones.",
            QuestionType.SYNTHESIS,
            TargetGapArea.SYNTHESIS_AND_GROWTH,
        ),
        InterviewStage.CLOSING.value: (
            "Thank you — that covers the technical areas I wanted to explore. "
            "Do you have any questions for me about the team, the architecture, "
            "or what success looks like in this role in the first six months?",
            QuestionType.CLOSING,
            TargetGapArea.GENERAL_BACKGROUND,
        ),
    }

    question, qtype, target = _stage_question_map.get(
        stage,
        _stage_question_map[InterviewStage.OPENING.value],
    )

    return InterviewerTurnOutput(
        spoken_question=question,
        question_type=qtype,
        target_gap_area=target,
        current_stage=InterviewStage(stage),
        expected_signal_strong=(
            "Candidate demonstrates specific technical knowledge with measurable outcomes."
        ),
        expected_signal_weak=(
            "Candidate gives a vague or generic answer without technical specifics."
        ),
        internal_follow_up_if_shallow=(
            "Can you be more specific about the technical approach and what the "
            "measurable outcome was?"
        ),
        internal_assessment_note=(
            f"[FALLBACK TURN — round {round_idx} — LLM invocation failed. "
            f"Stage-appropriate fallback question injected for stage '{stage}'.]"
        ),
        advance_stage_after_this_turn=False,
    )


def _fallback_candidate_output(state: Dict[str, Any]) -> CandidateTurnOutput:
    """
    Returns a structurally valid CandidateTurnOutput when the LLM invocation
    fails. For gap-targeted stages, the fallback acknowledges the gap with
    PostgreSQL-grounded adjacent reasoning. For other stages, the fallback
    anchors to the candidate's documented PostgreSQL expertise.
    """
    stage: str = state.get("current_stage", InterviewStage.OPENING.value)
    _gap_stages = {
        InterviewStage.DEEP_DIVE_CLICKHOUSE.value,
        InterviewStage.DEEP_DIVE_AIRFLOW.value,
        InterviewStage.DEEP_DIVE_SPARK.value,
    }

    if stage in _gap_stages:
        return CandidateTurnOutput(
            spoken_response=(
                "I want to be upfront — I don't have hands-on production experience "
                "with that specific technology. That said, I can reason through this "
                "from what I do know. From my PostgreSQL work, particularly the detailed "
                "EXPLAIN ANALYZE analysis I've done diagnosing query plan regressions "
                "on our bet-slips table, I have a solid mental model of I/O patterns, "
                "query execution stages, and the tradeoffs between different data access "
                "strategies. I believe that foundation would let me build the missing "
                "knowledge quickly with focused study and hands-on practice."
            ),
            internal_reasoning=(
                "[FALLBACK TURN — LLM invocation failed. Default gap-acknowledgement "
                "response anchored to PostgreSQL EXPLAIN ANALYZE expertise as the "
                "adjacent knowledge bridge.]"
            ),
            knowledge_domains_accessed=[
                KnowledgeDomain.POSTGRESQL,
                KnowledgeDomain.COLUMNAR_OLAP_CONCEPTS,
                KnowledgeDomain.IGAMING_DOMAIN,
            ],
            response_validity=ResponseValidity.BOUNDARY_ADJACENT,
            confidence_level=ConfidenceLevel.ACKNOWLEDGING_GAP,
            gap_acknowledged=True,
            gap_acknowledgement_text=(
                "I don't have hands-on production experience with that specific technology."
            ),
            adjacent_knowledge_invoked=(
                "PostgreSQL EXPLAIN ANALYZE experience and I/O pattern understanding "
                "as a conceptual bridge to reasoning about the gap technology."
            ),
        )

    return CandidateTurnOutput(
        spoken_response=(
            "At Digitain, I recently resolved a significant performance regression "
            "on our bet-slips table. The query was doing a full sequential scan on "
            "fifteen million rows because the WHERE clause filtered on a column not "
            "covered by our existing composite index. I implemented a partial index "
            "scoped to WHERE status = 'open', which reduced the index size from "
            "2.4 gigabytes to 580 megabytes and brought query execution from just "
            "over eight seconds down to under a hundred milliseconds. "
            "I can walk through the EXPLAIN ANALYZE output before and after if that "
            "would be useful — the plan shifted from a Seq Scan to an Index Only Scan."
        ),
        internal_reasoning=(
            "[FALLBACK TURN — LLM invocation failed. Default PostgreSQL expertise "
            "response anchored to documented work history at Digitain LLC.]"
        ),
        knowledge_domains_accessed=[
            KnowledgeDomain.POSTGRESQL,
            KnowledgeDomain.SQL_GENERAL,
            KnowledgeDomain.IGAMING_DOMAIN,
        ],
        response_validity=ResponseValidity.AUTHENTIC,
        confidence_level=ConfidenceLevel.HIGH,
        gap_acknowledged=False,
        gap_acknowledgement_text=None,
        adjacent_knowledge_invoked=None,
    )


def _compute_round_quality_score(
    interviewer_output: Optional[InterviewerTurnOutput],
    candidate_output:   Optional[CandidateTurnOutput],
    interviewer_turn:   SimulationTurn,
) -> Tuple[float, str]:
    """
    Deterministic quality scoring algorithm — no LLM call.
    Evaluates the candidate's response on four components using the
    module-level QUALITY_WEIGHT_* constants.

    Returns (score: float, rationale: str).

    Component 1 — Response Validity (weight 0.40):
      AUTHENTIC:          1.0 — full in-domain expertise demonstrated.
      BOUNDARY_ADJACENT:  0.5 — adjacent reasoning used, gap acknowledged.

    Component 2 — Adjacent Reasoning Depth (weight 0.30):
      Not a gap question (gap_acknowledged=False): 1.0 if AUTHENTIC, 0.6 otherwise.
      Gap question + rich adjacent bridge (>= 80 chars): 1.0.
      Gap question + brief adjacent bridge (< 80 chars):  0.55.
      Gap question + no adjacent reasoning:               0.0.

    Component 3 — Gap Honesty (weight 0.20):
      Question targets a gap area AND gap acknowledged:    1.0.
      Question targets a gap area AND gap NOT acknowledged: 0.15 (potential red flag).
      Question does NOT target a gap area:                 1.0 (honesty not at issue).

    Component 4 — Communication Quality (weight 0.10):
      ConfidenceLevel.HIGH:             1.0
      ConfidenceLevel.ACKNOWLEDGING_GAP: 0.65 (honest acknowledgement is valued)
      ConfidenceLevel.MEDIUM:           0.55
      ConfidenceLevel.LOW:              0.30
    """
    if candidate_output is None:
        return 0.0, "No candidate output available — defaulting to 0.0."

    target = interviewer_turn.target_gap_area if interviewer_turn else None
    is_gap_question = target in _GAP_PROBE_AREAS

    # ── Component 1: Response validity ──────────────────────────────────────
    validity_component: float
    if candidate_output.response_validity == ResponseValidity.AUTHENTIC:
        validity_component = 1.0
    elif candidate_output.response_validity == ResponseValidity.BOUNDARY_ADJACENT:
        validity_component = 0.5
    else:
        validity_component = 0.0   # BOUNDARY_BREACH — should never reach here

    # ── Component 2: Adjacent reasoning depth ───────────────────────────────
    adjacent_component: float
    if not candidate_output.gap_acknowledged:
        # Candidate answered from known domain
        adjacent_component = (
            1.0 if candidate_output.response_validity == ResponseValidity.AUTHENTIC
            else 0.6
        )
    elif candidate_output.adjacent_knowledge_invoked:
        bridge_text = candidate_output.adjacent_knowledge_invoked
        adjacent_component = 1.0 if len(bridge_text) >= 80 else 0.55
    else:
        adjacent_component = 0.0

    # ── Component 3: Gap honesty ─────────────────────────────────────────────
    honesty_component: float
    if is_gap_question:
        honesty_component = 1.0 if candidate_output.gap_acknowledged else 0.15
    else:
        honesty_component = 1.0

    # ── Component 4: Communication quality ───────────────────────────────────
    _comm_map: Dict[ConfidenceLevel, float] = {
        ConfidenceLevel.HIGH:              1.00,
        ConfidenceLevel.ACKNOWLEDGING_GAP: 0.65,
        ConfidenceLevel.MEDIUM:            0.55,
        ConfidenceLevel.LOW:               0.30,
    }
    comm_component = _comm_map.get(candidate_output.confidence_level, 0.50)

    # ── Weighted composite ────────────────────────────────────────────────────
    score = round(
        QUALITY_WEIGHT_RESPONSE_VALIDITY  * validity_component  +
        QUALITY_WEIGHT_ADJACENT_REASONING * adjacent_component  +
        QUALITY_WEIGHT_GAP_HONESTY        * honesty_component   +
        QUALITY_WEIGHT_COMMUNICATION      * comm_component,
        3,
    )
    score = max(0.0, min(1.0, score))

    rationale = (
        f"validity[{candidate_output.response_validity.value}]="
        f"{validity_component:.2f}×{QUALITY_WEIGHT_RESPONSE_VALIDITY} | "
        f"adjacent[bridge={'yes' if candidate_output.adjacent_knowledge_invoked else 'no'}]="
        f"{adjacent_component:.2f}×{QUALITY_WEIGHT_ADJACENT_REASONING} | "
        f"honesty[gap_q={is_gap_question},ack={candidate_output.gap_acknowledged}]="
        f"{honesty_component:.2f}×{QUALITY_WEIGHT_GAP_HONESTY} | "
        f"comm[{candidate_output.confidence_level.value}]="
        f"{comm_component:.2f}×{QUALITY_WEIGHT_COMMUNICATION} | "
        f"composite={score:.3f}"
    )
    return score, rationale


def _build_transcript(
    final_state: Dict[str, Any],
    config:      SimulationConfig,
) -> InterviewSimulationTranscript:
    """
    Constructs the InterviewSimulationTranscript from the completed graph state.
    Computes aggregate metrics across all completed rounds.
    """
    completed_rounds: List[SimulationRound] = final_state.get("completed_rounds", [])

    overall_score = (
        round(
            sum(r.round_quality_score for r in completed_rounds) / len(completed_rounds),
            3,
        )
        if completed_rounds
        else 0.0
    )

    gap_ack_count = sum(
        1 for r in completed_rounds
        if r.candidate_output.gap_acknowledged
    )
    strong_adjacent_count = sum(
        1 for r in completed_rounds
        if (
            r.candidate_output.adjacent_knowledge_invoked
            and len(r.candidate_output.adjacent_knowledge_invoked) >= 80
        )
    )

    notes: List[str] = final_state.get("interviewer_assessment_notes", [])
    final_assessment = notes[-1] if notes else "No assessment notes recorded."

    raw_stage = final_state.get("current_stage", InterviewStage.OPENING.value)
    final_stage = (
        raw_stage if isinstance(raw_stage, InterviewStage)
        else InterviewStage(raw_stage)
    )

    return InterviewSimulationTranscript(
        session_id=config.session_id,
        simulation_config=config,
        completed_rounds=completed_rounds,
        total_rounds=len(completed_rounds),
        overall_simulation_score=overall_score,
        gap_areas_covered=final_state.get("gap_areas_probed", []),
        final_stage_reached=final_stage,
        boundary_breach_count=0,
        honest_gap_acknowledgement_count=gap_ack_count,
        strong_adjacent_reasoning_count=strong_adjacent_count,
        final_interviewer_assessment=final_assessment,
        simulation_complete=final_state.get("simulation_complete", False),
        termination_reason=final_state.get("termination_reason"),
    )


# ---------------------------------------------------------------------------
# 10.5 — Node: run_interviewer_turn
# ---------------------------------------------------------------------------

async def run_interviewer_turn(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node — Agent A invocation.

    Actions:
      1. Reconstructs SimulationSessionState for prompt builder.
      2. Invokes the interviewer chain (INTERVIEWER_PROMPT_TEMPLATE | LLM | parser).
      3. Falls back to _fallback_interviewer_output on any exception.
      4. Wraps the spoken question in a SimulationTurn and appends it to history.
      5. Queues the interviewer's internal follow-up question onto the state.
      6. Appends the internal assessment note to interviewer_assessment_notes.

    Returns partial state update (only modified keys).
    """
    session = _state_to_session(state)
    round_idx: int = state.get("current_round_index", 0)

    try:
        chain = build_interviewer_chain()
        kwargs = build_interviewer_prompt_kwargs(session)
        interviewer_output: InterviewerTurnOutput = await chain.ainvoke(kwargs)
    except Exception as exc:
        logger.error(
            "run_interviewer_turn [round=%d]: LLM invocation failed: %s. "
            "Injecting fallback question.",
            round_idx, exc,
        )
        interviewer_output = _fallback_interviewer_output(state)

    # Build the conversation turn
    conversation_history: List[SimulationTurn] = list(state.get("conversation_history", []))
    turn_index = len(conversation_history)
    raw_stage = state.get("current_stage", InterviewStage.OPENING.value)
    current_stage_enum = (
        raw_stage if isinstance(raw_stage, InterviewStage)
        else InterviewStage(raw_stage)
    )

    interviewer_turn = SimulationTurn(
        turn_index=turn_index,
        role=TurnRole.INTERVIEWER,
        content=interviewer_output.spoken_question,
        stage=current_stage_enum,
        question_type=interviewer_output.question_type,
        target_gap_area=interviewer_output.target_gap_area,
    )
    conversation_history.append(interviewer_turn)

    # Append the cumulative assessment note
    notes: List[str] = list(state.get("interviewer_assessment_notes", []))
    if interviewer_output.internal_assessment_note:
        notes.append(
            f"[Round {round_idx} | {interviewer_output.target_gap_area.value}] "
            f"{interviewer_output.internal_assessment_note}"
        )

    logger.debug(
        "run_interviewer_turn [round=%d | stage=%s | target=%s]: question='%s...'",
        round_idx,
        current_stage_enum.value,
        interviewer_output.target_gap_area.value,
        interviewer_output.spoken_question[:60],
    )

    return {
        "conversation_history":        conversation_history,
        "interviewer_assessment_notes": notes,
        "pending_follow_up_question":   interviewer_output.internal_follow_up_if_shallow,
        "last_interviewer_output":      interviewer_output,
        "last_advance_stage_flag":      interviewer_output.advance_stage_after_this_turn,
    }


# ---------------------------------------------------------------------------
# 10.6 — Node: run_candidate_turn
# ---------------------------------------------------------------------------

async def run_candidate_turn(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node — Agent B invocation.

    Actions:
      1. Extracts the last interviewer question from conversation_history.
      2. Reconstructs SimulationSessionState for prompt builder.
      3. Invokes the candidate chain (CANDIDATE_PROMPT_TEMPLATE | LLM | parser).
      4. Falls back to _fallback_candidate_output on any exception.
      5. Validates that response_validity != BOUNDARY_BREACH (Pydantic validator
         already enforces this, but the node logs a warning if it somehow slips through).
      6. Wraps the spoken response in a SimulationTurn and appends it to history.

    Returns partial state update (only modified keys).
    """
    conversation_history: List[SimulationTurn] = list(state.get("conversation_history", []))
    round_idx: int = state.get("current_round_index", 0)

    # Locate the most recent interviewer turn for question extraction
    last_interviewer_turn: Optional[SimulationTurn] = next(
        (t for t in reversed(conversation_history) if t.role == TurnRole.INTERVIEWER),
        None,
    )
    interviewer_question: str = (
        last_interviewer_turn.content
        if last_interviewer_turn
        else "Please introduce yourself and describe your technical background."
    )

    session = _state_to_session(state)

    try:
        chain = build_candidate_chain()
        kwargs = build_candidate_prompt_kwargs(session, interviewer_question)
        candidate_output: CandidateTurnOutput = await chain.ainvoke(kwargs)
    except Exception as exc:
        logger.error(
            "run_candidate_turn [round=%d]: LLM invocation failed: %s. "
            "Injecting fallback response.",
            round_idx, exc,
        )
        candidate_output = _fallback_candidate_output(state)

    # Safety guard — should never fire due to model_validator, but logged if it does
    if candidate_output.response_validity == ResponseValidity.BOUNDARY_BREACH:
        logger.error(
            "run_candidate_turn [round=%d]: BOUNDARY_BREACH detected in candidate output. "
            "This should have been caught by the Pydantic model_validator. "
            "Replacing with fallback response.",
            round_idx,
        )
        candidate_output = _fallback_candidate_output(state)

    # Build the conversation turn
    turn_index = len(conversation_history)
    raw_stage = state.get("current_stage", InterviewStage.OPENING.value)
    current_stage_enum = (
        raw_stage if isinstance(raw_stage, InterviewStage)
        else InterviewStage(raw_stage)
    )

    candidate_turn = SimulationTurn(
        turn_index=turn_index,
        role=TurnRole.CANDIDATE,
        content=candidate_output.spoken_response,
        stage=current_stage_enum,
        response_validity=candidate_output.response_validity,
        confidence_level=candidate_output.confidence_level,
        domains_invoked=candidate_output.knowledge_domains_accessed,
        gap_acknowledged=candidate_output.gap_acknowledged,
    )
    conversation_history.append(candidate_turn)

    logger.debug(
        "run_candidate_turn [round=%d | validity=%s | gap_ack=%s]: response='%s...'",
        round_idx,
        candidate_output.response_validity.value,
        candidate_output.gap_acknowledged,
        candidate_output.spoken_response[:60],
    )

    return {
        "conversation_history": conversation_history,
        "last_candidate_output": candidate_output,
    }


# ---------------------------------------------------------------------------
# 10.7 — Node: assess_round_quality
# ---------------------------------------------------------------------------

async def assess_round_quality(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node — deterministic round quality scorer.

    Actions:
      1. Retrieves the last SimulationTurn pair and their structured outputs
         from the temporary state fields set by the prior two nodes.
      2. Calls _compute_round_quality_score for a deterministic float score.
      3. Assembles a SimulationRound and appends it to completed_rounds.
      4. Increments current_round_index and rounds_in_current_stage.
      5. Records the target_gap_area in gap_areas_probed (deduped).
      6. Clears all temporary state fields (last_interviewer_output,
         last_candidate_output, last_advance_stage_flag).

    This node does NOT make any LLM calls — scoring is deterministic.
    """
    conversation_history: List[SimulationTurn] = state.get("conversation_history", [])
    last_interviewer_output: Optional[InterviewerTurnOutput] = state.get("last_interviewer_output")
    last_candidate_output:   Optional[CandidateTurnOutput]   = state.get("last_candidate_output")

    # Locate the last complete turn pair
    candidate_turns   = [t for t in conversation_history if t.role == TurnRole.CANDIDATE]
    interviewer_turns = [t for t in conversation_history if t.role == TurnRole.INTERVIEWER]

    if not candidate_turns or not interviewer_turns:
        logger.warning("assess_round_quality: no complete turn pair available — skipping.")
        return {
            "last_interviewer_output": None,
            "last_candidate_output":   None,
            "last_advance_stage_flag": False,
        }

    last_interviewer_turn = interviewer_turns[-1]
    last_candidate_turn   = candidate_turns[-1]

    # Compute quality score
    quality_score, quality_rationale = _compute_round_quality_score(
        last_interviewer_output,
        last_candidate_output,
        last_interviewer_turn,
    )

    # Assemble SimulationRound
    round_idx = state.get("current_round_index", 0)
    raw_stage = state.get("current_stage", InterviewStage.OPENING.value)
    current_stage_enum = (
        raw_stage if isinstance(raw_stage, InterviewStage)
        else InterviewStage(raw_stage)
    )

    # Use fallbacks if structured outputs are somehow missing
    safe_interviewer_output = last_interviewer_output or _fallback_interviewer_output(state)
    safe_candidate_output   = last_candidate_output   or _fallback_candidate_output(state)

    simulation_round = SimulationRound(
        round_index=round_idx,
        stage=current_stage_enum,
        interviewer_turn=last_interviewer_turn,
        candidate_turn=last_candidate_turn,
        interviewer_output=safe_interviewer_output,
        candidate_output=safe_candidate_output,
        round_quality_score=quality_score,
        quality_rationale=quality_rationale,
    )

    # Append to completed rounds
    completed_rounds: List[SimulationRound] = list(state.get("completed_rounds", []))
    completed_rounds.append(simulation_round)

    # Update gap areas probed (deduplicated)
    gap_areas_probed: List[TargetGapArea] = list(state.get("gap_areas_probed", []))
    probed_target = safe_interviewer_output.target_gap_area
    if probed_target not in gap_areas_probed:
        gap_areas_probed.append(probed_target)

    logger.info(
        "assess_round_quality [round=%d | stage=%s | score=%.3f]: %s",
        round_idx,
        current_stage_enum.value,
        quality_score,
        quality_rationale,
    )

    return {
        "completed_rounds":          completed_rounds,
        "current_round_index":       round_idx + 1,
        "rounds_in_current_stage":   state.get("rounds_in_current_stage", 0) + 1,
        "gap_areas_probed":          gap_areas_probed,
        # Clear temporary handoff fields
        "last_interviewer_output":   None,
        "last_candidate_output":     None,
        "last_advance_stage_flag":   False,
    }


# ---------------------------------------------------------------------------
# 10.8 — Node: advance_stage
# ---------------------------------------------------------------------------

def advance_stage(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node — advances the interview to the next stage in STAGE_SEQUENCE.

    Actions:
      1. Looks up the current stage in STAGE_SEQUENCE.
      2. Advances to the next stage and resets rounds_in_current_stage to 0.
      3. If already at the final stage (CLOSING), sets simulation_complete=True
         so the conditional edge after this node routes to END.
      4. Clears pending_follow_up_question (new stage = fresh question context).

    Does NOT make LLM calls — purely deterministic state transition.
    """
    raw_stage: str = state.get("current_stage", InterviewStage.OPENING.value)
    current_stage = (
        raw_stage if isinstance(raw_stage, InterviewStage)
        else InterviewStage(raw_stage)
    )

    try:
        current_idx = STAGE_SEQUENCE.index(current_stage)
    except ValueError:
        logger.warning(
            "advance_stage: current_stage '%s' not found in STAGE_SEQUENCE. "
            "Defaulting to CLOSING.",
            current_stage.value,
        )
        current_idx = len(STAGE_SEQUENCE) - 2   # One before CLOSING

    next_idx = current_idx + 1

    if next_idx >= len(STAGE_SEQUENCE):
        # Exhausted all stages
        logger.info(
            "advance_stage: all stages completed after '%s'. Setting simulation_complete.",
            current_stage.value,
        )
        return {
            "simulation_complete":       True,
            "termination_reason":        "all_stages_completed",
            "rounds_in_current_stage":   0,
            "last_advance_stage_flag":   False,
            "pending_follow_up_question": None,
        }

    next_stage = STAGE_SEQUENCE[next_idx]

    # Check config to skip optional stages
    config = state.get("config")
    include_synthesis = getattr(config, "include_synthesis_stage", True)
    include_closing   = getattr(config, "include_closing_stage",   True)

    if next_stage == InterviewStage.SYNTHESIS_AND_GROWTH and not include_synthesis:
        next_idx += 1
        if next_idx >= len(STAGE_SEQUENCE):
            return {
                "simulation_complete":       True,
                "termination_reason":        "all_stages_completed_synthesis_skipped",
                "rounds_in_current_stage":   0,
                "last_advance_stage_flag":   False,
                "pending_follow_up_question": None,
            }
        next_stage = STAGE_SEQUENCE[next_idx]

    if next_stage == InterviewStage.CLOSING and not include_closing:
        return {
            "simulation_complete":       True,
            "termination_reason":        "simulation_complete_closing_skipped",
            "rounds_in_current_stage":   0,
            "last_advance_stage_flag":   False,
            "pending_follow_up_question": None,
        }

    logger.info(
        "advance_stage: %s → %s",
        current_stage.value, next_stage.value,
    )

    return {
        "current_stage":             next_stage.value,
        "rounds_in_current_stage":   0,
        "last_advance_stage_flag":   False,
        "pending_follow_up_question": None,
    }


# ---------------------------------------------------------------------------
# 10.9 — Conditional Edge: check_termination_condition
# ---------------------------------------------------------------------------

def check_termination_condition(state: Dict[str, Any]) -> str:
    """
    LangGraph conditional edge routing function — called after assess_round_quality.

    Returns one of three routing strings:
      "continue"        → loop back to run_interviewer_turn (same stage, next round)
      "advance_stage"   → route to advance_stage node
      "end_simulation"  → route to END

    Termination triggers (evaluated in priority order):
      1. simulation_complete flag already set (e.g., by a previous advance_stage call).
      2. current_round_index >= max_total_rounds (hard global limit).
      3. current_stage == CLOSING and rounds_in_current_stage >= 1 (one closing round).
      4. last_advance_stage_flag == True (interviewer signaled explicit advancement).
      5. rounds_in_current_stage >= stage-specific round limit (per-stage exhaustion).
    """
    if state.get("simulation_complete", False):
        return "end_simulation"

    config = state.get("config")
    max_total   = getattr(config, "max_total_rounds",    SIMULATION_MAX_ROUNDS)
    max_default = getattr(config, "max_rounds_per_stage", ROUNDS_PER_STAGE_DEFAULT)

    current_round     = state.get("current_round_index",      0)
    rounds_in_stage   = state.get("rounds_in_current_stage",  0)
    advance_flag      = state.get("last_advance_stage_flag",   False)
    current_stage     = state.get("current_stage", InterviewStage.OPENING.value)

    # Priority 1: Hard global round limit
    if current_round >= max_total:
        logger.info(
            "check_termination: max_total_rounds (%d) reached at round %d → end_simulation",
            max_total, current_round,
        )
        return "end_simulation"

    # Priority 2: Closing stage — one round is sufficient
    if current_stage == InterviewStage.CLOSING.value and rounds_in_stage >= 1:
        logger.info("check_termination: closing stage completed → end_simulation")
        return "end_simulation"

    # Priority 3: Explicit interviewer advancement signal
    if advance_flag:
        logger.info(
            "check_termination: advance_stage_after_this_turn=True at round %d → advance_stage",
            current_round,
        )
        return "advance_stage"

    # Priority 4: Per-stage round limit
    stage_limit = (
        ROUNDS_PER_STAGE_CLICKHOUSE
        if current_stage == InterviewStage.DEEP_DIVE_CLICKHOUSE.value
        else max_default
    )
    if rounds_in_stage >= stage_limit:
        logger.info(
            "check_termination: stage '%s' exhausted (%d/%d rounds) → advance_stage",
            current_stage, rounds_in_stage, stage_limit,
        )
        return "advance_stage"

    return "continue"


# ===========================================================================
# SECTION 11 — Graph Compilation and Main Orchestration Entry Point
# ===========================================================================

def _build_simulation_graph():
    """
    Constructs and compiles the LangGraph StateGraph for the two-agent simulation.

    Graph topology (see Section 10 header diagram for the full flow):
      Nodes:
        run_interviewer_turn  — Agent A invocation
        run_candidate_turn    — Agent B invocation
        assess_round_quality  — Deterministic scorer
        advance_stage         — Stage state transition

      Edges:
        run_interviewer_turn → run_candidate_turn (linear)
        run_candidate_turn   → assess_round_quality (linear)
        assess_round_quality → (conditional)
            "continue"      → run_interviewer_turn
            "advance_stage" → advance_stage
            "end_simulation"→ END
        advance_stage        → (conditional)
            "continue"      → run_interviewer_turn (simulation_complete=False)
            "end_simulation"→ END           (simulation_complete=True)
    """
    try:
        from langgraph.graph import StateGraph, END
    except ImportError as exc:
        raise ImportError(
            "langgraph is required for the candidate simulation engine. "
            "Install with: pip install langgraph>=0.2"
        ) from exc

    graph: StateGraph = StateGraph(SimulatorGraphState)

    # Register nodes
    graph.add_node("run_interviewer_turn", run_interviewer_turn)
    graph.add_node("run_candidate_turn",   run_candidate_turn)
    graph.add_node("assess_round_quality", assess_round_quality)
    graph.add_node("advance_stage",        advance_stage)

    # Entry point
    graph.set_entry_point("run_interviewer_turn")

    # Linear edges within a round
    graph.add_edge("run_interviewer_turn", "run_candidate_turn")
    graph.add_edge("run_candidate_turn",   "assess_round_quality")

    # Conditional routing after quality assessment
    graph.add_conditional_edges(
        "assess_round_quality",
        check_termination_condition,
        {
            "continue":       "run_interviewer_turn",
            "advance_stage":  "advance_stage",
            "end_simulation": END,
        },
    )

    # Conditional routing after stage advancement
    # If advance_stage set simulation_complete=True, route to END; otherwise loop back.
    graph.add_conditional_edges(
        "advance_stage",
        lambda s: "end_simulation" if s.get("simulation_complete", False) else "continue",
        {
            "continue":       "run_interviewer_turn",
            "end_simulation": END,
        },
    )

    return graph.compile()


@lru_cache(maxsize=1)
def get_simulation_graph():
    """
    Returns the module-level compiled simulation graph singleton.
    The graph is built exactly once per Python process.

    Import of LangGraph is deferred to _build_simulation_graph() so that
    test modules importing only schemas and parsers do not require langgraph.
    """
    return _build_simulation_graph()


async def candidate_simulator_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main orchestration entry point for the candidate simulation engine.
    Called by the Phase 3 tab component or directly in integration tests.

    Lifecycle:
      1. Extracts CVEntities, JDEntities, and SkillsOntologyResult from
         the incoming state dict (compatible with ArmeniaCareer payload structure).
      2. Constructs a SimulationConfig for this session.
      3. Builds the initial SimulatorGraphState dict.
      4. Invokes the compiled LangGraph simulation graph (fully async).
      5. Assembles and returns an InterviewSimulationTranscript from the
         final graph state.

    Fallback resilience:
      If the graph execution fails catastrophically (network outage, model "
      quota exhaustion, LangGraph internal error), the function catches the "
      exception, marks the session as failed, and returns a minimal transcript "
      with termination_reason documenting the failure. The simulation never "
      propagates an unhandled exception to the caller.

    Parameters
    ----------
    state : dict
        Must contain at minimum: 'cv_entities', 'jd_entities', 'skills_ontology'.
        Optionally: 'session_id', 'language', 'simulation_difficulty'.

    Returns
    -------
    dict
        {'interview_simulation_transcript': InterviewSimulationTranscript}
    """
    cv_entities:    Optional[CVEntities]          = state.get("cv_entities")
    jd_entities:    Optional[JDEntities]          = state.get("jd_entities")
    skills_ontology: Optional[SkillsOntologyResult] = state.get("skills_ontology")
    session_id:     str = state.get("session_id", f"sim-{uuid.uuid4().hex[:8]}")
    language:       str = state.get("language", "en")

    raw_difficulty: str = state.get(
        "simulation_difficulty",
        SimulationDifficulty.STANDARD.value,
    )
    try:
        difficulty = SimulationDifficulty(raw_difficulty)
    except ValueError:
        logger.warning(
            "candidate_simulator_node: unknown difficulty '%s', defaulting to STANDARD.",
            raw_difficulty,
        )
        difficulty = SimulationDifficulty.STANDARD

    if cv_entities is None or jd_entities is None or skills_ontology is None:
        logger.error(
            "candidate_simulator_node: missing required state keys "
            "(cv_entities, jd_entities, skills_ontology). Cannot run simulation."
        )
        empty_config = SimulationConfig(
            session_id=session_id, difficulty=difficulty
        )
        failed_transcript = InterviewSimulationTranscript(
            session_id=session_id,
            simulation_config=empty_config,
            simulation_complete=False,
            termination_reason="missing_required_state_inputs",
        )
        return {"interview_simulation_transcript": failed_transcript}

    # Build simulation configuration
    sim_config = SimulationConfig(
        session_id=session_id,
        difficulty=difficulty,
        max_rounds_per_stage=ROUNDS_PER_STAGE_DEFAULT,
        max_total_rounds=SIMULATION_MAX_ROUNDS,
        include_synthesis_stage=True,
        include_closing_stage=True,
        language=language,
        allow_adjacent_reasoning=True,
    )

    # Construct initial LangGraph state
    initial_graph_state: Dict[str, Any] = {
        "config":                      sim_config,
        "jd_entities":                 jd_entities,
        "cv_entities":                 cv_entities,
        "skills_ontology":             skills_ontology,
        "current_stage":               InterviewStage.OPENING.value,
        "current_round_index":         0,
        "rounds_in_current_stage":     0,
        "conversation_history":        [],
        "completed_rounds":            [],
        "gap_areas_probed":            [],
        "interviewer_assessment_notes": [],
        "pending_follow_up_question":  None,
        "simulation_complete":         False,
        "termination_reason":          None,
        "last_interviewer_output":     None,
        "last_candidate_output":       None,
        "last_advance_stage_flag":     False,
    }

    logger.info(
        "candidate_simulator_node: starting simulation | session=%s | difficulty=%s "
        "| max_rounds=%d | jd='%s'",
        session_id,
        difficulty.value,
        SIMULATION_MAX_ROUNDS,
        jd_entities.role_title,
    )

    # Execute the simulation graph
    try:
        graph = get_simulation_graph()
        final_state: Dict[str, Any] = await graph.ainvoke(initial_graph_state)
        termination_source = "graph_completed"
    except Exception as exc:
        logger.error(
            "candidate_simulator_node [session=%s]: graph execution failed: %s",
            session_id, exc,
        )
        final_state = dict(initial_graph_state)
        final_state["simulation_complete"] = True
        final_state["termination_reason"]  = f"graph_execution_error: {exc!s}"
        termination_source = "exception_fallback"

    logger.info(
        "candidate_simulator_node: simulation finished | session=%s | "
        "rounds=%d | source=%s | termination=%s",
        session_id,
        len(final_state.get("completed_rounds", [])),
        termination_source,
        final_state.get("termination_reason", "normal_completion"),
    )

    transcript = _build_transcript(final_state, sim_config)
    return {"interview_simulation_transcript": transcript}
