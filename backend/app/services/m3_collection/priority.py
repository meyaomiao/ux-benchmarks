"""
Priority scoring for the probe queue.

NOTE (theory grounding): this scoring formula is an ENGINEERING heuristic, not a
theory-backed model. Do not dress it up. The only theory-anchored piece in the
queue is the STOP condition (see saturation.py — thematic saturation, a
methodological stance), NOT this ordering formula.
"""
from dataclasses import dataclass

# Weights (spec section 6.1). Kept as module-level constants so they are
# tunable and inspectable. Positive weights sum to 0.85, negative to 0.15.
W_STRATEGIC_WEIGHT = 0.30
W_COVERAGE_GAP_RATIO = 0.25
W_FRESHNESS_DECAY = 0.20
W_TIER_ACCESSIBILITY = 0.10
W_RECENT_PROBE_PENALTY = 0.10
W_EXPECTED_COST = 0.05


@dataclass
class PriorityInputs:
    strategic_weight: float  # 0-1
    coverage_gap_ratio: float  # 0-1
    freshness_decay: float  # 0-1
    tier_accessibility: float  # 0-1
    recent_probe_penalty: float  # 0-1
    expected_cost: float  # 0-1


def clamp01(x: float) -> float:
    """Clamp a float into the inclusive [0.0, 1.0] range."""
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def priority_score(inp: PriorityInputs) -> float:
    """Compute the probe-queue priority score (spec section 6.1).

    Higher score => higher priority. The four positive terms reward strategic
    value, coverage gaps, staleness, and tier accessibility; the two negative
    terms penalise recently-probed cells and expensive probes.
    """
    return (
        W_STRATEGIC_WEIGHT * inp.strategic_weight
        + W_COVERAGE_GAP_RATIO * inp.coverage_gap_ratio
        + W_FRESHNESS_DECAY * inp.freshness_decay
        + W_TIER_ACCESSIBILITY * inp.tier_accessibility
        - W_RECENT_PROBE_PENALTY * inp.recent_probe_penalty
        - W_EXPECTED_COST * inp.expected_cost
    )
