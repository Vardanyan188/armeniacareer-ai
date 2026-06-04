# ArmeniaCareer AI — System Handbook

A single, central guide to how the whole system works. Written for a new
developer, evaluator, professor, or teammate. It is honest about scope: this is a
**strong local MVP / prototype**, not a hosted production system.

> **Academic deliverables:** [COURSE_TOPICS.md](COURSE_TOPICS.md) ·
> [PROMPTS.md](PROMPTS.md) · [EVALUATION.md](EVALUATION.md) ·
> [REPORT.md](REPORT.md) · [CONTRIBUTIONS.md](CONTRIBUTIONS.md).

---

## 1. Project Overview

**What it is.** ArmeniaCareer AI analyzes the fit between a **CV** and a **job
description (JD)** and turns that single analysis into two different experiences.

**Why it exists.** Job seekers get vague feedback; recruiters get noisy signals.
The system produces one structured analysis and serves it respectfully to both
sides.

**Two-sided product idea.**
- **Candidate** — supportive, educational coaching: CV quality, skill gaps, role
  directions, interview practice, a skill quiz.
- **Recruiter / HR** — conservative, evidence-based screening: composite score,
  skill coverage, bulk ranking, verification interview guide.

**Admin / Demo** is an internal testing mode that browses bundled sample data.

**Positioning.** Decision-support only. The system never makes a hiring decision;
every output requires human review.

---

## 2. High-Level Architecture

**Single backbone, dual surface:** one analysis runs per session and produces one
canonical payload; candidate and recruiter UIs are *access views* over it, not
separate computations.

```
  CV file + JD (paste/upload/select)
            │
            ▼
   document_loader  ──►  input_guardrail (PII mask + injection screen)
            │
            ▼
   adapters (JD → JDEntities, deterministic)
            │
            ▼
   ORCHESTRATOR  (run_analysis)
     ├─ Phase 1: Document intelligence → CVEntities
     │           Semantic alignment    → SemanticAnalysis   (OpenAI → Google → deterministic)
     │           Skills ontology        → SkillsOntologyResult
     ├─ Phase 2: Bias audit (deterministic fallback object)
     └─ payload_assembler → scoring (geometric mean + hard floor)
            │
            ▼
   CanonicalAnalysisPayload ──► output_guardrail
            │
      ┌─────┴───────────────┐
      ▼                     ▼
 get_candidate_view   get_recruiter_view / get_shared_view
      ▼                     ▼
 Candidate UI          Recruiter UI            (Admin = both, internal)
```

**Three views** (enforced in `access_control.py`):

| View | Shows | Hides |
|---|---|---|
| Candidate | composite, dimensions, skills, coaching | hire recommendation, verification points, red flags, raw bias |
| Recruiter | full dimensions, skills, verification, processed bias risk | coaching roadmap, motivational framing |
| Shared | neutral analysis + governance status | perspectives, hire recommendation, raw bias |

---

## 3. User Modes

| | Candidate | Recruiter / HR | Admin · Demo |
|---|---|---|---|
| **Purpose** | Improve your own CV | Screen candidates for a job | Internal testing |
| **Inputs** | Own CV (+ optional JD) | One JD + multiple CVs | Local sample CV + JD |
| **Outputs** | CV quality, match, interview, quiz | Ranked table, recruiter detail, verification | All four analysis tabs |
| **Can do** | Analyze, practice, (consent) add to pool | Rank, open detail, verification guide | Browse `data/raw`, inspect everything |
| **Never shows** | Recruiter-only content, the CV database | Candidate coaching/motivation | (internal — shows everything) |
| **Limitations** | Needs a JD to compare; no CV-only quiz | Sync batch, 10-CV cap | Demo only; not for real users |

---

## 4. Candidate Mode Flow

1. **Step 1 – Upload CV** (`pdf/docx/txt/md`). Processed in a temp file, deleted after.
2. **CV quality analysis** (`cv_quality.py`, deterministic): detected skills,
   sections present/missing, languages, role directions, improvement tips, and an
   extraction-quality band (with scanned-PDF detection).
3. **Candidate Pool** (optional): if quality ≥ threshold and the candidate gives
   **explicit consent**, the CV can be added to a local pool. Never automatic.
4. **Step 2 – Compare to a job** (optional): paste a JD → `run_analysis` → a
   candidate-safe match result.
