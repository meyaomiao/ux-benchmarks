"""Offline tests for the help-docs adapter (#17).

All tests run in mock mode (settings.use_collection_mock = True) so they never
touch the network.
"""
from uuid import uuid4

import pytest

from app.core.config import settings
from app.services.m3_collection.adapters.help_docs import HelpDocsAdapter
from app.services.m3_collection.contracts import SourceType


@pytest.fixture(autouse=True)
def _force_mock_mode(monkeypatch):
    """Guarantee mock mode for every test in this module (no network)."""
    monkeypatch.setattr(settings, "use_collection_mock", True)


_QUERIES = [
    "site:help.* pricing page setup",
    "how to configure billing",
    "subscription tiers overview",
    "cancel subscription",
    "team seats management",
]


def _fetch(limit: int = 10):
    adapter = HelpDocsAdapter()
    cell_id = uuid4()
    competitor_id = uuid4()
    results = adapter.fetch(cell_id, competitor_id, _QUERIES, limit=limit)
    return results, cell_id, competitor_id


def test_source_type_is_help_docs():
    results, _, _ = _fetch()
    assert results, "mock fetch should return candidates"
    assert all(c.source_type == SourceType.HELP_DOCS for c in results)


def test_ids_and_text_content_set():
    results, cell_id, competitor_id = _fetch()
    for c in results:
        assert c.cell_id == cell_id
        assert c.competitor_id == competitor_id
        assert c.text_content, "text_content must be non-empty"
        assert c.image_path is None  # no screenshots in this adapter
        assert c.rights_status == "third_party_official"


def test_limit_is_respected():
    results, _, _ = _fetch(limit=1)
    assert len(results) <= 1


def test_candidate_id_uniqueness():
    results, _, _ = _fetch()
    ids = [c.candidate_id for c in results]
    assert len(ids) == len(set(ids)), "candidate_id must be unique across results"


def test_deterministic_across_calls():
    """Mock fetch is deterministic in its capture fields (URLs/titles)."""
    r1, _, _ = _fetch()
    r2, _, _ = _fetch()
    assert [c.source_url for c in r1] == [c.source_url for c in r2]
    assert [c.title for c in r1] == [c.title for c in r2]
