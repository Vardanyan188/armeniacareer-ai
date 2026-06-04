# src/engine/scoring.py
#
# Composite scoring engine for ArmeniaCareer AI.
#
# Algorithm: Weighted Geometric Mean with Two-Tier Hard Flooring
#
#   D_composite = exp( Σ w_i * ln(D_i) )  =  Π (D_i ^ w_i)
#
# The geometric mean formulation is architecturally mandatory because it
# ensures that a near-zero score on any positively-weighted dimension drives
# the composite toward zero, regardless of performance elsewhere. This prevents
# the masking of disqualifying weaknesses — a property the arithmetic weighted
# mean does not possess.
#
# Two-Tier Floor Architecture
# ──────────────────────────────
# Tier 1 — General Floor
#   Threshold: 0.35  |  Cap: 0.50
#   Applies when ANY dimension falls below the threshold.
#   Rationale: any competency gap below 35% produces a composite that
#   misleadingly suggests a moderate candidate match.
#
# Tier 2 — Critical Dimension Floor
#   Threshold: 0.40  |  Cap: 0.44
#   Applies exclusively to `technical_skills_match` and
#   `experience_depth_alignment`.
#   Rationale: these two dimensions represent structural hiring prerequisites.
#   A candidate scoring below 40% on either is fundamentally unqualified
#   for the role. The Critical cap (0.44) is strictly lower than the General
#   cap (0.50), ensuring it always overrides when both tiers trigger.
#   The cap bypasses any arithmetic override — it is a hard ceiling that no
#   combination of strong scores in other dimensions can lift.

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dimension Weight Configuration
# Weights MUST sum to exactly 1.0. The assert below is a hard invariant.
# ---------------------------------------------------------------------------

DIMENSION_WEIGHTS: Dict[str, float] = {
    "technical_skills_match":        0.25,
    "experience_depth_alignment":    0.20,
    "semantic_contextual_alignment": 0.15,
    "domain_knowledge":              0.15,
    "educational_relevance":         0.10,
    "seniority_trajectory":          0.10,
    "soft_skills_signals":           0.05,
}

assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 1e-9, (
    f"DIMENSION_WEIGHTS must sum to exactly 1.0 "
    f"(current sum: {sum(DIMENSION_WEIGHTS.values()):.12f})"
)

# Ordered tuple used for iteration in tests and display components
ORDERED_DIMENSIONS: Tuple[str, ...] = tuple(DIMENSION_WEIGHTS.keys())

# ---------------------------------------------------------------------------
# Two-Tier Floor Constants
# ---------------------------------------------------------------------------

# Tier 1 — General Floor
GENERAL_FLOOR_THRESHOLD: float = 0.35
GENERAL_FLOOR_CAP: float       = 0.50

# Tier 2 — Critical Dimension Floor
CRITICAL_DIMENSIONS: FrozenSet[str] = frozenset({
    "technical_skills_match",
    "experience_depth_alignment",
})
CRITICAL_FLOOR_THRESHOLD: float = 0.40
CRITICAL_FLOOR_CAP: float       = 0.44  # MUST remain < GENERAL_FLOOR_CAP

assert CRITICAL_FLOOR_CAP < GENERAL_FLOOR_CAP, (
    "Architectural invariant violated: CRITICAL_FLOOR_CAP must be strictly "
    "less than GENERAL_FLOOR_CAP to ensure critical breaches produce a more "
    "conservative (lower) ceiling than general breaches."
)

# Numerical stability: clamp prevents log(0) singularity for zero-scored dimensions
LOG_ZERO_CLAMP: float = 1e-9


# ---------------------------------------------------------------------------
# Supporting Types
# ---------------------------------------------------------------------------

class FloorTierType(str, Enum):
    """Describes which floor tier(s) were evaluated and which, if any, was binding."""
    NONE                       = "none"
    GENERAL_ONLY               = "general_only"
    CRITICAL_ONLY              = "critical_only"
    CRITICAL_OVERRIDES_GENERAL = "critical_overrides_general"