5. **Results tabs:** Your Match (coaching), Shared Analysis, **Interview Practice**,
   **Skill Quiz**.

Candidate Mode never lists the local resume database and never shows recruiter-only content.

---

## 5. Recruiter Mode Flow

1. **Step 1 – Job description:** paste or upload (local JD browsing stays in Admin).
2. **Step 2 – Candidate CVs:** upload one or many.
3. **Step 3 – Rank & review:** **Bulk Ranking** analyzes each CV against the same
   JD with a progress indicator, then shows a ranked table.

**Ranked table columns:** Rank · Candidate N · short ID · Source file · Composite ·
Matched · Missing critical · Bucket · Status · Priority · Reason.

4. **Open a candidate** → recruiter-safe detail: **Recruiter View** (screening
   summary, hire recommendation, integrity risk), **Verification Interview**,
   **Shared Analysis**, **Governance / Fallback**.

**Why coaching is hidden:** the recruiter view is built only from
`get_recruiter_view`, which excludes the candidate's coaching roadmap and
motivational framing — a privacy boundary enforced in code.

---

## 6. Admin / Demo Mode Flow

- **Why it exists:** a reproducible internal demo over the bundled sample datasets
  in `data/raw`.
- **What it does:** local dataset selectors + all four analysis tabs.
- **Internal only:** it is clearly labelled "Internal Demo Mode" and is the **only**
  mode allowed to browse `data/raw`. It is not a real candidate or recruiter flow
  and should not be used with real private data.
- **Data Ingest (optional):** when `ACAI_ENABLE_INGEST=1`, an Admin-only panel here
  can save a single uploaded CV/JD into the **private** dataset (see §12). Hidden
  otherwise.

---

## 7. File and Folder Map

| path | responsibility | used by | notes |
|---|---|---|---|
| `streamlit_app.py` | Role router (Candidate/Recruiter/Admin) + theme | all modes | thin; no business logic |
| `src/engine/orchestrator.py` | End-to-end analysis driver (`run_analysis`) | all analysis | agent-or-fallback resolvers |
| `src/engine/adapters.py` | Map raw JD/agent outputs → canonical schema | orchestrator | deterministic JD skill extraction |
| `src/engine/access_control.py` | Candidate/recruiter/shared selectors | UI, ranking, interview, quiz | the privacy enforcement point |
| `src/engine/scoring.py` | Geometric-mean composite + hard floors | payload_assembler | **frozen** |
| `src/engine/cv_quality.py` | CV-only deterministic quality report | Candidate Mode | no JD, no LLM |
| `src/engine/candidate_pool.py` | Consent-gated local CV storage | Candidate/Recruiter | hash dedup, metadata index |
| `src/engine/data_ingest.py` | Admin-only **private** CV/JD ingest | Admin (env-gated) | writes only `data/private`; hash dedup; manifest |
| `src/engine/skill_depth/` | Skill proficiency / requirement depth | candidate/recruiter/shared UI | **explanatory only**; no scoring impact |
| `src/engine/jd_versioning/` | JD version snapshots + deterministic diff | Admin/Recruiter UI | **explanatory only**; private-safe storage |
| `src/ui/components/utility_bar.py` | Global status bar + sidebar status chips | all modes | visual/status only; no logic, no PII |
| `src/ui/components/summary_builders.py` | Pure role-safe Markdown export builders | export_panel | allowlist + PII/secret scrub; no raw CV/JD text |
| `src/ui/components/export_panel.py` | Export / Copy panel (Markdown + .md) | candidate/recruiter/admin/JD/gov | selector-sourced; no HTML/PDF |
| `src/ui/app_gates.py` | Runtime feature gates (public/demo safety) | streamlit_app + modes | env-only; pure; testable |
| `src/engine/audit_log.py` | Privacy-safe JSONL audit logs + shared scrubbers | guardrails, exports, UI | off by default; sanitized; best-effort |
| `src/engine/interview/` | Candidate practice + recruiter verification | interview panels | deterministic |
| `src/engine/quiz/` | Candidate skill quiz | quiz panel | deterministic question bank |
| `src/engine/ranking/` | Recruiter bulk ranking logic | ranking panel | pure, deterministic |
| `src/preprocessing/` | Loaders + parsing utils (sections/dates/language/quality) | orchestrator, cv_quality | scanned-PDF flag, no OCR |
| `src/evaluation/` | Offline parsing evaluation harness | tests | enforced thresholds |
| `src/guardrails/` | Input/output guardrails | orchestrator | PII mask, injection screen |
| `src/schemas/` | Canonical payload + CV parsing schemas | everything | single source of truth |
| `src/ui/` | Modes, tabs, components, theme | streamlit_app | premium dark UI |
| `docs/` | Documentation (this handbook, setup, governance) | humans | — |
| `data/` | `raw` (demo), `uploads` (pool), `private` (real) | loaders, pool | all git-ignored |

