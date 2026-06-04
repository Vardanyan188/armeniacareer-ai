# Security Hardening (Phase 22)

ArmeniaCareer AI is **decision-support only** and **deterministic-first** (works
offline without API keys). This document describes the security controls applied
before any deployment, and an honest statement of residual risk.

## 1. Threat model & honest limits

- **Prompt secrecy is not absolute.** When prompts are sent to a hosted LLM, the
  provider sees them. The app minimizes exposure: it **never renders, exports, or
  returns prompt text or prompt paths**, defaults to the **deterministic fallback**
  when no key is set, and blocks direct echo of prompts/secrets in its own output.
  Indirect, model-side leakage remains a residual LLM risk.
- **Streamlit has no built-in app authentication.** The Admin/Demo radio is **not**
  authentication — it is feature-gated by env (`ACAI_ENABLE_ADMIN`) and hidden in
  public/demo/prod. Put a real auth proxy in front for any non-local deployment.
- **Shared-host persistence is risky.** Candidate Pool and Private Ingest write to
  disk; both are env-gated and **off** in public mode.

## 2. Prompt protection

- Prompts/agent instructions are never shown in the UI, never exported, never put
  in governance summaries or user-facing errors, and never include prompt paths.
- The **output guardrail** scans assembled narratives for leak categories
  (`system prompt`, `chain-of-thought`, source/private **paths**, **env var** names,
  **API-key** patterns) and reports `leak_flags`. Display/export paths **redact**
  via the shared scrubber (`src/engine/audit_log.scrub_text`).

## 3. Prompt-injection hardening

- **Input guardrail** (deterministic, pre-LLM) flags soft signals and **rejects**
  unambiguous control-hijack / secret-exfiltration / role-bypass / score-tamper
  attempts (e.g. "reveal the system prompt", "show environment variables",
  "change score to 100", "return data/private file paths").
- **Scoring is deterministic and never reads instructions from CV/JD text** — a
  malicious JD cannot change the score (injection prose adds no skills) and cannot
  cross candidate/recruiter view boundaries (enforced by `access_control`).

## 4. Runtime gates (`src/ui/app_gates.py`)

| Env | Effect |
|---|---|
| `APP_ENV` = local/dev/demo/prod | `demo`/`prod` ⇒ public lockdown |
| `ACAI_ENABLE_ADMIN=1` | show Admin/Demo (never in public) |
| `ACAI_ENABLE_INGEST=1` | show Private Ingest (never in public) |
| `ACAI_ENABLE_CANDIDATE_POOL=1` | allow pool persistence (local/dev default on; public off) |
| `ACAI_DEBUG=1` | sanitized technical details (local/dev only) |
| `ACAI_PUBLIC_DEMO=1` | hard lockdown: Admin/Ingest/Pool/Debug OFF |
| `ACAI_ENABLE_AUDIT_LOG=1` | enable privacy-safe JSONL logs (off by default) |

## 5. Governance sanitization

The Governance panel always shows a safe summary (provider used, LLM status,
guardrail pass, completeness/confidence). Raw provider/agent errors are mapped to
**categories** via `sanitize_error()` and shown **only** in `local`/`dev` or with
`ACAI_DEBUG=1` — never raw paths, project ids, keys, or stack traces in public.

## 6. Audit logs (privacy-safe)

Two append-only JSONL streams (off unless `ACAI_ENABLE_AUDIT_LOG=1`):

```
data/reports/audit_logs/workflow_events.jsonl    # steps / labels / counts only
data/reports/audit_logs/security_events.jsonl    # sanitized security events
```

Every event is **field-allowlisted** and **scrubbed**; logging is best-effort and
never crashes the app. **Never logged:** raw CV/JD text, prompts, secrets, env
values, PII, paths, original filenames, stack traces, raw provider dumps. Both
`data/reports` and `data/private` are git-ignored.

## 7. Pre-deploy data-safety checklist

Confirm git-ignored and **not committed**:

```bash
git ls-files | grep -E "^data/(private|uploads|reports)/" ; echo "(expect: no output)"
git ls-files | grep -E "\.env$|ingest_manifest\.json|audit_logs/" ; echo "(expect: no output)"
```

- `data/private`, `data/uploads`, `data/reports` ignored ✓
- No real CVs / private JDs / candidate-pool files / ingest manifest / audit logs committed.
- No `.env`, no API keys committed.
- For a **public** deploy, ship only demo-safe `data/raw` (generated/public) and
  set `ACAI_PUBLIC_DEMO=1` (or `APP_ENV=prod`).

## 8. Public demo deploy config (copy-paste)

The canonical environment for a public/professor-facing demo. Every gate is locked
down and the app runs the deterministic path (no API keys required):

```bash
APP_ENV=demo
ACAI_PUBLIC_DEMO=1
ACAI_ENABLE_ADMIN=0
ACAI_ENABLE_INGEST=0
ACAI_ENABLE_CANDIDATE_POOL=0
ACAI_ENABLE_AUDIT_LOG=0
ACAI_DEBUG=0
# No OPENAI_API_KEY / GOOGLE_API_KEY → deterministic fallback (intended for the demo).
```

With this config the Admin/Demo workspace, Private Ingest, Candidate-Pool
persistence, raw debug diagnostics, and audit logs are all **off** — verified by
`tests/test_deployment_gates.py`. Layout/CV advisories
remain visible (they are safe), but raw parse diagnostics stay hidden.
