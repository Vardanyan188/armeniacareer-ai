# Roadmap

## Completed phases

| Phase | Outcome |
|---|---|
| 1 — Schema keystone | `canonical_payload.py`, package wiring, prompt path fixes. |
| 2 — Loaders | `document_loader.py` (pdf/docx/txt/md + JD JSON), requirements, `.env.example`. |
| 3 — Adapters | `ParsedCVOutput`/JD/agent → canonical mapping; deterministic JD skill extraction. |
| 4 — Guardrails + access control | Input/output guardrails, candidate/recruiter/shared selectors. |
| 5 — Orchestrator | End-to-end deterministic pipeline with agent-or-fallback resolvers. |
| 6 — MVP UI | Streamlit tabs, score cards, governance panel. |
| 7 — Role-based UI | Candidate / Recruiter / Admin modes; upload bridge; CV-only intelligence. |
| 8 — Candidate Pool | Consent + threshold + SHA-256 dedup local storage. |
| 9 — UI interaction polish | Calmer scores, button states, pool UX, diagnostics. |
| 10 — Robust parsing + eval | Section/date/language utils, parsing-quality, scanned-PDF flag, eval harness. |
| 11 — Premium narratives | Dark UI, safe low-score wording, enum cleanup, fallback clarity. |
| 12 — Theme config | `.streamlit/config.toml` dark base. |
| 13 — Interview engine | Deterministic candidate practice + recruiter verification guide. |
| 13.1 — Product polish | Sidebar, micro-interactions, interview progress, semantic provider chain. |
| 14 — Documentation | This documentation set. |

Tagged checkpoints: `mvp-working-v1`, `role-ui-polished-v1`, `interview-engine-v1`.

## Remaining phases (planned)

| Phase | Scope |
|---|---|
| **Quiz / Test Generator** | Deterministic skill-check questions derived from the gap analysis; optional auto-grading. |
| **Recruiter Bulk Ranking** | Analyze multiple CVs against one JD and rank by composite (replacing the current placeholder). |
| **Final Cleanup / Presentation Pack** | Dead-code removal, polish pass, slides/video, reproducible demo data. |

## Future production ideas

- **OCR** for scanned/image PDFs (currently detected and flagged only).
- **Stronger LLM feedback** layer for interview answers and narratives (optional, behind keys).
- **Database-backed candidate pool** (replace the file-based store; add retention/delete).
- **Auth / user accounts** with per-user data isolation.
- **Real deployment** (hosting, secrets management, observability, rate limiting).

## Non-goals (for now)

- Automated hiring decisions — the system stays decision-support only.
- Storing or indexing CVs on any external service.
