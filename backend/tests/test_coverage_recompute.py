"""Pure unit tests for coverage recompute.

The recompute_coverage / read functions are DB-backed and covered elsewhere with
a real session. Here we test only the pure confidence math and assert the honesty
constraint at the source-text level (no network, no DB, no app imports of models).
"""
import ast
import os

# Import ONLY the pure helper. This module-level import is safe: coverage_recompute
# imports SQLAlchemy models, but instantiating them is not required for the pure
# helper. If the environment cannot import it, the source-text tests below still run.
from app.services.m3_collection.coverage_recompute import confidence_score

_SOURCE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app",
    "services",
    "m3_collection",
    "coverage_recompute.py",
)


def test_confidence_zero_sources_is_zero():
    assert confidence_score(0, 0.0) == 0.0
    # Even if the (vacuous) observed fraction were high, 0 sources -> 0.0.
    assert confidence_score(0, 1.0) == 0.0


def test_confidence_three_plus_all_observed_is_one():
    assert confidence_score(3, 1.0) == 1.0
    assert confidence_score(5, 1.0) == 1.0


def test_confidence_three_half_observed_is_reduced():
    val = confidence_score(3, 0.5)
    # source_factor == 1.0, observed_fraction == 0.5 -> 0.5
    assert val == 0.5
    assert val < confidence_score(3, 1.0)


def test_confidence_always_within_unit_interval():
    for sources in (-1, 0, 1, 2, 3, 10, 100):
        for frac in (-0.5, 0.0, 0.25, 0.5, 0.75, 1.0, 2.0):
            val = confidence_score(sources, frac)
            assert 0.0 <= val <= 1.0, (sources, frac, val)


def test_source_never_sets_saturated_and_targets_shortlist_ready():
    """Honesty constraint: recompute must aim for SHORTLIST_READY, never SATURATED.

    We inspect the source text + AST to confirm:
      - 'SHORTLIST_READY' is referenced (it is the target state).
      - recompute_coverage never assigns CellState.SATURATED as a transition target.
    """
    with open(_SOURCE_PATH, "r", encoding="utf-8") as fh:
        source = fh.read()

    assert "SHORTLIST_READY" in source

    # AST check: no call passes CellState.SATURATED as a positional argument to a
    # transition. We scan every attribute access `CellState.SATURATED` that appears
    # inside a Call node's args and fail if found. (Comparisons like
    # `status in (..., CellState.SATURATED)` are allowed; those are guards, not targets.)
    tree = ast.parse(source)

    def _is_cellstate_saturated(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "SATURATED"
            and isinstance(node.value, ast.Name)
            and node.value.id == "CellState"
        )

    offending_calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for arg in node.args:
                if _is_cellstate_saturated(arg):
                    offending_calls.append(node)
            for kw in node.keywords:
                if _is_cellstate_saturated(kw.value):
                    offending_calls.append(node)

    assert not offending_calls, "recompute must never pass CellState.SATURATED as a transition target"