---

## 8. Analysis Pipeline (step by step)

1. **Input guardrail** — mask emails/phones/URLs, screen for prompt injection;
   severe injection aborts with a clear reason.
2. **Text extraction** — `document_loader` reads `pdf/docx/txt/md`; JD JSON is loaded
   and flattened to text.
3. **CV/JD parsing** — deterministic path extracts skills, sections, dates,
   languages; JD → `JDEntities` via adapters.
4. **Deterministic adapters** — convert parsed/agent outputs into the canonical
   `CVEntities` / `JDEntities` / `SemanticAnalysis` / `SkillsOntologyResult`.
5. **Semantic alignment** — OpenAI embeddings → Google embeddings → deterministic
   skill-overlap (whichever is available).
6. **Skills ontology** — match required/preferred skills; produce matched / missing
   critical / missing preferred / transferable.
7. **Scoring / payload assembly** — `payload_assembler` computes seven dimension
   scores and the composite (via `scoring.py`), and builds the canonical payload.
8. **Access control** — candidate/recruiter/shared selectors expose only the right
   fields.
9. **UI rendering** — premium dark components render the selected view.
10. **Governance output** — provider used, fallback status, guardrail flags,
    completeness, timing.

---

## 9. Providers and Fallback Logic

The system is **deterministic-first**: it runs fully without API keys. LLM/embedding
providers only *raise quality*, never change the contract.

**Semantic provider chain:**

| Order | Provider | Needs | If it fails |
|---|---|---|---|
| 1 | OpenAI embeddings | `OPENAI_API_KEY` + model access | try Google |
| 2 | Google/Gemini embeddings | `GOOGLE_API_KEY` + library | use deterministic |
| 3 | Deterministic skill-overlap | nothing | final fallback |

- `provider_status["semantic_alignment"]` records `openai | google | deterministic`.
- **Fallback is not a failure.** Governance shows a clean summary; technical errors
  live inside a "Technical details" expander.
- **Common errors:** OpenAI **403** (project lacks embedding-model access → tries
  Google); Google **model not found** (outdated model name → fixed default).
- **`GOOGLE_EMBEDDING_MODEL`** env var sets the Google model; default
  `gemini-embedding-001` (resolved with a `models/` prefix in `orchestrator.py`).

---

## 10. Scoring and Matching

- **Composite score** — a weighted **geometric mean** of seven dimensions, so a
  very weak dimension pulls the whole score down (and a **hard floor** caps the
  result when a critical dimension is below threshold).
- **Seven dimensions** — technical skills, experience depth, education, domain
  knowledge, soft skills, seniority fit, contextual alignment.
- **Skills** — matched, missing critical, missing preferred (and transferable in the
  LLM path).
- **Honest limitation:** matching is currently **binary** (skill present or not). It
  is **not yet skill-depth aware** — a CV that merely mentions a skill counts the
  same as deep production experience. Depth-aware matching is planned (see §18).
  Treat scores as **directional signals**, not precise measurements.

---

## 11. CV Quality and Parsing

- **Extraction quality band** — good / partial / low, from text length and letter
  ratio.
- **Language detection** — Armenian / Russian / English (+ mixed) by script and
  keyword cues.
- **Section detection** — multilingual aliases for summary/experience/education/skills/etc.
- **Scanned/image PDF** — detected and **flagged** (low extraction quality). **No OCR**
  is performed; the UI advises uploading a text-based file.
- **Date normalization** — numeric, named-month (EN/HY/RU), 2-digit years,
  present/current forms, and ranges (e.g. `Jan 2024 – Present`, `2023-ից մինչ օրս`).
