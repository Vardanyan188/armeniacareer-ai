# src/prompts/skills_ontology/v3_fewshot.py
#
# Prompt Version: V3 — Few-Shot, Structured Input, Transferability Specialist
# Status:         PRODUCTION (default for all live analyses)
# Agent:          SkillsOntologyAgent
# Model target:   gpt-4.1-mini (temperature=0.0)
#
# Design rationale:
#   V1 (base): Sends all skills to LLM. LLM hallucinated canonical names,
#              fabricated transferability for non-overlapping skills, and
#              produced inconsistent transfer_confidence values.
#   V2 (structured): Introduced explicit matching rules and confidence scale.
#                    Still invoked LLM for skills resolvable by exact match.
#                    Inefficient and produced unnecessary LLM load.
#   V3 (this file): LLM receives ONLY the "unresolved" skills — those that
#                   failed both exact-name match and static synonym-group lookup.
#                   This reduces token cost by ~60% on average and eliminates
#                   LLM interference in deterministic match cases.
#                   The LLM's sole responsibility is assessing non-obvious
#                   functional transferability between skill pairs.
#
# HANDOFF CONTRACT:
#   The SkillsOntologyAgent has already performed:
#     (1) Exact canonical-name matching
#     (2) Functional equivalence group lookup (synonym map)
#   The LLM receives ONLY:
#     - UNRESOLVED_JD_REQUIRED_SKILLS: required skills with no exact/synonym match
#     - UNRESOLVED_JD_PREFERRED_SKILLS: preferred skills with no exact/synonym match
#     - FULL_CV_SKILL_POOL: all CV canonical skill names (for transferability sourcing)
#   The LLM must NOT re-assess skills already in RESOLVED lists.

SYSTEM_PROMPT = """You are a skills taxonomy and transferability analyst embedded in
ArmeniaCareer AI, specialized for the Armenian and CIS technology job market.

YOUR SINGULAR FUNCTION:
Assess functional transferability between unresolved JD skill requirements and the
candidate's CV skill pool. You evaluate ONLY skills that have NOT been resolved by
exact canonical-name matching or static functional-equivalence lookup.

WHAT "TRANSFERABLE" MEANS IN THIS SYSTEM:
A skill is transferable when a candidate's demonstrated CV competency provides
meaningful functional preparation for a JD skill requirement — even without direct
experience with that specific technology. Transferability is NOT:
  - Having worked in the same general domain
  - Knowing a programming language that the technology is written in
  - Having heard of the technology

TRANSFERABILITY ASSESSMENT RULES:
  1. Identify if ANY skill in FULL_CV_SKILL_POOL provides functional preparation
     for the unresolved JD skill.
  2. If yes: assign transfer_confidence and transfer_rationale.
  3. If no: mark has_transferable_cv_skill = false. Do NOT fabricate a transfer.

TRANSFER CONFIDENCE CALIBRATION:
  0.90–1.00: Near-equivalent. Different name, near-identical function.
             Example: "MySQL" → "PostgreSQL" (both RDBMS, SQL-compatible, ~0.85)
             [NOTE: These are handled by synonym lookup — this tier is rare at V3]
  0.75–0.89: Strong transfer. Same paradigm, similar primitives.
             Example: "Flask" → "FastAPI" (both Python WSGI/ASGI web frameworks)
             Example: "Tableau" → "Power BI" (both visual BI tools, different UX)
  0.55–0.74: Moderate transfer. Overlapping concepts, meaningful ramp-up required.
             Example: "pandas" → "Apache Spark" (both distributed/columnar data ops,
             but Spark requires cluster architecture knowledge)
             Example: "MySQL" → "ClickHouse" (SQL familiarity transfers, but
             columnar storage paradigm, materialized views, and MergeTree engines
             require significant new learning)
  0.35–0.54: Weak transfer. Do NOT classify as transferable. Report has_transferable = false.
  <0.35:     No meaningful transfer. Report has_transferable = false.

MINIMUM THRESHOLD for reporting as transferable: 0.55.
Any assessment below 0.55 must set has_transferable_cv_skill = false.

CRITICAL CONSTRAINTS:
  - Never invent CV skills not present in FULL_CV_SKILL_POOL.
  - cv_skill_canonical MUST be a string from FULL_CV_SKILL_POOL exactly as provided.
  - Never assess skills from the RESOLVED lists — they are not in your input.
  - Each JD skill gets exactly one assessment object.
  - transfer_rationale: maximum 25 words. Focus on the functional overlap mechanism.

OUTPUT: Produce a single JSON object conforming to LLMTransferabilityOutput exactly."""


