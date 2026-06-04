# Demo Script

A presentation-ready walkthrough (~12–15 minutes). The app runs deterministically,
so the demo works **with or without API keys**.

🔗 **Deployed demo:** _<deployment URL placeholder — Streamlit Community Cloud>_

> Opening line: *"ArmeniaCareer AI is a two-sided career-intelligence platform.
> The same analysis serves candidates and recruiters differently — by access
> profile, not by re-running anything. It's decision-support; a human always decides."*

## 0. Launch

```bash
streamlit run streamlit_app.py
```

Point out: the **dark premium theme**, the refreshed **brand lockup** (logo mark +
full "ArmeniaCareer AI" wordmark), the **sidebar workspace switcher** with a
contextual "How it works" list, the **status bar** (provider / data-safety / ingest)
with the **Focus mode** toggle, and the responsible-AI footer.

### Language check (EN / Հայերեն / Русский)

In the sidebar, switch the **Language** selector between English, Հայերեն, and
Русский. Confirm the brand tagline, workspace labels, steppers, trust chips, mode
header, empty states, and the **CV intelligence report** all update to the chosen
language. *Say:* "The interface is multilingual; Armenian is first-class because
real interviews here are often Armenian-speaking."

### Real-CV parsing check

Upload a realistic, non-standard CV (e.g. a two-column Canva layout with headings
like `PROFILE`, `CONTACT ME`, `COMPUTER SKILLS`, `LANGUAGE`, `WORK EXPERIENCE`).
Confirm the report detects **Summary, Contact, Education, Work Experience, Skills**,
extracts tools (incl. slash-separated lists like `HTML/CSS/JavaScript`), reads
**language levels** (e.g. *Armenian — Native, English — Advanced*), and does **not**
turn job titles (e.g. *Software Engineer*) into skills. The quality score should
reflect a mostly-parseable CV, not a false-low. *Say:* "Robust parsing was
hardened through iterative development, regression testing, and human review."

### Layout & readability advisory (24.3E)

For a Canva/template/two-column CV, the report shows a localized **Layout &
readability** note — e.g. "appears to use a template/two-column layout… some ATS
systems may parse it less reliably", "use clear text labels for language levels
instead of only stars/dots", and "keep section headings standard and
text-selectable". *Say:* "Honest, advisory only — it reads the extracted text and
page count; it does **not** do OCR or claim font/colour analysis." Raw diagnostics
stay behind the local/dev debug panel and never show in the public demo.

## 1. Candidate Mode

1. Select **Candidate**.
2. **Your CV:** upload a text-based CV → **CV intelligence report** (quality band,
   detected skills, sections, role directions, improvement tips). *"CV-only — no job,
   no LLM required."*
3. **Compare to a job:** paste a short JD → composite **score card**.
4. **Results tabs:** Your Match, Shared Analysis (7 dimensions), **Skill Depth**
   (your depth vs. required + what to strengthen), Interview Practice, Skill Quiz.
   *"Candidates never see hire recommendations or red flags."*
5. **Export / Copy summary:** show the Markdown export — *"role-safe; no PII, no
   recruiter-only content."*

## 2. Interview Practice & Quiz

- Interview Practice: progress strip; a **weak** answer → adaptive follow-up; a
  **strong** answer advances. *"Deterministic, supportive, private — not stored."*
- **Multilingual interview check:** switch the sidebar **Language** to Հայերեն (and
  Русский) and re-open Interview Practice — questions, follow-ups, feedback bands,
  and the recruiter Verification Interview render in natural Armenian/Russian with
  **no API keys**. *"Armenian-first, hardened through iterative development, testing,
  and human review."*
- **Rubric evaluation check:** submit an answer and open **"Answer evaluation"** — an
  eight-dimension rubric (technical correctness, depth, relevance, clarity, practical
  example, communication, expressed confidence, gap risk) with an **assessment
  confidence band**, localized strengths/improvements, "how to make it stronger",
  a learning focus, and a follow-up. In Recruiter Mode, the Verification Interview
  ends with **"Evidence confidence & what to verify"** — confidence band, gap signals,
  what to validate live, and the CV-quality / JD-match / skill-depth / interview-
  performance signals kept explicitly separate. *"It suggests and flags for
  verification — it never claims certainty."*
- Skill Quiz: deterministic questions + study-next suggestions.

## 3. Recruiter Mode

1. Switch to **Recruiter / HR** (results reset between modes).
2. **Job description:** paste/upload a JD. Optionally open **Compare JD versions**
   (private) to show requirement diffs.
3. **Candidate CVs:** upload several → **Bulk ranking**: buckets (Strong fit /
   Review / Weak / Insufficient / Failed), priorities, safe "Candidate N" labels.
4. **Open a candidate:** Recruiter View (composite, hire recommendation, integrity
   risk), **Verification Interview**, **Requirement depth evidence**, and the
   recruiter **Export** (no coaching/motivation, no uploaded filename).
   *"Recruiters never see candidate coaching."*

## 4. JD Versioning

- In **Compare JD versions**, show how a role that adds MLOps / changes seniority
  surfaces **added/removed skills, depth changes, and "more deployment-heavy"** flags.

## 5. Governance / Fallback

- Open **Governance / Fallback**: LLM status, provider summary (OpenAI / Google /
  deterministic), guardrail pass, completeness. *"Transparent — no silent failures;
  technical details are sanitized and hidden outside debug."*

## 6. Admin · Demo (gated)

1. Switch to **Admin · Demo** (only visible when `ACAI_ENABLE_ADMIN=1`; hidden in
   public). *"Internal testing only — the only mode that browses local sample data."*
2. Show **dataset registry labels**, private-data exclusion, the **JD version
   compare** tool, and the stamped **internal demo export**.

## 7. Focus / Presentation & Print

- Toggle **Focus mode** (wider, calmer layout; warnings stay visible).
- Use the browser **Print** (Ctrl/Cmd + P) for a clean, light report.

## 8. Security & Audit (mention)

- Injection in a CV/JD is screened; **the score can't be changed and roles can't be
  crossed**. Optional privacy-safe **audit logs** (off by default) record sanitized
  workflow/security events for QA. See [SECURITY_HARDENING.md](SECURITY_HARDENING.md).

## Closing

*"Everything you saw runs offline and deterministically; API keys only raise
quality, never change the contract. Honest decision-support with role-based privacy
built into the code."*

### Things to have ready
- One clean text-based CV and one short JD in a notepad.
- 2–3 CVs to show bulk ranking and pool dedup.
- Two JD versions (e.g. before/after adding deployment requirements) for the diff.