- **Parsing evaluation harness** (`src/evaluation/parsing_eval.py`) runs over
  synthetic fixtures and enforces aggregate thresholds in tests.
- **Low-quality CVs** — flagged clearly; pool/compare features are limited so results
  aren't trusted blindly.

---

## 12. Candidate Pool

- **Consent + quality threshold** — a CV is stored only if quality ≥ threshold
  (default 70%) **and** the candidate ticks consent **and** clicks the button.
- **Duplicate detection** — by **SHA-256 file hash**; re-adds are rejected.
- **Metadata** — `candidate_id`, original/stored filename, hash, quality, skills,
  role families, timestamp, consent.
- **Separate from `data/raw`** — stored under `data/uploads/candidate_pool/`, never in
  the demo dataset.
- **Git-ignored** — real CVs are never committed; the recruiter view shows metadata
  only (no filename, no raw text).

### Data Ingest (internal, Admin-only) — separate store

- **Purpose** — an explicit, opt-in way to persist an uploaded CV/JD into the
  **private** local dataset for internal testing. Implemented in
  `src/engine/data_ingest.py` + `src/ui/components/data_ingest_panel.py`.
- **Env-gated** — the panel renders **only** when `ACAI_ENABLE_INGEST=1`; otherwise
  it is hidden and no private-persistence action exists (Admin is a role, not auth).
- **Private destinations only** — CV → `data/private/real_resumes/`; private JD →
  `data/private/job_descriptions/company_private/`. Never `data/raw`, never the
  Candidate Pool. raw/demo import is **deferred** to a later phase.
- **Authorization + dedup** — requires an explicit authorization checkbox; SHA-256
  duplicates are not written twice.
- **Filename privacy** — stored as `<record_id><ext>` (no human name on disk); the
  original filename lives only in `data/private/ingest_manifest.json`.
- **Not in demo listings** — ingested files stay out of the Admin/Demo selectors
  because `document_loader` excludes the `private` path segment.

---

## 13. Interview Engine

**Candidate Interview Practice** (deterministic):
- Prioritized question queue: missing skills → weak dimensions → matched skills →
  general.
- **Answer evaluation axes:** **Structure** (STAR cues), **Relevance** (mentions the
  target), **Specificity** (numbers, tools, outcomes).
- **Adaptive follow-up:** a weak answer triggers a deeper prompt for the weakest
  axis; a strong answer advances. A progress strip shows question, answered, average,
  and target.

**Recruiter Verification Interview** (deterministic, guide only — no live grading):
- Built from the payload's verification points + missing/matched skills.
- Each item: the **question**, **what a strong answer should contain**, **what
  weak/unclear answers may indicate**, and **suggested follow-ups**, sorted by importance.

---

## 14. Quiz Engine

**Candidate Skill Quiz** (deterministic, candidate-safe):
- **MCQ + scenario "best-approach" MCQs** (auto-graded for immediate feedback).
- Priority: **missing critical skills** first, then weak dimensions, then **matched
  skills for validation**; capped at ~8.
- **Question bank** is curated per skill/dimension, with a generic template for
  unknown skills; correct-answer position is deterministically varied.
- **Scoring** — correct/total; bands: ≥80 strong, 60–79 solid, <60 keep building
  (supportive, never shaming).
- **Study-next** — prioritizes wrong missing-critical skills, remaining missing
  skills, then weak dimensions.

---

## 15. Recruiter Bulk Ranking

- **Batch analysis** — each uploaded CV is analyzed against the **same** JD using
  `run_analysis`, with an "Analyzed X / total" indicator. Synchronous (no background
  queue), **capped at 10 CVs** (a warning shows if more are uploaded).
- **Buckets:** Strong fit (≥70) · Review closely (50–69) · Weak fit (<50, matched≥1)
  · Insufficient evidence (<50, matched=0) · Failed.
- **Failed CVs** stay in the table, ranked last, with a reason; one bad CV never
  crashes the batch.
- **Candidate detail** reuses the recruiter-safe tabs.
- **Privacy:** safe "Candidate N" + short id (filename shown only for the recruiter's
  own mapping); temp files deleted after each analysis; nothing written to `data/raw`
  or the candidate pool.

---

## 15a. Skill Proficiency / Requirement Depth (explanatory)

