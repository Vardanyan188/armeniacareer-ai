# tests/mock_fixtures.py
#
# Deterministic synthetic fixture module for ArmeniaCareer AI.
#
# Purpose:
#   Provides structurally complete, domain-accurate mock objects that feed
#   the Phase 2 scoring and governance pipeline (PayloadAssembler, scoring.py)
#   and serve as the immutable input state for Phase 3 (Candidate Simulation).
#
# Target Domain:
#   High-Throughput iGaming Analytics Platform.
#   JD: Senior Data Engineer — ClickHouse clusters, Apache Airflow orchestration,
#   Apache Spark streaming at 10k+ events/sec.
#
# Mathematical Invariant (validated pre-generation):
#   technical_skills_match score = 0.19   (< 0.40 → CRITICAL FLOOR TRIGGERED)
#   geometric mean of all 7 dims  = 0.461 (> 0.44 → CRITICAL CAP IS BINDING)
#   final composite score          = 0.44  (capped at CRITICAL_FLOOR_CAP)
#
# Localization Coverage:
#   Work history start/end dates encoded in Armenian script to exercise the
#   multilingual date parser in cv_parsing_schema.py (_ARMENIAN_MONTHS map
#   and present-token detection via "Ներկա").
#
# File Layout:
#   Section A  — Domain Context Constants
#   Section B  — MOCK_JD_ENTITIES        (JDEntities)
#   Section C  — MOCK_PARSED_CV          (ParsedCVOutput — Armenian dates)
#   Section D  — MOCK_CV_ENTITIES        (CVEntities — deterministic, no date deps)
#   Section E  — MOCK_SKILLS_ONTOLOGY    (SkillsOntologyResult)
#   Section F  — MOCK_SEMANTIC_ANALYSIS  (SemanticAnalysis)
#   Section G  — EXPECTED_SCORING_OUTCOMES
#   Section H  — Variant Factory Functions

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.schemas.cv_parsing_schema import (
    CEFRLevel,
    CVFormatQualitySignals,
    CVFormatType,
    DegreeLevel,
    EmploymentType,
    InstitutionType,
    LanguageProficiency,
    ParsedCertification,
    ParsedCVOutput,
    ParsedEducationEntry,
    ParsedProject,
    ParsedSkillEntry,
    ParsedWorkExperience,
    QuantitativeAchievement,
    ScriptType,
    SkillCategory as ParsedSkillCategory,
    SeniorityLevel as ParsedSeniorityLevel,
)
from src.schemas.canonical_payload import (
    CVEntities,
    EducationEntry,
    GapSeverity,
    JDEntities,
    SemanticAnalysis,
    SkillCategory,
    SkillEntry,
    SkillMatchEntry,
    SkillMatchType,
    SkillsOntologyResult,
    SeniorityLevel,
    WorkExperience,
)


# ===========================================================================
# SECTION A — Domain Context Constants
# ===========================================================================
# These constants are referenced throughout the fixture to ensure terminology
# consistency and to document the iGaming Analytics domain vocabulary that
# the Semantic Alignment Agent is expected to surface in key-phrase extraction.

DOMAIN_SLUG:          str = "igaming"
ROLE_TITLE:           str = "Senior Data Engineer (iGaming Analytics)"
REQUIRED_SENIORITY:   str = SeniorityLevel.SENIOR
REQUIRED_EXP_YEARS:   float = 5.0
CANDIDATE_EXP_YEARS:  float = 3.6    # Deterministic value for scoring tests
CANDIDATE_SENIORITY:  str = SeniorityLevel.MID

# Required skill names — canonical forms
SKILL_CLICKHOUSE  = "ClickHouse"
SKILL_AIRFLOW     = "Apache Airflow"
SKILL_SPARK       = "Apache Spark"
SKILL_PYTHON      = "Python"
SKILL_SQL         = "SQL"

# Preferred skill names — canonical forms
SKILL_KAFKA       = "Apache Kafka"
SKILL_DBT         = "dbt"
SKILL_REDIS       = "Redis"
SKILL_SCALA       = "Scala"

# JD domain context phrase samples — for SemanticAnalysis fixture
JD_UNIQUE_KEY_PHRASES: List[str] = [
    "ClickHouse ReplacingMergeTree",
    "Apache Airflow DAG orchestration",
    "Apache Spark structured streaming",
    "10k+ events per second",
    "sharding and replication",
    "clickstream processing pipeline",
    "low-latency OLAP queries",
    "MergeTree engine family",
]

# CV domain key phrase samples — overlap with JD vocabulary is intentionally limited
CV_UNIQUE_KEY_PHRASES: List[str] = [
    "FastAPI microservice",
    "PostgreSQL partial index",
    "CTE refactoring",
    "asyncio task queue",
    "SQLAlchemy ORM",
    "Docker Compose deployment",
    "pytest integration tests",
    "odds calculation API",
    "Redis cache layer",
]

# Shared phrases — Python and SQL appear in both CV and JD
SHARED_KEY_PHRASES: List[str] = [
    "Python",
    "SQL",
    "data pipeline",
    "backend engineering",
]


# ===========================================================================
# SECTION B — MOCK_JD_ENTITIES
# ===========================================================================
# JDEntities: Senior Data Engineer at a fictional Armenian iGaming operator.
# Required stack is deliberately ClickHouse-centric and streaming-oriented —
# domains entirely absent from the candidate CV.

MOCK_JD_ENTITIES = JDEntities(
    role_title=ROLE_TITLE,
    company_context=(
        "Mid-sized Armenian iGaming operator running a proprietary sports-betting "
        "and casino platform across CIS and African markets. Analytics team owns a "
        "ClickHouse-based data warehouse processing 10k+ bet and clickstream events "
        "per second, with Airflow-orchestrated ETL and Spark-based real-time "
        "aggregation pipelines."
    ),
    required_qualifications=[
        "5+ years of professional data engineering experience in production environments.",
        "Expert-level ClickHouse: ReplacingMergeTree / AggregatingMergeTree engine design, "
        "distributed sharding, replication topology, and query plan optimization.",
        "Apache Airflow DAG authoring, dependency management, and production incident response.",
        "Apache Spark: structured streaming, partitioning strategies, and broadcast join tuning "
        "for high-cardinality iGaming event datasets.",
        "Advanced Python: type-annotated ETL pipelines, async I/O, custom Airflow operators.",
        "Complex SQL: window functions, materialized views, query plan analysis.",
    ],
    preferred_qualifications=[
        "Experience with Apache Kafka for event-bus integration between microservices and ClickHouse.",
        "Familiarity with dbt for transformation layer modeling on ClickHouse or BigQuery.",
        "Redis usage for hot-cache layers in real-time leaderboard or session-state services.",
        "Exposure to Scala for Spark job authoring.",
        "Knowledge of RA Labor Code and GDPR-adjacent data residency requirements.",
    ],
    responsibilities=[
        "Design and own the ClickHouse cluster schema for bet event and clickstream ingestion.",
        "Build and maintain Apache Airflow DAGs for hourly and daily aggregation pipelines.",
        "Optimize Spark streaming jobs to maintain sub-500ms latency at peak event load.",
        "Partner with the Data Science team to productionize prediction model feature pipelines.",
        "Conduct on-call incident response for pipeline failures impacting live sportsbook data.",
        "Define and enforce data quality SLAs across all analytical datasets.",
    ],
    required_skills=[
        SkillEntry(
            raw_name="ClickHouse",
            canonical_name=SKILL_CLICKHOUSE,
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="Expert — ReplacingMergeTree, sharding, replication required",
        ),
        SkillEntry(
            raw_name="Apache Airflow",
            canonical_name=SKILL_AIRFLOW,
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="3yr+ production DAG authoring",
        ),
        SkillEntry(
            raw_name="Apache Spark",
            canonical_name=SKILL_SPARK,
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="Structured streaming and batch, 2yr+",
        ),
        SkillEntry(
            raw_name="Python",
            canonical_name=SKILL_PYTHON,
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="Advanced — async, type annotations, custom operators",
        ),
        SkillEntry(
            raw_name="SQL",
            canonical_name=SKILL_SQL,
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="Complex analytical SQL: window functions, explain plans",
        ),
    ],
    preferred_skills=[
        SkillEntry(
            raw_name="Apache Kafka",
            canonical_name=SKILL_KAFKA,
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="Event-bus integration experience preferred",
        ),
        SkillEntry(
            raw_name="dbt",
            canonical_name=SKILL_DBT,
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="Transformation layer modeling",
        ),
        SkillEntry(
            raw_name="Redis",
            canonical_name=SKILL_REDIS,
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="Hot-cache and session-state patterns",
        ),
        SkillEntry(
            raw_name="Scala",
            canonical_name=SKILL_SCALA,
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="Spark job authoring in Scala is a plus",
        ),
    ],
    required_experience_years=REQUIRED_EXP_YEARS,
    required_seniority=SeniorityLevel.SENIOR,
    industry=DOMAIN_SLUG,
    location="Yerevan, Armenia",
    work_arrangement="hybrid",
)


