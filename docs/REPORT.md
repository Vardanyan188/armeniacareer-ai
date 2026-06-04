# ArmeniaCareer AI — Written Report (Draft)

*LLM Applications — Group Project. Draft for review; exportable to PDF.*
*Decision-support system only — it does not make hiring decisions.*

---

## 1. Problem statement and motivation

Job-matching in the Armenian and wider CIS market is noisy and one-sided.
Candidates rarely get structured, honest feedback on *why* their CV does or does
not fit a role, and recruiters spend disproportionate time screening CVs of
uneven quality and format. Generic keyword matching treats a skill as a binary
("Python: yes/no") and ignores depth, context, and changing requirements.

ArmeniaCareer AI addresses this with a **two-sided career-intelligence assistant**
that produces the *same underlying analysis* but presents it differently to
candidates and recruiters, with privacy and governance built into the code. It is
explicitly **decision-support**: every output requires human review.

## 2. Target users and use cases

- **Candidates** — upload a CV for a private, local quality analysis; optionally
  compare against a job; see matched/missing skills, **skill-depth gaps**,
  interview practice, and a skill quiz; export a personal summary.
- **Recruiters / HR** — provide a job description, upload candidate CVs, get a
  **deterministic bulk ranking**, a recruiter-safe screening view, verification
  questions, and **JD requirement-versioning** to see how a role changed over time.
- **Admin / internal (gated)** — run the pipeline over demo data, inspect
  governance/fallback diagnostics, the dataset registry, and (locally) private
  data ingest.

## 3. System architecture and design decisions

**Single backbone, dual surface.** One canonical analysis payload
(`src/schemas/canonical_payload.py`) is produced once and then *viewed* through
role-specific selectors (`src/engine/access_control.py`). Candidates never see
recruiter content (hire recommendation, red flags); recruiters never see candidate
coaching/motivation. This information-asymmetry is the **single enforcement point**.

**Pipeline:** document loading → input guardrail (PII mask + injection screen) →
adapters (deterministic entity/skill extraction) → orchestrator (agents *or*
deterministic fallback) → scoring & payload assembly → output guardrail → role
views → UI. Supporting engines: skill-depth, JD-versioning, ranking, quiz,
interview, candidate pool, dataset registry, audit logging.

**Why deterministic-first:** reproducibility, offline operation, testability, and
safety. LLMs *raise quality* but never change the contract or the score.

## 4. LLM and prompt-engineering approach

Three prompt-driven agents (document intelligence, semantic alignment, skills
ontology) return **schema-constrained JSON**; deterministic code turns those
signals into a composite score and seven dimensions. Prompts evolved over three
iterations — naïve matching → structured few-shot extraction → role-safe and
guardrailed (PII-masked inputs, output leak-scanning, access control). Full
internal templates are not published; sanitized patterns and rationale are in
[PROMPTS.md](PROMPTS.md).

## 5. Deterministic fallback and provider strategy

Every agent has a deterministic, prompt-free fallback. Semantic alignment follows
a provider chain: **OpenAI embeddings → Google/Gemini embeddings → deterministic
skill-overlap**. The governance layer records which provider was actually used, so
there are no silent failures. With no API keys the system is fully functional —
this is the configuration used for the public demo.

## 6. Optional RAG module

An advanced hybrid retrieval pipeline (`src/engine/rag_pipeline.py`) combines a
sparse BM25 retriever and a dense Chroma retriever (RRF fusion) with a
cross-encoder reranker, degrading gracefully when models/packages are absent. It
is presented as an **optional/advanced** component, not the deployed MVP backbone.

## 7. Evaluation methodology and results

Automated: **406 passing tests** plus a parsing-evaluation harness covering
extraction quality, guardrails, security/no-leak, prompt-injection, deterministic
fallback, ranking, quiz, interview, skill-depth, and JD-versioning. Human
evaluation is planned (8 demo-safe pairs, 2 reviewers; 5-pair fallback) on
recruiter usefulness, candidate usefulness, skill-match accuracy, and
safety/clarity. Full methodology and the results table: [EVALUATION.md](EVALUATION.md).

## 8. Responsible AI, privacy, and governance

- **PII masking** before any model call; **no raw CV/JD text** stored in the payload.
- **Access control** enforces candidate/recruiter separation in code.
- **Guardrails** block injection/exfiltration; a malicious CV/JD **cannot change
  the score or cross roles**.
- **Governance panel** is transparent about live-vs-fallback; technical details
  are sanitized and gated to debug environments.
- **Runtime gates** disable Admin/Ingest/Pool/Debug in public; **audit logs** are
  privacy-safe and off by default.
- Details: [PRIVACY_AND_GOVERNANCE.md](PRIVACY_AND_GOVERNANCE.md),
  [SECURITY_HARDENING.md](SECURITY_HARDENING.md).

## 9. Limitations

- Local prototype: Candidate Pool / private ingest are file-based (no auth/database).
- No OCR — scanned/image PDFs are detected and flagged, not read.
- No guaranteed font/color/visual-layout analysis yet — a richer CV visual/layout analyzer is deferred to future work.
- UI internationalization (EN/HY/RU) is partial — the most visible surfaces and the CV intelligence report are localized; internal panels remain English.
- Interview/quiz evaluation is deterministic/heuristic, not LLM-graded.
- Skill-depth and JD-diff are heuristic and English-dominant (directional).
- Prompt secrecy is best-effort once prompts reach a hosted LLM.
- Streamlit has no built-in authentication; a proxy is required for non-local use.
- Human evaluation not yet executed at time of writing.

## 10. Reflection / lessons learned

Separating *analysis* from *presentation* (one payload, many views) made privacy
tractable and the system testable. Deterministic-first design paid off repeatedly:
it kept the app demoable offline, made security properties provable, and prevented
LLM nondeterminism from leaking into scores. The hardest work was not features but
**framing, safety, and honest scoping**.

## 11. Future work

- Public deployment hardening (Streamlit Community Cloud) and a real auth layer.
- Full UI internationalization (extend EN/HY/RU to the remaining internal panels) and natural multilingual interview questions/feedback.
- A CV visual/layout analyzer (page-count auto-detection, font/heading consistency, two-column risk) where the extractor supports it.
- Optional fine-tuning / model adaptation for domain-specific extraction.
- Multilingual (hy/ru) depth and JD-diff coverage.
- Database-backed candidate pool with consent lifecycle.
- Activating the RAG module in the live demo with curated, demo-safe corpora.

---

*See also: [COURSE_TOPICS.md](COURSE_TOPICS.md), [SYSTEM_HANDBOOK.md](SYSTEM_HANDBOOK.md),
[ARCHITECTURE.md](ARCHITECTURE.md), [CONTRIBUTIONS.md](CONTRIBUTIONS.md).*
