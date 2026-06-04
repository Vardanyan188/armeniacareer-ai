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
}
