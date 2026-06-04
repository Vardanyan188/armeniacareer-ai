# src/engine/skill_depth/__init__.py
#
# Deterministic Skill Proficiency / Requirement Depth layer (Phase 19).
# Explanatory only — never feeds scoring/ranking/quiz/interview.

from src.engine.skill_depth.analyzer import analyze_skill_depth
from src.engine.skill_depth.models import (
    DepthMatchType,
    SkillDepth,
    SkillDepthAnalysis,
    SkillDepthEntry,
    depth_label,
)

__all__ = [
    "analyze_skill_depth",
    "SkillDepth",
    "DepthMatchType",
    "SkillDepthEntry",
    "SkillDepthAnalysis",
    "depth_label",
]
