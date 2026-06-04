# Setup

## Requirements

- Python 3.10+ (developed and tested on 3.12).
- The packages in `requirements.txt`.

## 1. Create and activate a virtual environment

```bash
python -m venv .venv
```

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

## 2. Install dependencies

```bash
pip install -r requirements.txt
```

## 3. API keys (optional)

The app runs end to end **without keys** using deterministic fallbacks. Provide
keys to enable the LLM-enhanced paths.

Copy the template and edit:

```bash
cp .env.example .env     # PowerShell: Copy-Item .env.example .env
```

| Variable | Enables |
|---|---|
| `OPENAI_API_KEY` | Analysis agents + OpenAI embeddings |
| `GOOGLE_API_KEY` | Gemini narratives + alternate embedding provider |
| `GOOGLE_EMBEDDING_MODEL` | Optional. Google embedding model for semantic fallback (default `gemini-embedding-001`) |
| `ACAI_ENABLE_INGEST` | Optional. Set to `1` to unlock the internal Admin-only **Data Ingest** panel (private-dataset persistence). Hidden by default. |
| `APP_ENV` | `local` / `dev` / `demo` / `prod` — `demo`/`prod` trigger public lockdown |
| `ACAI_ENABLE_ADMIN` | Optional. Show the Admin/Demo workspace (never in public). |
| `ACAI_ENABLE_CANDIDATE_POOL` | Optional. Allow Candidate Pool persistence (local/dev default on; public off). |
| `ACAI_DEBUG` | Optional. Show sanitized technical details (local/dev only). |
| `ACAI_PUBLIC_DEMO` | Optional. Hard lockdown: Admin/Ingest/Pool/Debug all off. |
| `ACAI_ENABLE_AUDIT_LOG` | Optional. Enable privacy-safe JSONL audit logs (off by default). |

### Setting environment variables

```powershell
# Windows PowerShell (current session)
$env:OPENAI_API_KEY = "sk-..."
$env:GOOGLE_API_KEY = "..."
```

```bash
# macOS / Linux (current session)
export OPENAI_API_KEY="sk-..."
export GOOGLE_API_KEY="..."
```

`.env` is git-ignored. Never commit real keys.

### Internal Data Ingest (optional, Admin-only)

The **Data Ingest** panel lets an internal operator save a single uploaded CV/JD
into the git-ignored private dataset (`data/private/`). It is **hidden by default**
because "Admin" is only a sidebar role, not real authentication. Enable it
deliberately, for a local session only:

```powershell
# Windows PowerShell (current session)
$env:ACAI_ENABLE_INGEST = "1"
```

```bash
# macOS / Linux (current session)
export ACAI_ENABLE_INGEST=1
```

When unset, no ingest UI is shown and no private-persistence action is available.
Do **not** enable this on a shared/public deployment.

## 4. Run the app

```bash
streamlit run streamlit_app.py
```

The app opens in the browser with the dark theme from `.streamlit/config.toml`.

### Focus / Presentation mode & printing

Toggle **Focus mode** from the top utility bar for a presentation-friendly layout
(wider content, trimmed sidebar steps). Warnings, disclaimers, and consent
indicators always stay visible. To print or save a clean copy, use your browser's
**Print** (Ctrl/Cmd + P) — the app injects print-friendly CSS (light background,
interactive controls hidden). For a portable text artifact, use the **Export /
Copy summary** panels (Markdown). No PDF is generated server-side.

## 5. Run the tests (offline, no network)

```bash
python -m pytest -q
```

Tests are deterministic and **environment-independent**: `AnalysisOrchestrator(enable_llm=False)`
is a hard external-provider kill-switch — no OpenAI, Google/Gemini, embedding, or
narrative calls are made even if `OPENAI_API_KEY` / `GOOGLE_API_KEY` are set. So
`python -m pytest` passes identically with or without keys in the environment.

## Common issues

| Symptom | Cause | Fix |
|---|---|---|
| "requires the 'pypdf' package" / "python-docx" | PDF/DOCX parser not installed | `pip install -r requirements.txt` (or `pip install pypdf python-docx`). TXT/MD always work. |
| OpenAI embedding **403** | API project lacks embedding-model access | The orchestrator automatically tries Google, then deterministic fallback. Set `GOOGLE_API_KEY` or rely on the deterministic path. Governance shows which was used. |
| Google embedding **model not found** | Outdated/unsupported model name for the current Gemini API | The default is now `gemini-embedding-001`. Override with `GOOGLE_EMBEDDING_MODEL` if your project requires a different supported model. If it still fails, the deterministic fallback is used. |
| `GOOGLE_API_KEY` missing | No Gemini/alternate provider | Narratives and the alternate embedding path fall back deterministically — expected, not an error. |
| UI looks light / tables harsh white | `.streamlit/config.toml` not picked up | Run from the project root so Streamlit finds `.streamlit/config.toml`; restart the app. |
| `Activate.ps1 cannot be loaded` on Windows | PowerShell execution policy | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`, then re-activate. |
| Scanned PDF returns "low extraction quality" | Image-only PDF, no text layer | Expected — OCR is not implemented. Upload a text-based PDF/DOCX. |

## Notes

- Uploaded CVs are written only to temporary files (deleted after analysis) or,
  with consent, to the git-ignored `data/uploads/candidate_pool/`. They are never
  written to `data/raw/`.
- `data/raw/` sample datasets are used **only** by Admin · Demo mode.
