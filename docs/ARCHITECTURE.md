# Architecture

ArmeniaCareer AI follows a **single-backbone, dual-surface** design: one analysis
runs per session and produces a single canonical payload; candidate and recruiter
experiences are *rendering and access* concerns over that payload, not separate
computations.

## High-level flow

```
File(s) ──► document_loader ──► input_guardrail ──► adapters ──► orchestrator
                                                                     │
                          ┌──────────────────────────────────────────┘
                          ▼
        Phase 1 (agents if keys present, else deterministic fallbacks)
          • Document intelligence  → CVEntities
          • Semantic alignment     → SemanticAnalysis   (OpenAI → Google → deterministic)
          • Skills ontology        → SkillsOntologyResult
        Phase 2 bias audit (deterministic fallback object)
                          │
                          ▼
        payload_assembler ──► scoring (geometric mean + hard floor)
                          │
                          ▼
        CanonicalAnalysisPayload ──► output_guardrail
                          │
            ┌─────────────┴───────────────┐
            ▼                             ▼
     get_candidate_view            get_recruiter_view / get_shared_view
            ▼                             ▼
     Candidate UI                   Recruiter UI            (Admin = both, internal)
```

## Data flow (deterministic-first)

The pipeline is designed to run **without any API keys**. Each LLM step is lazily
imported and gated on an env var; any import/dependency/API failure degrades to a
deterministic fallback rather than raising. With keys present, the same steps use
real models and the outputs improve in quality but not in shape.

## Role-based access separation

`src/engine/access_control.py` is the single enforcement point:

| Selector | Exposes | Excludes |
|---|---|---|
| `get_candidate_view` | composite score, dimension scores, skills, candidate coaching | hire recommendation, verification points, red flags, raw bias signals |
| `get_recruiter_view` | full dimensional analysis, skills, verification, processed bias risk | candidate coaching roadmap, motivational framing |
| `get_shared_view` | neutral analysis + governance status | perspectives, hire recommendation, raw bias |

UI components read **only** through these selectors. Raw CV text is never rendered.

## CV / JD parsing flow

Two paths share canonical schemas:

- **Deterministic path (default):** `document_loader` extracts text (pdf/docx/txt/md);
  `cv_quality` + `src/preprocessing/{section_detector, date_normalizer, language_utils,
  parsing_quality}` produce skills, sections, languages, dates, and an extraction-quality
  band (incl. scanned-PDF detection — flagged, not OCR’d).
- **LLM path (optional):** `cv_preprocessor` → `document_intelligence_agent` → `ParsedCVOutput`.

JD JSON is loaded by `document_loader`, then `adapters.jd_json_to_jd_entities`
extracts skills/sections deterministically from `raw_text`.

## Orchestrator flow

`src/engine/orchestrator.py` (`AnalysisOrchestrator` / `run_analysis`):

1. Load CV text + JD JSON.
2. Input guardrail (PII masking, prompt-injection screen). Severe injection → failed result.
3. Build `JDEntities` from the masked JD.
4. Phase 1 resolvers (CV / semantic / skills) — agent-or-fallback, recording
   per-signal `provider_status` and per-agent `agent_errors`.
5. Deterministic bias-audit fallback object.
6. `PayloadAssembler.assemble(...)` → scoring + perspectives.
7. Output guardrail; return `AnalysisRunResult`.

## Fallback logic

| Step | Live provider | Fallback |
|---|---|---|
| Document intelligence | `DocumentIntelligenceAgent` (OpenAI) | deterministic `CVEntities` from text |
| Semantic alignment | OpenAI embeddings → Google embeddings | deterministic skill-overlap |
| Skills ontology | `SkillsOntologyAgent` (OpenAI) | deterministic exact-match gap analysis |
| Narratives | Gemini | deterministic templated perspectives |
| Bias audit | (future agent) | deterministic low-risk object |

Governance surfaces which provider/fallback was used; technical details sit in an expander.

## Candidate Pool

`src/engine/candidate_pool.py` stores **approved** CVs under `data/uploads/candidate_pool/`
(git-ignored): `index.json` (metadata) + `files/`. Consent + a quality threshold are
required; SHA-256 prevents duplicates. Recruiter view shows metadata only (no filename, no raw text).

## Interview engine

`src/engine/interview/` (deterministic, no network):

- `candidate_practice.py` — prioritized question queue (missing skills → weak dims →
  matched skills → general), `evaluate_answer` (Structure/Relevance/Specificity), adaptive follow-ups.
- `recruiter_verification.py` — structured guide: question + strong-answer criteria +
  weak-answer indicators + follow-ups + importance.
- `answer_eval.py`, `models.py` — scoring heuristics and shared dataclasses.

## Evaluation harness

`src/evaluation/parsing_eval.py` runs section/date/language/quality checks over
`tests/fixtures/cv_parsing_cases/` and reports aggregate metrics; `tests/test_parsing_eval.py`
enforces thresholds (recall, date-parse rate, etc.).

## Important folders / files

| Path | Role |
|---|---|
| `streamlit_app.py` | Role router (Candidate / Recruiter / Admin). |
| `src/schemas/canonical_payload.py` | The single canonical payload schema. |
| `src/engine/orchestrator.py` | End-to-end analysis driver. |
| `src/engine/scoring.py` | Geometric-mean composite + hard floors (frozen). |
| `src/engine/access_control.py` | Candidate/recruiter/shared selectors. |
| `src/engine/candidate_pool.py` | Approved-CV persistence. |
| `src/engine/interview/` | Deterministic interview engine. |
| `src/preprocessing/` | Loaders + parsing utilities. |
| `src/ui/` | Modes, tabs, components, theme. |
| `.streamlit/config.toml` | Dark theme. |
| `tests/` | Deterministic, offline test suite. |
