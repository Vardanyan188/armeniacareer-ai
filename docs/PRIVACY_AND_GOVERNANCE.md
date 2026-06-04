# Privacy & Governance

ArmeniaCareer AI is a **decision-support assistant**, not an automated hiring
system. This document describes the privacy and governance posture of the current
local prototype.

## Core principles

- **Decision-support only.** The system surfaces evidence and structure; it does
  not decide outcomes.
- **Human review required.** Every recruiter-facing output is framed as input to a
  human decision, never a verdict.
- **No automatic hiring decision.** There is no auto-accept/auto-reject anywhere
  in the pipeline.

## Candidate vs. Recruiter access separation

Enforced in code via `src/engine/access_control.py`. UI components read only
through these selectors.

| Candidates never see | Recruiters never see |
|---|---|
| Hire recommendation | Candidate coaching roadmap |
| Recruiter verification points | Motivational framing |
| Red flags | (candidate-only perspective fields) |
| Raw demographic/bias signals | — |

Neither side ever sees raw CV text in the UI — only canonical skill/role/dimension
data and masked entities.

## Candidate Pool consent logic

Storing a CV in the pool requires **all** of:

1. A CV quality score at or above the configured threshold (default 70%).
2. An explicit consent checkbox.
3. A deliberate "Add to Candidate Pool" click.

Nothing is ever stored automatically. Duplicate uploads (same SHA-256) are
rejected. The recruiter-facing pool list shows **metadata only** — short id,
quality, role directions, skills, date — and deliberately omits the original
filename (which may contain a name).

## Data locations

| Location | Contents | Committed? |
|---|---|---|
| `data/raw/` | Bundled sample resumes/JDs for Admin · Demo only | git-ignored |
| `data/uploads/candidate_pool/` | Consented, approved CVs + metadata index | git-ignored |
| System temp dir | Uploaded files during analysis (deleted after) | n/a |

Uploaded CVs are **never** written to `data/raw/`. The Candidate and Recruiter
modes never browse the local resume database — only Admin · Demo does.

## PII handling

The input guardrail masks emails, phone numbers, and LinkedIn/GitHub URLs before
any processing, and screens for prompt-injection patterns. Severe injection
attempts abort the analysis with a clear reason.

## API key safety

- Keys are read from environment variables / `.env` (git-ignored). They are never
  logged or shown in the UI.
- No network call is made without the relevant key present.
- Provider/error details appear only inside a collapsed "Technical details"
  expander in Governance — never in the main surface, and never the key itself.

## Fallback transparency

The Governance panel reports, per run: whether live LLMs were used, each Phase-1
agent's status, the **semantic provider** actually used (OpenAI / Google /
deterministic), guardrail pass/flags, completeness, and timing. Fallbacks are
labelled, not hidden.

## Bias & safety — current limitations (honest scope)

- The bias audit in this prototype is a **deterministic low-risk fallback object**,
  not a trained bias detector; it provides structured-interview reminders, not a
  demographic analysis.
- Heuristic parsing and scoring can misread unusual CV layouts; the extraction-
  quality band flags low-confidence cases.
- No fairness guarantee is claimed. Outputs must be reviewed by a human, and any
  hiring decision must comply with applicable employment law in the relevant
  jurisdiction.
