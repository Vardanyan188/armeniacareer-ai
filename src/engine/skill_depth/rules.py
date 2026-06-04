# src/engine/skill_depth/rules.py
#
# Curated, deterministic depth rules for the Skill Proficiency / Requirement
# Depth layer (Phase 19). No LLM, no network.
#
# Three rule families:
#   1. SKILL_DEPTH_RULES   — per-skill ecosystem tokens that authoritatively set
#                            ANY depth tier (the only way to reach ADVANCED+).
#   2. GENERIC_CLAIM_TOKENS — cross-skill proficiency *claims*; capped at APPLIED
#                            so a bare claim never inflates to ADVANCED/PRODUCTION/
#                            DEPLOYMENT without real ecosystem evidence.
#   3. JD_DEPTH_PHRASES    — JD intent phrases → required depth.
#
# All tokens are matched as lowercase substrings against already-masked,
# structured CV/JD fields — never against raw CV/JD text.

from __future__ import annotations

from typing import Dict, List, Tuple

from src.engine.skill_depth.models import SkillDepth

# Default required depth for a required JD skill with no depth clues (decision 2).
DEFAULT_REQUIRED_DEPTH = SkillDepth.APPLIED

# Highest tier a generic proficiency *claim* may reach (anti-overconfidence).
GENERIC_CLAIM_CAP = SkillDepth.APPLIED

# Cap on how many evidence labels are surfaced per skill.
MAX_EVIDENCE_LABELS = 6


# ---------------------------------------------------------------------------
# 1. Per-skill curated ecosystem tokens (authoritative; can reach any tier)
# ---------------------------------------------------------------------------
# canonical skill name (lowercased) → {tier: (tokens, …)}
SKILL_DEPTH_RULES: Dict[str, Dict[SkillDepth, Tuple[str, ...]]] = {
    "python": {
        SkillDepth.APPLIED: (
            "pandas", "numpy", "eda", "exploratory data analysis", "matplotlib",
            "seaborn", "data analysis", "data cleaning", "jupyter",
        ),
        SkillDepth.ADVANCED: (
            "scikit-learn", "sklearn", "model training", "classification",
            "regression", "machine learning", "ml model", "xgboost",
            "tensorflow", "pytorch", "nlp",
        ),
        SkillDepth.PRODUCTION: (
            "fastapi", "django", "flask", "rest api", "production",
            "optimization", "microservice", "backend api",
        ),
        SkillDepth.DEPLOYMENT: (
            "mlops", "ci/cd", "cicd", "docker", "kubernetes", "k8s",
            "monitoring", "deployment", "airflow", "sagemaker",
        ),
    },
    "sql": {
        SkillDepth.APPLIED: (
            "join", "joins", "query", "queries", "select", "group by",
            "aggregation", "reporting",
        ),
        SkillDepth.ADVANCED: (
            "window function", "cte", "stored procedure", "indexing",
            "query optimization", "subquery",
        ),
        SkillDepth.PRODUCTION: (
            "etl", "data warehouse", "partitioning", "performance tuning",
        ),
        SkillDepth.DEPLOYMENT: (
            "replication", "sharding", "database administration", "dba",
        ),
    },
    "docker": {
        SkillDepth.APPLIED: ("dockerfile", "container", "containerize", "image"),
        SkillDepth.PRODUCTION: ("docker compose", "multi-stage", "registry"),
        SkillDepth.DEPLOYMENT: (
            "kubernetes", "k8s", "ci/cd", "cicd", "orchestration",
            "production deployment", "monitoring",
        ),
    },
    "kubernetes": {
        SkillDepth.APPLIED: ("pod", "deployment manifest", "kubectl"),
        SkillDepth.PRODUCTION: ("helm", "autoscaling", "ingress"),
        SkillDepth.DEPLOYMENT: (
            "production cluster", "monitoring", "observability", "ci/cd", "cicd",
        ),
    },
    "react": {
        SkillDepth.APPLIED: ("hooks", "component", "jsx", "state", "props"),
        SkillDepth.ADVANCED: ("redux", "context api", "performance", "testing"),
        SkillDepth.PRODUCTION: ("ssr", "next.js", "production build", "optimization"),
        SkillDepth.DEPLOYMENT: ("ci/cd", "cicd", "deployment", "monitoring"),
    },
}


# ---------------------------------------------------------------------------
# 2. Generic cross-skill proficiency claims (capped at APPLIED)
# ---------------------------------------------------------------------------
# tier → tokens. Tiers above APPLIED are intentionally absent here: a generic
# claim (e.g. "advanced", "production-ready") is treated as a claim, not as
# ecosystem evidence, and is clamped to APPLIED in the analyzer.
GENERIC_CLAIM_TOKENS: Dict[SkillDepth, Tuple[str, ...]] = {
    SkillDepth.BASIC: (
        "basic", "beginner", "familiar", "familiarity", "learning", "coursework",
        "fundamentals", "introductory", "exposure", "entry-level",
    ),
    SkillDepth.APPLIED: (
        "used", "experience with", "hands-on", "hands on", "applied", "projects",
        "built", "developed", "implemented", "worked with", "proficient",
        "advanced", "expert",  # claims — clamped to APPLIED by the analyzer
    ),
}


# ---------------------------------------------------------------------------
# 3. JD requirement-depth intent phrases (highest tier first)
# ---------------------------------------------------------------------------
JD_DEPTH_PHRASES: List[Tuple[SkillDepth, Tuple[str, ...]]] = [
    (SkillDepth.DEPLOYMENT, (
        "deploy", "deployment", "monitor", "monitoring", "mlops", "ci/cd",
        "cicd", "observability", "production deployment", "operate",
    )),
    (SkillDepth.PRODUCTION, (
        "production-ready", "production ready", "production", "optimize",
        "optimization", "scalable", "high-load", "reliability", "performance",
    )),
    (SkillDepth.ADVANCED, (
        "build", "train", "design", "architect", "develop models",
        "implement", "modeling", "build ml", "machine learning models",
    )),
    (SkillDepth.APPLIED, (
        "analysis", "analyze", "analytics", "work with", "use", "apply",
        "hands-on", "reporting",
    )),
    (SkillDepth.BASIC, (
        "basic", "basic knowledge", "knowledge of", "familiarity",
        "understanding of", "exposure", "awareness",
    )),
]