Deterministic depth layer in `src/engine/skill_depth/` (Phase 19). **Explanatory
only** — it never changes the composite score, ranking sort, quiz, or interview.

- **Depth ladder:** `MENTIONED < BASIC < APPLIED < ADVANCED < PRODUCTION <
  DEPLOYMENT`. **Match types:** full / partial / mentioned-only / missing.
- **Candidate depth** is inferred from already-masked structured entities
  (`raw_skills` + `proficiency_signal`, `work_history` technologies/responsibilities,
  `career_domain_signals`). Only **curated per-skill ecosystem tokens** can reach
  ADVANCED+; generic proficiency claims are clamped to APPLIED, and a bare
  signal/years can lift `MENTIONED → BASIC` only (anti-overconfidence).
- **Required depth** is read from JD phrasing in lines that mention the skill;
  default is **APPLIED** when unqualified.
- **Access:** the single neutral selector `access_control.get_skill_depth_view(payload)`
  returns a PII-free `SkillDepthAnalysis` (skill, candidate/required depth, match
  type, gap, **curated evidence labels**, neutral explanations). No raw CV/JD text.
- **Surfaces:** Candidate room → "Skill depth" / "What to strengthen" (supportive);
  Recruiter → "Requirement depth evidence" / "Depth gaps to verify" + probes; Shared
  Analysis → one neutral summary line. All carry a **directional** disclaimer.

---

## 15b. JD Refresh / Requirement Versioning (explanatory)

Deterministic JD versioning in `src/engine/jd_versioning/` (Phase 20). **Explanatory
only** — it never changes scoring, ranking, the orchestrator, or the payload schema.

- **`JDVersion` snapshot:** `jd_id` (operator-editable, hash-seeded default),
  `version_number`, `created_at`, `source_type`, `raw_text_hash` (normalized
  SHA-256), a `JDEntities` snapshot, and the reused **Phase-19 required-depth map**
  (`analyze_skill_depth(CVEntities(), jd_entities)` — read-only).
- **`diff_versions(old, new)`:** added/removed required & preferred skills,
  seniority/role/experience changes, responsibilities added/removed, required-depth
  changes, `newly_required_depth_gaps`, and advisory `became_more_senior` /
  `became_more_deployment_heavy` flags + a neutral summary.
- **Storage (`store.py`):** demo-safe (`generated`/`public`) versions →
  `data/raw/jd_version_history/`; everything else (pasted/uploaded/recruiter
  "current") → `data/private/jd_version_history/`. A private source is **never**
  written to the raw history (`PrivateJDMisroutingError`). Both are git-ignored
  **siblings** of the scanned JD dirs, so `document_loader` is untouched and
  snapshots never appear in the JD selectors.
- **Surfaces:** Admin "JD version compare" (demo data only); Recruiter "Compare
  JD versions" (private). Decision-support disclaimer on both. No candidate-facing
  versioning.

---

## 15c. UI Utilities / Product Comfort (Phase 21.1)

Visual-only comfort layer — **no business logic, no scoring, no access-control
change, no PII**.

- **`ui_kit` primitives** (each has a pure `*_html` builder + a thin render
  wrapper): `empty_state`, `confidence_chip` / `confidence_label`, `trust_badges`
  (`DEFAULT_TRUST_LABELS`), `stepper`, `hero_panel`, `status_chip_html`.
- **Global utility bar** (`utility_bar.render_utility_bar`): a compact status row
  — static checkpoint label (`CHECKPOINT_LABEL`, **not** read from git), current
  workspace, "Local only · not committed", provider status (`Deterministic-ready`
  by default), ingest enabled/disabled (from `ACAI_ENABLE_INGEST`), and a **Reset**
  action that clears only known session result keys.
- **Sidebar status block** (`render_sidebar_status`): Mode · Local data safe ·
  Candidate Pool protected · Ingest status · Fallback-ready · Decision-support.
- **Per-mode polish:** hero panel + visual **stepper** (Candidate: CV→Compare→
  Results→Practice→Quiz; Recruiter: JD→CVs→Ranking→Review→Verify; Admin: Select
  data→Analyze→Inspect→Governance), trust chips, and premium **empty states**.
- **Deferred:** runtime light theme (future). All status surfaces never list
  private paths or API keys.

### Focus / Presentation mode + Print comfort (Phase 21.3)

