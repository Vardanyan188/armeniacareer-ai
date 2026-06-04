# src/engine/quiz/question_bank.py
#
# Deterministic question bank for the Candidate Skill Quiz (no LLM, no network).
#
# Curated multiple-choice items per skill and per dimension, plus generic
# templates for uncovered skills. Correct-option placement is deterministically
# derived from the question id (stable across runs) so the answer isn't always
# in the same slot, while remaining fully reproducible.
#
# Extension seam: a future LLM generator can produce equivalent QuizQuestion
# objects; the builder/eval contracts do not change.

from __future__ import annotations

import hashlib
from typing import Dict, List, Tuple

from src.engine.quiz.models import Focus, QuestionType, QuizQuestion


def _seed(qid: str) -> int:
    return int(hashlib.md5(qid.encode("utf-8")).hexdigest(), 16)


def _place(correct: str, distractors: List[str], qid: str) -> Tuple[List[str], int]:
    """Places `correct` among distractors at a deterministic position."""
    options = [correct] + list(distractors)
    n = len(options)
    pos = _seed(qid) % n
    # Move correct from index 0 to index `pos`.
    options.insert(pos, options.pop(0))
    return options, pos


# ── Curated skill items: skill → (stem, correct, [distractors], explanation, tip)
_SKILL_BANK: Dict[str, dict] = {
    "Python": {
        "stem": "Which best reflects strong, job-ready Python practice?",
        "correct": "Use clear functions, appropriate data structures, comprehensions, and tests.",
        "distractors": [
            "Keep all logic in one long script with no functions.",
            "Share state through global variables everywhere.",
            "Copy-paste code instead of reusing functions.",
        ],
        "explanation": "Idiomatic Python favors small tested functions, suitable data structures, "
                       "and comprehensions. The other options are anti-patterns that hurt readability "
                       "and maintainability.",
        "tip": "Write small, tested functions and review PEP 8 and common idioms.",
    },
    "SQL": {
        "stem": "You need to combine rows from two tables on a shared key. What is most appropriate?",
        "correct": "Use a JOIN on the shared key.",
        "distractors": [
            "Export both tables to CSV and merge them by hand.",
            "Always run two queries and merge in application memory.",
            "SELECT * without conditions and filter later in code.",
        ],
        "explanation": "A JOIN on the key is the standard, efficient relational approach. Manual "
                       "merges and unfiltered SELECT * are inefficient and error-prone.",
        "tip": "Practice INNER/LEFT JOINs and indexing on join keys.",
    },
    "PostgreSQL": {
        "stem": "A query filtering on one column is slow. What is the most effective first step?",
        "correct": "Add an appropriate index and read the query plan (EXPLAIN ANALYZE).",
        "distractors": [
            "Restart the database after each query.",
            "Remove all constraints from the table.",
            "Always SELECT * and let the planner decide.",
        ],
        "explanation": "Indexing the filtered column and reading the plan targets the real "
                       "bottleneck; the other options don't address it.",
        "tip": "Practice EXPLAIN ANALYZE and B-tree indexing.",
    },
    "Docker": {
        "stem": "What is the primary purpose of a Docker container?",
        "correct": "Package an app with its dependencies to run consistently across environments.",
        "distractors": [
            "Permanently store database backups.",
            "Replace version control.",
            "Compile source code into machine code.",
        ],
        "explanation": "Containers bundle an app and its dependencies for consistent, isolated "
                       "runtime. They are not backups, version control, or compilers.",
        "tip": "Write a Dockerfile for a small app and run it locally.",
    },
    "Kubernetes": {
        "stem": "What problem does Kubernetes primarily solve?",
        "correct": "Orchestrating and scaling containerized workloads across machines.",
        "distractors": [
            "Writing frontend UI components.",
            "Formatting SQL queries.",
            "Designing CSS layouts.",
        ],
        "explanation": "Kubernetes schedules, scales, and manages containers across a cluster; "
                       "the other options are unrelated concerns.",
        "tip": "Learn Pods, Deployments, and Services; try a local cluster (kind/minikube).",
    },
    "React": {
        "stem": "Which best describes idiomatic React component design?",
        "correct": "Build small, reusable components and manage state with hooks and props.",
        "distractors": [
            "Manipulate the DOM directly with getElementById everywhere.",
            "Put all logic into one giant component.",
            "Avoid components and use inline scripts.",
        ],
        "explanation": "React favors composable components with state via hooks/props and a "
                       "declarative model rather than direct DOM manipulation.",
        "tip": "Build a small app using useState/useEffect and component composition.",
    },
    "JavaScript": {
        "stem": "Which is a sound modern JavaScript practice?",
        "correct": "Use const/let, clear async/await flows, and handle errors.",
        "distractors": [
            "Use var for everything and rely on global state.",
            "Block the event loop with long synchronous loops.",
            "Ignore error handling in promises.",
        ],
        "explanation": "Modern JS favors const/let, explicit async handling, and error handling; "
                       "the other options cause bugs and poor performance.",
        "tip": "Practice promises, async/await, and map/filter/reduce.",
    },
    "AWS": {
        "stem": "Which best reflects cloud (AWS) fundamentals?",
        "correct": "Use managed services and least-privilege IAM, with logging enabled.",
        "distractors": [
            "Hardcode root credentials in application code.",
            "Run everything on one server with no backups.",
            "Disable all logging to save money.",
        ],
        "explanation": "Cloud best practice uses managed services, least-privilege IAM, and "
                       "observability. Hardcoding root keys or disabling logging are serious risks.",
        "tip": "Learn IAM roles, S3, and one compute service (EC2 or Lambda).",
    },
    "Git": {
        "stem": "What is a healthy Git workflow practice?",
        "correct": "Commit small, logical changes with clear messages and use feature branches.",
        "distractors": [
            "Commit once at the very end with the message 'final'.",
            "Routinely force-push over teammates' work.",
            "Store secrets directly in the repository.",
        ],
        "explanation": "Small, well-described commits and feature branches keep history reviewable; "
                       "the other options cause conflicts and security issues.",
        "tip": "Practice branching and writing clear commit messages.",
    },
    "REST API": {
        "stem": "Which best reflects good REST API design?",
        "correct": "Use resource-oriented URLs with proper HTTP verbs and status codes.",
        "distractors": [
            "Use GET requests to modify data.",
            "Return 200 for every response, including errors.",
            "Put verbs like /createUserNow in every path.",
        ],
        "explanation": "REST uses resource URLs, correct verbs (GET/POST/PUT/DELETE), and meaningful "
                       "status codes; mutating via GET or always-200 is incorrect.",
        "tip": "Design a small CRUD API and map verbs and status codes correctly.",
    },
    "Linux": {
        "stem": "Which command-line practice is sound for a developer on Linux?",
        "correct": "Use the shell and pipes, apply least-privilege permissions, and script repetitive tasks.",
        "distractors": [
            "Run everything as root by default.",
            "Avoid the terminal entirely.",
            "Disable file permissions for convenience.",
        ],
        "explanation": "Comfort with the shell, pipes, and least-privilege permissions is core; "
                       "running as root or disabling permissions is risky.",
        "tip": "Practice grep/awk/pipes and file-permission basics.",
    },
}