# ===========================================================================
# SECTION C — MOCK_PARSED_CV   (ParsedCVOutput from cv_parsing_schema.py)
# ===========================================================================
# Candidate: Mid-level Python Backend Engineer with 3.5 years of experience
# working at Armenian iGaming companies in pure API/backend roles.
#
# Localization invariants exercised:
#   • start_date_raw = "Հուլիս 2025"    — Armenian month "հուլիս" (July) + year
#   • end_date_raw   = "Ներկա"          — present-token triggering is_current_role=True
#   • start_date_raw = "Հոկտեմբեր 2022" — Armenian month "հոկտեմբեր" (October)
#   • end_date_raw   = "Հունիս 2025"    — Armenian month "հունիս" (June)
#
# Expected duration computation (at fixture design time, current month = June 2026):
#   Role 1 — Հուլիս 2025 → Ներկա (June 2026): (2026-2025)*12 + (6-7) = 11 months
#   Role 2 — Հոկտեմբեր 2022 → Հունիս 2025:   (2025-2022)*12 + (6-10) = 32 months
#   total_months = 43,  overlap_penalty = 1.0 (len <= 3),  total_years = 43/12 ≈ 3.58
#
# NOTE: Role 1 duration is time-dependent. Use MOCK_CV_ENTITIES (Section D)
# for deterministic score assertions. Use MOCK_PARSED_CV for date-parsing tests.

