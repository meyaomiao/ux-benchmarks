"""Pure unit tests for probe-queue priority scoring (no DB)."""
import math

from app.services.m3_collection.priority import (
    W_COVERAGE_GAP_RATIO,
    W_EXPECTED_COST,
    W_FRESHNESS_DECAY,
    W_RECENT_PROBE_PENALTY,
    W_STRATEGIC_WEIGHT,
    W_TIER_ACCESSIBILITY,
    PriorityInputs,
    clamp01,
    priority_score,
)


def test_priority_score_known_inputs():
    inp = PriorityInputs(
        strategic_weight=0.8,
        coverage_gap_ratio=0.6,
        freshness_decay=0.5,
        tier_accessibility=1.0,
        recent_probe_penalty=0.2,
        expected_cost=0.4,
    )
    # 0.30*0.8 + 0.25*0.6 + 0.20*0.5 + 0.10*1.0 - 0.10*0.2 - 0.05*0.4
    # = 0.24 + 0.15 + 0.10 + 0.10 - 0.02 - 0.02 = 0.55
    expected = 0.55
    assert math.isclose(priority_score(inp), expected, rel_tol=1e-9, abs_tol=1e-9)


def test_weights_sum_sanity():
    positive = (
        W_STRATEGIC_WEIGHT
        + W_COVERAGE_GAP_RATIO
        + W_FRESHNESS_DECAY
        + W_TIER_ACCESSIBILITY
    )
    negative = W_RECENT_PROBE_PENALTY + W_EXPECTED_COST
    assert math.isclose(positive, 0.85, rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(negative, 0.15, rel_tol=1e-9, abs_tol=1e-9)


def test_clamp01():
    assert clamp01(-0.5) == 0.0
    assert clamp01(0.0) == 0.0
    assert clamp01(0.5) == 0.5
    assert clamp01(1.0) == 1.0
    assert clamp01(1.5) == 1.0


def test_high_strategic_gap_outranks_low():
    high = PriorityInputs(
        strategic_weight=0.9,
        coverage_gap_ratio=0.9,
        freshness_decay=0.5,
        tier_accessibility=0.5,
        recent_probe_penalty=0.1,
        expected_cost=0.1,
    )
    low = PriorityInputs(
        strategic_weight=0.1,
        coverage_gap_ratio=0.1,
        freshness_decay=0.5,
        tier_accessibility=0.5,
        recent_probe_penalty=0.1,
        expected_cost=0.1,
    )
    assert priority_score(high) > priority_score(low)
