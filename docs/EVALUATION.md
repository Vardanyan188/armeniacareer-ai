# Evaluation Methodology

ArmeniaCareer AI is evaluated with (1) an automated test + parsing-evaluation
suite and (2) a planned human-evaluation study. The system is deterministic-first,
so automated results are reproducible offline without API keys.

## 1. Automated evaluation

**Latest full run (Phase 22): `314 passed, 2 skipped`** (`python -m pytest -q`).

| Category | Representative tests | Purpose |
|---|---|---|
| Parsing evaluation | `tests/test_parsing_eval.py`, `src/evaluation/parsing_eval.py` | Thresholded CV-parsing quality (sections, dates, language) |
| Parsing utilities | `test_section_detector`, `test_date_normalizer`, `test_language_utils`, `test_parsing_quality` | Deterministic extraction building blocks |
| Guardrails | `test_guardrails` | PII masking + injection detection + output structure |
| Security / no-leak | `test_security_hardening` | Output-guardrail leak scan + export secret scrubbing |
| Prompt injection | `test_prompt_injection_hardening` | Block exfiltration; score & roles invariant under attack |
| Deployment gates | `test_deployment_gates` | Public/demo lockdown of Admin/Ingest/Pool/Debug |
| Audit logs | `test_audit_log` | Sanitized JSONL, allowlist, crash-safe |
| Access control | `test_access_control` | Candidate/recruiter view separation |
| Scoring inputs | `test_adapters` | Deterministic JD skill extraction |
| Orchestration | `test_orchestrator` | End-to-end deterministic fallback (no keys) |
| Ranking | `test_bulk_ranker` | Buckets, ordering, failure isolation |
| Quiz | `test_quiz_bank`, `test_quiz_builder`, `test_quiz_eval` | Deterministic question bank + scoring |
| Interview | `test_interview_candidate`, `test_interview_recruiter`, `test_answer_eval` | Practice loop + verification guide |
| Skill depth | `test_skill_depth` | Depth ladder + match types |
| JD versioning | `test_jd_versioning` | Diff + private-store routing |
| CV quality | `test_cv_quality` | Quality bands |
| UI safety | `test_ui_imports`, `test_ui_utilities`, `test_presentation_mode`, `test_summary_builders` | Import stability, no-PII helpers, export safety |

**Determinism:** the same input yields identical output across runs (covered by
explicit determinism tests in skill-depth, jd-versioning, and summary builders).

## 2. Human evaluation (planned)

**Target:** 8 demo-safe CV×JD pairs, 2 independent reviewers.
**Fallback minimum:** 5 pairs if time is short.
**Data:** generated/public demo-safe samples only — no private or real-personal CVs.

Each reviewer rates every pair on a 1–5 Likert scale:

| pair_id | composite % | recruiter usefulness | candidate usefulness | skill-match accuracy | safety / clarity | notes |
|---|---|---|---|---|---|---|
| P1 |  |  |  |  |  |  |
| P2 |  |  |  |  |  |  |
| … |  |  |  |  |  |  |
| P8 |  |  |  |  |  |  |

**Reporting:** per-criterion means (and inter-reviewer spread), plus qualitative
notes on failure modes (e.g. over/under-credited skills, unclear wording). A
short summary paragraph will go into [REPORT.md](REPORT.md) §Evaluation.

**Safety review:** reviewers also confirm no PII, no cross-role leakage, and that
every surface carries the decision-support disclaimer.