MOCK_PARSED_CV = ParsedCVOutput(
    masked_identifier="[CANDIDATE]",
    contact_info_present=True,
    professional_summary=(
        "Backend Engineer with 3.5+ years building high-performance REST APIs "
        "and transactional systems in production iGaming environments. "
        "Deep expertise in PostgreSQL performance engineering — partial indexing, "
        "CTE refactoring to eliminate redundant sequential scans, and EXPLAIN ANALYZE "
        "driven query plan tuning. Proficient in FastAPI async microservice architecture, "
        "SQLAlchemy ORM, Docker containerization, and Celery distributed task queuing. "
        "Seeking to apply relational data and backend engineering foundations to a "
        "data engineering role in high-throughput analytics infrastructure."
    ),
    work_history=[
        ParsedWorkExperience(
            company="Digitain LLC",
            title="Backend Engineer",
            title_english="Backend Engineer",
            employment_type=EmploymentType.FULL_TIME,
            start_date_raw="Հուլիս 2025",
            end_date_raw="Ներկա",
            # duration_months and is_current_role computed by model_validator:
            # parse_approximate_date("հուլիս 2025") → (2025, 7)
            # is_present("ներկա") → True → end = datetime.utcnow() ≈ (2026, 6)
            # duration = (2026-2025)*12 + (6-7) = 11 months  [as of June 2026]
            responsibilities=[
                "Design and maintain FastAPI microservices handling 2,000+ concurrent WebSocket "
                "connections for real-time odds delivery to frontend betting clients.",
                "Architect SQLAlchemy models and PostgreSQL schema for player session, "
                "transaction ledger, and bet-slip tables — 15M+ rows with sub-100ms p99 reads.",
                "Implement partial indexing strategy on bet_slips table (WHERE status = 'open') "
                "reducing index size by 76% while maintaining full query coverage for live queries.",
                "Refactor three high-cardinality CTEs in the player leaderboard query from "
                "correlated sub-selects to window-function equivalents, dropping execution from "
                "4.2 seconds to 380ms on 8M-row dataset.",
                "Own Docker Compose deployment manifests and Kubernetes resource definitions "
                "for staging and pre-production environments.",
                "Maintain pytest test suite at 91% code coverage; introduce hypothesis-based "
                "property testing for financial calculation edge cases.",
            ],
            technologies_mentioned=[
                "Python", "FastAPI", "PostgreSQL", "SQLAlchemy",
                "Docker", "Kubernetes", "pytest", "Redis", "Celery",
            ],
            quantitative_achievements=[
                QuantitativeAchievement(
                    raw_statement=(
                        "Implement partial indexing strategy on bet_slips table (WHERE status = 'open') "
                        "reducing index size by 76% while maintaining full query coverage for live queries."
                    ),
                    numeric_value=76.0,
                    unit="percent",
                    direction="reduction",
                    domain_context="index_size",
                ),
                QuantitativeAchievement(
                    raw_statement=(
                        "Refactor three high-cardinality CTEs in the player leaderboard query "
                        "dropping execution from 4.2 seconds to 380ms on 8M-row dataset."
                    ),
                    numeric_value=380.0,
                    unit="ms",
                    direction="reduction",
                    domain_context="query_latency",
                ),
            ],
            domain="igaming",
            location="Yerevan, Armenia",
        ),
        ParsedWorkExperience(
            company="Softconstruct CJSC",
            title="Junior Python Developer",
            title_english="Junior Python Developer",
            employment_type=EmploymentType.FULL_TIME,
            start_date_raw="Հոկտեմբեր 2022",
            end_date_raw="Հունիս 2025",
            # duration_months computed by model_validator:
            # (2025-2022)*12 + (6-10) = 36 - 4 = 32 months
            responsibilities=[
                "Develop internal REST APIs for sportsbook odds management using Django REST Framework, "
                "serving trading team consumers with latency SLA of <200ms.",
                "Maintain PostgreSQL data models for events, markets, and selections; "
                "write complex multi-join analytical queries for trading dashboard.",
                "Build Celery task queues for asynchronous payout calculation and "
                "email notification dispatch — processing 30,000+ tasks per day.",
                "Participate in code reviews, enforce PEP-8 standards, and document "
                "all API endpoints in OpenAPI 3.0 specifications.",
                "Migrate legacy synchronous Django views to async view handlers, "
                "reducing P95 latency from 650ms to 210ms under load.",
            ],
            technologies_mentioned=[
                "Python", "Django REST Framework", "PostgreSQL", "Celery",
                "Redis", "Git", "Docker", "Linux",
            ],
            quantitative_achievements=[
                QuantitativeAchievement(
                    raw_statement=(
                        "Migrate legacy synchronous Django views to async view handlers, "
                        "reducing P95 latency from 650ms to 210ms under load."
                    ),
                    numeric_value=210.0,
                    unit="ms",
                    direction="reduction",
                    domain_context="request_latency",
                ),
                QuantitativeAchievement(
                    raw_statement=(
                        "Build Celery task queues for asynchronous payout calculation and "
                        "email notification dispatch — processing 30,000+ tasks per day."
                    ),
                    numeric_value=30000.0,
                    unit="tasks",
                    direction="absolute",
                    domain_context="throughput",
                ),
            ],
            domain="igaming",
            location="Yerevan, Armenia",
        ),
    ],
    education=[
        ParsedEducationEntry(
            institution="Երևանի Պետական Համալսարան",
            institution_english="Yerevan State University",
            institution_type=InstitutionType.STATE_UNIVERSITY,
            degree_level=DegreeLevel.BACHELOR,
            degree_label="Bachelor of Science in Computer Science",
            field_of_study="Computer Science",
            graduation_year=2022,
            gpa=4.6,                         # Armenian 5.0 scale
            is_relevant_to_role=None,         # To be set by Semantic Alignment Agent
            honors=None,
        ),
    ],
    skills=[
        # ── Technical Skills (backend-oriented — NO data engineering stack) ─────
        ParsedSkillEntry(
            raw_name="Python",
            canonical_name="Python",
            category=ParsedSkillCategory.TECHNICAL,
            taxonomy_code="TECH-PYT-0001",
            proficiency_signal="3.5 years production",
            context_phrase="FastAPI async microservices, Celery tasks, pytest — 3.5yr production",
        ),
        ParsedSkillEntry(
            raw_name="FastAPI",
            canonical_name="FastAPI",
            category=ParsedSkillCategory.TECHNICAL,
            taxonomy_code="TECH-FAP-0001",
            proficiency_signal="advanced",
            context_phrase="Design and maintain FastAPI microservices handling 2,000+ concurrent WebSocket connections.",
        ),
        ParsedSkillEntry(
            raw_name="PostgreSQL",
            canonical_name="PostgreSQL",
            category=ParsedSkillCategory.TECHNICAL,
            taxonomy_code="TECH-PGS-0001",
            proficiency_signal="advanced — query plan optimization, partial indexing",
            context_phrase="Implement partial indexing strategy on bet_slips table reducing index size by 76%.",
        ),
        ParsedSkillEntry(
            raw_name="SQL",
            canonical_name="SQL",
            category=ParsedSkillCategory.TECHNICAL,
            taxonomy_code="TECH-SQL-0001",
            proficiency_signal="advanced — CTEs, window functions, EXPLAIN ANALYZE",
            context_phrase="Write complex multi-join analytical queries; refactor CTEs to window functions.",
        ),
        ParsedSkillEntry(
            raw_name="SQLAlchemy",
            canonical_name="SQLAlchemy",
            category=ParsedSkillCategory.TECHNICAL,
            taxonomy_code="TECH-SAL-0001",
            proficiency_signal="intermediate-advanced",
            context_phrase="Architect SQLAlchemy models for player session and transaction ledger tables.",
        ),
        ParsedSkillEntry(
            raw_name="Docker",
            canonical_name="Docker",
            category=ParsedSkillCategory.TECHNICAL,
            taxonomy_code="TECH-DOK-0001",
            proficiency_signal="intermediate",
            context_phrase="Own Docker Compose deployment manifests and Kubernetes resource definitions.",
        ),
        ParsedSkillEntry(
            raw_name="Kubernetes",
            canonical_name="Kubernetes",
            category=ParsedSkillCategory.TECHNICAL,
            taxonomy_code="TECH-K8S-0001",
            proficiency_signal="basic — manifests and resource definitions",
            context_phrase="Own Docker Compose deployment manifests and Kubernetes resource definitions.",
        ),
        ParsedSkillEntry(
            raw_name="Redis",
            canonical_name="Redis",
            category=ParsedSkillCategory.TECHNICAL,
            taxonomy_code="TECH-RDS-0001",
            proficiency_signal="intermediate — cache layer client usage",
            context_phrase="Redis cache layer used in Celery broker and session storage.",
        ),
        ParsedSkillEntry(
            raw_name="Celery",
            canonical_name="Celery",
            category=ParsedSkillCategory.TECHNICAL,
            taxonomy_code="TECH-CLR-0001",
            proficiency_signal="intermediate",
            context_phrase="Build Celery task queues processing 30,000+ tasks per day.",
        ),
        ParsedSkillEntry(
            raw_name="pytest",
            canonical_name="pytest",
            category=ParsedSkillCategory.TECHNICAL,
            taxonomy_code="TECH-PYT-0002",
            proficiency_signal="advanced — 91% coverage, property testing",
            context_phrase="Maintain pytest test suite at 91% code coverage; hypothesis-based property testing.",
        ),
        ParsedSkillEntry(
            raw_name="Git",
            canonical_name="Git",
            category=ParsedSkillCategory.TECHNICAL,
            taxonomy_code="TECH-GIT-0001",
            proficiency_signal="proficient",
            context_phrase="Version control, branch management, code review workflows.",
        ),
        ParsedSkillEntry(
            raw_name="Linux",
            canonical_name="Linux",
            category=ParsedSkillCategory.TECHNICAL,
            taxonomy_code="TECH-LNX-0001",
            proficiency_signal="intermediate",
            context_phrase="Shell scripting and server administration in staging environments.",
        ),
        ParsedSkillEntry(
            raw_name="REST API Design",
            canonical_name="REST API Design",
            category=ParsedSkillCategory.TECHNICAL,
            taxonomy_code="TECH-API-0001",
            proficiency_signal="advanced — OpenAPI 3.0 specification",
            context_phrase="Document all API endpoints in OpenAPI 3.0 specifications.",
        ),
        # ── Domain Skills ─────────────────────────────────────────────────────
        ParsedSkillEntry(
            raw_name="iGaming Domain Knowledge",
            canonical_name="iGaming Domain Knowledge",
            category=ParsedSkillCategory.DOMAIN,
            taxonomy_code="DOM-IGM-0001",
            proficiency_signal="2+ years in sportsbook and casino backend systems",
            context_phrase="Sportsbook odds management, bet-slip processing, player ledger systems.",
        ),
        ParsedSkillEntry(
            raw_name="Odds Calculation Logic",
            canonical_name="Odds Calculation Logic",
            category=ParsedSkillCategory.DOMAIN,
            taxonomy_code="DOM-IGM-0002",
            proficiency_signal="familiar — European and decimal format handling",
            context_phrase="Hypothesis-based property testing for financial calculation edge cases.",
        ),
        # ── Soft Skills ───────────────────────────────────────────────────────
        # count=2 → soft_skills_signals score = 0.48 (per score_map[2])
        ParsedSkillEntry(
            raw_name="Technical Communication",
            canonical_name="Technical Communication",
            category=ParsedSkillCategory.SOFT,
            taxonomy_code="SOFT-COM-0001",
            proficiency_signal=None,
            context_phrase="Participate in code reviews; enforce PEP-8 standards.",
        ),
        ParsedSkillEntry(
            raw_name="Problem Solving",
            canonical_name="Problem Solving",
            category=ParsedSkillCategory.SOFT,
            taxonomy_code="SOFT-PRB-0001",
            proficiency_signal=None,
            context_phrase="Diagnosed and resolved high-cardinality CTE performance regression.",
        ),
    ],
    language_proficiencies=[
        LanguageProficiency(
            language="Armenian",
            cefr_level=CEFRLevel.NATIVE,
            raw_proficiency_label="մայրենի",
        ),
        LanguageProficiency(
            language="Russian",
            cefr_level=CEFRLevel.C1,
            raw_proficiency_label="свободно",
        ),
        LanguageProficiency(
            language="English",
            cefr_level=CEFRLevel.B2,
            raw_proficiency_label="Upper Intermediate — professional working proficiency",
        ),
    ],
    certifications=[
        ParsedCertification(
            name="PCEP – Certified Entry-Level Python Programmer",
            issuing_organization="Python Institute",
            issue_date_raw="Հոկտեմբեր 2022",
            expiry_date_raw=None,
            credential_id="PCEP-30-02",
            is_active=True,
        ),
    ],
    projects=[
        ParsedProject(
            title="Async Bet Settlement Microservice",
            description=(
                "FastAPI + PostgreSQL microservice handling end-to-end bet settlement for "
                "a mock sportsbook. Implements idempotent payout processing with Celery "
                "retries, PostgreSQL advisory locks, and full OpenAPI specification."
            ),
            technologies=["Python", "FastAPI", "PostgreSQL", "Celery", "Redis", "Docker"],
            role="sole developer",
            url_or_repo="https://github.com/[CANDIDATE]/bet-settlement-service",
            is_academic=False,
            impact_statement="Processes 500 concurrent settlement requests per second in load tests.",
        ),
        ParsedProject(
            title="PostgreSQL Query Optimization Workbook",
            description=(
                "Annotated collection of 18 slow-query case studies from production iGaming "
                "workloads. Each case documents the EXPLAIN ANALYZE output before and after "
                "optimization, with rationale for index strategy or CTE refactor choice."
            ),
            technologies=["PostgreSQL", "SQL"],
            role="sole author",
            url_or_repo="https://github.com/[CANDIDATE]/pg-optimization-workbook",
            is_academic=False,
            impact_statement="Referenced by 3 colleagues for on-call query performance triage.",
        ),
        ParsedProject(
            title="YSU Final Thesis — Web Scraping Pipeline for Armenian Job Market Analysis",
            description=(
                "Scraped and processed 12,000+ Armenian job postings using BeautifulSoup "
                "and requests. Stored in PostgreSQL and analyzed skill demand trends "
                "using Python pandas aggregations."
            ),
            technologies=["Python", "PostgreSQL", "pandas", "BeautifulSoup", "requests"],
            role="sole developer",
            url_or_repo=None,
            is_academic=True,
            impact_statement="Awarded distinction by faculty evaluation committee.",
        ),
    ],
    format_quality=CVFormatQualitySignals(
        detected_format_type=CVFormatType.CHRONOLOGICAL,
        # Primary script is LATIN (English CV body) with Armenian in date fields
        primary_script=ScriptType.LATIN,
        detected_languages=["English", "Armenian"],
        section_headers_found=[
            "Professional Summary",
            "Work Experience",
            "Education",
            "Technical Skills",
            "Projects",
            "Languages",
            "Certifications",
        ],
        has_contact_section=True,
        has_summary_section=True,
        has_skills_section=True,
        has_experience_section=True,
        has_education_section=True,
        estimated_ats_compliance=0.78,
        # "mixed_rtl_ltr" anomaly: Armenian Hayots Gir script embedded in English document
        # preprocessing_confidence computed by degrade_confidence_for_anomalies:
        #   1.0 - 1 * 0.08 = 0.92
        extraction_anomalies=["mixed_rtl_ltr"],
    ),
    section_extraction_confidence={
        "work_history":   0.95,
        "education":      1.00,
        "skills":         0.95,
        "languages":      1.00,
        "certifications": 1.00,
        "projects":       0.90,
    },
    extraction_notes=[
        "Work history start/end dates in Armenian (Հուլիս, Հոկտեմբեր, Հունիս) parsed via _ARMENIAN_MONTHS.",
        "End date 'Ներկա' matched against present_tokens; is_current_role set to True for Role 1.",
        "Skills deduplicated by (canonical_name, category) — no conflicts detected.",
        "quantitative_achievements extracted from three numeric-containing responsibility bullets.",
        "thesis project flagged is_academic=True based on 'YSU Final Thesis' title prefix.",
    ],
    # total_years_experience and inferred_seniority are computed by model_validator.
    # Expected as of June 2026:
    #   total_months = 11 (Role 1) + 32 (Role 2) = 43
    #   total_years  = 43 / 12 = 3.583 → rounded to 3.6
    #   inferred_seniority: total_years ≈ 3.6 → bracket [3, 6) → SeniorityLevel.MID
    inferred_seniority=ParsedSeniorityLevel.MID,
    career_domain_signals=["igaming", "fintech", "backend_engineering"],
)


