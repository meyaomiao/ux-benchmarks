"""Tests for asset_store (#22 write-once store + #20 dedup).

Scope: the PURE ``compute_checksum`` dedup helper — no DB, no network, no
app-module imports beyond the dataclass contracts.

The DB-backed functions (``find_by_checksum``, ``persist_candidate``,
``persist_passing``, ``list_assets_for_cell``) need a live Postgres session and
the write-once/dedup invariants exercised against real rows; those belong in an
integration suite and are intentionally not covered here. See the skipped
placeholder below for the intended cases.
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.services.m3_collection.asset_store import compute_checksum
from app.services.m3_collection.contracts import Candidate, SourceType


def _candidate(**overrides) -> Candidate:
    """Build a Candidate with fixed identity so checksums are comparable."""
    base = dict(
        cell_id=uuid4(),
        competitor_id=uuid4(),
        source_url="https://example.com/help/create-account",
        source_type=SourceType.HELP_DOCS,
        text_content="Step 1: click Sign up.",
        captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return Candidate(**base)


def test_same_content_same_checksum():
    """Same identity + same content -> identical checksum (dedup match)."""
    cell = uuid4()
    comp = uuid4()
    a = _candidate(cell_id=cell, competitor_id=comp)
    b = _candidate(cell_id=cell, competitor_id=comp)
    assert compute_checksum(a) == compute_checksum(b)


def test_different_source_url_different_checksum():
    """Different source_url -> different checksum (distinct evidence)."""
    cell = uuid4()
    comp = uuid4()
    a = _candidate(cell_id=cell, competitor_id=comp, source_url="https://example.com/a")
    b = _candidate(cell_id=cell, competitor_id=comp, source_url="https://example.com/b")
    assert compute_checksum(a) != compute_checksum(b)


def test_different_content_different_checksum():
    """Different text_content -> different checksum."""
    cell = uuid4()
    comp = uuid4()
    a = _candidate(cell_id=cell, competitor_id=comp, text_content="one")
    b = _candidate(cell_id=cell, competitor_id=comp, text_content="two")
    assert compute_checksum(a) != compute_checksum(b)


def test_scoped_per_cell_and_competitor():
    """Same content under a different cell or competitor -> different checksum."""
    base = _candidate()
    other_cell = _candidate(competitor_id=base.competitor_id, source_url=base.source_url,
                            text_content=base.text_content)
    other_comp = _candidate(cell_id=base.cell_id, source_url=base.source_url,
                            text_content=base.text_content)
    assert compute_checksum(base) != compute_checksum(other_cell)
    assert compute_checksum(base) != compute_checksum(other_comp)


def test_image_path_used_when_no_text():
    """Image-only captures fall back to image_path as the content signal."""
    cell = uuid4()
    comp = uuid4()
    a = _candidate(cell_id=cell, competitor_id=comp, text_content="", image_path="/tmp/a.png")
    b = _candidate(cell_id=cell, competitor_id=comp, text_content="", image_path="/tmp/b.png")
    assert compute_checksum(a) != compute_checksum(b)


def test_stable_across_calls():
    """Checksum is deterministic across repeated calls on the same candidate."""
    c = _candidate()
    assert compute_checksum(c) == compute_checksum(c) == compute_checksum(c)


def test_returns_sha256_hex():
    """Result is a 64-char lowercase hex sha256 digest."""
    digest = compute_checksum(_candidate())
    assert len(digest) == 64
    assert all(ch in "0123456789abcdef" for ch in digest)


@pytest.mark.skip(reason="DB-backed: needs live Postgres session (integration suite)")
def test_db_backed_persist_and_dedup():
    """Integration placeholder for the write-once + dedup DB path.

    Intended cases (require a real Session):
      - persist_candidate inserts a new row and returns (asset, True)
      - re-persisting the same content returns (existing, False), no 2nd row
      - media_disposition is derived from rights_status via rights_policy
      - evidence_type stores score.evidence_type (not the candidate hint)
      - persist_passing skips pairs where score.passed is False
      - list_assets_for_cell orders by ai_score desc, nulls last
    """
