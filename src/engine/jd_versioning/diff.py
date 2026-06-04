# src/engine/jd_versioning/diff.py
#
# Deterministic JD version diff (Phase 20). Explanatory only — never touches
# scoring, ranking, or the payload. Pure set/ordering logic over two JDVersion
# snapshots; no LLM, no network.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.engine.jd_versioning.models import JDVersion
from src.engine.skill_depth.models import SkillDepth  # read-only import

# Seniority ordering (low → high). Mirrors SeniorityLevel without importing the
# pydantic enum's value-coercion behavior.
_SENIORITY_ORDER = ["intern", "junior", "mid", "senior", "lead", "principal", "executive"]

# Required-depth tiers at/above which a role is considered "deployment-heavy".
_HEAVY_DEPTH = SkillDepth.PRODUCTION


def _seniority_rank(value: str) -> int:
    try:
        return _SENIORITY_ORDER.index(str(value).strip().lower())
    except ValueError:
        return -1


def _depth_order(label: Optional[str]) -> int:
    if not label:
        return -1
    try:
        return int(SkillDepth[str(label).strip().upper()])
    except KeyError:
        return -1


@dataclass
class DepthChange:
    skill: str
    old_depth: Optional[str]
    new_depth: Optional[str]


@dataclass
class JDVersionDiff:
    jd_id: str
    old_version_number: int
    new_version_number: int

    added_required_skills: List[str] = field(default_factory=list)
    removed_required_skills: List[str] = field(default_factory=list)
    added_preferred_skills: List[str] = field(default_factory=list)
    removed_preferred_skills: List[str] = field(default_factory=list)

    seniority_changed: bool = False
    old_seniority: str = ""
    new_seniority: str = ""

    role_title_changed: bool = False
    old_role_title: str = ""
    new_role_title: str = ""

    responsibilities_added: List[str] = field(default_factory=list)
    responsibilities_removed: List[str] = field(default_factory=list)

    required_experience_changed: bool = False
    old_required_experience_years: float = 0.0
    new_required_experience_years: float = 0.0

    required_depth_changed: List[DepthChange] = field(default_factory=list)
    newly_required_depth_gaps: List[str] = field(default_factory=list)

    became_more_senior: bool = False
    became_more_deployment_heavy: bool = False

    summary: str = ""


def _added_removed(old: List[str], new: List[str]) -> tuple:
    old_set = {s.lower(): s for s in old}
    new_set = {s.lower(): s for s in new}
    added = sorted(new_set[k] for k in new_set.keys() - old_set.keys())
    removed = sorted(old_set[k] for k in old_set.keys() - new_set.keys())
    return added, removed


def diff_versions(old: JDVersion, new: JDVersion) -> JDVersionDiff:
    """Deterministically compares two JDVersion snapshots (old → new)."""
    oe, ne = old.entities, new.entities

    added_req, removed_req = _added_removed(oe.required_skills, ne.required_skills)
    added_pref, removed_pref = _added_removed(oe.preferred_skills, ne.preferred_skills)

    resp_added, resp_removed = _added_removed(oe.responsibilities, ne.responsibilities)

    seniority_changed = oe.required_seniority != ne.required_seniority
    became_more_senior = _seniority_rank(ne.required_seniority) > _seniority_rank(oe.required_seniority)

    role_changed = oe.role_title != ne.role_title
    exp_changed = abs(oe.required_experience_years - ne.required_experience_years) > 1e-9

    # Required-depth comparison over the union of skills in either depth map.
    depth_changes: List[DepthChange] = []
    newly_gaps: List[str] = []
    heavy_old = heavy_new = 0
    for skill in old.required_depth:
        if _depth_order(old.required_depth[skill]) >= int(_HEAVY_DEPTH):
            heavy_old += 1
    for skill in new.required_depth:
        if _depth_order(new.required_depth[skill]) >= int(_HEAVY_DEPTH):
            heavy_new += 1

    all_skills = sorted(set(old.required_depth) | set(new.required_depth), key=str.lower)
    for skill in all_skills:
        old_d = old.required_depth.get(skill)
        new_d = new.required_depth.get(skill)
        if old_d == new_d:
            continue
        depth_changes.append(DepthChange(skill=skill, old_depth=old_d, new_depth=new_d))
        old_o, new_o = _depth_order(old_d), _depth_order(new_d)
        # Increased depth on a shared skill, or a newly-required skill at a heavy tier.
        if (old_d is not None and new_o > old_o) or (old_d is None and new_o >= int(_HEAVY_DEPTH)):
            newly_gaps.append(skill)

    became_more_deployment_heavy = heavy_new > heavy_old or bool(newly_gaps)

    diff = JDVersionDiff(
        jd_id=new.jd_id,
        old_version_number=old.version_number,
        new_version_number=new.version_number,
        added_required_skills=added_req,
        removed_required_skills=removed_req,
        added_preferred_skills=added_pref,
        removed_preferred_skills=removed_pref,
        seniority_changed=seniority_changed,
        old_seniority=oe.required_seniority,
        new_seniority=ne.required_seniority,
        role_title_changed=role_changed,
        old_role_title=oe.role_title,
        new_role_title=ne.role_title,
        responsibilities_added=resp_added,
        responsibilities_removed=resp_removed,
        required_experience_changed=exp_changed,
        old_required_experience_years=oe.required_experience_years,
        new_required_experience_years=ne.required_experience_years,
        required_depth_changed=depth_changes,
        newly_required_depth_gaps=sorted(set(newly_gaps), key=str.lower),
        became_more_senior=became_more_senior,
        became_more_deployment_heavy=became_more_deployment_heavy,
    )
    diff.summary = _summarize(diff)
    return diff


def _summarize(d: JDVersionDiff) -> str:
    parts: List[str] = []
    if d.added_required_skills:
        parts.append(f"+{len(d.added_required_skills)} required skill(s)")
    if d.removed_required_skills:
        parts.append(f"-{len(d.removed_required_skills)} required skill(s)")
    if d.seniority_changed:
        parts.append(f"seniority {d.old_seniority}→{d.new_seniority}")
    if d.required_experience_changed:
        parts.append(
            f"experience {d.old_required_experience_years:g}→{d.new_required_experience_years:g}y"
        )
    if d.newly_required_depth_gaps:
        parts.append(f"{len(d.newly_required_depth_gaps)} deeper requirement(s)")
    if not parts:
        return "No material requirement changes detected (directional)."
    flags = []
    if d.became_more_senior:
        flags.append("more senior")
    if d.became_more_deployment_heavy:
        flags.append("more deployment-heavy")
    flag_txt = f" — role became {', '.join(flags)}" if flags else ""
    return "Changes: " + "; ".join(parts) + flag_txt + " (directional, decision-support only)."