@dataclass(frozen=True)
class FloorTriggerReport:
    """
    Immutable diagnostic record of the floor analysis for a single scoring run.
    Persisted in GovernanceLayer for audit purposes and displayed in the
    Recruiter Intelligence Room's Evaluation Integrity panel.
    """
    tier_applied:                  FloorTierType
    critical_dimensions_breached:  List[str]   # Dims below CRITICAL_FLOOR_THRESHOLD
    general_dimensions_breached:   List[str]   # Dims below GENERAL_FLOOR_THRESHOLD
    applied_cap:                   Optional[float]  # Cap value enforced, or None
    pre_floor_geometric_mean:      float            # Raw geometric mean before any cap
    binding_description:           str              # Human-readable explanation for UI


@dataclass(frozen=True)
class ScoringResult:
    """
    Immutable result container returned by `compute_composite_score`.

    All fields required to populate `DimensionalAnalysis` in the payload
    are present here. The `floor_report` is serialized into `GovernanceLayer`
    by the PayloadAssembler.
    """
    composite_score:                 float            # Final score in [0.0, 1.0]
    composite_percentage:            float            # Final score × 100 in [0.0, 100.0]
    geometric_mean_raw:              float            # Pre-cap geometric mean
    hard_floor_applied:              bool             # True if any cap was binding
    floor_report:                    FloorTriggerReport
    outlier_alert:                   bool             # True if any dim < GENERAL_FLOOR_THRESHOLD
    outlier_dimensions:              List[str]        # All dims below GENERAL_FLOOR_THRESHOLD
    per_dimension_log_contributions: Dict[str, float] # w_i * ln(D_i) per dimension (diagnostic)


# ---------------------------------------------------------------------------
# Internal: Floor Trigger Analysis
# ---------------------------------------------------------------------------

