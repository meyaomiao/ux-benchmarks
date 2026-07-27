"""Shared web content fetcher for live M3 candidates.

The first bounded set of URLs is rendered in Chromium so SPA content and real
product UI reach the vision scorer. Browser failures, non-HTML responses and
near-blank screenshots fall back to the existing httpx/trafilatura path. URLs
beyond the render budget remain HTTP-only.

Normal network/browser failures never escape. Celery's SoftTimeLimitExceeded is
always re-raised so the task-level timeout handling remains authoritative.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from uuid import uuid4

from billiard.exceptions import SoftTimeLimitExceeded

from app.core.config import settings
from app.services.m3_collection.adapters.interactive_demo import (
    _BROWSER_LAUNCH_TIMEOUT_MS,
    _GOTO_TIMEOUT_MS,
    _MIN_USEFUL_PNG_BYTES,
    _RESCORE_VIEWPORT,
    _close_playwright_resource,
    _configure_page_timeouts,
    _dismiss_consent,
    _wait_for_page_settle,
)

logger = logging.getLogger(__name__)

_TIMEOUT = 12.0
_MAX_CHARS = 6000           # cap body sent to the scorer (token budget)
_MIN_USABLE_CHARS = 120     # below this = SPA shell / nav-only, treat as empty
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)

# Rendering is intentionally narrow: the three eligible live adapters each get
# at most three attempts, and the default pipeline shares an eight-attempt budget.
DEFAULT_RENDER_LIMIT_PER_ADAPTER = 3
DEFAULT_RENDER_LIMIT_PER_PROBE = 8


@dataclass(frozen=True)
class FetchedPage:
    """Usable page content returned to a candidate adapter."""

    title: str
    text_content: str
    image_path: str | None = None


@dataclass
class RenderBudget:
    """Shared per-probe cap counted by browser attempts, not successes."""

    remaining: int

    def __post_init__(self) -> None:
        self.remaining = max(0, self.remaining)

    def reserve(self, requested: int) -> int:
        granted = min(max(0, requested), self.remaining)
        self.remaining -= granted
        return granted


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


def _dedupe_urls(urls: list[str]) -> list[str]:
    """Return non-empty URLs once, preserving search rank."""
    return list(dict.fromkeys(url.strip() for url in urls if url.strip()))


def _is_html_response(response) -> bool:
    """Treat a missing content type as renderable, but reject known binaries."""
    if response is None:
        return True
    headers = getattr(response, "headers", {}) or {}
    content_type = headers.get("content-type", "").lower()
    return not content_type or "html" in content_type


def _rendered_main_text(page) -> str:
    """Read the best available DOM main region after client-side rendering."""
    text = page.evaluate(
        """() => {
            const root = document.querySelector("main, article, [role='main']")
                || document.body;
            return root ? (root.innerText || "") : "";
        }"""
    )
    return " ".join(str(text or "").split())[:_MAX_CHARS]


def _render_many(urls: list[str]) -> dict[str, FetchedPage]:
    """Render URLs in one browser session; omit failures for HTTP fallback."""
    if not urls:
        return {}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright unavailable; using HTTP candidate fetch")
        return {}

    out: dict[str, FetchedPage] = {}
    try:
        shot_dir = Path(settings.assets_dir) / "candidate_pages"
        shot_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as pw:
            browser = None
            try:
                browser = pw.chromium.launch(
                    headless=True, timeout=_BROWSER_LAUNCH_TIMEOUT_MS
                )
                for url in urls:
                    page = browser.new_page(viewport=_RESCORE_VIEWPORT)
                    _configure_page_timeouts(page)
                    fpath: Path | None = None
                    try:
                        response = page.goto(
                            url,
                            wait_until="domcontentloaded",
                            timeout=_GOTO_TIMEOUT_MS,
                        )
                        if not _is_html_response(response):
                            logger.info("candidate render is non-HTML for %s", url)
                            continue
                        _dismiss_consent(page)
                        _wait_for_page_settle(page)

                        title = (page.title() or url).strip()[:200]
                        text = _rendered_main_text(page)
                        digest = hashlib.sha256(url.encode()).hexdigest()[:12]
                        fpath = shot_dir / f"{digest}_{uuid4().hex[:12]}.png"
                        page.screenshot(path=str(fpath), full_page=True)
                        if fpath.stat().st_size < _MIN_USEFUL_PNG_BYTES:
                            logger.info("candidate screenshot too empty for %s", url)
                            fpath.unlink(missing_ok=True)
                            continue

                        out[url] = FetchedPage(
                            title=title or url,
                            text_content=text or title or url,
                            image_path=str(fpath),
                        )
                    except SoftTimeLimitExceeded:
                        raise
                    except Exception as exc:  # noqa: BLE001 — per-URL fallback
                        if fpath is not None:
                            fpath.unlink(missing_ok=True)
                        logger.warning("candidate render failed for %s: %s", url, exc)
                    finally:
                        _close_playwright_resource(page, "page")
            finally:
                if browser is not None:
                    _close_playwright_resource(browser, "browser")
    except SoftTimeLimitExceeded:
        raise
    except Exception as exc:  # noqa: BLE001 — launch/context failure falls back
        logger.warning("candidate browser unavailable; using HTTP fetch: %s", exc)
        return out

    return out


def fetch_candidate_pages(
    urls: list[str],
    *,
    render_limit: int = DEFAULT_RENDER_LIMIT_PER_ADAPTER,
    max_workers: int = 8,
) -> dict[str, FetchedPage]:
    """Fetch deduplicated URLs in rank order with browser-to-HTTP fallback."""
    unique_urls = _dedupe_urls(urls)
    if not unique_urls:
        return {}

    rendered = _render_many(unique_urls[: max(0, render_limit)])
    fallback_urls = [url for url in unique_urls if url not in rendered]
    fetched = fetch_many(fallback_urls, max_workers=max_workers)

    out: dict[str, FetchedPage] = {}
    for url in unique_urls:
        if url in rendered:
            out[url] = rendered[url]
        elif url in fetched:
            title, text = fetched[url]
            out[url] = FetchedPage(title=title, text_content=text)
    return out