# ===========================================================================
# SECTION D — MOCK_CV_ENTITIES  (CVEntities — deterministic, no datetime deps)
# ===========================================================================
# This is the canonical form consumed by PayloadAssembler. Unlike MOCK_PARSED_CV,
# total_years_experience is hardcoded to 3.6 so that scoring assertions remain
# deterministic regardless of when tests execute.
#
# Scoring implication of 3.6 years vs 5.0 required:
#   ratio = 3.6 / 5.0 = 0.720
#   bracket: ratio ∈ [0.60, 0.80) → base_score = 0.52
#   seniority bonus: inferred=MID (rank 2) ≠ required=SENIOR (rank 3) → +0.00
#   experience_depth_alignment = 0.52  (NOT below 0.40 — critical floor NOT
#   triggered by this dimension alone; only technical_skills_match triggers it)

MOCK_CV_ENTITIES = CVEntities(
    masked_identifier="[CANDIDATE]",
    contact_info_present=True,
    work_history=[
        WorkExperience(
            company="Digitain LLC",
            title="Backend Engineer",
            start_date="2025-07",
            end_date="Present",
            duration_months=11,
            responsibilities=[
                "FastAPI microservices for 2,000+ concurrent WebSocket connections.",
                "PostgreSQL partial indexing — 76% index size reduction on bet_slips.",
                "CTE refactoring: leaderboard query from 4.2s to 380ms.",
                "Docker Compose and Kubernetes resource manifest ownership.",
                "pytest suite at 91% coverage with hypothesis property tests.",
            ],
            technologies_mentioned=[
                "Python", "FastAPI", "PostgreSQL", "SQLAlchemy",
                "Docker", "Kubernetes", "pytest", "Redis", "Celery",
            ],
            domain="igaming",
        ),
        WorkExperience(
            company="Softconstruct CJSC",
            title="Junior Python Developer",
            start_date="2022-10",
            end_date="2025-06",
            duration_months=32,
            responsibilities=[
                "REST APIs for sportsbook odds management — <200ms SLA.",
                "PostgreSQL schema for events, markets, and selections (multi-join queries).",
                "Celery task queues: 30,000+ payout tasks per day.",
                "Django async view migration: P95 latency 650ms → 210ms.",
            ],
            technologies_mentioned=[
                "Python", "Django REST Framework", "PostgreSQL",
                "Celery", "Redis", "Git", "Docker", "Linux",
            ],
            domain="igaming",
        ),
    ],
    education=[
        EducationEntry(
            institution="Yerevan State University",
            degree="Bachelor of Science in Computer Science",
            field_of_study="Computer Science",
            graduation_year=2022,
            is_relevant_to_role=None,   # Not yet assessed by Semantic Alignment Agent
        ),
    ],
    raw_skills=[
        SkillEntry(
            raw_name="Python",
            canonical_name="Python",
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="3.5 years production",
        ),
        SkillEntry(
            raw_name="FastAPI",
            canonical_name="FastAPI",
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="advanced",
        ),
        SkillEntry(
            raw_name="PostgreSQL",
            canonical_name="PostgreSQL",
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="advanced — partial indexing, query plan optimization",
        ),
        SkillEntry(
            raw_name="SQL",
            canonical_name="SQL",
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="advanced — CTEs, window functions, EXPLAIN ANALYZE",
        ),
        SkillEntry(
            raw_name="SQLAlchemy",
            canonical_name="SQLAlchemy",
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="intermediate-advanced",
        ),
        SkillEntry(
            raw_name="Docker",
            canonical_name="Docker",
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="intermediate",
        ),
        SkillEntry(
            raw_name="Kubernetes",
            canonical_name="Kubernetes",
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="basic",
        ),
        SkillEntry(
            raw_name="Redis",
            canonical_name="Redis",
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="intermediate — cache layer client",
        ),
        SkillEntry(
            raw_name="Celery",
            canonical_name="Celery",
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="intermediate",
        ),
        SkillEntry(
            raw_name="pytest",
            canonical_name="pytest",
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="advanced",
        ),
        SkillEntry(
            raw_name="Git",
            canonical_name="Git",
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="proficient",
        ),
        SkillEntry(
            raw_name="Linux",
            canonical_name="Linux",
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="intermediate",
        ),
        SkillEntry(
            raw_name="REST API Design",
            canonical_name="REST API Design",
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="advanced",
        ),
        # ── Domain skills ────────────────────────────────────────────────
        SkillEntry(
            raw_name="iGaming Domain Knowledge",
            canonical_name="iGaming Domain Knowledge",
            category=SkillCategory.DOMAIN,
            taxonomy_code=None,
            proficiency_signal="2+ years in sportsbook and casino backend systems",
        ),
        SkillEntry(
            raw_name="Odds Calculation Logic",
            canonical_name="Odds Calculation Logic",
            category=SkillCategory.DOMAIN,
            taxonomy_code=None,
            proficiency_signal="familiar",
        ),
        # ── Soft skills (count=2 → soft_skills_signals score = 0.48) ────
        SkillEntry(
            raw_name="Technical Communication",
            canonical_name="Technical Communication",
            category=SkillCategory.SOFT,
            taxonomy_code=None,
            proficiency_signal=None,
        ),
        SkillEntry(
            raw_name="Problem Solving",
            canonical_name="Problem Solving",
            category=SkillCategory.SOFT,
            taxonomy_code=None,
            proficiency_signal=None,
        ),
    ],
    languages=["Armenian", "Russian", "English"],
    certifications=["PCEP – Certified Entry-Level Python Programmer (Python Institute, 2022)"],
    total_years_experience=CANDIDATE_EXP_YEARS,   # 3.6 — deterministic
    inferred_seniority=SeniorityLevel.MID,
    career_domain_signals=["igaming", "fintech", "backend_engineering"],
)


