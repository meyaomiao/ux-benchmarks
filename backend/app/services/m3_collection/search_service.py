"""Search engine integration for live collection (A1).

Converts query strings (like "site:help.* role permissions setup") into real
URLs by calling a search engine, so the HelpDocsAdapter and other adapters can
fetch actual content in live mode.

Supported providers (in priority order):
  1. mock          -- always used when use_collection_mock=True
  2. brave/serpapi -- used when SEARCH_API_KEY is set in .env
  3. duckduckgo    -- default fallback, zero config, no API key needed

Usage:
    from app.services.m3_collection.search_service import resolve_queries_to_urls
    urls = resolve_queries_to_urls(["site:help.linear.app role permissions"])
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from app.core.config import settings

logger = logging.getLogger(__name__)

_RESULTS_PER_QUERY = 5
_MAX_URLS_TOTAL = 20


# ---------------------------------------------------------------------------
# Mock search
# ---------------------------------------------------------------------------

def _mock_search(query: str, n: int = _RESULTS_PER_QUERY) -> list[str]:
    """Return plausible-looking URLs without any network call."""
    site_match = re.search(r"site:([\w.*-]+)", query)
    raw_domain = site_match.group(1) if site_match else "help.competitor.example.com"
    domain = raw_domain.replace(".*", ".example.com").replace("*", "example.com")
    if not domain.startswith("http"):
        domain = "https://" + domain

    words = re.sub(r"site:\S+", "", query)
    words = re.sub(r"[^\w\s-]", " ", words).split()
    slug_words = [w for w in words if w and w.lower() not in
                  {"how", "to", "the", "a", "an", "and", "or", "of", "in", "for"}]
    base_slug = "-".join(slug_words[:5]).lower() or "help-article"

    paths = [
        f"/docs/{base_slug}",
        f"/guides/{base_slug}",
        f"/help/{base_slug}",
        f"/support/{base_slug}",
        f"/articles/{base_slug}-guide",
    ]
    return [f"{domain}{p}" for p in paths[:n]]


# ---------------------------------------------------------------------------
# DuckDuckGo (default, no API key needed)
# ---------------------------------------------------------------------------

def _duckduckgo_search(query: str, n: int) -> list[str]:
    """Search via duckduckgo_search package -- no API key required.

    Uses DDG's internal API. Suitable for development and moderate production
    use. Raises on failure -- caller catches and falls back to mock.
    """
    from duckduckgo_search import DDGS  # lazy import

    urls: list[str] = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=n):
            href = r.get("href") or r.get("url")
            if href:
                urls.append(href)
    return urls[:n]


# ---------------------------------------------------------------------------
# Brave Search (optional, requires SEARCH_API_KEY)
# ---------------------------------------------------------------------------

def _brave_search(query: str, n: int) -> list[str]:
    """Call Brave Web Search API -- requires SEARCH_API_KEY.

    Raises on HTTP or parse error.
    """
    import httpx  # lazy import

    resp = httpx.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": n, "text_decorations": 0},
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": settings.search_api_key,
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    data = resp.json()
    results = data.get("web", {}).get("results", [])
    return [r["url"] for r in results if r.get("url")][:n]


# ---------------------------------------------------------------------------
# SerpAPI (optional, requires SEARCH_API_KEY)
# ---------------------------------------------------------------------------

def _serpapi_search(query: str, n: int) -> list[str]:
    """Call SerpAPI -- requires SEARCH_API_KEY.

    Raises on HTTP or parse error.
    """
    import httpx  # lazy import

    resp = httpx.get(
        "https://serpapi.com/search",
        params={"q": query, "api_key": settings.search_api_key, "num": n},
        timeout=12.0,
    )
    resp.raise_for_status()
    data = resp.json()
    results = data.get("organic_results", [])
    return [r["link"] for r in results if r.get("link")][:n]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search_urls(query: str, n: int = _RESULTS_PER_QUERY) -> list[str]:
    """Return up to `n` URLs for `query`.

    Provider selection order:
      1. Mock         -- when use_collection_mock=True
      2. Brave/SerpAPI-- when SEARCH_API_KEY is set in .env
      3. DuckDuckGo   -- default, zero config, no key needed
      4. Mock fallback-- on any failure

    Always returns something.
    """
    if settings.use_collection_mock:
        return _mock_search(query, n)

    # Premium provider if explicitly configured.
    if settings.search_api_key:
        try:
            if settings.search_api_provider == "serpapi":
                return _serpapi_search(query, n)
            return _brave_search(query, n)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "search_service: %s failed for %r, trying DDG: %s",
                settings.search_api_provider, query[:60], exc,
            )

    # Default: DuckDuckGo, works with zero configuration.
    try:
        return _duckduckgo_search(query, n)
    except Exception as exc:  # noqa: BLE001
        logger.warning("search_service: DDG failed for %r, using mock: %s", query[:60], exc)
        return _mock_search(query, n)


def resolve_queries_to_urls(
    queries: list[str],
    *,
    max_total: int = _MAX_URLS_TOTAL,
) -> list[str]:
    """Resolve a list of query strings into a deduplicated URL list.

    Queries that already look like http(s) URLs are passed through unchanged.
    Non-URL queries are resolved via search_urls(). Total capped at max_total.
    """
    seen: set[str] = set()
    urls: list[str] = []

    for query in queries:
        if len(urls) >= max_total:
            break
        parsed = urlparse(query.strip())
        if parsed.scheme in ("http", "https") and parsed.netloc:
            if query not in seen:
                seen.add(query)
                urls.append(query)
        else:
            remaining = max_total - len(urls)
            for url in search_urls(query, n=min(_RESULTS_PER_QUERY, remaining)):
                if url not in seen:
                    seen.add(url)
                    urls.append(url)
                    if len(urls) >= max_total:
                        break

    return urls
