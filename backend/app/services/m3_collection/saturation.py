"""Saturation evaluation for M3 cell collection.

Pure functions, no DB access. Determines whether a (cell x competitor) pair
has collected enough independent, fresh evidence to be considered saturated,
per spec section 6.1.
"""
from dataclasses import dataclass


@dataclass
class SaturationInputs:
    independent_source_count: int
    target_sources: int
    has_fresh_asset: bool
    consecutive_zero_net_new: int
    coverage_confidence: float


def is_saturated(inp: SaturationInputs) -> bool:
    """Return True when all four saturation conditions hold (spec section 6.1)."""
    return (
        inp.independent_source_count >= inp.target_sources
        and inp.has_fresh_asset is True
        and inp.consecutive_zero_net_new >= 2
        and inp.coverage_confidence >= 0.75
    )


def target_for_tier(tier: str | None) -> int:
    """Return the independent-source target for a tier.

    "A" -> 3, "B" -> 2, "C" -> 999 (C never truly saturates),
    None or any other value -> 3.
    """
    if tier == "A":
        return 3
    if tier == "B":
        return 2
    if tier == "C":
        return 999
    return 3


def next_state_after_probe(inp: SaturationInputs, tier: str | None) -> str:
    """Return the next state string after a probe cycle."""
    return "SATURATED" if is_saturated(inp) else "PARTIAL"
