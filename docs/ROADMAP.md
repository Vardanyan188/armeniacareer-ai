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
| 15–18 — Quiz, bulk ranking, data governance, handbook | Candidate skill quiz, recruiter bulk ranking, dataset registry, system handbook. |
| 19–21 — Depth, versioning, comfort | Skill-depth analysis, JD versioning/diff, UI comfort (status bar, exports, focus/print). |
| 22–23 — Security & academics | Security hardening, prompt protection, audit logs, deployment gates, academic deliverables. |
| 24.0–24.2 — Parser & CV intelligence | Robust section/skill parsing, multilingual + open-vocabulary extraction, CV quality advisory layer. |
| 24.3A+B — Brand & i18n foundation | Brand/header lockup, header-spacing fix, and EN/HY/RU translation system with a language selector. |
| 24.3 hotfix — Parser stabilization | Two-column header merges, section-content bounding (no skills bleed), language levels before/after the name, job-title filtering, character-spaced PDF repair, name/title/institution skill filtering, and **CV intelligence report localization**. |
| 24.3C — Multilingual interview foundation | Natural EN/HY/RU interview questions, follow-ups, feedback bands, and recruiter verification guides — deterministic, curated (Armenian-first), no keys required. |
| 24.3D — Interview rubric / evaluation quality | Eight-dimension deterministic rubric, weak-answer pattern flags, localized candidate feedback (strengths/improvements/better answer/learning focus/follow-up) and a recruiter evidence-confidence summary — confidence bands, no overclaiming. |
| 24.3D/E hotfix — Deploy + compatibility | Fixed a public-deploy import mismatch (brand helpers in `ui_kit`), added a Streamlit version-compat helper for full-width tables (`use_container_width` → `width="stretch"`), and hardened import-contract tests. |
| 24.3E — CV layout analyzer (MVP) | Safe layout diagnostics for Canva/template/two-column CVs: PDF page-count auto-detection, character-spaced/symbol/visual-level risk flags, and localized ATS-readability advisories. No OCR; no font/color claims. |

Tagged checkpoints: `mvp-working-v1`, `role-ui-polished-v1`, `interview-engine-v1`,
and the per-phase tags through `brand-i18n-foundation-v1`.

## Remaining phases (planned)

| Phase | Scope |
|---|---|
| **Quiz / Test Generator** | Deterministic skill-check questions derived from the gap analysis; optional auto-grading. |
| **Recruiter Bulk Ranking** | Analyze multiple CVs against one JD and rank by composite (replacing the current placeholder). |
| **Final Cleanup / Presentation Pack** | Dead-code removal, polish pass, slides/video, reproducible demo data. |

## Future production ideas

- **Multilingual interview enhancement** — optional LLM layer (Gemini-preferred for Armenian) wrapping the deterministic 24.3C localizer; the curated multilingual foundation already works with no keys.
- **Full UI i18n** — extend EN/HY/RU coverage to the remaining internal panels (quiz, skill-depth, governance, exports) and dynamic interview answer-feedback text.
- **CV visual/layout analyzer — deeper** — font/heading consistency and color-coded proficiency, only where the extractor truly exposes it. The 24.3E MVP covers page count + character-spaced/symbol/visual-level risk + ATS advisories; **no guaranteed font/color analysis yet**.
- **OCR** for scanned/image PDFs (currently detected and flagged only).
- **Stronger LLM feedback** layer for interview answers and narratives (optional, behind keys).
- **Database-backed candidate pool** (replace the file-based store; add retention/delete).
- **Auth / user accounts** with per-user data isolation.
- **Real deployment** (hosting, secrets management, observability, rate limiting).

## Non-goals (for now)

- Automated hiring decisions — the system stays decision-support only.
- Storing or indexing CVs on any external service.