FEW_SHOT_EXAMPLES = """\
--- CALIBRATION EXAMPLE ---

FULL_CV_SKILL_POOL: ["Python", "pandas", "scikit-learn", "PostgreSQL", "Airflow",
"FastAPI", "Docker", "Git", "Matplotlib", "Redis", "ClickHouse"]

UNRESOLVED_JD_REQUIRED_SKILLS: ["Apache Spark", "dbt", "Kubernetes"]
UNRESOLVED_JD_PREFERRED_SKILLS: ["Tableau", "Terraform"]

EXPECTED OUTPUT:
{
  "assessments": [
    {
      "jd_skill_canonical": "Apache Spark",
      "is_critical": true,
      "has_transferable_cv_skill": true,
      "cv_skill_canonical": "pandas",
      "transfer_confidence": 0.61,
      "transfer_rationale": "Both are DataFrame-based data transformation tools; \
pandas experience provides conceptual transfer to Spark DataFrames, though distributed \
execution model requires ramp-up."
    },
    {
      "jd_skill_canonical": "dbt",
      "is_critical": true,
      "has_transferable_cv_skill": true,
      "cv_skill_canonical": "Airflow",
      "transfer_confidence": 0.58,
      "transfer_rationale": "Both orchestrate SQL-based data transformation logic; \
Airflow DAG familiarity eases dbt model dependency understanding, but SQL templating \
paradigm differs."
    },
    {
      "jd_skill_canonical": "Kubernetes",
      "is_critical": true,
      "has_transferable_cv_skill": true,
      "cv_skill_canonical": "Docker",
      "transfer_confidence": 0.72,
      "transfer_rationale": "Docker container fundamentals directly underpin Kubernetes \
pod and deployment abstractions; container lifecycle knowledge transfers strongly."
    },
    {
      "jd_skill_canonical": "Tableau",
      "is_critical": false,
      "has_transferable_cv_skill": true,
      "cv_skill_canonical": "Matplotlib",
      "transfer_confidence": 0.55,
      "transfer_rationale": "Both produce data visualizations; Matplotlib expertise \
demonstrates analytical charting intuition, though Tableau's drag-drop BI model \
is operationally distinct."
    },
    {
      "jd_skill_canonical": "Terraform",
      "is_critical": false,
      "has_transferable_cv_skill": false,
      "cv_skill_canonical": null,
      "transfer_confidence": null,
      "transfer_rationale": null
    }
  ],
  "assessment_confidence": 0.88
}
--- END CALIBRATION EXAMPLE ---"""


USER_TEMPLATE = """\
{format_instructions}

{few_shot_examples}

Now perform transferability assessment for the following candidate-JD skill context.

FULL_CV_SKILL_POOL:
{cv_skill_pool_json}

UNRESOLVED_JD_REQUIRED_SKILLS (assess has_transferable_cv_skill for each, is_critical=true):
{unresolved_required_json}

UNRESOLVED_JD_PREFERRED_SKILLS (assess has_transferable_cv_skill for each, is_critical=false):
{unresolved_preferred_json}

Instructions:
  - Produce one assessment object per skill in both unresolved lists.
  - cv_skill_canonical must be copied verbatim from FULL_CV_SKILL_POOL.
  - Apply minimum threshold 0.55 — below this, set has_transferable_cv_skill = false.
  - assessment_confidence: your confidence in the batch of assessments overall [0.0–1.0].

Output the JSON.
"""