# ── Dimension items: dimension key → item ──────────────────────────────────
_DIMENSION_BANK: Dict[str, dict] = {
    "technical_skills_match": {
        "stem": "In an interview, the strongest way to prove a technical skill is to...",
        "correct": "Describe a concrete project, your specific decisions, and the measurable outcome.",
        "distractors": [
            "Say you 'know it' without any example.",
            "List buzzwords without context.",
            "Avoid the question.",
        ],
        "explanation": "Concrete, owned examples with outcomes are convincing; vague claims are not.",
        "tip": "Prepare two project stories with specifics and results.",
    },
    "experience_depth_alignment": {
        "stem": "To show depth of experience, you should...",
        "correct": "Walk through a complex project you owned end to end, with specifics.",
        "distractors": [
            "List job titles without detail.",
            "Mention only how long you've worked.",
            "Describe tasks someone else did.",
        ],
        "explanation": "Ownership and specifics demonstrate real depth, not tenure alone.",
        "tip": "Pick your most complex project and rehearse the details and trade-offs.",
    },
    "educational_relevance": {
        "stem": "To connect your education to a role, you should...",
        "correct": "Tie specific coursework or projects to the role's actual tasks.",
        "distractors": [
            "Only state your degree title.",
            "Claim education is irrelevant.",
            "List unrelated achievements.",
        ],
        "explanation": "Relevance comes from linking concrete learning to the job's needs.",
        "tip": "Map two courses/projects to responsibilities in the JD.",
    },
    "domain_knowledge": {
        "stem": "To demonstrate domain knowledge, you should...",
        "correct": "Reference concrete domain problems and how you addressed them.",
        "distractors": [
            "Use generic statements anyone could make.",
            "Avoid domain specifics entirely.",
            "Rely only on job titles.",
        ],
        "explanation": "Specific domain problems and solutions show genuine understanding.",
        "tip": "Research the role's industry and prepare one concrete domain example.",
    },
    "soft_skills_signals": {
        "stem": "Strong evidence of soft skills is...",
        "correct": "A specific story of collaboration or conflict resolution with an outcome.",
        "distractors": [
            "Saying 'I'm a great team player' with no example.",
            "Listing adjectives about yourself.",
            "Avoiding behavioral questions.",
        ],
        "explanation": "Behavioral evidence (a real story with a result) beats self-description.",
        "tip": "Prepare one STAR story about teamwork or a disagreement you resolved.",
    },
    "seniority_trajectory": {
        "stem": "To show growing responsibility, you should...",
        "correct": "Describe how your scope and ownership increased over time, with examples.",
        "distractors": [
            "Only list years of experience.",
            "Claim seniority without evidence.",
            "Describe a flat, unchanging role.",
        ],
        "explanation": "Trajectory is shown by increasing scope and ownership, not tenure alone.",
        "tip": "Outline how your responsibilities grew across roles.",
    },
    "semantic_contextual_alignment": {
        "stem": "To show you fit this specific role, you should...",
        "correct": "Connect your concrete experience directly to the role's needs.",
        "distractors": [
            "Give a generic answer that fits any job.",
            "Focus only on unrelated strengths.",
            "Avoid referencing the role.",
        ],
        "explanation": "Fit is demonstrated by explicitly tying your experience to the role.",
        "tip": "Draft a two-sentence 'why I fit this role' grounded in real examples.",
    },
}

