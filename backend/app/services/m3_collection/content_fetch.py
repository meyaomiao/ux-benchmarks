"""Shared web content fetcher — download a URL and extract its MAIN text.

Used by every live adapter so they get real article/doc body instead of nav +
footer noise (which scored ~0 and was the root cause of empty collection).

Strategy:
  1. httpx GET (12s, one retry, browser-ish UA) — many doc/community sites 403
     a default client.
  2. trafilatura.extract() — pulls the main content, strips nav/footer/ads/
     comments. Best-in-class boilerplate removal.
  3. BeautifulSoup fallback — if trafilatura yields nothing (rare / odd markup),
     grab <main>/<article>/<body> text as a last resort.

Returns (title, text) or None when nothing usable came back (e.g. SPA shell,
binary, blocked). Never raises for normal failures.
"""
from __future__ import annotations

import logging
from typing import Optional

from billiard.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger(__name__)

_TIMEOUT = 12.0
_MAX_CHARS = 6000           # cap body sent to the scorer (token budget)
_MIN_USABLE_CHARS = 120     # below this = SPA shell / nav-only, treat as empty
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)


def _http_get(url: str) -> Optional[str]:
    """GET url as HTML text, one retry. Returns None on failure/non-HTML."""
    import httpx

    for attempt in (1, 2):
        try:
            resp = httpx.get(
                url,
                timeout=_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": _UA, "Accept-Language": "en,zh;q=0.8"},
            )
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "")
            if "html" not in ctype and "text" not in ctype:
                return None  # PDF / binary / json — not our job here
            return resp.text
        except SoftTimeLimitExceeded:
            raise
        except Exception as exc:  # noqa: BLE001
            if attempt == 2:
                logger.debug("content_fetch: GET failed %s: %s", url[:60], exc)
                return None
    return None


def _title_from_html(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.string:
            return soup.title.string.strip()[:200]
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)[:200]
    except SoftTimeLimitExceeded:
        raise
    except Exception:  # noqa: BLE001
        pass
    return ""


def _bs4_fallback(html: str) -> str:
    """Last-resort main-text grab when trafilatura returns nothing."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()
        node = soup.find("main") or soup.find("article") or soup.body or soup
        return node.get_text(" ", strip=True)
    except SoftTimeLimitExceeded:
        raise
    except Exception:  # noqa: BLE001
        return ""


def fetch_main_text(url: str) -> Optional[tuple[str, str]]:
    """Fetch `url` and return (title, main_text), or None if nothing usable.

    main_text is the article/doc body with nav/footer/ads removed, capped at
    _MAX_CHARS. Returns None for SPA shells, binaries, blocked pages, etc.
    """
    html = _http_get(url)
    if not html:
        return None

    text = ""
    try:
        import trafilatura
        extracted = trafilatura.extract(
            html, include_comments=False, include_tables=True,
            favor_recall=True, no_fallback=False,
        )
        if extracted:
            text = extracted
    except SoftTimeLimitExceeded:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.debug("content_fetch: trafilatura failed %s: %s", url[:60], exc)

    if len(text) < _MIN_USABLE_CHARS:
        text = _bs4_fallback(html)

    text = (text or "").strip()
    if len(text) < _MIN_USABLE_CHARS:
        return None  # SPA shell / nav-only — not usable evidence

    return _title_from_html(html) or url, text[:_MAX_CHARS]


def fetch_many(urls: list[str], max_workers: int = 8) -> dict[str, tuple[str, str]]:
    """Fetch many URLs CONCURRENTLY. Returns {url: (title, text)} for usable ones.

    Each fetch is network-bound (I/O), so a thread pool gives near-linear speedup
    — 28 URLs go from ~28×(fetch) serial to ceil(28/8) rounds. Failed/empty URLs
    are simply absent from the result.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    out: dict[str, tuple[str, str]] = {}
    if not urls:
        return out
    with ThreadPoolExecutor(max_workers=min(max_workers, len(urls))) as pool:
        futures = {pool.submit(fetch_main_text, u): u for u in urls}
        for fut in as_completed(futures):
            url = futures[fut]
            try:
                got = fut.result()
            except SoftTimeLimitExceeded:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.debug("fetch_many: %s failed: %s", url[:60], exc)
                got = None
            if got:
                out[url] = got
    return out
