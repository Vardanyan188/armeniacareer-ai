# Data Governance Plan

This document defines how ArmeniaCareer AI organizes, classifies, and protects
CV/JD data. It is the source of truth for the (future, approved) data
reorganization. **Phase 17.1 establishes only the safety baseline** — the
`.gitignore` privacy fix and the empty target folders. **No data files have been
moved, renamed, or deleted.**

Policy: **privacy-first**. All of `data/` is git-ignored. No synthetic demo data
is committed in this phase.

---

## 1. Target folder structure

```
data/
├── raw/                                  (git-ignored)  — demo / non-private datasets
│   ├── job_descriptions/
│   │   ├── generated_samples/international/    generated/mock JDs (demo-safe)
│   │   └── public_scraped/
│   │       ├── international/                  public scraped JDs (demo-safe)
│   │       └── local/                          public scraped local JDs (demo-safe)
│   ├── resumes/
│   │   ├── generated_samples/                  generated/synthetic CVs (demo-safe)
│   │   ├── linkedin_profiles/                  LinkedIn/profile CVs (sensitive, internal)
│   │   └── public_datasets/kaggle/             Kaggle public dataset CVs (sensitive, internal)
│   └── jd_version_history/                     demo-safe JD version snapshots (Phase 20)
├── uploads/                              (git-ignored)
│   └── candidate_pool/                   consent + threshold gated CVs + index.json
├── private/                              (git-ignored)  — REAL data, never committed
│   ├── ingest_manifest.json              Admin-ingest audit/dedup record (Phase 17.3)
│   ├── real_resumes/                     real human CVs (local testing only)
│   ├── jd_version_history/               private / recruiter JD version snapshots (Phase 20)
│   └── job_descriptions/
│       └── company_private/              private/internal real company JDs
├── processed/                            (git-ignored)
└── reports/                              (git-ignored)  — generated outputs/reports
```

**Dataset registry.** `src/engine/dataset_registry.py` declares each known source
(key, folder path, data type, sensitivity, `demo_safe`, label, description). The
Admin/Demo selectors label files by source and exclude private/uploads; demo
loaders (`list_resume_files` / `list_jd_files`) recurse into these folders but
never return files under `private`, `uploads`, or `candidate_pool`.

**Private data ingest (Phase 17.3).** `src/engine/data_ingest.py` +
`src/ui/components/data_ingest_panel.py` provide an Admin-only, opt-in way to
persist a single uploaded CV/JD into the **private** dataset. It is **env-gated**
(`ACAI_ENABLE_INGEST=1`); when unset, no ingest UI or persistence action exists.
Destinations are private-only — CV → `data/private/real_resumes/`, private JD →
`data/private/job_descriptions/company_private/`. It never writes to `data/raw`
or the Candidate Pool, requires an explicit authorization flag, dedups by SHA-256,
stores files as `<record_id><ext>` (no human name on disk), and records an audit
entry in `data/private/ingest_manifest.json` (original filename kept there only).
raw/demo import and pasted-JD persistence are **deferred** to later phases.

## 2. Classification rules

| Class | Indicators | Destination | Sensitivity |
|---|---|---|---|
| **Real (private)** | human name, email, phone, address, photo/scan, or unknown human origin | `data/private/real_resumes/` or `private/job_descriptions/company_private/` | High |
| **LinkedIn/profile** | profile-style exports (`cvN.pdf`), may contain real people | `data/raw/resumes/linkedin_profiles/` | Medium (flag) |
| **Generated/synthetic** | programmatic patterns (`cv_NN_*`, `cv_fullpage_*`), no real contact data | `data/raw/resumes/generated_samples/` | Low |
| **Public scraped JD** | public job posting from a public source | `data/raw/job_descriptions/public_scraped/` | Low–Med |
| **Generated JD** | mock/generated JD | `data/raw/job_descriptions/generated_samples/` | Low |
| **Private JD** | real internal/company JD | `private/job_descriptions/company_private/` | High |
| **Ambiguous** | unclear provenance (e.g. bare `NN.pdf`) | **default to private** until reviewed | Treat as High |

**Rule of conservatism:** when in doubt, classify as private. Never classify a
file as synthetic without confirming it carries no real personal data.

## 3. Privacy rules

- Real people's CVs must **never** be moved into `data/raw/` (demo) folders.
- Real CVs (names, emails, phones, photos, addresses, personal history) are
  **private** and live only under `data/private/`.