_DIMENSION_LABELS: Dict[str, str] = {
    "technical_skills_match": "Technical Skills",
    "experience_depth_alignment": "Experience Depth",
    "educational_relevance": "Education",
    "domain_knowledge": "Domain Knowledge",
    "soft_skills_signals": "Soft Skills",
    "seniority_trajectory": "Seniority Fit",
    "semantic_contextual_alignment": "Contextual Alignment",
}


def has_curated_skill(skill: str) -> bool:
    return skill in _SKILL_BANK


def make_skill_mcq(skill: str, focus: Focus, qid: str) -> QuizQuestion:
    """Knowledge MCQ for a skill (curated if available, else generic template)."""
    item = _SKILL_BANK.get(skill)
    if item is None:
        return _generic_skill_mcq(skill, focus, qid)
    options, correct_index = _place(item["correct"], item["distractors"], qid)
    return QuizQuestion(
        qid=qid, stem=item["stem"], options=options, correct_index=correct_index,
        explanation=item["explanation"], study_tip=item["tip"],
        focus=focus, target=skill, qtype=QuestionType.MULTIPLE_CHOICE,
    )


def _generic_skill_mcq(skill: str, focus: Focus, qid: str) -> QuizQuestion:
    correct = (f"Showing a concrete project where you applied {skill}, with clear decisions "
               f"and measurable results.")
    distractors = [
        f"Mentioning {skill} once on your CV without any example.",
        f"Listing {skill} among many buzzwords without context.",
        f"Claiming expertise in {skill} but being unable to explain your choices.",
    ]
    options, correct_index = _place(correct, distractors, qid)
    return QuizQuestion(
        qid=qid, stem=f"Which best demonstrates strong, job-ready use of {skill}?",
        options=options, correct_index=correct_index,
        explanation=(f"Employers trust evidence: a concrete project using {skill}, your specific "
                     f"role and decisions, and a measurable outcome — not buzzwords or unexplained claims."),
        study_tip=(f"Build or document one small project that uses {skill}, and prepare to explain "
                   f"your decisions and results."),
        focus=focus, target=skill, qtype=QuestionType.MULTIPLE_CHOICE,
    )


def make_missing_skill_scenario(skill: str, qid: str) -> QuizQuestion:
    """Best-approach scenario MCQ for a skill the candidate lacks."""
    correct = ("Acknowledge your current level honestly and explain how you'd ramp up, citing "
               "related experience.")
    distractors = [
        "Pretend you're an expert and hope they don't probe.",
        "Refuse to answer the question.",
        "Change the subject to an unrelated skill.",
    ]
    options, correct_index = _place(correct, distractors, qid)
    return QuizQuestion(
        qid=qid,
        stem=f"You're asked about {skill}, which isn't on your CV. What is the best approach?",
        options=options, correct_index=correct_index,
        explanation=("Honesty plus a credible ramp-up plan and transferable reasoning builds trust. "
                     "Bluffing or deflecting is easily detected and erodes credibility."),
        study_tip=(f"Prepare a short, honest plan for learning {skill} and identify transferable "
                   f"skills you already have."),
        focus=Focus.MISSING_SKILL, target=skill, qtype=QuestionType.SCENARIO,
    )


def make_dimension_mcq(dim_key: str, qid: str) -> QuizQuestion:
    item = _DIMENSION_BANK.get(dim_key, _DIMENSION_BANK["technical_skills_match"])
    label = _DIMENSION_LABELS.get(dim_key, dim_key)
    options, correct_index = _place(item["correct"], item["distractors"], qid)
    return QuizQuestion(
        qid=qid, stem=item["stem"], options=options, correct_index=correct_index,
        explanation=item["explanation"], study_tip=item["tip"],
        focus=Focus.WEAK_DIMENSION, target=label, qtype=QuestionType.SCENARIO,
    )
