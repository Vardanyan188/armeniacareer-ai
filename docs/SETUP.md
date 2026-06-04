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
| `ACAI_ENABLE_LLM` | **Opt-in switch for AI providers.** Set to `1` (outside public demo) to allow live provider calls. Unset/`0` ⇒ deterministic only, even with keys present. |
| `OPENAI_API_KEY` | Analysis agents + OpenAI embeddings (used when `ACAI_ENABLE_LLM=1`) |
| `GOOGLE_API_KEY` | Gemini narratives + alternate embedding provider |
| `GEMINI_API_KEY` | Accepted as an **alias** for the Gemini/Google key (use either name) |
| `ACAI_LLM_PROVIDER` | Optional. `auto` (default) / `gemini` / `openai` — provider preference when keys exist. |
| `GOOGLE_EMBEDDING_MODEL` | Optional. Google embedding model for semantic fallback (default `gemini-embedding-001`) |
| `ACAI_ENABLE_INGEST` | Optional. Set to `1` to unlock the internal Admin-only **Data Ingest** panel (private-dataset persistence). Hidden by default. |
| `APP_ENV` | `local` / `dev` / `demo` / `prod` — `demo`/`prod` trigger public lockdown (and disable all providers) |
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

### Provider modes & how the fallback works

Provider usage is **opt-in and gated**. The app never calls a provider unless it
is explicitly enabled, and every provider failure degrades to the deterministic
path without crashing.

| Mode | Env | Behaviour |
|---|---|---|
| **Local deterministic fallback** | `APP_ENV=local` (no `ACAI_ENABLE_LLM`) | No provider calls; deterministic analysis. Keys, if present, are ignored. |
| **Local AI-enabled** | `APP_ENV=local`, `ACAI_ENABLE_LLM=1`, at least one key | Uses Gemini (`GOOGLE_API_KEY` or `GEMINI_API_KEY`) and/or OpenAI (`OPENAI_API_KEY`); preference via `ACAI_LLM_PROVIDER`. On missing/invalid/quota-limited keys or any provider error → deterministic fallback. |
| **Public demo** | `APP_ENV=demo` or `ACAI_PUBLIC_DEMO=1` | **Hard lockdown**: providers disabled and keys ignored even if set; deterministic only; no provider errors shown. |

```powershell
# 1) Local deterministic fallback (no keys needed)
$env:APP_ENV = "local"
streamlit run streamlit_app.py

# 2) Local AI-enabled mode (Gemini and/or OpenAI)
$env:APP_ENV = "local"
$env:ACAI_ENABLE_LLM = "1"
# set ONE or BOTH (placeholders shown — never commit real values):
$env:GOOGLE_API_KEY = "<your-gemini-key>"   # or $env:GEMINI_API_KEY
$env:OPENAI_API_KEY = "<your-openai-key>"
# optional preference: gemini | openai | auto
$env:ACAI_LLM_PROVIDER = "auto"
streamlit run streamlit_app.py

# 3) Public demo simulation (providers disabled, keys ignored)
$env:APP_ENV = "demo"
$env:ACAI_PUBLIC_DEMO = "1"
streamlit run streamlit_app.py
```

The status bar shows a **safe** summary only — "AI provider active: Gemini/OpenAI"
or "AI provider unavailable — deterministic fallback is active". It never prints
keys or raw provider errors.

### Verify a key is set without printing it

Check only the **length** (never the value), so a key is never echoed to the
terminal, logs, or screenshots:

```powershell
# PowerShell — prints only a length number, not the secret
if ($env:GOOGLE_API_KEY) { "GOOGLE_API_KEY length: $($env:GOOGLE_API_KEY.Length)" } else { "GOOGLE_API_KEY: not set" }
if ($env:OPENAI_API_KEY) { "OPENAI_API_KEY length: $($env:OPENAI_API_KEY.Length)" } else { "OPENAI_API_KEY: not set" }
```

```bash
# macOS / Linux — prints only the character count
[ -n "$GOOGLE_API_KEY" ] && echo "GOOGLE_API_KEY length: ${#GOOGLE_API_KEY}" || echo "GOOGLE_API_KEY: not set"
```

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