# ===========================================================================
# SECTION E — MOCK_SKILLS_ONTOLOGY_RESULT
# ===========================================================================
# Mathematical invariant:
#   total_required_skills = 5
#   matched_count         = 2   (Python, SQL)
#   coverage_ratio        = 2/5 = 0.40
#   critical_gap_count    = 3   (ClickHouse, Airflow, Spark)
#   critical_penalty      = min(3 * 0.07, 0.30) = 0.21
#   adjusted_tech_score   = max(0, 0.40 - 0.21) = 0.19  ← triggers critical floor
#   gap_severity          = CRITICAL (critical_gap_count >= 3)
#
# Redis is in JD preferred AND in CV → appears in matched_skills (is_critical=False).
# ClickHouse, Airflow, Spark have NO transferable equivalents in CV:
#   ClickHouse requires OLAP columnar engine knowledge — PostgreSQL RDBMS expertise
#     does not transfer (architecture is fundamentally different).
#   Airflow requires workflow orchestration DAG authoring — Celery covers task
#     queuing only, not DAG-level dependency management.
#   Spark requires distributed in-memory computation — no equivalent in CV.
# All three are therefore in missing_critical, not transferable.

MOCK_SKILLS_ONTOLOGY_RESULT = SkillsOntologyResult(
    matched_skills=[
        # Required skill matches
        SkillMatchEntry(
            skill_name="Python",
            canonical_name="Python",
            match_type=SkillMatchType.MATCHED,
            transfer_confidence=None,
            transfer_rationale=None,
            is_critical=True,
        ),
        SkillMatchEntry(
            skill_name="SQL",
            canonical_name="SQL",
            match_type=SkillMatchType.MATCHED,
            transfer_confidence=None,
            transfer_rationale=None,
            is_critical=True,
        ),
        # Preferred skill match
        SkillMatchEntry(
            skill_name="Redis",
            canonical_name="Redis",
            match_type=SkillMatchType.MATCHED,
            transfer_confidence=None,
            transfer_rationale=None,
            is_critical=False,
        ),
    ],
    missing_critical=[
        # ── ClickHouse — zero transferable equivalent ───────────────────
        SkillMatchEntry(
            skill_name="ClickHouse",
            canonical_name="ClickHouse",
            match_type=SkillMatchType.MISSING_CRITICAL,
            transfer_confidence=None,
            transfer_rationale=(
                "Candidate's PostgreSQL expertise covers relational SQL authoring but "
                "does not transfer to ClickHouse's columnar OLAP architecture, "
                "MergeTree engine family, sharding topology, or distributed query planner. "
                "The skill gap is architectural, not syntactic."
            ),
            is_critical=True,
        ),
        # ── Apache Airflow — zero transferable equivalent ───────────────
        SkillMatchEntry(
            skill_name="Apache Airflow",
            canonical_name="Apache Airflow",
            match_type=SkillMatchType.MISSING_CRITICAL,
            transfer_confidence=None,
            transfer_rationale=(
                "Candidate uses Celery for distributed task queuing, which covers "
                "async task execution but not DAG-level workflow orchestration, "
                "dependency graphs, SLA monitoring, or backfill mechanics that "
                "Airflow provides for data pipeline scheduling."
            ),
            is_critical=True,
        ),
        # ── Apache Spark — zero transferable equivalent ─────────────────
        SkillMatchEntry(
            skill_name="Apache Spark",
            canonical_name="Apache Spark",
            match_type=SkillMatchType.MISSING_CRITICAL,
            transfer_confidence=None,
            transfer_rationale=(
                "Candidate has no distributed computation framework experience. "
                "Pandas data manipulation (thesis project) does not transfer to "
                "Spark's RDD/DataFrame abstraction, structured streaming, "
                "Catalyst optimizer, or cluster resource management."
            ),
            is_critical=True,
        ),
    ],
    missing_preferred=[
        SkillMatchEntry(
            skill_name="Apache Kafka",
            canonical_name="Apache Kafka",
            match_type=SkillMatchType.MISSING_PREFERRED,
            transfer_confidence=None,
            transfer_rationale=None,
            is_critical=False,
        ),
        SkillMatchEntry(
            skill_name="dbt",
            canonical_name="dbt",
            match_type=SkillMatchType.MISSING_PREFERRED,
            transfer_confidence=None,
            transfer_rationale=None,
            is_critical=False,
        ),
        SkillMatchEntry(
            skill_name="Scala",
            canonical_name="Scala",
            match_type=SkillMatchType.MISSING_PREFERRED,
            transfer_confidence=None,
            transfer_rationale=None,
            is_critical=False,
        ),
    ],
    transferable=[],      # Intentionally empty — gaps are architectural, not syntactic
    total_required_skills=5,
    matched_count=2,      # Python, SQL
    critical_gap_count=3, # ClickHouse, Airflow, Spark
    coverage_ratio=0.40,  # 2/5 — satisfies model_validator: abs(0.40 - 2/5) < 0.01
    gap_severity=GapSeverity.CRITICAL,
)


# ===========================================================================
# SECTION F — MOCK_SEMANTIC_ANALYSIS
# ===========================================================================
# Values are engineered to produce the following downstream dimension scores:
#
#   semantic_contextual_alignment:
#     = 0.65 * embedding_cosine_similarity + 0.35 * key_phrase_overlap_ratio
#     = 0.65 * 0.68 + 0.35 * 0.49
#     = 0.4420 + 0.1715
#     = 0.6135   (rounds to 0.614 in DimensionScoreMapper)
#
#   domain_knowledge (uses contextual_domain_alignment = 0.72):
#     domain_overlap ≈ 0.62 (career_domain_signals contain 'igaming' ↔ JD industry)
#     = 0.60 * 0.72 + 0.40 * 0.62
#     = 0.4320 + 0.2480
#     = 0.6800
#
# Rationale for moderate similarity scores:
#   Candidate CV and JD share Python/SQL vocabulary, iGaming domain context, and
#   backend engineering framing. However, the JD's dominant vocabulary
#   (ClickHouse, Airflow, Spark, streaming, OLAP, MergeTree) is completely absent
#   from the CV, producing a moderate-low embedding cosine similarity of 0.68
#   and low phrase overlap of 0.49.

MOCK_SEMANTIC_ANALYSIS = SemanticAnalysis(
    embedding_cosine_similarity=0.68,
    key_phrase_overlap_ratio=0.49,
    cv_unique_key_phrases=CV_UNIQUE_KEY_PHRASES,
    jd_unique_key_phrases=JD_UNIQUE_KEY_PHRASES,
    shared_key_phrases=SHARED_KEY_PHRASES,
    contextual_domain_alignment=0.72,
)


# ===========================================================================
# SECTION G — EXPECTED_SCORING_OUTCOMES
# ===========================================================================
# Deterministic mathematical expectations for test assertions.
# Time-dependent values are annotated with the date context used in design.
#
# These values must be used in test assertions AFTER running:
#   compute_composite_score(EXPECTED_RAW_DIMENSION_SCORES)
# to verify that scoring.py produces them exactly.

EXPECTED_RAW_DIMENSION_SCORES: Dict[str, float] = {
    # ── Computed by DimensionScoreMapper ─────────────────────────────────────
    # technical_skills_match:
    #   coverage_ratio = 0.40, critical_gap_count = 3
    #   adjusted = max(0, 0.40 - min(3*0.07, 0.30)) = max(0, 0.40 - 0.21) = 0.19
    "technical_skills_match":        0.19,

    # experience_depth_alignment:
    #   actual=3.6, required=5.0 → ratio=0.720 → bracket [0.60, 0.80) → base=0.52
    #   seniority_bonus=0 (inferred=MID ≠ required=SENIOR)
    "experience_depth_alignment":    0.52,

    # semantic_contextual_alignment:
    #   0.65*0.68 + 0.35*0.49 = 0.442 + 0.1715 = 0.6135
    "semantic_contextual_alignment": 0.6135,

    # domain_knowledge:
    #   0.60*0.72 (contextual_domain_alignment) + 0.40*0.62 (domain_overlap) = 0.68
    "domain_knowledge":              0.68,

    # educational_relevance:
    #   CS field → EDUCATION_HIGH_RELEVANCE_KEYWORDS match → base=0.88
    #   is_relevant_to_role=None (not set by SemanticAlignmentAgent yet) → uses heuristic
    "educational_relevance":         0.88,

    # seniority_trajectory:
    #   required=SENIOR (rank 3), inferred=MID (rank 2), delta=3-2=1
    #   score_table[1] = 0.62
    "seniority_trajectory":          0.62,

    # soft_skills_signals:
    #   count=2 soft skills → score_map[2] = 0.48
    "soft_skills_signals":           0.48,
}

