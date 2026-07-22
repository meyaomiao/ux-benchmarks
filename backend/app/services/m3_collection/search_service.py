"""Search engine integration for live collection (A1).

Converts query strings (like "site:help.* role permissions setup") into real
URLs by calling a search API, so the HelpDocsAdapter and other adapters can
fetch actual content in live mode.

Supported providers:
  - brave   (default) — https://brave.com/search/api/  free tier 2000 req/month
  - serpapi             — https://serpapi.com/          free tier 100 req/month

When settings.use_collection_mock is True OR settings.search_api_key is empty,
_mock_search() is used: it returns a short list of plausible-looking URLs derived
from the query text. This lets the whole chain run offline / in CI without a key.

Usage:
    from app.services.m3_collection.search_service import resolve_queries_to_urls
    urls = resolve_queries_to_urls(["site:help.linear.app role permissions"])
"""
from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus, urlparse

from app.core.config import settings

logger = logging.getLogger(__name__)

# How many result URLs to request per query.
_RESULTS_PER_QUERY = 5
# Hard cap on total URLs returned for a query bundle (guards against API cost).
_MAX_URLS_TOTAL = 20


# ---------------------------------------------------------------------------
# Mock search
# ---------------------------------------------------------------------------

def _mock_search(query: str, n: int = _RESULTS_PER_QUERY) -> list[str]:
    """Return plausible-looking URLs without any network call.

    Derives a slug from the query keywords and mixes in a few realistic-looking
    help/docs domain patterns. Deterministic given the same query.
    """
    # Extract the site: scope from the query if present (e.g. "site:help.*")
    site_match = re.search(r"site:([\w.*-]+)", query)
    raw_domain = site_match.group(1) if site_match else "help.competitor.example.com"
    # Replace wildcard with a concrete subdomain for URL realism.
    domain = raw_domain.replace(".*", ".example.com").replace("*", "example.com")
    if not domain.startswith("http"):
        domain = "https://" + domain

    # Build a slug from non-operator words.
    words = re.sub(r"site:\S+", "", query)
    words = re.sub(r"[^\w\s-]", " ", words).split()
    slug_words = [w for w in words if w and not w.lower() in
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
# Brave Search
# ---------------------------------------------------------------------------

def _brave_search(query: str, n: int) -> list[str]:
    """Call Brave Web Search API and return result URLs.

    Raises on HTTP or parse error — caller should catch and fall back to mock.
    """
    import httpx  # lazy import — not needed in mock mode

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
# SerpAPI
# ---------------------------------------------------------------------------

def _serpapi_search(query: str, n: int) -> list[str]:
    """Call SerpAPI and return organic result URLs.

    Raises on HTTP or parse error — caller should catch and fall back to mock.
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
    """Return up to `n` URLs for `query`, using the configured search provider.

    Always returns something (falls back to mock on any failure).
    """
    use_mock = settings.use_collection_mock or not settings.search_api_key
    if use_mock:
        return _mock_search(query, n)

    try:
        if settings.search_api_provider == "serpapi":
            return _serpapi_search(query, n)
        return _brave_search(query, n)
    except Exception as exc:  # noqa: BLE001 — network is best-effort
        logger.warning("search_service: %s search failed for %r, using mock: %s",
                       settings.search_api_provider, query[:60], exc)
        return _mock_search(query, n)


def resolve_queries_to_urls(
    queries: list[str],
    *,
    max_total: int = _MAX_URLS_TOTAL,
) -> list[str]:
    """Resolve a list of query strings into a deduplicated URL list.

    Queries that already look like http(s) URLs are passed through unchanged.
    Non-URL queries are resolved via search_urls(). The total is capped at
    `max_total` to keep API cost bounded.
    """
    seen: set[str] = set()
    urls: list[str] = []

    for query in queries:
        if len(urls) >= max_total:
            break
        parsed = urlparse(query.strip())
        if parsed.scheme in ("http", "https") and parsed.netloc:
            # Already a URL — pass through.
            if query not in seen:
                seen.add(query)
                urls.append(query)
        else:
            # Search query — resolve to URLs.
            remaining = max_total - len(urls)
            for url in search_urls(query, n=min(_RESULTS_PER_QUERY, remaining)):
                if url not in seen:
                    seen.add(url)
                    urls.append(url)
                    if len(urls) >= max_total:
                        break

    return urls
