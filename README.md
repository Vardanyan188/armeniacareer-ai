# ArmeniaCareer AI

A premium, two-sided **career intelligence platform** that analyzes the fit
between a CV and a job description, then serves separate, access-controlled
experiences for candidates and recruiters.

> **Status:** Working MVP / local prototype. Runs fully **offline** with
> deterministic logic; optional LLM providers enhance results when API keys are
> present. This is a decision-support tool, **not** an automated hiring system.

---

## What problem it solves

Hiring decisions and job applications both suffer from vague, one-sided signals.
ArmeniaCareer AI produces a single, structured analysis of a CV ↔ JD match and
then renders it two ways:

- **Candidates** get supportive, realistic coaching: CV quality, skill gaps,
  role directions, and interview practice.
- **Recruiters** get conservative, evidence-based screening: a composite score,
  skill coverage, and a structured verification interview guide.

The same analysis powers both — the difference is *access profile*, not a second
computation.

## Roles

| Mode | For | What it does |
|---|---|---|
| **Candidate** | The job seeker (own CV only) | CV quality report, skills/role directions, optional JD comparison, interview practice. Never sees recruiter-only content or the resume database. |
| **Recruiter / HR** | Hiring teams | Paste/upload a JD, upload candidate CV(s), screen one against the JD, structured verification interview guide. Never sees candidate coaching content. |
| **Admin · Demo** | Internal testing only | Browse the bundled local sample datasets (`data/raw`) and inspect all detail tabs. Clearly labelled internal demo. |

## Key features

- Multilingual (EN / HY / RU) CV & JD parsing with robust section and date detection.
- Seven-dimension scoring with a geometric-mean composite and hard-floor rules.
- Role-based access control enforcing candidate/recruiter information separation.
- Candidate Pool: consent-gated, threshold-gated local storage of approved CVs.
- Deterministic Interview Engine: candidate practice loop + recruiter verification guide.
- Premium dark theme; graceful fallbacks when no API keys are configured.
- Offline parsing evaluation harness with enforced quality thresholds.

## Responsible AI notice

ArmeniaCareer AI is a **decision-support assistant only**. It does not make
hiring decisions. Every output requires human review. PII is masked before
processing, and the candidate/recruiter access split is enforced in code. See
[docs/PRIVACY_AND_GOVERNANCE.md](docs/PRIVACY_AND_GOVERNANCE.md).

## Security & privacy

Deterministic-first and offline-capable. Prompts/secrets/internal paths are never
rendered, exported, or logged; the input guardrail blocks injection/exfiltration
attempts and a malicious CV/JD **cannot change the score or cross role views**.
Admin/Demo, Private Ingest, Candidate-Pool persistence, debug details, and audit
logs are **env-gated and off in public** (`ACAI_PUBLIC_DEMO=1` / `APP_ENV=prod`).
Streamlit has **no built-in auth** — put a real auth proxy in front of any
non-local deployment. Honest caveat: prompt secrecy can't be guaranteed once sent
to a hosted LLM. Full details + pre-deploy checklist:
[docs/SECURITY_HARDENING.md](docs/SECURITY_HARDENING.md) ·
[docs/QA_CHECKLIST.md](docs/QA_CHECKLIST.md).

## Quick start

