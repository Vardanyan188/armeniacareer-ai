# Full QA Checklist (Phase 22)

Manual + automated regression checklist before deployment. Automated coverage:
`python -m pytest -q` (currently 314 passed, 2 skipped).

## Candidate Mode
- [ ] CV upload (PDF/DOCX/TXT/MD) → temp file, deleted after
- [ ] CV quality report renders; scanned/low-quality flagged (no OCR)
- [ ] JD paste → compare runs (deterministic fallback without keys)
- [ ] Candidate Pool gate: consent + quality threshold; **disabled note** when pool gate off
- [ ] Skill Depth tab: gaps + recommendations (directional)
- [ ] Interview Practice + Skill Quiz render
- [ ] Export: candidate Markdown (no recruiter content, no PII/secrets/paths)
- [ ] Focus mode + browser print readable

## Recruiter Mode
- [ ] JD paste/upload (temp) — private JD version save stays under `data/private`
- [ ] Bulk ranking (≤10) with buckets; failed CVs ranked last
- [ ] Selected candidate detail (recruiter-safe tabs)
- [ ] Skill Depth evidence + verification prompts
- [ ] JD version compare (added/removed skills, seniority, depth)
- [ ] Verification interview guide
- [ ] Export: recruiter Markdown (no coaching/motivation, no `source_filename`, no secrets)
- [ ] Governance summary present

## Admin / Demo Mode (gated)
- [ ] Hidden unless `ACAI_ENABLE_ADMIN=1`; hidden in public/demo/prod
- [ ] Demo selectors over `data/raw`; registry labels shown
- [ ] Private data excluded from selectors
- [ ] Private Ingest hidden unless `ACAI_ENABLE_INGEST=1`
- [ ] JD version compare (demo)
- [ ] Internal stamped export ("INTERNAL DEMO — not a hiring decision")

## System / Security
- [ ] Deterministic fallback works with **no** API keys
- [ ] OpenAI/Gemini provider path used when keys exist (governance shows which)
- [ ] Low-quality/scanned PDF → flagged, features limited
- [ ] Duplicate Candidate Pool add blocked (SHA-256)
- [ ] Duplicate Private Ingest blocked; private→raw routing rejected
- [ ] JD version routing: demo→`data/raw`, private→`data/private`
- [ ] Reset clears session only (never deletes files)
- [ ] Mode isolation: switching modes clears results; **no cross-role leakage**
- [ ] Injection in CV/JD: severe attempts rejected; score unchanged; roles not crossed
- [ ] Governance technical details hidden unless debug
- [ ] `data/private` / `data/uploads` never surfaced in UI
- [ ] Audit logs (if enabled) are sanitized JSONL; disabled by default
- [ ] Public lockdown (`ACAI_PUBLIC_DEMO=1`): Admin/Ingest/Pool/Debug all off

## Pre-deploy
- [ ] `git ls-files` shows no `data/private|uploads|reports`, no `.env`, no keys, no logs
- [ ] Only demo-safe `data/raw` shipped for public
- [ ] Real auth proxy in front of any non-local deployment
