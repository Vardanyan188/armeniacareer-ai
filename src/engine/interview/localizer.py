# src/engine/interview/localizer.py
#
# Phase 24.3C — additive multilingual localizer for the deterministic interview
# engine. It REGENERATES natural EN/HY/RU text from the engine's structured
# question objects (kind + target), rather than translating English strings.
#
# Pure + deterministic: no LLM, no network, no provider calls, no prompts, no
# secrets. The interview engine core is unchanged; this only wraps its output.
# An optional LLM enhancement could later wrap these functions, but the demo
# stays fully functional on this deterministic path with no API keys.

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.engine.interview import templates as T

_DEFAULT_LANG = "en"


def _lang(lang: Optional[str]) -> str:
    return lang if lang in T.LANGS else _DEFAULT_LANG


def _fmt(text: str, *, skill: str = "", target: str = "", role: str = "") -> str:
    try:
        return text.format(skill=skill, target=target, role=role)
    except Exception:  # pragma: no cover - defensive against stray braces
        return text


def _kind_value(kind: Any) -> str:
    return str(getattr(kind, "value", kind) or "general")


# ---------------------------------------------------------------------------
# Candidate
# ---------------------------------------------------------------------------

def localize_candidate_question(question: Any, lang: Optional[str]) -> str:
    """Natural localized text for a candidate InterviewQuestion (kind + target)."""
    lang = _lang(lang)
    kind = _kind_value(getattr(question, "kind", "general"))
    target = str(getattr(question, "target", "") or "")

    if kind == "weak_dimension":
        block = T.WEAK_DIMENSION.get(target)
        if block:
            return block.get(lang) or block.get(_DEFAULT_LANG)
        return T.get_generic_dimension(lang)

    block = T.CANDIDATE_QUESTIONS.get(kind, T.CANDIDATE_QUESTIONS["general"])
    text = block.get(lang) or block.get(_DEFAULT_LANG)
    out = _fmt(text, skill=target, target=target)
    # Last-resort safety: never return empty.
    return out or str(getattr(question, "text", "") or "")


def localize_followup(text: str, target: str, lang: Optional[str]) -> str:
    """
    Localizes a candidate follow-up. The engine emits a small, fixed set of
    follow-up strings; we map them by prefix to a localized template. Unknown
    text is returned unchanged (never empty).
    """
    lang = _lang(lang)
    if not text:
        return text
    low = text.lower()
    if low.startswith("can you give a concrete example"):
        reason = "specificity"
    elif low.startswith("let's focus specifically"):
        reason = "relevance"
    elif low.startswith("re-tell that using star"):
        reason = "structure"
    else:
        return text
    block = T.FOLLOWUPS[reason]
    return _fmt(block.get(lang) or block.get(_DEFAULT_LANG), target=target)


def localize_band(band: str, lang: Optional[str]) -> str:
    lang = _lang(lang)
    block = T.BANDS.get(str(band).lower())
    if not block:
        return str(band).title()
    return block.get(lang) or block.get(_DEFAULT_LANG)


# ---------------------------------------------------------------------------
# Recruiter verification
# ---------------------------------------------------------------------------

def _verification_category(importance: str) -> str:
    # must_ask items are typically gap probes; the rest are skill verifications.
    return "probe_gap" if str(importance).lower() == "must_ask" else "verify"


def localize_verification(vq: Any, lang: Optional[str]) -> Dict[str, Any]:
    """
    Returns a localized recruiter verification entry regenerated from the target
    skill/topic + importance — fully localized question, strong/weak indicators,
    and follow-ups.
    """
    lang = _lang(lang)
    target = str(getattr(vq, "target", "") or "the claim")
    importance = str(getattr(vq, "importance", "recommended"))
    category = _verification_category(importance)
    block = T.VERIFICATION[category]

    def _line(field: str) -> str:
        section = block[field]
        return _fmt(section.get(lang) or section.get(_DEFAULT_LANG), skill=target)

    def _lines(field: str) -> List[str]:
        section = block[field]
        items = section.get(lang) or section.get(_DEFAULT_LANG)
        return [_fmt(item, skill=target) for item in items]

    return {
        "question": _line("question"),
        "strong": _lines("strong"),
        "weak": _lines("weak"),
        "followups": _lines("followups"),
        "importance": importance,
        "target": target,
    }
