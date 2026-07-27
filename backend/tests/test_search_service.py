"""Unit tests for search query resolution."""
import pytest
from billiard.exceptions import SoftTimeLimitExceeded

from app.services.m3_collection import search_service


def test_site_query_falls_back_without_anchor_when_empty(monkeypatch):
    anchored = (
        "site:thoughtriver.com ThoughtRiver "
        "Risk Highlight State Routine Review documentation"
    )
    fallback = (
        "ThoughtRiver Risk Highlight State Routine Review documentation"
    )
    fallback_urls = [
        "https://www.thought-river.com/docs/risk-1",
        "https://www.thought-river.com/docs/risk-2",
        "https://www.thought-river.com/docs/risk-3",
    ]
    calls: list[str] = []

    def fake_search(query: str, n: int) -> list[str]:
        calls.append(query)
        return fallback_urls if query == fallback else []

    monkeypatch.setattr(search_service, "search_urls", fake_search)

    result = search_service.resolve_queries_to_urls(
        [anchored], max_total=3, max_searches=3
    )

    assert result == fallback_urls
    assert calls == [anchored, fallback]


def test_site_query_does_not_fallback_when_results_exist(monkeypatch):
    anchored = "site:docs.github.com GitHub pull request review documentation"
    expected = ["https://docs.github.com/pull-requests/reviewing-changes"]
    calls: list[str] = []

    def fake_search(query: str, n: int) -> list[str]:
        calls.append(query)
        return expected

    monkeypatch.setattr(search_service, "search_urls", fake_search)

    result = search_service.resolve_queries_to_urls(
        [anchored], max_total=1, max_searches=3
    )

    assert result == expected
    assert calls == [anchored]


def test_official_bucket_query_does_not_fall_back_unanchored(monkeypatch):
    """Official buckets stay on the competitor's own domain.

    The scorer hard-fails help_docs / interactive_demo below PRODUCT_MATCH_GATE,
    so an unanchored retry can only return pages that cannot pass — it just burns
    the screenshot + vision budget on some other vendor's site.
    """
    anchored = "site:adobe.com Adobe Acrobat contract risk scan product tour"
    calls: list[str] = []

    def fake_search(query: str, n: int) -> list[str]:
        calls.append(query)
        return []

    monkeypatch.setattr(search_service, "search_urls", fake_search)

    result = search_service.resolve_queries_to_urls(
        [anchored], max_total=3, max_searches=3, allow_unanchored_fallback=False
    )

    assert result == []
    assert calls == [anchored]  # no unanchored retry


def test_resolution_reports_actual_search_and_url_counts(monkeypatch):
    monkeypatch.setattr(
        search_service,
        "search_urls",
        lambda _query, n: ["https://example.com/result"],
    )
    metrics = {}

    result = search_service.resolve_queries_to_urls(
        ["https://example.com/direct", "permissions query"], metrics=metrics
    )

    assert result == ["https://example.com/direct", "https://example.com/result"]
    assert metrics == {"search_calls": 1, "urls_found": 2}


def test_resolution_preserves_partial_metrics_on_soft_timeout(monkeypatch):
    monkeypatch.setattr(
        search_service,
        "search_urls",
        lambda _query, n: (_ for _ in ()).throw(SoftTimeLimitExceeded()),
    )
    metrics = {}

    with pytest.raises(SoftTimeLimitExceeded):
        search_service.resolve_queries_to_urls(["permissions query"], metrics=metrics)

    assert metrics == {"search_calls": 1, "urls_found": 0}
