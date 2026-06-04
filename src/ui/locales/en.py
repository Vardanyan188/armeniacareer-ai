# src/ui/locales/en.py
# English translations (the canonical key set; hy/ru mirror these keys).

STRINGS = {
    # Brand
    "app.name": "ArmeniaCareer AI",
    "app.tagline": "Career Intelligence",

    # Sidebar
    "sidebar.workspace": "Workspace",
    "sidebar.how_it_works": "How it works",
    "sidebar.language": "Language",
    "sidebar.status": "Status",
    "sidebar.disclaimer": (
        "Decision-support only. Human review is required before any hiring "
        "decision. Files are processed locally and not committed."
    ),

    # Modes
    "mode.candidate": "Candidate",
    "mode.recruiter": "Recruiter / HR",
    "mode.admin": "Admin · Demo",
    "mode.candidate.intro": "Analyze and improve your own CV.",
    "mode.recruiter.intro": "Screen candidates against a job.",
    "mode.admin.intro": "Internal demo with local sample data.",
    "mode.admin.badge": "Internal Demo Mode",

    # Heroes
    "hero.candidate.title": "Improve your CV and prepare for interviews",
    "hero.candidate.subtitle": (
        "Upload your CV for a private, local analysis — quality, skills, gaps, and practice."
    ),
    "hero.recruiter.title": "Rank candidates and verify evidence",
    "hero.recruiter.subtitle": (
        "Provide a job description, upload candidate CVs, then review a recruiter-safe ranking."
    ),
    "hero.admin.title": "Internal demo and governance tools",
    "hero.admin.subtitle": (
        "Run the deterministic pipeline over local sample data and inspect every layer."
    ),

    # Steppers (lists)
    "steps.candidate": ["CV", "Compare", "Results", "Practice", "Quiz"],
    "steps.recruiter": ["JD", "CVs", "Ranking", "Review", "Verify"],
    "steps.admin": ["Select data", "Analyze", "Inspect", "Governance"],

    # Trust chips
    "trust.offline_ready": "Offline-ready",
    "trust.deterministic_fallback": "Deterministic fallback",
    "trust.private_excluded": "Private data excluded",
    "trust.decision_support": "Decision-support only",
    "trust.no_auto_hiring": "No auto-hiring",

    # Utility bar
    "util.reset": "Reset",
    "util.focus_mode": "Focus mode",
    "util.presentation_ready": "Presentation ready",
    "util.print_hint": "Print: Ctrl/Cmd + P",
    "util.workspace_prefix": "Workspace",

    # Status chips
    "status.local_only": "Local only · not committed",
    "status.local_data_safe": "Local data safe",
    "status.pool_protected": "Candidate Pool protected",
    "status.ingest_enabled": "Ingest: enabled",
    "status.ingest_disabled": "Ingest: disabled",
    "status.fallback_ready": "Fallback-ready · API optional",
    "status.decision_support": "Decision-support only",
    "status.mode_prefix": "Mode",
    "status.provider_active": "AI provider active",
    "status.provider_fallback": "AI provider unavailable — deterministic fallback is active",

    # Candidate mode
    "candidate.cv_step": "Your CV",
    "candidate.upload_cv": "Upload your CV",
    "candidate.format_caption": (
        "Accepted: PDF, DOCX, TXT, MD. Text-based PDFs work best — scanned/image "
        "PDFs may be flagged as low extraction quality (OCR is not implemented yet)."
    ),
    "candidate.no_cv_title": "No CV uploaded yet",
    "candidate.no_cv_hint": "Upload a CV to see your CV intelligence report.",
    "candidate.compare_step": "Compare to a specific job (optional)",
    "candidate.results": "Results",
    "candidate.compare_button": "Compare with this job",

    # Recruiter mode
    "recruiter.no_cv_title": "No candidate CVs yet",
    "recruiter.no_cv_hint": "Upload at least one candidate CV to continue.",

    # Admin mode
    "admin.internal_notice": (
        "Internal Demo Mode — uses the local sample datasets in data/raw. "
        "Not for real candidate users. All four detail tabs are shown for testing."
    ),
    "admin.disabled_notice": "Admin / Demo tools are disabled in this environment.",

    # CV intelligence report (Candidate Mode)
    "cv.report.title": "CV intelligence report",
    "cv.report.scanned_warning": (
        "Low extraction quality — this looks like a scanned/image PDF with no text "
        "layer. Please upload a text-based PDF or DOCX for an accurate analysis."
    ),
    "cv.report.low_warning": (
        "Low extraction quality — very little readable text was found. "
        "Results may be unreliable."
    ),
    "cv.report.partial_warning": "Partial extraction — some sections may not have been detected.",
    "cv.report.quality_score": "CV quality score",
    "cv.report.skills_detected": "Skills detected",
    "cv.report.word_count": "Word count",
    "cv.report.sections": "Sections",
    "cv.report.contact_info": "Contact info",
    "cv.report.work_experience": "Work Experience",
    "cv.report.education": "Education",
    "cv.report.skills": "Skills",
    "cv.report.summary": "Summary",
    "cv.report.present": "Yes",
    "cv.report.missing": "Missing",
    "cv.report.detected_skills": "Detected skills",
    "cv.report.no_skills": "No recognised technical skills detected. Add a clear Skills section.",
    "cv.report.languages": "Languages",
    "cv.report.role_directions": "Possible role directions",
    "cv.report.improvement": "Improvement suggestions",
    "cv.report.no_issues": "No major structural issues detected. Strong CV foundation.",

    # CV layout / readability advisory (24.3E)
    "cv.layout.title": "Layout & readability",
    "cv.layout.warn_template": (
        "This CV appears to use a template/two-column layout. It is readable now, "
        "but some ATS systems may parse it less reliably."
    ),
    "cv.layout.warn_visual_levels": (
        "Use clear text labels for language levels (e.g. B2, Fluent) instead of "
        "only visual stars/dots/bars."
    ),
    "cv.layout.warn_headings": (
        "Keep section headings standard and text-selectable for reliable parsing."
    ),
    "cv.layout.warn_char_spaced": (
        "The text was extracted with unusual character spacing; it was auto-repaired, "
        "but a cleaner PDF or DOCX export improves reliability."
    ),

    # Interview (candidate practice + recruiter verification)
    "interview.practice_title": "Interview Practice",
    "interview.practice_notice": (
        "Practice mode — private, supportive coaching. Your answers are not stored or shared."
    ),
    "interview.question": "Question",
    "interview.answered": "Answered",
    "interview.avg_score": "Avg score",
    "interview.target": "Target",
    "interview.session_progress": "Session progress",
    "interview.on_track": "On track — your average meets the target.",
    "interview.keep_going": "Keep going — aim to lift your average toward the target.",
    "interview.current_question": "Current question",
    "interview.your_answer": "Your answer",
    "interview.your_answer_prefix": "Your answer",
    "interview.submit": "Submit answer",
    "interview.skip": "Skip question",
    "interview.end": "End session",
    "interview.write_answer": "Write an answer before submitting.",
    "interview.complete": "Practice session complete. Review the feedback above.",
    "interview.avg_answer_score": "Average answer score",
    "interview.restart": "Restart practice",
    "interview.followup": "Follow-up",
    "interview.verify_title": "Verification Interview",
    "interview.verify_notice": (
        "Structured, evidence-based verification guide for manual evaluation. "
        "Decision-support only — the recruiter judges the answers."
    ),
    "interview.no_questions": "No verification questions generated for this analysis.",
    "interview.strong_header": "A strong answer should contain",
    "interview.weak_header": "Weak / unclear answers may indicate",
    "interview.followups_header": "Suggested follow-ups",
    "interview.must_ask": "Must ask",
    "interview.recommended": "Recommended",
    "interview.optional": "Optional",

    # Interview rubric / evaluation quality (24.3D)
    "interview.rubric.title": "Answer evaluation",
    "interview.rubric.confidence": "Assessment confidence",
    "interview.rubric.strengths": "Strengths",
    "interview.rubric.improvements": "Improvement areas",
    "interview.rubric.better": "How to make it stronger",
    "interview.rubric.learning": "Suggested learning focus",
    "interview.rubric.followup": "Useful follow-up",
    "interview.evidence_title": "Evidence confidence & what to verify",
    "interview.risk_signals": "Risk / gap signals",
    "interview.validate": "What to validate in the live interview",
    "interview.distinction_title": "Signals kept separate",
    "interview.dim.technical_correctness": "Technical correctness",
    "interview.dim.depth": "Depth",
    "interview.dim.relevance": "Relevance",
    "interview.dim.clarity": "Clarity",
    "interview.dim.practical_example": "Practical example",
    "interview.dim.communication": "Communication",
    "interview.dim.confidence": "Expressed confidence",
    "interview.dim.gap_risk": "Gap risk",
}