EXPECTED_SCORING_OUTCOMES: Dict[str, Any] = {

    # ── Per-dimension score assertions ───────────────────────────────────────
    "technical_skills_match_score":           0.19,
    "experience_depth_alignment_score":       0.52,
    "semantic_contextual_alignment_score":    0.6135,
    "domain_knowledge_score":                 0.68,
    "educational_relevance_score":            0.88,
    "seniority_trajectory_score":             0.62,
    "soft_skills_signals_score":              0.48,

    # ── Floor threshold assertions ────────────────────────────────────────────
    # CRITICAL_FLOOR_THRESHOLD = 0.40
    "technical_skills_match_below_critical_floor":    True,   # 0.19 < 0.40 ✓
    "experience_depth_alignment_below_critical_floor": False,  # 0.52 >= 0.40 ✓
    "critical_floor_triggered":                        True,   # tech breach → True
    "expected_critical_dimensions_breached":           ["technical_skills_match"],

    # GENERAL_FLOOR_THRESHOLD = 0.35
    "technical_skills_match_below_general_floor":     True,   # 0.19 < 0.35 ✓
    "expected_general_dimensions_breached":            ["technical_skills_match"],

    # ── Geometric mean and cap assertions ────────────────────────────────────
    # geo_mean = 0.461 (verified by pre-generation script)
    # CRITICAL_FLOOR_CAP = 0.44; since 0.461 > 0.44, cap IS binding
    "expected_geometric_mean_raw":   0.461,   # Computed value
    "expected_geometric_mean_min":   0.44,    # Lower bound for assertion tolerance
    "expected_geometric_mean_max":   0.52,    # Upper bound (accounts for time-dep exp score)

    # ── Final composite assertions (deterministic — cap always applied) ───────
    # As long as technical_skills_match < 0.40, geo_mean will remain above 0.44
    # for any reasonable set of scores in the other 6 dimensions.
    "expected_composite_score":       0.44,   # = CRITICAL_FLOOR_CAP
    "expected_composite_percentage":  44.0,
    "expected_hard_floor_applied":    True,
    "expected_floor_tier":            "critical_only",

    # ── Outlier detection assertions ─────────────────────────────────────────
    # Only technical_skills_match (0.19) is below GENERAL_FLOOR_THRESHOLD (0.35)
    "expected_outlier_alert":         True,
    "expected_outlier_dimensions":    ["technical_skills_match"],

    # ── Skills match assertions ───────────────────────────────────────────────
    "expected_matched_required_count": 2,        # Python, SQL
    "expected_critical_gap_count":     3,        # ClickHouse, Airflow, Spark
    "expected_coverage_ratio":         0.40,     # 2/5
    "expected_gap_severity":           "critical",

    # ── Hire recommendation tier (for recruiter perspective validation) ───────
    # At 44% composite with 3 critical gaps: NO
    "expected_hire_recommendation_tier": "no",

    # ── Experience depth tier ────────────────────────────────────────────────
    # 3.6 years vs 5.0 required: under-qualified but not severely
    "expected_experience_ratio":    0.72,
    "expected_experience_score":    0.52,
    "candidate_exp_years":          CANDIDATE_EXP_YEARS,
    "required_exp_years":           REQUIRED_EXP_YEARS,
}


# ===========================================================================
# SECTION H — Variant Factory Functions
# ===========================================================================
# Factory functions that produce modified CVEntities objects for parametric
# testing. Each variant isolates a single variable to validate that scoring.py
# responds correctly to dimension-specific changes.

def create_clickhouse_qualified_cv() -> CVEntities:
    """
    Variant: Candidate with ClickHouse, Airflow, and Spark added to skill set.

    Expected effect on scoring:
      technical_skills_match:
        matched_count → 5 (all required), coverage_ratio → 1.0
        critical_gap_count → 0, critical_penalty → 0.0
        adjusted_score → 1.0
        → 1.0 >= 0.40: critical floor NOT triggered
      composite_score: should rise to approximately 0.75–0.85 range
      hard_floor_applied: False (assuming experience_depth_alignment also >= 0.40)
    """
    data_engineering_skills = [
        SkillEntry(
            raw_name="ClickHouse",
            canonical_name="ClickHouse",
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="intermediate — ReplacingMergeTree, basic sharding",
        ),
        SkillEntry(
            raw_name="Apache Airflow",
            canonical_name="Apache Airflow",
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="intermediate — DAG authoring, sensor usage",
        ),
        SkillEntry(
            raw_name="Apache Spark",
            canonical_name="Apache Spark",
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="basic — PySpark DataFrame API",
        ),
    ]
    return CVEntities(
        masked_identifier="[CANDIDATE_VARIANT_A]",
        contact_info_present=True,
        work_history=MOCK_CV_ENTITIES.work_history,
        education=MOCK_CV_ENTITIES.education,
        raw_skills=MOCK_CV_ENTITIES.raw_skills + data_engineering_skills,
        languages=MOCK_CV_ENTITIES.languages,
        certifications=MOCK_CV_ENTITIES.certifications,
        total_years_experience=CANDIDATE_EXP_YEARS,
        inferred_seniority=SeniorityLevel.MID,
        career_domain_signals=["igaming", "data_analytics", "backend_engineering"],
    )


def create_senior_experience_cv() -> CVEntities:
    """
    Variant: Candidate with 6.0 years of experience (above the 5.0 requirement).

    Expected effect on scoring:
      experience_depth_alignment:
        ratio = 6.0 / 5.0 = 1.20 → bracket [1.0, 1.5) → base = 0.85
        seniority_bonus: inferred=SENIOR matches required=SENIOR → +0.05
        score = min(1.0, 0.85 + 0.05) = 0.90
      technical_skills_match: unchanged at 0.19 (still triggers critical floor)
      composite_score: still capped at 0.44 (technical_skills_match still < 0.40)
      hard_floor_applied: True (critical floor still binding)
    """
    senior_work_history = [
        WorkExperience(
            company="Digitain LLC",
            title="Senior Backend Engineer",
            start_date="2023-06",
            end_date="Present",
            duration_months=24,
            responsibilities=[
                "Led backend architecture for real-time odds delivery microservices.",
                "PostgreSQL performance ownership: partial indexes, materialized views, query plan audits.",
            ],
            technologies_mentioned=["Python", "FastAPI", "PostgreSQL", "Docker", "Redis"],
            domain="igaming",
        ),
        WorkExperience(
            company="Softconstruct CJSC",
            title="Backend Developer",
            start_date="2020-06",
            end_date="2023-05",
            duration_months=35,
            responsibilities=[
                "REST APIs for sportsbook platform — SLA <200ms.",
                "Celery distributed task queues for payout processing.",
            ],
            technologies_mentioned=["Python", "Django", "PostgreSQL", "Celery", "Redis"],
            domain="igaming",
        ),
        WorkExperience(
            company="Nairi Soft LLC",
            title="Junior Python Developer",
            start_date="2019-04",
            end_date="2020-05",
            duration_months=13,
            responsibilities=[
                "Maintained Django CMS for corporate clients.",
                "Wrote SQL reports for management dashboards.",
            ],
            technologies_mentioned=["Python", "Django", "PostgreSQL", "SQL"],
            domain="saas",
        ),
    ]
    return CVEntities(
        masked_identifier="[CANDIDATE_VARIANT_B]",
        contact_info_present=True,
        work_history=senior_work_history,
        education=MOCK_CV_ENTITIES.education,
        raw_skills=MOCK_CV_ENTITIES.raw_skills,
        languages=MOCK_CV_ENTITIES.languages,
        certifications=MOCK_CV_ENTITIES.certifications,
        total_years_experience=6.0,
        inferred_seniority=SeniorityLevel.SENIOR,
        career_domain_signals=["igaming", "backend_engineering", "saas"],
    )


