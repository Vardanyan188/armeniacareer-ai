# src/engine/skill_depth/analyzer.py
#
# Deterministic Skill Proficiency / Requirement Depth analyzer (Phase 19).
#
# analyze_skill_depth(cv_entities, jd_entities) -> SkillDepthAnalysis
#
# Explanatory layer ONLY: it reads already-masked, structured entity fields
# (never raw CV/JD text), never touches scoring/ranking/quiz/interview, and
# emits a neutral, PII-free object of per-skill depth comparisons.
#
# Privacy: candidate evidence is reduced to CURATED LABELS (e.g. "pandas",
# "docker") taken from the rule tables — never the originating sentence.

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from src.engine.skill_depth.models import (
    DepthMatchType,
    SkillDepth,
    SkillDepthAnalysis,
    SkillDepthEntry,
)
from src.engine.skill_depth.rules import (
    DEFAULT_REQUIRED_DEPTH,
    GENERIC_CLAIM_CAP,
    GENERIC_CLAIM_TOKENS,
    JD_DEPTH_PHRASES,
    MAX_EVIDENCE_LABELS,
    SKILL_DEPTH_RULES,
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _canon(name: Any) -> str:
    return str(name or "").strip()


def _present(corpus: str, token: str) -> bool:
    return token.lower() in corpus


def _present_tokens(corpus: str, tokens: Tuple[str, ...]) -> List[str]:
    return [t for t in tokens if _present(corpus, t)]


def _dedupe(labels: List[str]) -> List[str]:
    seen: set = set()
    out: List[str] = []
    for lbl in labels:
        key = lbl.lower()
        if key not in seen:
            seen.add(key)
            out.append(lbl)
    return out


# ---------------------------------------------------------------------------
# Candidate evidence corpus (structured, already-masked fields only)
# ---------------------------------------------------------------------------

def _build_candidate_corpus(cv_entities: Any) -> Tuple[str, set, dict, float]:
    """
    Returns (corpus_text, present_skill_names, proficiency_signals, years).
    The corpus is a single lowercased string of NON-PII structured signals.
    """
    parts: List[str] = []
    present: set = set()
    prof: dict = {}

    for skill in getattr(cv_entities, "raw_skills", []) or []:
        name = _canon(getattr(skill, "canonical_name", None) or getattr(skill, "raw_name", None))
        if name:
            present.add(name.lower())
            parts.append(name)
        sig = getattr(skill, "proficiency_signal", None)
        if sig:
            prof[name.lower()] = str(sig)
            parts.append(str(sig))

    for exp in getattr(cv_entities, "work_history", []) or []:
        parts.extend(getattr(exp, "technologies_mentioned", []) or [])
        parts.extend(getattr(exp, "responsibilities", []) or [])

    parts.extend(getattr(cv_entities, "career_domain_signals", []) or [])

    corpus = " ".join(str(p) for p in parts).lower()
    try:
        years = float(getattr(cv_entities, "total_years_experience", 0.0) or 0.0)
    except (TypeError, ValueError):
        years = 0.0
    return corpus, present, prof, years


# ---------------------------------------------------------------------------
# Candidate depth detection
# ---------------------------------------------------------------------------

def _detect_candidate_depth(
    skill: str, corpus: str, prof_signal: Optional[str], years: float,
) -> Tuple[SkillDepth, List[str], bool]:
    """
    Returns (candidate_depth, evidence_labels, has_ecosystem_evidence).

    Only per-skill curated tokens can reach ADVANCED+. Generic proficiency
    claims are clamped to APPLIED (anti-overconfidence). proficiency_signal /
    years can lift MENTIONED → BASIC only.
    """
    key = skill.lower()
    best = SkillDepth.MENTIONED
    labels: List[str] = []
    ecosystem = False

    # 1. Per-skill curated ecosystem tokens (authoritative; any tier).
    skill_rules = SKILL_DEPTH_RULES.get(key)
    if skill_rules:
        for tier, tokens in skill_rules.items():
            found = _present_tokens(corpus, tokens)
            if found:
                labels.extend(found)
                if tier > best:
                    best = tier
                ecosystem = True

    # 2. Generic proficiency claims — clamped to APPLIED.
    for tier, tokens in GENERIC_CLAIM_TOKENS.items():
        found = _present_tokens(corpus, tokens)
        if found:
            labels.extend(found)
            capped = min(tier, GENERIC_CLAIM_CAP)
            if capped > best:
                best = capped

    # 3. Anti-overconfidence lift: signal/years can only reach BASIC.
    if best == SkillDepth.MENTIONED:
        has_signal = bool(prof_signal and str(prof_signal).strip())
        if has_signal or years >= 1.0:
            best = SkillDepth.BASIC

    return best, _dedupe(labels)[:MAX_EVIDENCE_LABELS], ecosystem


# ---------------------------------------------------------------------------
# JD required depth detection
# ---------------------------------------------------------------------------

def _jd_lines(jd_entities: Any) -> List[str]:
    lines: List[str] = []
    lines.extend(getattr(jd_entities, "responsibilities", []) or [])
    lines.extend(getattr(jd_entities, "required_qualifications", []) or [])
    return [str(ln).lower() for ln in lines]


def _detect_required_depth(skill: str, jd_lines: List[str]) -> SkillDepth:
    """
    Required depth from JD phrasing. Scans only the JD lines that mention the
    skill; if a skill-specific intent phrase is found, that tier wins (highest
    first). Otherwise the conservative default (APPLIED) applies.
    """
    key = skill.lower()
    mentioning = [ln for ln in jd_lines if key in ln]
    if not mentioning:
        return DEFAULT_REQUIRED_DEPTH

    blob = " ".join(mentioning)
    for tier, phrases in JD_DEPTH_PHRASES:  # highest tier first
        if any(p in blob for p in phrases):
            return tier
    return DEFAULT_REQUIRED_DEPTH


# ---------------------------------------------------------------------------
# Explanation / recommendation / verification templates (neutral, label-based)
# ---------------------------------------------------------------------------

def _tier_examples(skill: str, tier: SkillDepth) -> str:
    tokens = SKILL_DEPTH_RULES.get(skill.lower(), {}).get(tier, ())
    return ", ".join(tokens[:3]) if tokens else ""


def _build_entry(
    skill: str, required: SkillDepth, candidate: Optional[SkillDepth],
    evidence: List[str],
) -> SkillDepthEntry:
    if candidate is None:
        match = DepthMatchType.MISSING_SKILL
        gap = int(required)
        explanation = f"{skill} is required at {required.label} depth but was not found in the CV."
        recommendation = f"Consider building {skill} fundamentals relevant to this role."
        verify = f"Confirm whether {skill} can be ramped up, or if it is a hard requirement."
    elif candidate == SkillDepth.MENTIONED:
        match = DepthMatchType.MENTIONED_ONLY
        gap = max(0, int(required) - int(candidate))
        explanation = (
            f"{skill} is named but the CV shows no evidence of use; "
            f"required depth is {required.label}."
        )
        recommendation = f"Add concrete {skill} examples (projects, tools, outcomes) to show real use."
        verify = f"Probe whether {skill} was actually used — ask for a concrete {skill} example."
    elif int(candidate) >= int(required):
        match = DepthMatchType.FULL_DEPTH_MATCH
        gap = 0
        explanation = (
            f"Evidence suggests {candidate.label} depth, which meets the "
            f"required {required.label} depth."
        )
        recommendation = f"Strong on {skill} — keep it current and cite recent examples."
        verify = f"Optionally confirm depth with one applied {skill} question."
    else:
        match = DepthMatchType.PARTIAL_DEPTH_MATCH
        gap = int(required) - int(candidate)
        examples = _tier_examples(skill, required)
        ex_hint = f" (e.g. {examples})" if examples else ""
        explanation = (
            f"Evidence suggests {candidate.label} depth, below the required "
            f"{required.label} depth."
        )
        recommendation = f"Deepen {skill} toward {required.label}{ex_hint}."
        verify = f"Ask the candidate to walk through a {skill} task at the {required.label} level{ex_hint}."

    return SkillDepthEntry(
        skill=skill,
        required_depth=required,
        candidate_depth=candidate,
        match_type=match,
        depth_gap=gap,
        evidence_labels=evidence,
        gap_explanation=explanation,
        recommendation=recommendation,
        verification_prompt=verify,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_skill_depth(cv_entities: Any, jd_entities: Any) -> SkillDepthAnalysis:
    """
    Deterministically compares candidate skill-evidence depth against JD required
    depth for each required JD skill. Pure, side-effect-free, PII-free.
    """
    corpus, present, prof, years = _build_candidate_corpus(cv_entities)
    jd_lines = _jd_lines(jd_entities)

    entries: List[SkillDepthEntry] = []
    seen: set = set()

    for req_skill in getattr(jd_entities, "required_skills", []) or []:
        skill = _canon(getattr(req_skill, "canonical_name", None) or getattr(req_skill, "raw_name", None))
        if not skill or skill.lower() in seen:
            continue
        seen.add(skill.lower())

        required = _detect_required_depth(skill, jd_lines)
        is_present = skill.lower() in present or _present(corpus, skill.lower())

        if not is_present:
            entries.append(_build_entry(skill, required, None, []))
            continue

        candidate, evidence, _ecosystem = _detect_candidate_depth(
            skill, corpus, prof.get(skill.lower()), years,
        )
        entries.append(_build_entry(skill, required, candidate, evidence))

    analysis = SkillDepthAnalysis(entries=entries)
    analysis.full_count = sum(1 for e in entries if e.match_type == DepthMatchType.FULL_DEPTH_MATCH)
    analysis.partial_count = sum(1 for e in entries if e.match_type == DepthMatchType.PARTIAL_DEPTH_MATCH)
    analysis.mentioned_count = sum(1 for e in entries if e.match_type == DepthMatchType.MENTIONED_ONLY)
    analysis.missing_count = sum(1 for e in entries if e.match_type == DepthMatchType.MISSING_SKILL)
    return analysis
