# src/engine/skill_depth/models.py
#
# Plain-dataclass models for the deterministic Skill Proficiency / Requirement
# Depth layer (Phase 19). These are intentionally SEPARATE from the pydantic
# canonical payload — the payload schema is never modified by this feature.
#
# Everything here is neutral and PII-free: skill names, depth levels, curated
# evidence labels, and templated explanations only. No raw CV/JD text.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import List, Optional


class SkillDepth(IntEnum):
    """
    Ordered proficiency ladder. Numeric so depths compare directly
    (candidate_depth >= required_depth → full match).
    """
    MENTIONED = 0    # name appears, no evidence of use
    BASIC = 1        # foundational / learning
    APPLIED = 2      # used on real tasks/data
    ADVANCED = 3     # builds non-trivial artifacts (models/services/designs)
    PRODUCTION = 4   # ships production-grade, optimized work
    DEPLOYMENT = 5   # operates/deploys/monitors in production (MLOps/CI-CD/SRE)

    @property
    def label(self) -> str:
        return _DEPTH_LABELS[self]


_DEPTH_LABELS = {
    SkillDepth.MENTIONED: "Mentioned",
    SkillDepth.BASIC: "Basic",
    SkillDepth.APPLIED: "Applied",
    SkillDepth.ADVANCED: "Advanced",
    SkillDepth.PRODUCTION: "Production",
    SkillDepth.DEPLOYMENT: "Deployment",
}


def depth_label(depth: Optional[SkillDepth]) -> str:
    """Human label for a depth (or '—' when absent)."""
    return depth.label if isinstance(depth, SkillDepth) else "—"


class DepthMatchType(str, Enum):
    FULL_DEPTH_MATCH = "full_depth_match"
    PARTIAL_DEPTH_MATCH = "partial_depth_match"
    MENTIONED_ONLY = "mentioned_only"
    MISSING_SKILL = "missing_skill"


@dataclass
class SkillDepthEntry:
    skill: str
    required_depth: SkillDepth
    candidate_depth: Optional[SkillDepth]
    match_type: DepthMatchType
    depth_gap: int = 0
    evidence_labels: List[str] = field(default_factory=list)
    gap_explanation: str = ""
    recommendation: str = ""              # candidate-safe
    verification_prompt: str = ""         # recruiter-safe

    @property
    def candidate_depth_label(self) -> str:
        return depth_label(self.candidate_depth)

    @property
    def required_depth_label(self) -> str:
        return depth_label(self.required_depth)


@dataclass
class SkillDepthAnalysis:
    entries: List[SkillDepthEntry] = field(default_factory=list)
    full_count: int = 0
    partial_count: int = 0
    mentioned_count: int = 0
    missing_count: int = 0
    is_directional: bool = True           # heuristic, never a hiring decision

    @property
    def total(self) -> int:
        return len(self.entries)

    def summary_line(self) -> str:
        """Neutral one-line summary for the Shared Analysis surface."""
        if not self.entries:
            return "No required skills available for depth analysis."
        return (
            f"{self.full_count} of {self.total} required skills meet the needed "
            f"depth · {self.partial_count} partial · {self.mentioned_count} "
            f"name-only · {self.missing_count} missing (directional)."
        )