def create_fully_qualified_cv() -> CVEntities:
    """
    Variant: Ideal candidate — all required and preferred skills present,
    6.0 years experience, SENIOR seniority.

    Expected effect on scoring:
      technical_skills_match: coverage_ratio = 5/5 = 1.0, critical_gap_count = 0 → score = 1.0
      experience_depth_alignment: ratio = 1.2, seniority match → score ≈ 0.90
      All other dimensions: high scores (0.75–0.95 range)
      critical_floor_triggered: False (tech = 1.0 >= 0.40)
      hard_floor_applied: False
      composite_score: expected 0.85–0.95
    """
    full_skills = MOCK_CV_ENTITIES.raw_skills + [
        SkillEntry(
            raw_name="ClickHouse",
            canonical_name="ClickHouse",
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="3 years — ReplacingMergeTree, sharding, replication",
        ),
        SkillEntry(
            raw_name="Apache Airflow",
            canonical_name="Apache Airflow",
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="2 years — custom operators, SLA monitoring, backfill",
        ),
        SkillEntry(
            raw_name="Apache Spark",
            canonical_name="Apache Spark",
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="2 years — structured streaming, partitioning strategies",
        ),
        SkillEntry(
            raw_name="Apache Kafka",
            canonical_name="Apache Kafka",
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="1 year — consumer groups, topic partitioning",
        ),
        SkillEntry(
            raw_name="dbt",
            canonical_name="dbt",
            category=SkillCategory.TECHNICAL,
            taxonomy_code=None,
            proficiency_signal="familiar — models, tests, documentation",
        ),
    ]
    return CVEntities(
        masked_identifier="[CANDIDATE_VARIANT_C]",
        contact_info_present=True,
        work_history=create_senior_experience_cv().work_history,
        education=[
            EducationEntry(
                institution="Yerevan State University",
                degree="Master of Science in Data Science for Business",
                field_of_study="Data Science",
                graduation_year=2022,
                is_relevant_to_role=True,
            ),
        ],
        raw_skills=full_skills,
        languages=["Armenian", "Russian", "English"],
        certifications=[
            "PCEP – Certified Entry-Level Python Programmer (Python Institute, 2022)",
            "ClickHouse Certified Developer (ClickHouse Inc., 2024)",
        ],
        total_years_experience=6.0,
        inferred_seniority=SeniorityLevel.SENIOR,
        career_domain_signals=["igaming", "data_analytics", "backend_engineering"],
    )


def create_skills_ontology_for_variant(
    matched_required_skills: List[str],
    all_required_skills: Optional[List[str]] = None,
) -> SkillsOntologyResult:
    """
    Factory for constructing a SkillsOntologyResult with a custom matched set.
    Used in parametric tests to sweep over different coverage_ratio values.

    Parameters
    ----------
    matched_required_skills : list of canonical skill names (subset of required)
    all_required_skills     : full required skill list; defaults to JD required set

    Returns
    -------
    SkillsOntologyResult with consistent coverage_ratio and critical_gap_count.
    """
    if all_required_skills is None:
        all_required_skills = [
            SKILL_CLICKHOUSE, SKILL_AIRFLOW, SKILL_SPARK, SKILL_PYTHON, SKILL_SQL
        ]

    matched_set = set(matched_required_skills)
    missing_set = set(all_required_skills) - matched_set

    matched_entries = [
        SkillMatchEntry(
            skill_name=name,
            canonical_name=name,
            match_type=SkillMatchType.MATCHED,
            transfer_confidence=None,
            transfer_rationale=None,
            is_critical=True,
        )
        for name in matched_required_skills
    ]
    missing_entries = [
        SkillMatchEntry(
            skill_name=name,
            canonical_name=name,
            match_type=SkillMatchType.MISSING_CRITICAL,
            transfer_confidence=None,
            transfer_rationale=None,
            is_critical=True,
        )
        for name in sorted(missing_set)
    ]

    n_required = len(all_required_skills)
    n_matched  = len(matched_required_skills)
    ratio      = round(n_matched / n_required, 4) if n_required > 0 else 0.0
    n_gaps     = len(missing_entries)
    severity   = (
        GapSeverity.CRITICAL  if n_gaps >= 3 else
        GapSeverity.MODERATE  if n_gaps >= 1 else
        GapSeverity.NONE
    )

    return SkillsOntologyResult(
        matched_skills=matched_entries,
        missing_critical=missing_entries,
        missing_preferred=[],
        transferable=[],
        total_required_skills=n_required,
        matched_count=n_matched,
        critical_gap_count=n_gaps,
        coverage_ratio=ratio,
        gap_severity=severity,
    )


# ===========================================================================
# SECTION I — Parametric Floor Sweep Table
# ===========================================================================
# Provides a table of (technical_skills_match_score, expected_floor_behavior)
# pairs for parametric scoring tests. Tests sweep across this table using
# `create_skills_ontology_for_variant` to generate the corresponding ontology.
#
# Each row is: (n_matched_required, expected_tech_score, floor_tier, cap_value)

PARAMETRIC_FLOOR_SWEEP: List[Dict[str, Any]] = [
    {
        "description":        "0/5 required matched — catastrophic gap",
        "n_matched_required": 0,
        "coverage_ratio":     0.00,
        "critical_gap_count": 5,
        "expected_tech_score": 0.00,   # max(0, 0.00 - 0.30) = 0.00
        "critical_floor_triggered": True,
        "note": "geo_mean will be 0 due to log(0) clamp — cap non-binding",
    },
    {
        "description":        "1/5 required matched — severe gap",
        "n_matched_required": 1,
        "coverage_ratio":     0.20,
        "critical_gap_count": 4,
        "expected_tech_score": 0.00,   # max(0, 0.20 - 0.28) = 0.00 (clamped)
        "critical_floor_triggered": True,
        "note": "4*0.07=0.28 > 0.20 → adjusted_score clamped to 0.0",
    },
    {
        "description":        "2/5 required matched — baseline fixture (ClickHouse/Airflow/Spark missing)",
        "n_matched_required": 2,
        "coverage_ratio":     0.40,
        "critical_gap_count": 3,
        "expected_tech_score": 0.19,   # max(0, 0.40 - 0.21) = 0.19
        "critical_floor_triggered": True,
        "expected_floor_tier": "critical_only",
        "expected_composite_score": 0.44,
        "note": "Baseline fixture — primary test case for critical floor binding",
    },
    {
        "description":        "3/5 required matched — one critical gap remains",
        "n_matched_required": 3,
        "coverage_ratio":     0.60,
        "critical_gap_count": 2,
        "expected_tech_score": 0.46,   # max(0, 0.60 - 0.14) = 0.46
        "critical_floor_triggered": False,
        "note": "0.46 >= 0.40 → critical floor NOT triggered; general floor unlikely",
    },
    {
        "description":        "4/5 required matched — preferred gap only",
        "n_matched_required": 4,
        "coverage_ratio":     0.80,
        "critical_gap_count": 1,
        "expected_tech_score": 0.73,   # max(0, 0.80 - 0.07) = 0.73
        "critical_floor_triggered": False,
        "note": "Strong match; composite in healthy range",
    },
    {
        "description":        "5/5 required matched — all critical skills present",
        "n_matched_required": 5,
        "coverage_ratio":     1.00,
        "critical_gap_count": 0,
        "expected_tech_score": 1.00,
        "critical_floor_triggered": False,
        "note": "Perfect technical coverage; composite driven by other dimensions",
    },
]


# ===========================================================================
# SECTION J — Lazy-Loading Accessor Interface
# ===========================================================================
# All public fixture accessors are implemented as functions rather than bare
# module-level references. This design avoids circular import risk: downstream
# modules (PayloadAssembler tests, orchestrator integration tests, Phase 3
# simulation harness) can import ONLY the accessor they need without triggering
# the full construction of every Pydantic object at import time in their own
# test module's global scope.
#
# Usage pattern (in any test module):
#
#   from tests.mock_fixtures import get_synthetic_jd, get_synthetic_cv_entities
#
#   def test_experience_depth_score():
#       jd  = get_synthetic_jd()
#       cv  = get_synthetic_cv_entities()
#       score = DimensionScoreMapper().experience_depth_alignment(cv, jd)
#       assert score.raw_score == 0.52
#
# Every accessor is idempotent: multiple calls within the same process return
# the identical module-level object without reconstructing it. Pydantic
# model_validators run exactly once, at module import time, when the
# module-level constants (MOCK_JD_ENTITIES, MOCK_PARSED_CV, …) are defined.


