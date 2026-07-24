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

_RESULTS_PER_QUERY = 6
# Cap URLs actually fetched per probe. Each fetch (httpx 6s) is serial. With
# Serper (fast, ~3s/search) we can afford more candidates → better recall.
_MAX_URLS_TOTAL = 10
# Cap real search-engine calls per probe. Serper is fast, so 3 doc-seeking
# queries per probe is fine and widens coverage.
_MAX_SEARCHES_PER_PROBE = 3

# Domains that never contain real product UI/docs — filter them out before
# fetching (they dominated results: YouTube, press wires, social, app stores).
_JUNK_DOMAINS = (
    "youtube.com", "youtu.be", "vimeo.com",
    "prnewswire.com", "businesswire.com", "globenewswire.com", "prweb.com",
    "facebook.com", "twitter.com", "x.com", "linkedin.com", "instagram.com",
    "reddit.com", "quora.com", "medium.com",
    "play.google.com", "apps.apple.com",
    "crunchbase.com", "g2.com", "capterra.com", "trustpilot.com",
    "wikipedia.org", "everycrsreport.com",
)


def _is_junk_url(url: str) -> bool:
    """True if the URL's host is a known non-doc source (video/PR/social/etc)."""
    from urllib.parse import urlparse
    host = (urlparse(url).netloc or "").lower()
    return any(host == d or host.endswith("." + d) for d in _JUNK_DOMAINS)


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
    """Search via the `ddgs` package (successor to duckduckgo_search).

    No API key required. Raises on failure -- caller decides how to handle it.
    """
    from ddgs import DDGS  # lazy import

    urls: list[str] = []
    # Hard per-query timeout so one slow/blocked backend can't stall the probe.
    # Pin to a single backend where supported (ddgs otherwise retries across
    # yandex/google/bing serially, each with its own timeout = minutes).
    with DDGS(timeout=8) as ddgs:
        try:
            results = ddgs.text(query, max_results=n, backend="duckduckgo")
        except TypeError:
            # Older/newer ddgs without the backend kwarg — fall back to default.
            results = ddgs.text(query, max_results=n)
        for r in results:
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
# Serper.dev (recommended — Google results, cheapest; requires SEARCH_API_KEY)
# ---------------------------------------------------------------------------

def _serper_search(query: str, n: int) -> list[str]:
    """Call Serper.dev (Google Search API) -- requires SEARCH_API_KEY.

    Best coverage for niche B2B help docs (Google index) at ~1/10th SerpAPI's
    price. Raises on HTTP or parse error.
    """
    import httpx  # lazy import

    resp = httpx.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": settings.search_api_key, "Content-Type": "application/json"},
        json={"q": query, "num": n},
        timeout=10.0,
    )
    resp.raise_for_status()
    data = resp.json()
    results = data.get("organic", [])
    return [r["link"] for r in results if r.get("link")][:n]


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
    """Return up to `n` real result URLs for `query`.

    Provider selection order:
      1. Mock URLs         -- ONLY when use_collection_mock=True (offline fixtures)
      2. serper/serpapi/brave -- when SEARCH_API_KEY set (SEARCH_API_PROVIDER picks)
      3. DuckDuckGo        -- default, zero config, no key needed

    In real mode (use_collection_mock=False), a search failure returns [] —
    we do NOT fabricate mock URLs, because those point to nonexistent domains
    and would silently yield zero candidates while looking like a "no results"
    outcome. Empty means "search unavailable", which the caller surfaces.
    """
    if settings.use_collection_mock:
        return _mock_search(query, n)

    # Premium provider if explicitly configured.
    if settings.search_api_key:
        try:
            provider = settings.search_api_provider
            if provider == "serper":
                return _serper_search(query, n)
            if provider == "serpapi":
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
        # Real mode: do NOT fabricate fake URLs. Return empty; caller reports it.
        logger.warning("search_service: DDG failed for %r: %s", query[:60], exc)
        return []


def resolve_queries_to_urls(
    queries: list[str],
    *,
    max_total: int = _MAX_URLS_TOTAL,
    max_searches: int = _MAX_SEARCHES_PER_PROBE,
) -> list[str]:
    """Resolve a list of query strings into a deduplicated URL list.

    Queries that already look like http(s) URLs are passed through unchanged
    (free — no network). Non-URL queries are resolved via search_urls(), but at
    most `max_searches` of them actually hit the search engine, so one probe
    can't fan out into a dozen slow searches. Total URLs capped at max_total.
    """
    seen: set[str] = set()
    urls: list[str] = []
    searches_done = 0

    for query in queries:
        if len(urls) >= max_total:
            break
        parsed = urlparse(query.strip())
        if parsed.scheme in ("http", "https") and parsed.netloc:
            if query not in seen:
                seen.add(query)
                urls.append(query)
        else:
            if searches_done >= max_searches:
                continue  # search budget spent — skip remaining search queries
            searches_done += 1
            # Over-fetch (2x) then drop junk domains, so the filter doesn't
            # shrink the usable set below what the probe needs.
            remaining = max_total - len(urls)
            for url in search_urls(query, n=min(_RESULTS_PER_QUERY * 2, remaining * 2 + 4)):
                if url in seen or _is_junk_url(url):
                    continue
                seen.add(url)
                urls.append(url)
                if len(urls) >= max_total:
                    break

    return urls