def _analyse_floor_triggers(
    dimension_scores: Dict[str, float],
    geometric_mean: float,
) -> FloorTriggerReport:
    """
    Evaluates both floor tiers against the current dimension scores and
    geometric mean. Determines which tier, if any, would be binding.

    This function does NOT modify the composite score — it only produces
    the diagnostic `FloorTriggerReport`. The actual cap is applied in
    `compute_composite_score`.

    The binding logic:
      1. Critical tier evaluated first. If any critical dimension is below
         CRITICAL_FLOOR_THRESHOLD AND the geometric mean exceeds CRITICAL_FLOOR_CAP,
         the critical floor is binding.
      2. General tier evaluated only if critical tier is NOT binding. If any
         dimension (including non-critical) is below GENERAL_FLOOR_THRESHOLD AND
         the geometric mean exceeds GENERAL_FLOOR_CAP, the general floor is binding.
      3. If the geometric mean is already at or below the relevant cap, the cap
         is logically triggered but non-binding (the geometric mean is already
         sufficiently penalized).
    """
    critical_breached: List[str] = [
        dim for dim in CRITICAL_DIMENSIONS
        if dimension_scores.get(dim, 1.0) < CRITICAL_FLOOR_THRESHOLD
    ]
    general_breached: List[str] = [
        dim for dim, score in dimension_scores.items()
        if score < GENERAL_FLOOR_THRESHOLD
    ]

    has_critical = bool(critical_breached)
    has_general  = bool(general_breached)

    if has_critical and geometric_mean > CRITICAL_FLOOR_CAP:
        tier = (
            FloorTierType.CRITICAL_OVERRIDES_GENERAL
            if has_general
            else FloorTierType.CRITICAL_ONLY
        )
        applied_cap = CRITICAL_FLOOR_CAP
        desc = (
            f"Critical dimension floor binding (cap={CRITICAL_FLOOR_CAP:.2f}). "
            f"Breached: {critical_breached}. "
            f"Pre-cap geometric mean {geometric_mean:.4f} exceeded critical ceiling. "
            f"This cap cannot be lifted by strong scores on other dimensions."
        )

    elif has_general and not has_critical and geometric_mean > GENERAL_FLOOR_CAP:
        tier        = FloorTierType.GENERAL_ONLY
        applied_cap = GENERAL_FLOOR_CAP
        desc = (
            f"General floor binding (cap={GENERAL_FLOOR_CAP:.2f}). "
            f"Breached general dimensions: {general_breached}. "
            f"Pre-cap geometric mean {geometric_mean:.4f} exceeded general ceiling."
        )

    elif has_critical and geometric_mean <= CRITICAL_FLOOR_CAP:
        # Geometric mean is already sufficiently penalized — cap is non-binding.
        tier        = FloorTierType.NONE
        applied_cap = None
        desc = (
            f"Critical dimension(s) {critical_breached} breached threshold, but "
            f"geometric mean {geometric_mean:.4f} is already at or below critical "
            f"cap {CRITICAL_FLOOR_CAP:.2f}. Cap is logically triggered but non-binding."
        )

    else:
        tier        = FloorTierType.NONE
        applied_cap = None
        desc = (
            f"No floor cap binding. "
            f"Geometric mean {geometric_mean:.4f} satisfies all threshold constraints."
        )

    return FloorTriggerReport(
        tier_applied                 = tier,
        critical_dimensions_breached = critical_breached,
        general_dimensions_breached  = general_breached,
        applied_cap                  = applied_cap,
        pre_floor_geometric_mean     = geometric_mean,
        binding_description          = desc,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_composite_score(
    dimension_scores: Dict[str, float],
    weights: Optional[Dict[str, float]] = None,
) -> ScoringResult:
    """
    Computes the weighted geometric mean composite score with two-tier hard flooring.

    Parameters
    ----------
    dimension_scores : dict
        Mapping of dimension name → float score in [0.0, 1.0].
        Must contain exactly the seven canonical dimension keys defined in
        DIMENSION_WEIGHTS. No extra or missing keys are tolerated.

    weights : dict, optional
        Override for dimension weights. If provided, must sum to 1.0 and
        have identical keys to DIMENSION_WEIGHTS. Defaults to DIMENSION_WEIGHTS.
        Used by the Evaluation Tab for prompt-version A/B scoring comparisons.

    Returns
    -------
    ScoringResult
        Fully populated immutable result object. All fields are required
        to populate DimensionalAnalysis in the CanonicalAnalysisPayload.

    Raises
    ------
    ValueError
        If dimension_scores contains unknown keys, scores outside [0, 1],
        or if a custom weights dict does not sum to 1.0.

    Notes on the two-tier floor:
        The geometric mean naturally penalizes low scores, but can still
        produce misleadingly moderate results when a single critical dimension
        is just below threshold while all others are high. Example:

            technical_skills_match = 0.39, all others = 0.90
            → geometric mean ≈ 0.730 (73% — would appear as a viable candidate)
            → after critical floor cap at 0.44 → 44% (correctly signals critical gap)

        This is why the floor mechanism exists independently of the geometric mean.
    """
    if weights is None:
        weights = DIMENSION_WEIGHTS

    # ── Validation ────────────────────────────────────────────────────────
    provided_keys  = set(dimension_scores.keys())
    expected_keys  = set(weights.keys())
    if provided_keys != expected_keys:
        missing = expected_keys - provided_keys
        extra   = provided_keys - expected_keys
        raise ValueError(
            f"dimension_scores key mismatch.\n"
            f"  Missing keys: {sorted(missing) or 'none'}\n"
            f"  Unexpected keys: {sorted(extra) or 'none'}"
        )

    weights_sum = sum(weights.values())
    if abs(weights_sum - 1.0) >= 1e-9:
        raise ValueError(
            f"Weights must sum to 1.0 (provided sum: {weights_sum:.12f})"
        )

    for dim, score in dimension_scores.items():
        if not (0.0 <= score <= 1.0):
            raise ValueError(
                f"Score out of range [0.0, 1.0] for dimension '{dim}': {score!r}"
            )

    # ── Weighted Geometric Mean via Log-Space ──────────────────────────────
    # log-space computation avoids numerical underflow for many small scores.
    log_contributions: Dict[str, float] = {}
    log_sum = 0.0

    for dim, score in dimension_scores.items():
        clamped     = max(score, LOG_ZERO_CLAMP)
        contribution = weights[dim] * math.log(clamped)
        log_contributions[dim] = round(contribution, 6)
        log_sum += contribution

    geometric_mean = round(
        min(max(math.exp(log_sum), 0.0), 1.0),
        4,
    )

    # ── Two-Tier Floor Analysis ────────────────────────────────────────────
    floor_report       = _analyse_floor_triggers(dimension_scores, geometric_mean)
    composite          = geometric_mean
    hard_floor_applied = False

    if floor_report.applied_cap is not None:
        capped = min(geometric_mean, floor_report.applied_cap)
        if capped < composite:
            composite          = capped
            hard_floor_applied = True

    composite            = round(min(max(composite, 0.0), 1.0), 4)
    composite_percentage = round(composite * 100, 1)

    # ── Outlier Detection (for UI radar chart highlighting) ────────────────
    outlier_dimensions: List[str] = [
        dim for dim, score in dimension_scores.items()
        if score < GENERAL_FLOOR_THRESHOLD
    ]

    if hard_floor_applied:
        logger.info(
            "Hard floor applied | tier=%s | pre_floor=%.4f | final=%.4f "
            "| cap=%.2f | breached_dims=%s",
            floor_report.tier_applied.value,
            geometric_mean,
            composite,
            floor_report.applied_cap,
            (
                floor_report.critical_dimensions_breached
                or floor_report.general_dimensions_breached
            ),
        )

    return ScoringResult(
        composite_score                 = composite,
        composite_percentage            = composite_percentage,
        geometric_mean_raw              = geometric_mean,
        hard_floor_applied              = hard_floor_applied,
        floor_report                    = floor_report,
        outlier_alert                   = bool(outlier_dimensions),
        outlier_dimensions              = outlier_dimensions,
        per_dimension_log_contributions = log_contributions,
    )


# ---------------------------------------------------------------------------
# Diagnostic Utilities
# ---------------------------------------------------------------------------

def format_scoring_report(result: ScoringResult) -> str:
    """
    Returns a human-readable multi-line scoring report string.
    Used in unit tests and the Evaluation Tab's diagnostic panel.
    """
    lines = [
        "=" * 60,
        "COMPOSITE SCORING REPORT",
        "=" * 60,
        f"  Composite Score       : {result.composite_score:.4f} ({result.composite_percentage:.1f}%)",
        f"  Geometric Mean (raw)  : {result.geometric_mean_raw:.4f}",
        f"  Hard Floor Applied    : {result.hard_floor_applied}",
        f"  Floor Tier            : {result.floor_report.tier_applied.value}",
    ]
    if result.floor_report.applied_cap is not None:
        lines.append(f"  Applied Cap           : {result.floor_report.applied_cap:.2f}")
    if result.floor_report.critical_dimensions_breached:
        lines.append(
            f"  Critical Breaches     : {result.floor_report.critical_dimensions_breached}"
        )
    if result.floor_report.general_dimensions_breached:
        lines.append(
            f"  General Breaches      : {result.floor_report.general_dimensions_breached}"
        )
    lines += [
        "",
        "  Log Contributions (w_i * ln(D_i)):",
    ]
    for dim in ORDERED_DIMENSIONS:
        lines.append(
            f"    {dim:<36s}: {result.per_dimension_log_contributions.get(dim, 0.0):+.6f}"
        )
    lines += [
        "",
        f"  Binding Description:",
        f"    {result.floor_report.binding_description}",
        "=" * 60,
    ]
    return "\n".join(lines)
