"""Pure-logic tests for the M3 source registry dedup index.

Only the pure list-merge helper is tested here (no database). The DB-backed
functions (get_by_url, register_source, is_fresh, mark_fetched, list_sources)
require a live session and are deferred to integration tests.
"""
from app.services.m3_collection.source_registry_service import _merge_cell


def test_merge_cell_appends_new():
    assert _merge_cell(["a"], "b") == ["a", "b"]


def test_merge_cell_dedups_existing():
    # Appending a cell already present must not duplicate it.
    assert _merge_cell(["a", "b"], "b") == ["a", "b"]


def test_merge_cell_preserves_order():
    assert _merge_cell(["c", "a", "b"], "d") == ["c", "a", "b", "d"]


def test_merge_cell_none_safe():
    # None (uninitialized JSONB column) is treated as an empty list.
    assert _merge_cell(None, "a") == ["a"]


def test_merge_cell_empty_list():
    assert _merge_cell([], "a") == ["a"]


def test_merge_cell_returns_new_list():
    # Helper must return a fresh list (not mutate in place) so callers can
    # reassign for SQLAlchemy JSONB mutation tracking.
    original = ["a"]
    result = _merge_cell(original, "b")
    assert result is not original
    assert original == ["a"]


def test_merge_cell_dedup_returns_copy():
    # Even on the no-op dedup path, a distinct list is returned.
    original = ["a", "b"]
    result = _merge_cell(original, "a")
    assert result == ["a", "b"]
    assert result is not original