CSS-only, fully reversible — no business logic or access-control change.

- **Focus mode:** an `st.toggle` in the utility bar sets `session_state["focus_mode"]`;
  `streamlit_app` injects `presentation_css(is_focus_mode())` after the global
  style. Focus CSS widens `.block-container` and trims the decorative sidebar
  "How it works" steps (`.acai-sidebar-steps`) while keeping the workspace switch
  and status visible. It **never** blanket-hides `st.caption`, so governance and
  directional disclaimers stay on screen. A "Presentation ready" + print-hint chip
  appears when enabled.
- **Print comfort:** `print_css()` is **always** injected — an `@media print` block
  that hides interactive chrome (sidebar, header/toolbar, buttons, uploaders,
  download buttons), forces a light background with dark text, recolors
  `.acai-card`/`.acai-surface` via `!important`, and adds `break-inside: avoid`.
  Browser Print-to-PDF only; no server-side PDF, no dependencies.
- **Surface class:** `hero_panel`, `empty_state`, and `notice` now carry
  `.acai-surface` so print CSS can recolor them reliably.

---

## 15d. Export / Copy Summaries (Phase 21.2)

Safe, copyable Markdown summaries — **built only from role-safe selectors**, so
privacy is structural.

- **Pure builders** (`summary_builders.py`): `build_candidate_…`, `build_recruiter_…`,
  `build_governance_…`, `build_jd_diff_…`, `build_bulk_ranking_…`,
  `build_admin_demo_…`. Each uses an **explicit allowlist**, defensively scrubs
  emails/phones/URLs, **omits uploaded `source_filename`**, never reads files/APIs,
  and ends with a decision-support disclaimer.
- **Export panel** (`export_panel.py`): a collapsed "Export / Copy summary"
  expander with a privacy note, a copyable `st.code` Markdown preview, a `.md`
  download button, and a print-via-browser tip. **No HTML download, no PDF.**
- **Role sourcing:** candidate ← `get_candidate_view` (+shared, +skill-depth);
  recruiter ← `get_recruiter_view` (+ranking record); governance ← neutral
  `result`; JD diff ← `JDVersionDiff`; admin ← a single **stamped** "INTERNAL DEMO
  — not a hiring decision" document. Candidate exports never contain hire
  recommendations / verification / red flags; recruiter exports never contain
  candidate coaching/motivation (enforced by the selector boundary + tests).
- **Mounted in:** Candidate results, Recruiter ranking detail + bulk table, JD
  version diff, Governance panel, Admin/Demo.

---

## 15e. Security Hardening & Audit (Phase 22)

Deterministic-first, defense-in-depth. Full detail in
[SECURITY_HARDENING.md](SECURITY_HARDENING.md) + [QA_CHECKLIST.md](QA_CHECKLIST.md).

- **Prompt protection:** prompts/secrets/paths never rendered/exported/logged; the
  output guardrail scans narratives (`leak_flags`) and display/export paths redact
  via the shared scrubber.
- **Injection hardening:** input guardrail rejects unambiguous
  exfiltration/control/score-tamper/role-bypass asks; **scoring never reads
  instructions from CV/JD text** (malicious input can't change the score or cross
  roles).
- **Runtime gates** (`app_gates`): `APP_ENV` + `ACAI_ENABLE_ADMIN` / `_INGEST` /
  `_CANDIDATE_POOL` / `ACAI_DEBUG` / `ACAI_PUBLIC_DEMO`. Admin/Ingest/Pool/Debug are
  off in public; Admin/Demo is hidden from the switcher.
- **Governance sanitization:** raw provider/agent errors → `sanitize_error()`
  categories; raw details only in local/dev or `ACAI_DEBUG=1`.
- **Audit logs** (`audit_log`, `ACAI_ENABLE_AUDIT_LOG=1`, off by default): two
  sanitized, field-allowlisted, append-only JSONL streams under
  `data/reports/audit_logs/`; best-effort, never crashes the app.
- **Honest limit:** prompt secrecy isn't absolute once sent to a hosted LLM;
  Streamlit has no built-in auth (use a proxy for non-local deploys).

---

## 15f. Brand, i18n & Parser Robustness (Phase 24.3)

