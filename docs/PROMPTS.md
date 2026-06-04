# Prompt Engineering (Sanitized)

This document describes our prompt-engineering approach **safely**. We publish
**sanitized patterns and structure**, not full internal templates. The
application itself never renders, exports, or logs prompt text (see
[SECURITY_HARDENING.md](SECURITY_HARDENING.md)).

> Honesty note: prompt secrecy cannot be guaranteed once prompts are sent to a
> hosted LLM. The app minimizes exposure and **defaults to a deterministic path**
> that uses no prompts/keys at all.

## Where prompts live

Three prompt-driven analysis agents, each with a versioned few-shot family:

| Agent | Role | Prompt family |
|---|---|---|
| Document Intelligence | Parse CV → structured entities | `src/prompts/document_intelligence/v3_fewshot.py` |
| Semantic Alignment | CV↔JD semantic comparison | `src/prompts/semantic_alignment/v3_fewshot.py` |
| Skills Ontology | Skill matching / gap classification | `src/prompts/skills_ontology/v3_fewshot.py` |

Each produces a **canonical schema object** consumed by deterministic scoring and
assembly — the prompt's job is *structured extraction*, not free-form judgement.

## Prompt pattern (sanitized)

Common structure used across the agents (illustrative, not the real template):

```
ROLE: You are a deterministic {task} assistant for CV/JD analysis.
INPUT: PII-masked CV text and/or JD text (emails/phones/URLs already redacted).
TASK: Extract {entities|alignment|skill matches} as STRICT JSON matching {schema}.
CONSTRAINTS:
  - Output JSON only; no commentary, no chain-of-thought.
  - Never infer protected attributes; never invent contact details.
  - If evidence is insufficient, return empty/neutral fields, not guesses.
FEW-SHOT: 2–3 worked examples mapping input → exact JSON output.
```

Key design choices: **schema-constrained JSON output**, **PII-masked inputs**,
**no chain-of-thought in output**, and **conservative empty-on-uncertainty**.

## Three documented iterations

### Iteration 1 — Naïve matching prompt
A single prompt: *"Compare this CV to this JD and give a match score."*
- **Problems:** non-deterministic scores, free-text output hard to parse, no
  privacy controls, easy to derail, no separation of candidate/recruiter content.

### Iteration 2 — Structured few-shot extraction/matching
Split into focused agents (entities, semantic, skills) each returning
**schema-constrained JSON** with few-shot examples; a deterministic scorer turns
structured signals into the composite + 7 dimensions.
- **Gains:** reproducible structure, parseable outputs, testable, scoring removed
  from the LLM's discretion.

### Iteration 3 — Role-safe + guardrailed
Added an **input guardrail** (PII masking + injection screening) before any model
call, an **output guardrail** (structural + leak scanning), a single
**access-control** boundary so candidate vs recruiter views never cross, and a
**deterministic fallback** for every agent.
- **Gains:** privacy by construction, prompt/secret leakage prevention, offline
  operation, and safety under malicious CV/JD input (injection cannot change the
  score or cross roles).

## Leakage prevention (UI / export / logs)
- **UI:** prompts are never displayed; technical error details are sanitized and
  shown only in local/dev or with `ACAI_DEBUG=1`.
- **Export:** Markdown summaries are built from role-safe selectors and scrubbed
  for secrets/paths/env/prompt markers (`src/ui/components/summary_builders.py`).
- **Logs:** audit logs are field-allowlisted and scrubbed; prompts/secrets/paths
  are never written (`src/engine/audit_log.py`).

## Deterministic fallback (no keys required)
When no API key is configured (or a model is unavailable), the orchestrator uses
**deterministic, prompt-free** logic: keyword/alias skill extraction, skill-overlap
semantic scoring, and rule-based narratives. Governance reports which provider
was used (`OpenAI → Google → deterministic`). The deployed demo runs fully on
this path.