def get_synthetic_jd() -> JDEntities:
    """
    Returns the canonical JDEntities fixture for the Senior Data Engineer role.

    Downstream consumers:
      - PayloadAssembler.assemble() integration tests
      - DimensionScoreMapper.experience_depth_alignment() unit tests
      - DimensionScoreMapper.seniority_trajectory() unit tests
      - Recruiter Intelligence Room rendering tests
    """
    return MOCK_JD_ENTITIES


def get_synthetic_cv_output() -> ParsedCVOutput:
    """
    Returns the ParsedCVOutput fixture with Armenian-encoded work history dates.

    Downstream consumers:
      - cv_parsing_schema date-parser unit tests (validate Armenian month regex)
      - DocumentIntelligenceAgent response-parsing integration tests
      - Phase 3 Candidate Simulation session initialisation
      - ATS compliance scoring tests (format_quality field)

    Important:
      total_years_experience and Role 1 duration_months are time-dependent
      (Role 1 end_date_raw = "Ններ" → computed against datetime.utcnow()).
      For deterministic scoring assertions, use get_synthetic_cv_entities()
      which hardcodes total_years_experience = 3.6.
    """
    return MOCK_PARSED_CV


def get_synthetic_cv_entities() -> CVEntities:
    """
    Returns the canonical CVEntities fixture with total_years_experience = 3.6
    (deterministic — not computed from live datetime).

    This is the primary fixture for scoring.py and PayloadAssembler tests.

    Scoring expectations (against get_synthetic_jd()):
      technical_skills_match     = 0.19  (< 0.40 → critical floor triggered)
      experience_depth_alignment = 0.52  (>= 0.40 → does not independently trigger floor)
      composite_score            = 0.44  (capped at CRITICAL_FLOOR_CAP)
    """
    return MOCK_CV_ENTITIES


def get_synthetic_skills_ontology() -> SkillsOntologyResult:
    """
    Returns the SkillsOntologyResult fixture encoding the 2/5 required skill
    coverage state (Python + SQL matched; ClickHouse, Airflow, Spark missing).

    Scoring expectations:
      coverage_ratio    = 0.40
      critical_gap_count = 3
      adjusted_score    = max(0, 0.40 - min(3*0.07, 0.30)) = 0.19
    """
    return MOCK_SKILLS_ONTOLOGY_RESULT


def get_synthetic_semantic_analysis() -> SemanticAnalysis:
    """
    Returns the SemanticAnalysis fixture calibrated for moderate-low CV/JD
    similarity (Python/SQL vocabulary overlap; ClickHouse/Airflow/Spark absent).

    Scoring expectations:
      semantic_contextual_alignment = 0.65*0.68 + 0.35*0.49 = 0.614
      domain_knowledge (via contextual_domain_alignment=0.72) = 0.68
    """
    return MOCK_SEMANTIC_ANALYSIS


def get_expected_outcomes() -> Dict[str, Any]:
    """
    Returns the EXPECTED_SCORING_OUTCOMES mapping for test assertion look-ups.

    Usage example:
      outcomes = get_expected_outcomes()
      assert result.composite_score == outcomes["expected_composite_score"]
      assert result.hard_floor_applied == outcomes["expected_hard_floor_applied"]
    """
    return EXPECTED_SCORING_OUTCOMES


def get_expected_raw_scores() -> Dict[str, float]:
    """
    Returns the pre-computed seven-dimensional score dictionary that, when
    passed to compute_composite_score(), must produce:
      geometric_mean_raw  ≈ 0.461
      composite_score     = 0.44  (CRITICAL_FLOOR_CAP binding)
      hard_floor_applied  = True
    """
    return EXPECTED_RAW_DIMENSION_SCORES


def get_floor_sweep_table() -> List[Dict[str, Any]]:
    """
    Returns the parametric floor sweep table for coverage-ratio → score mapping
    tests. Each row isolates the effect of varying n_matched_required while
    holding all other dimension scores constant at the fixture baseline values.
    """
    return PARAMETRIC_FLOOR_SWEEP


def get_expected_scoring_result():
    """
    Lazily executes compute_composite_score against EXPECTED_RAW_DIMENSION_SCORES
    and returns the live ScoringResult object.

    Import of src.engine.scoring is deferred to call time so that tests that
    only need structural fixture data (date parsing, schema validation) do not
    transitively import the scoring engine and its assert-at-import-time
    DIMENSION_WEIGHTS invariant check.

    Returns
    -------
    ScoringResult
        Fully populated result object. Callers should assert:
          result.composite_score       == 0.44
          result.hard_floor_applied    == True
          result.floor_report.tier_applied.value == "critical_only"
          result.outlier_dimensions    == ["technical_skills_match"]
    """
    from src.engine.scoring import compute_composite_score
    return compute_composite_score(EXPECTED_RAW_DIMENSION_SCORES)


def get_all_fixtures() -> Dict[str, Any]:
    """
    Returns a single dictionary containing every primary fixture object.
    Intended for integration tests that need the full payload assembly context.

    Keys
    ----
    "jd"            : JDEntities
    "cv_output"     : ParsedCVOutput   (Armenian dates, time-dependent duration)
    "cv_entities"   : CVEntities       (deterministic, hardcoded years)
    "skills"        : SkillsOntologyResult
    "semantic"      : SemanticAnalysis
    "outcomes"      : Dict[str, Any]   (EXPECTED_SCORING_OUTCOMES)
    "raw_scores"    : Dict[str, float] (EXPECTED_RAW_DIMENSION_SCORES)
    "floor_sweep"   : List[Dict]       (PARAMETRIC_FLOOR_SWEEP)
    """
    return {
        "jd":          MOCK_JD_ENTITIES,
        "cv_output":   MOCK_PARSED_CV,
        "cv_entities": MOCK_CV_ENTITIES,
        "skills":      MOCK_SKILLS_ONTOLOGY_RESULT,
        "semantic":    MOCK_SEMANTIC_ANALYSIS,
        "outcomes":    EXPECTED_SCORING_OUTCOMES,
        "raw_scores":  EXPECTED_RAW_DIMENSION_SCORES,
        "floor_sweep": PARAMETRIC_FLOOR_SWEEP,
    }


def create_assembler_input_state(
    session_id: str = "fixture-session-001",
    language:   str = "en",
) -> Dict[str, Any]:
    """
    Constructs a fully populated AssemblerInputState-compatible dict using
    the canonical fixtures. This is the primary integration entry point for
    PayloadAssembler tests.

    The dict mirrors the `AssemblerInputState` TypedDict defined in
    payload_assembler.py. Importing AssemblerInputState directly is avoided
    to prevent circular imports in test modules.

    Parameters
    ----------
    session_id : str
        Session identifier injected into the payload. Use unique values per
        test to allow parallel test execution without state collision.
    language : str
        Language code for narrative generation. "en" for unit tests (avoids
        Armenian/Russian output that would complicate assertion strings).

    Returns
    -------
    dict
        Ready to pass directly to `await PayloadAssembler().assemble(state)`.
    """
    from src.schemas.canonical_payload import AgentExecutionStatus

    return {
        "cv_text":               "[REDACTED — PII-masked CV text placeholder for assembler input]",
        "jd_text":               "[REDACTED — JD text placeholder for assembler input]",
        "session_id":            session_id,
        "language":              language,
        "seniority_context":     "mid",
        "analysis_start_time_ms": 0,
        "cv_entities":           MOCK_CV_ENTITIES,
        "jd_entities":           MOCK_JD_ENTITIES,
        "semantic_result":       MOCK_SEMANTIC_ANALYSIS,
        "skills_result":         MOCK_SKILLS_ONTOLOGY_RESULT,
        "bias_audit_result":     None,    # PayloadAssembler will apply fallback
        "phase1_statuses": {
            "document_intelligence": AgentExecutionStatus.SUCCESS,
            "semantic_alignment":    AgentExecutionStatus.SUCCESS,
            "skills_ontology":       AgentExecutionStatus.SUCCESS,
        },
        "phase2_status": AgentExecutionStatus.SUCCESS,
        "agent_errors":  {
            "document_intelligence": None,
            "semantic_alignment":    None,
            "skills_ontology":       None,
        },
    }