```bash
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# macOS/Linux:         source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Without API keys, the app runs end to end using deterministic fallbacks.

## Environment variables

Copy `.env.example` to `.env` and fill in what you have (all optional for the
deterministic path):

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | Enables the LLM analysis agents + OpenAI embeddings. |
| `GOOGLE_API_KEY` | Enables Gemini narratives + the alternate embedding provider. |
| `APP_ENV` | `local` / `staging` / `production` (informational). |

See [docs/SETUP.md](docs/SETUP.md) for details and troubleshooting.

## Deployed app

🔗 **Live demo:** _<deployment URL placeholder — planned on Streamlit Community Cloud>_

The public demo runs the **deterministic path** (no API keys) with Admin / Private
Ingest / Candidate-Pool persistence / debug all disabled via `ACAI_PUBLIC_DEMO=1`.

## Current status

- Full MVP complete: loaders → guardrails → adapters → orchestrator → assembler → access control → role-based UI.
- Implemented: CV quality, CV↔JD matching, Candidate Pool, **Recruiter Bulk Ranking**, Skill Depth, JD Versioning, Interview Practice, Skill Quiz, Governance/Fallback, Dataset Registry, Private Ingest, Safe Exports, Focus/Print mode, Security Hardening, and audit logging.
- **Brand & multilingual UI:** a refreshed brand/header lockup and an **EN / Հայերեն / Русский** language selector. The most visible Candidate/Recruiter/Admin surfaces and the **CV intelligence report** are localized (full UI i18n is rolling out incrementally).
- **Robust multilingual parsing:** CV/JD parsing handles non-standard headings (e.g. `PROFILE`, `CONTACT ME`, `COMPUTER SKILLS`), Armenian/Russian sections, two-column PDF header merges, open-vocabulary skills, slash-separated tool lists, and language proficiency levels — hardened through iterative development and regression testing.
- **Multilingual interview + rubric:** EN/HY/RU interview questions, follow-ups, feedback, and an eight-dimension answer rubric with confidence bands — deterministic, key-free, Armenian-first.
- **CV layout analyzer (MVP):** advisory ATS/readability notes for Canva/template/two-column CVs (page count, character-spaced/symbol/visual-level risks). No OCR; no font/colour claims.
- **Tests:** `437 passed, 2 skipped` (`python -m pytest -q`); deterministic, offline, no keys required. See [docs/EVALUATION.md](docs/EVALUATION.md).

## Limitations

- Local prototype: Candidate Pool / private ingest are file-based (no auth, no database).
- No OCR — scanned/image PDFs are detected and flagged, not read.
- No guaranteed font/color/visual-layout analysis yet — page count and visual cues are best-effort; a richer CV visual/layout analyzer is deferred to future work.
- UI i18n is partial — internal panels (interview, quiz, skill-depth, governance, export Markdown) remain English for now.
- Interview/quiz evaluation is deterministic/heuristic (no LLM grading).
- Skill-depth and JD-diff are heuristic and English-dominant (directional signals).
- Prompt secrecy is best-effort once prompts reach a hosted LLM; full internal prompts are **not** exposed. Streamlit has no built-in auth (use a proxy for non-local deploys).
- LLM paths require valid API keys and model access; otherwise deterministic fallbacks are used.

## Documentation

- [docs/SYSTEM_HANDBOOK.md](docs/SYSTEM_HANDBOOK.md) — **start here**: the complete system handbook.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system design and data flow.
- [docs/SETUP.md](docs/SETUP.md) — install, keys, and troubleshooting.
- [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) — presentation-ready walkthrough.
- [docs/ROADMAP.md](docs/ROADMAP.md) — completed and upcoming work.
- [docs/PRIVACY_AND_GOVERNANCE.md](docs/PRIVACY_AND_GOVERNANCE.md) — responsible-AI posture.
- [docs/SECURITY_HARDENING.md](docs/SECURITY_HARDENING.md) — security controls + pre-deploy checklist.

### Academic deliverables

- [docs/COURSE_TOPICS.md](docs/COURSE_TOPICS.md) — course-requirement → evidence mapping.
- [docs/PROMPTS.md](docs/PROMPTS.md) — sanitized prompt patterns + iteration history.
- [docs/EVALUATION.md](docs/EVALUATION.md) — automated results + planned human evaluation.
- [docs/REPORT.md](docs/REPORT.md) — written report draft (8–12 pp).
- [docs/CONTRIBUTIONS.md](docs/CONTRIBUTIONS.md) — team roles & contribution evidence.
- [docs/QA_CHECKLIST.md](docs/QA_CHECKLIST.md) — full QA regression checklist.