- **Brand/header (24.3A):** a proper brand lockup (inline-SVG mark + full
  "ArmeniaCareer AI" wordmark + tagline) in the sidebar and a clean main header
  band, plus a top-padding fix so content never tucks under the top bar. CSS/HTML
  only — `ui_kit.brand_mark_svg` / `brand_lockup_html` / `app_header_html`.
- **i18n foundation (24.3B):** a central translation registry
  (`src/ui/i18n.py` + `src/ui/locales/{en,hy,ru}.py`) with `t()`/`tlist()`,
  English fallback, and a never-empty result. A **Language selector** (EN /
  Հայերеն / Русский) writes `session_state["ui_lang"]` (default English).
  Localized today: sidebar, header, mode names/intros, hero panels, steppers,
  trust/status chips, utility-bar controls, key Candidate/Recruiter/Admin labels,
  and the full **CV intelligence report**. Internal panels (interview, quiz,
  skill-depth, governance, export Markdown) remain English for now.
- **Parser stabilization (24.3 hotfix):** robust to real-world extraction —
  two-column PDF header merges (multi-alias ALL-CAPS header pass), section-content
  bounding so a skills block never bleeds into a later section, language
  proficiency levels written **before or after** the language name, and job-title
  words excluded from technical skills. Verified with regression tests over the
  real-CV template and a simulated two-column extraction. **No OCR**, and **no
  guaranteed font/color/visual-layout analysis yet** (deferred to 24.3E).
- **Safety:** public-demo behavior is unchanged — the selector is presentational,
  no provider/API logic changed, gates still default off, deterministic offline.

### Multilingual interview foundation (Phase 24.3C)

- **Additive localizer** (`src/engine/interview/localizer.py` + `templates.py`)
  **regenerates** natural EN/HY/RU interview text from the engine's structured
  question objects (kind + target) — **not** machine translation. The interview
  engine core is unchanged.
- Localized surfaces: candidate practice questions, follow-ups, feedback bands,
  the completion summary, and the recruiter **Verification Interview** (question +
  strong/weak indicators + follow-ups, by gap-probe vs. verify category).
- **Armenian-first**, hand-authored for professional phrasing; **deterministic and
  key-free** (no provider calls, no prompts/secrets/errors exposed). An optional
  LLM enhancement could later wrap the localizer without changing this floor.
- **Remaining English:** recorded history prompts (the current question is localized).

### Interview rubric / evaluation quality (Phase 24.3D)

- **Additive rubric** (`src/engine/interview/rubric.py`) — deterministic, derives
  eight bounded (0–1) dimensions per answer: technical correctness, depth,
  relevance, clarity, practical example, communication, expressed confidence, and
  gap risk. The interview engine is **not** modified.
- **Weak-answer detection:** vague, generic/memorized, irrelevant, does-not-address,
  no practical example, no measurable detail, missing key concept, too-short, and
  overconfident-but-unsupported.
- **Candidate feedback (EN/HY/RU):** band + score, strengths, improvement areas,
  "how to make it stronger", a learning focus, one useful follow-up, and an
  **assessment confidence band** (how much to trust the evaluation, not a verdict).
- **Recruiter summary (read-only over `recruiter_view`):** evidence confidence band,
  gap/risk signals to verify, what to validate live, and the four signals — **CV
  quality, JD match, skill-depth confidence, interview performance** — kept
  explicitly separate.
- **Anti-overclaim:** wording uses "suggests" / "may indicate" / "needs verification"
  / confidence bands — never "definitely" or "proves". Deterministic and key-free.

### CV layout analyzer MVP + deploy/compatibility (Phase 24.3E)

- **Public-deploy import fix:** the brand helpers (`brand_mark_svg`,
  `brand_lockup_html`, `app_header_html`) live in `ui_kit` and are imported by
  `streamlit_app`. A public deploy of an older intermediate commit lacked them in
  `ui_kit`, causing an `ImportError`; redeploying current `main` resolves it, and a
  new import-contract test (`test_brand_header`) guards against recurrence.
- **Streamlit compatibility:** `ui_kit.df_width_kwargs()` returns `width="stretch"`
  on Streamlit ≥ 1.40 and `use_container_width=True` on older versions, so full-width
  tables work without the deprecation warning. All panels call the helper; only
  `ui_kit` references the legacy parameter (guarded by a test).
