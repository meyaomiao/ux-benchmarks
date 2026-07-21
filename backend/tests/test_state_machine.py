"""Pure-logic tests for the M3 collection state machine and saturation rules.

These run without a database.
"""
import pytest

from app.core.errors import AppError
from app.services.m3_collection.saturation import (
    SaturationInputs,
    is_saturated,
    next_state_after_probe,
    target_for_tier,
)
from app.services.m3_collection.state_machine import (
    ALLOWED_TRANSITIONS,
    CellState,
    assert_transition,
    can_transition,
)


# --- transitions ---------------------------------------------------------

@pytest.mark.parametrize(
    "frm,to",
    [
        (CellState.UNPROBED, CellState.QUEUED),
        (CellState.QUEUED, CellState.PROBING),
        (CellState.PROBING, CellState.SHORTLIST_READY),
        (CellState.PROBING, CellState.REJECTED_EMPTY),
        (CellState.SHORTLIST_READY, CellState.PARTIAL),
        (CellState.SHORTLIST_READY, CellState.SATURATED),
        (CellState.SHORTLIST_READY, CellState.REJECTED_EMPTY),
        (CellState.PARTIAL, CellState.QUEUED),
        (CellState.PARTIAL, CellState.SATURATED),
        (CellState.SATURATED, CellState.STALE),
        (CellState.REJECTED_EMPTY, CellState.QUEUED),
        (CellState.STALE, CellState.QUEUED),
    ],
)
def test_allowed_transitions(frm, to):
    assert can_transition(frm, to) is True
    # Should not raise.
    assert_transition(frm, to)


@pytest.mark.parametrize(
    "frm,to",
    [
        (CellState.UNPROBED, CellState.PROBING),
        (CellState.QUEUED, CellState.SATURATED),
        (CellState.PROBING, CellState.QUEUED),
        (CellState.SATURATED, CellState.QUEUED),
        (CellState.SATURATED, CellState.PARTIAL),
        (CellState.STALE, CellState.SATURATED),
        (CellState.REJECTED_EMPTY, CellState.PROBING),
        (CellState.PARTIAL, CellState.PROBING),
    ],
)
def test_disallowed_transitions(frm, to):
    assert can_transition(frm, to) is False
    with pytest.raises(AppError) as exc:
        assert_transition(frm, to)
    assert exc.value.code == "INVALID_TRANSITION"
    assert exc.value.status_code == 409


def test_can_transition_unknown_state():
    assert can_transition("BOGUS", CellState.QUEUED) is False
    assert can_transition(CellState.QUEUED, "BOGUS") is False


def test_string_values_work():
    # Plain strings (as stored on the model) should validate too.
    assert can_transition("UNPROBED", "QUEUED") is True
    assert can_transition("SATURATED", "QUEUED") is False


def test_every_state_has_transition_entry():
    for state in CellState:
        assert state in ALLOWED_TRANSITIONS


# --- saturation ----------------------------------------------------------

def _saturated_inputs() -> SaturationInputs:
    return SaturationInputs(
        independent_source_count=3,
        target_sources=3,
        has_fresh_asset=True,
        consecutive_zero_net_new=2,
        coverage_confidence=0.75,
    )


def test_is_saturated_true_at_boundaries():
    assert is_saturated(_saturated_inputs()) is True


def test_is_saturated_false_insufficient_sources():
    inp = _saturated_inputs()
    inp.independent_source_count = 2
    assert is_saturated(inp) is False


def test_is_saturated_false_no_fresh_asset():
    inp = _saturated_inputs()
    inp.has_fresh_asset = False
    assert is_saturated(inp) is False


def test_is_saturated_false_zero_net_new_too_low():
    inp = _saturated_inputs()
    inp.consecutive_zero_net_new = 1
    assert is_saturated(inp) is False


def test_is_saturated_false_low_confidence():
    inp = _saturated_inputs()
    inp.coverage_confidence = 0.74
    assert is_saturated(inp) is False


@pytest.mark.parametrize(
    "tier,expected",
    [
        ("A", 3),
        ("B", 2),
        ("C", 999),
        (None, 3),
        ("Z", 3),
        ("", 3),
    ],
)
def test_target_for_tier(tier, expected):
    assert target_for_tier(tier) == expected


def test_next_state_after_probe_saturated():
    assert next_state_after_probe(_saturated_inputs(), "A") == "SATURATED"


def test_next_state_after_probe_partial():
    inp = _saturated_inputs()
    inp.coverage_confidence = 0.5
    assert next_state_after_probe(inp, "A") == "PARTIAL"
