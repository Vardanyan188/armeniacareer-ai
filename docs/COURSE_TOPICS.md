# Course Topic Coverage

How ArmeniaCareer AI maps to the LLM Applications course requirements. We claim
**four core topics** and present **two bonus topics** as additional evidence.
Claims are framed honestly — see each "Limitations" note.

## Official claimed topics (4 core)

### 1. Prompt engineering
- **Where:** the three Phase-1 analysis agents are prompt-driven, with versioned
  few-shot prompt families.
- **Evidence:** `src/prompts/document_intelligence/v3_fewshot.py`,
  `src/prompts/semantic_alignment/v3_fewshot.py`,
  `src/prompts/skills_ontology/v3_fewshot.py`; orchestration in
  `src/engine/orchestrator.py`; documented iterations in
  [PROMPTS.md](PROMPTS.md).
- **Limitations:** full internal prompt templates are intentionally **not**
  published (security). We document sanitized patterns and iteration rationale.

### 2. LangChain / agentic components
- **Where:** an orchestrator drives five agents (document intelligence, semantic
  alignment, skills ontology, plus optional candidate-simulator and
  recruiter-verifier), each with a deterministic fallback. The RAG module uses
  LangChain retrievers.
- **Evidence:** `src/agents/`, `src/engine/orchestrator.py` (agent-or-fallback
  resolvers, provider chain), `src/engine/rag_pipeline.py`
  (`EnsembleRetriever`, `BM25Retriever`, Chroma).
- **Limitations:** agents are **opt-in** (require API keys); the deployed demo
  defaults to the deterministic path.

### 3. Evaluation framework
- **Where:** an offline parsing-evaluation harness plus a broad automated test
  suite (314 passing).
- **Evidence:** `src/evaluation/parsing_eval.py`, `tests/` (32 files), and
  [EVALUATION.md](EVALUATION.md) (automated + planned human evaluation).
- **Limitations:** human evaluation is **planned** (8 pairs, 2 reviewers), not
  yet executed.

### 4. Responsible AI / guardrails / transparency
- **Where:** input/output guardrails, PII masking, a single access-control
  boundary between candidate/recruiter views, governance/fallback diagnostics,
  privacy-safe audit logs, and runtime safety gates.
- **Evidence:** `src/guardrails/`, `src/engine/access_control.py`,
  `src/engine/audit_log.py`, `src/ui/app_gates.py`,
  `src/ui/components/governance_panel.py`,
  [SECURITY_HARDENING.md](SECURITY_HARDENING.md),
  [PRIVACY_AND_GOVERNANCE.md](PRIVACY_AND_GOVERNANCE.md).
- **Limitations:** prompt secrecy is best-effort once prompts reach a hosted LLM;
  Streamlit has no built-in authentication.

## Bonus / additional evidence

### Content detection / classification
Deterministic classification appears throughout: skills-ontology categorization,
CV-quality bands (good / partial / low), scanned-PDF detection (no OCR),
prompt-injection detection, and recruiter ranking buckets.
- **Evidence:** `src/engine/skill_depth/`, `src/engine/cv_quality.py`,
  `src/preprocessing/` (parsing quality), `src/guardrails/input_guardrail.py`,
  `src/engine/ranking/`.

### RAG pipeline (optional / advanced module)
A hybrid retrieval pipeline (BM25 + Chroma dense, RRF fusion, cross-encoder
reranking) with graceful fallback when models/packages are unavailable.
- **Evidence:** `src/engine/rag_pipeline.py`.
- **Honest framing:** this is an **advanced, runtime-optional** module, **not**
  the deployed MVP backbone. We present it as supporting evidence, not as the
  primary system, unless explicitly used in the final demo.

## Requirement → evidence summary

| Course requirement | Primary evidence |
|---|---|
| ≥4 course topics | this document (4 core + 2 bonus) |
| Prompt templates used | [PROMPTS.md](PROMPTS.md) |
| Evaluation framework | [EVALUATION.md](EVALUATION.md), `tests/` |
| Responsible AI / ethics | [PRIVACY_AND_GOVERNANCE.md](PRIVACY_AND_GOVERNANCE.md), [SECURITY_HARDENING.md](SECURITY_HARDENING.md) |
| Known limitations | [REPORT.md](REPORT.md) §Limitations, README |
| Team contribution | [CONTRIBUTIONS.md](CONTRIBUTIONS.md) |