- **Layout analyzer** (`src/preprocessing/layout_analysis.py`): honest, deterministic
  diagnostics from extracted text + optional PDF page count (`pypdf` if present, else
  `None`). Detects character-spaced extraction, high symbol/icon density, visual-only
  language levels, and template/two-column risk; emits localized **ATS-readability
  advisories** (template/two-column, visual levels, standard headings, char-spacing).
  **No OCR; no font/colour claims.** Raw diagnostics are debug-gated; the advisory
  notes are safe and visible.

---

## 16. Privacy and Governance

- **No automatic hiring decision** — decision-support only; human review required.
- **Candidate/recruiter separation** — enforced by `access_control.py`; neither side
  sees the other's restricted content.
- **Raw CV text is never shown** — only canonical skills/role/dimension data and
  masked entities.
- **PII handling** — guardrail masks emails/phones/URLs before processing.
- **Data zones:** `data/raw` (demo, git-ignored) · `data/uploads` (consented pool,
  git-ignored) · `data/private` (real CVs/JDs, **git-ignored**).
- **Governance baseline** — established in Phase 17.1 (`docs/DATA_GOVERNANCE_PLAN.md`):
  privacy-first, all `data/` ignored, target folders prepared.
- **Phase 17.2 (the actual file move) is deferred** until organized files arrive and
  a reviewed move table is approved.

---

## 17. Current Limitations (honest)

- Deterministic heuristics are **MVP-level** — directional, not precise.
- **No OCR** — scanned/image PDFs are flagged, not read.
- **No skill-depth matching** yet — matching is binary.
- **No JD versioning** yet.
- **No production auth/database** — the pool is local files; no accounts.
- **Streamlit synchronous batch** — the UI is busy during a bulk run (10-CV cap).
- **LLM provider availability** depends on your API key + project model access;
  otherwise deterministic fallbacks are used.

---

## 18. Future Roadmap

**UI utilities:** light/dark/system theme toggle · full-screen mode · export/print to
PDF · demo capture · richer toolbar/actions.

**Model / accuracy:** skill proficiency / requirement depth · JD refresh / versioning ·
stronger semantic matching · optional LLM-enhanced interview/quiz feedback.

**Data governance:** Phase 17.2 **Move Table + Loader Scope Plan** once organized files
arrive · approved data migration · recursive, demo-scoped loaders that exclude
`data/private`.

**Production:** auth · database-backed candidate pool · background jobs · deployment.

---

## 19. How to Explain the Project in a Presentation

**1-minute:** *"ArmeniaCareer AI analyzes a CV against a job description and serves
the result two ways — supportive coaching for candidates, evidence-based screening
for recruiters — with privacy enforced in code. It's decision-support; a human
always decides, and it runs fully offline with deterministic logic."*

**3-minute:** Add: one analysis → role-based views; candidate gets CV quality, match,
interview practice, and a skill quiz; recruiter gets bulk ranking + verification
guide; governance shows exactly what ran live vs. fell back; no raw CV/PII is exposed.

**5-minute demo flow:** Candidate (CV → quality → JD compare → interview → quiz) →
Recruiter (JD + CVs → bulk ranking → open detail → verification → governance) →
Admin/Demo (internal samples).

**Product value:** two-sided, privacy-first, supportive yet honest.
**Technical value:** deterministic-first with graceful LLM fallback chain, role-based
access control, multilingual parsing + evaluation harness, full offline test suite.
**Honest limitations:** MVP heuristics, no OCR, binary skill matching, local prototype.

---

## 20. Glossary

| Term | Meaning |
|---|---|
| **CV parsing** | Extracting structured info (skills, sections, dates) from a resume. |
| **JD** | Job description — the role's requirements. |
| **Semantic alignment** | How closely CV and JD mean the same thing, via embeddings or skill overlap. |
| **Skills ontology** | Matching candidate skills to JD-required skills (matched/missing). |
| **Deterministic fallback** | Rule-based logic used when no LLM/API is available — always works. |
| **Candidate Pool** | Consent-gated local store of approved CVs. |
| **Bulk ranking** | Analyzing many CVs against one JD and ordering them. |
| **Governance** | Transparency panel: providers used, fallbacks, guardrails, timing. |
| **Skill depth** | How deeply a skill is demonstrated (mention → basics → production) — planned. |
| **JD versioning** | Tracking how a job's requirements change over time — planned. |
