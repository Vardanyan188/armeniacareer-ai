# src/engine/interview/recruiter_verification.py
#
# Deterministic Recruiter Verification Interview guide (no LLM, no network).
#
# Reads ONLY recruiter-facing data (the dict from access_control.get_recruiter_view),
# which excludes the candidate coaching roadmap and motivational framing — so
# those can never enter the guide by construction. This phase produces a
# structured guide only; there is no live recruiter answer evaluation.

from __future__ import annotations

from typing import Any, Dict, List

from src.engine.interview.models import RecruiterVerificationGuide, VerificationQuestion

_MAX_MISSING = 3
_MAX_MATCHED = 3
_MAX_TOTAL = 8

_IMPORTANCE_RANK = {"must_ask": 0, "recommended": 1, "optional": 2}


def _names(entries: List[Any]) -> List[str]:
    out: List[str] = []
    for e in entries or []:
        name = getattr(e, "canonical_name", None) or getattr(e, "skill_name", None)
        if name and name not in out:
            out.append(name)
    return out


def _from_verification_point(vp: Any) -> VerificationQuestion:
    topic = getattr(vp, "topic", "") or "the claim"
    why = getattr(vp, "why_it_matters", "") or "role relevance"
    gap = getattr(vp, "evidence_gap_description", "") or "the evidence gap"
    importance = getattr(vp, "importance_level", "recommended")
    return VerificationQuestion(
        question=getattr(vp, "suggested_interview_question", f"Verify the candidate's {topic}."),
        strong_answer_contains=[
            f"specific, first-hand detail that addresses: {why}",
            "a concrete example with the candidate's own role and decisions",
            "a measurable outcome (numbers, impact, scale)",
        ],
        weak_answer_indicates=[
            f"{gap} remains unaddressed",
            "a generic, second-hand, or theoretical answer",
            "inability to explain why decisions were made",
        ],
        suggested_followups=[
            "Can you give one specific example with concrete numbers?",
            "What was your exact contribution versus the team's?",
        ],
        importance=importance,
        target=topic,
    )


def _matched_skill_question(skill: str) -> VerificationQuestion:
    return VerificationQuestion(
        question=(f"Ask the candidate to describe a specific project where they used {skill}, "
                  f"including their role and the key decisions they made."),
        strong_answer_contains=[
            f"a concrete project that genuinely used {skill}",
            "specific trade-offs/decisions and the candidate's personal role",
            "measurable outcomes (numbers, performance, impact)",
        ],
        weak_answer_indicates=[
            "vague or generic description with no specifics",
            "no measurable outcome or unclear personal contribution",
            f"cannot explain {skill} choices → possible overstated claim",
        ],
        suggested_followups=[
            f"What problems did you hit with {skill}, and how did you resolve them?",
            f"What would you do differently in that {skill} work today?",
        ],
        importance="recommended",
        target=skill,
    )


def _missing_skill_question(skill: str) -> VerificationQuestion:
    return VerificationQuestion(
        question=(f"{skill} is required but not evident in the CV. Probe whether the candidate "
                  f"can already do it or could ramp up quickly."),
        strong_answer_contains=[
            f"prior exposure to {skill} or a close equivalent",
            "a clear, realistic plan to get productive",
            "transferable reasoning from related work",
        ],
        weak_answer_indicates=[
            f"no awareness of {skill} and no related experience",
            "overconfidence asserted without any evidence",
            "no credible plan to close the gap",
        ],
        suggested_followups=[
            f"Have you used anything functionally similar to {skill}?",
            f"How would you approach learning {skill} on the job?",
        ],
        importance="must_ask",
        target=skill,
    )


def build_recruiter_verification_guide(recruiter_view: Dict[str, Any]) -> RecruiterVerificationGuide:
    """Builds an evidence-based verification guide from recruiter-facing data only."""
    jd = recruiter_view.get("jd_entities")
    role_title = getattr(jd, "role_title", "this role") if jd else "this role"
    seniority = str(getattr(getattr(jd, "required_seniority", "mid"), "value",
                            getattr(jd, "required_seniority", "mid"))).lower() if jd else "mid"

    questions: List[VerificationQuestion] = []

    rp = recruiter_view.get("recruiter_perspective")
    vps = list(getattr(rp, "verification_points", []) or []) if rp else []
    vps.sort(key=lambda vp: _IMPORTANCE_RANK.get(getattr(vp, "importance_level", "recommended"), 1))
    questions += [_from_verification_point(vp) for vp in vps]

    skills = recruiter_view.get("skills_ontology")
    if skills is not None:
        for skill in _names(getattr(skills, "missing_critical", []))[:_MAX_MISSING]:
            questions.append(_missing_skill_question(skill))
        for skill in _names(getattr(skills, "matched_skills", []))[:_MAX_MATCHED]:
            questions.append(_matched_skill_question(skill))

    # De-duplicate by target while preserving order, then cap.
    seen = set()
    deduped: List[VerificationQuestion] = []
    for q in questions:
        key = (q.target.lower(), q.question[:40])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(q)

    deduped.sort(key=lambda q: _IMPORTANCE_RANK.get(q.importance, 1))
    return RecruiterVerificationGuide(
        role_title=role_title,
        seniority=seniority,
        questions=deduped[:_MAX_TOTAL],
    )