- LinkedIn/profile CVs are **sensitive** and excluded from Admin/Demo unless a
  file is explicitly confirmed synthetic or approved for demo use.
- Candidate Pool storage stays **consent + quality-threshold gated**; it is not a
  dumping folder, and bulk ranking never writes to it.
- **Do not commit** private CVs/JDs. Uploaded CVs are never written into `data/raw`.
- Stored candidate-pool filenames may contain names on disk; they are never
  surfaced in the recruiter UI.

## 4. Move table format

A reviewed table is produced (in a later, approved phase) with one row per file.
**No per-file rows are generated in this phase.** Template:

| current path | detected type | sensitivity | proposed destination | reason | action |
| --- | --- | --- | --- | --- | --- |
| _(example)_ `data/raw/resumes/<name>_CV.pdf` | real CV | high | `data/private/real_resumes/` | real PII in demo folder | move |
| _(example)_ `data/raw/resumes/cv_NN_first_last.pdf` | generated | low–med | `data/raw/resumes/generated_samples/` | synthetic, name-bearing | move after spot-check |
| _(example)_ `data/raw/resumes/NN.pdf` | ambiguous | high | _(TBD)_ | provenance unclear | **review (no auto-move)** |

`action` values: `move` · `keep` · `review` (review = no automatic move).

## 5. Current risk summary

| Risk | Status after Phase 17.1 |
|---|---|
| `data/private/` not git-ignored | **Fixed** — now ignored |
| `data/reports/` not git-ignored | **Fixed** — now ignored |
| Real-name CVs in `data/raw/resumes/` top level | **Still present** — exposed to Admin/Demo; pending the (approved) move phase |
| Ambiguous `NN.pdf` provenance | **Still present** — review required before any move |
| `.png` real CV (photo/scan) | **Still present** — private; not parseable (no OCR) |
| Candidate-pool filenames contain names on disk | Accepted — consent-gated, ignored, hidden in UI |

## 6. Approval workflow before any move

1. `.gitignore` privacy baseline confirmed (this phase).
2. Generate the per-file audit table (writes the table only — moves nothing).
3. **Human review** of every `review`/high-sensitivity row; lock destinations.
4. Explicit approval of the finalized move table.
5. Execute moves (private first), then update loaders/Admin, then docs, then tests.

No file is moved without an approved row in the reviewed table.

## 7. JD versioning (implemented — Phase 20)

Requirements change over time. `src/engine/jd_versioning/` stores `JDVersion`
records (`jd_id`, version number, timestamp, parsed `JDEntities` snapshot,
normalized raw-text SHA-256, and the reused Phase-19 required-depth map) and a
deterministic `diff_versions` reporting added/removed required & preferred
skills, changed seniority/role/experience, responsibilities added/removed,
required-depth changes, `newly_required_depth_gaps`, and advisory
`became_more_senior` / `became_more_deployment_heavy` flags. Surfaced via an
Admin compare tool and a Recruiter "Compare JD versions" panel. **Explanatory
only — no scoring/ranking change.**

**Storage & privacy.** Version history lives in **siblings** of the scanned JD
dirs, so `document_loader` is untouched and snapshots never appear in the JD
selectors:

```
data/raw/jd_version_history/        (git-ignored)  demo-safe (generated/public) versions
data/private/jd_version_history/    (git-ignored)  private / recruiter "current" JD versions
```

A **private-source version is never written to the raw (demo) history** — the
store raises `PrivateJDMisroutingError` and the Recruiter panel persists only
under `data/private/`. No version snapshots are written under
`…/job_descriptions/**`. No candidate-facing JD versioning; no auto-migration.

## 8. Skill Proficiency / Requirement Depth (implemented — Phase 19)

Skills are no longer treated as binary. `src/engine/skill_depth/` defines a
depth ladder (`MENTIONED < BASIC < APPLIED < ADVANCED < PRODUCTION <
DEPLOYMENT`), infers candidate evidence depth and JD required depth, and reports
**full / partial / mentioned-only / missing** per required skill. It is
**explanatory only** — `scoring.py`, ranking, quiz, and interview are unchanged;
integrating depth into the composite score remains a separate, explicitly
approved step.

**Privacy:** depth reads only already-masked structured entity fields (never raw
CV/JD text) and surfaces **curated evidence labels** (e.g. `pandas`, `docker`,
`ci/cd`) — never raw snippets or PII. It is exposed through the single neutral
selector `access_control.get_skill_depth_view`, carries a directional disclaimer
on every surface, and makes no hiring decision.
