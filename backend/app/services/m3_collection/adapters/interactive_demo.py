"""Interactive demo adapter (#18).

Produces `Candidate`s with REAL screenshots from embedded product-tour demos
(Navattic, Storylane, Arcade, Demostack, Supademo and compatible platforms).

Unlike the help-docs adapter (text-only), this adapter sets `image_path` on
every Candidate so the AI scorer uses its strict image-mode rubric — directly
answering "does this screenshot SHOW the target UI/state?"

Two modes (settings.use_collection_mock):

  mock (default ON)
    Creates tiny real PNG files in settings.assets_dir / "mock_demo_frames/".
    The images are visually blank (coloured squares) but are valid PNG files
    the scorer can open. This lets the entire "screenshot → Claude Vision
    image-mode scoring" path run offline without a browser.

  live (flag OFF)
    Uses Playwright (sync API) to:
    1. Open each query URL in a headless browser.
    2. Scan the page for iframes matching known demo-platform signatures.
    3. Screenshot the iframe region for the first detected demo.
    4. Attempt to advance the demo (click a "next" button / press ArrowRight)
       and screenshot up to `limit` steps.
    Network / browser errors are caught and skipped; the method returns
    whatever succeeded (possibly []).

LIMITATIONS (live mode):
- Only processes queries that are http(s) URLs. Query-expansion buckets
  produce search operators, not URLs, so callers should pass concrete page
  URLs (e.g. a competitor's product-tour landing page).
- Platform-specific step navigation is best-effort; if a platform changes its
  DOM structure the adapter returns fewer frames rather than crashing.
- Playwright must be installed: `playwright install chromium --with-deps`.
  The import is lazy so mock mode has no hard dependency on it.

Rights: `embedded_third_party` → `thumbnail_only` per rights_policy.
capture_context: `guided_demo` (ideal path through a vendor-curated tour,
NOT a real user session).
"""
from __future__ import annotations

import io
import logging
import os
import struct
import time
import zlib
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from billiard.exceptions import SoftTimeLimitExceeded

from app.core.config import settings
from app.services.m3_collection.contracts import Candidate, EvidenceType, SourceType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known demo-platform iframe fingerprints.
# These are checked against the iframe `src` attribute (substring match).
# Add new platforms here as they emerge; the rest of the adapter is agnostic.
# ---------------------------------------------------------------------------
DEMO_PLATFORM_SIGNATURES: dict[str, list[str]] = {
    "navattic":   ["navattic.com"],
    "storylane":  ["storylane.io"],
    "arcade":     ["arcade.software", "app.arcade.software"],
    "demostack":  ["demostack.com"],
    "supademo":   ["supademo.com"],
    "walnut":     ["walnut.io"],
    "reprise":    ["reprise.com"],
}

# CSS selectors tried (in order) to advance a demo to the next step.
# Platforms differ; we try generically first, then give up gracefully.
_NEXT_SELECTORS = [
    "[aria-label*='next' i]",
    "[aria-label*='forward' i]",
    "button[class*='next' i]",
    "button[class*='forward' i]",
    "[data-testid*='next' i]",
]

# How long (seconds) to wait after a step advance before screenshotting.
_STEP_WAIT_S = 0.8

# Page-load budget. 8s dropped slow-but-valid vendor sites (docusign.com,
# power.law) before they ever rendered, so their screenshots never existed.
_GOTO_TIMEOUT_MS = 25_000

# Every Playwright operation that supports a timeout inherits this bound. It
# covers selectors, clicks, screenshots, evaluation and title reads after the
# separately bounded navigation completes.
_ACTION_TIMEOUT_MS = 5_000
_BROWSER_LAUNCH_TIMEOUT_MS = 15_000


def _configure_page_timeouts(page) -> None:
    page.set_default_timeout(_ACTION_TIMEOUT_MS)
    page.set_default_navigation_timeout(_GOTO_TIMEOUT_MS)


def _close_playwright_resource(resource, label: str) -> None:
    """Best-effort close that still lets Celery soft timeouts propagate."""
    try:
        resource.close()
    except SoftTimeLimitExceeded:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("failed to close Playwright %s: %s", label, exc)


def _detect_platform(src: str) -> str | None:
    """Return the platform name if `src` matches a known signature, else None."""
    for platform, sigs in DEMO_PLATFORM_SIGNATURES.items():
        if any(sig in src for sig in sigs):
            return platform
    return None


def _looks_like_url(query: str) -> bool:
    parsed = urlparse(query.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


# ---------------------------------------------------------------------------
# Minimal valid PNG builder (no external deps).
# Produces a tiny coloured square — a real, parseable PNG file.
# ---------------------------------------------------------------------------

def _make_png(width: int = 8, height: int = 8, rgb: tuple = (100, 149, 237)) -> bytes:
    """Return the bytes of a minimal valid PNG (solid colour, W×H pixels).

    Pure Python — no Pillow dependency. The PNG is tiny (≤ a few hundred bytes)
    but is a fully valid image that PIL, browsers, and the relay vision API
    can all open/read. Used for mock-mode fixture images.
    """
    r, g, b = rgb
    # Build raw scanlines: filter byte 0x00 + RGB triples.
    scanline = bytes([0x00]) + bytes([r, g, b] * width)
    raw = scanline * height
    compressed = zlib.compress(raw)

    def chunk(name: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        crc = struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)
        return length + name + data + crc

    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    out = b"\x89PNG\r\n\x1a\n"
    out += chunk(b"IHDR", ihdr_data)
    out += chunk(b"IDAT", compressed)
    out += chunk(b"IEND", b"")
    return out


# Mock frame colours: vary by step index so frames are visually distinct.
_MOCK_COLOURS = [
    (100, 149, 237),  # cornflower blue
    ( 60, 179, 113),  # medium sea green
    (255, 165,   0),  # orange
    (147, 112, 219),  # medium purple
    (220,  20,  60),  # crimson
]


class InteractiveDemoAdapter:
    """Adapter that screenshots interactive product-tour demos.

    Satisfies the `Adapter` Protocol in `..contracts`.
    """

    source_type: SourceType = SourceType.INTERACTIVE_DEMO

    def __init__(self) -> None:
        self.last_stats = {"browser_pages": 0, "candidates_found": 0}

    def fetch(
        self,
        cell_id: UUID,
        competitor_id: UUID,
        queries: list[str],
        *,
        limit: int = 10,
    ) -> list[Candidate]:
        """Return up to `limit` demo-frame Candidates for this (cell, competitor)."""
        self.last_stats = {"browser_pages": 0, "candidates_found": 0}
        if settings.use_collection_mock:
            candidates = self._mock_fetch(cell_id, competitor_id, queries, limit=limit)
        else:
            candidates = self._live_fetch(cell_id, competitor_id, queries, limit=limit)
        self.last_stats["candidates_found"] = len(candidates)
        return candidates

    # ------------------------------------------------------------------
    # Mock path
    # ------------------------------------------------------------------

    def _mock_fetch(
        self,
        cell_id: UUID,
        competitor_id: UUID,
        queries: list[str],
        *,
        limit: int,
    ) -> list[Candidate]:
        """Return deterministic fixture Candidates backed by real PNG files.

        Files are written to settings.assets_dir / 'mock_demo_frames/' so the
        AI scorer's image path is genuinely openable. The images are tiny
        coloured squares — valid PNGs that test the image-mode scoring path
        without any browser or network dependency.
        """
        frame_dir = Path(settings.assets_dir) / "mock_demo_frames"
        frame_dir.mkdir(parents=True, exist_ok=True)

        n_frames = min(3, limit)
        candidates: list[Candidate] = []

        for idx in range(n_frames):
            colour = _MOCK_COLOURS[idx % len(_MOCK_COLOURS)]
            png_bytes = _make_png(rgb=colour)

            # Stable filename: keyed on step index (deterministic across runs).
            fname = f"mock_demo_step_{idx:02d}.png"
            fpath = frame_dir / fname
            fpath.write_bytes(png_bytes)

            source_url = (
                f"https://app.storylane.io/demo/mock-tour-{idx}"
            )
            candidates.append(
                Candidate(
                    cell_id=cell_id,
                    competitor_id=competitor_id,
                    source_url=source_url,
                    source_type=self.source_type,
                    title=f"Product tour – step {idx + 1}",
                    snippet=f"Mock interactive demo frame {idx + 1}",
                    text_content=f"Demo step {idx + 1}: guided tour frame from the product demo.",
                    image_path=str(fpath),
                    rights_status="embedded_third_party",
                    evidence_type_hint=EvidenceType.OBSERVED,
                )
            )

        return candidates

    # ------------------------------------------------------------------
    # Live path (Playwright)
    # ------------------------------------------------------------------

    def _live_fetch(
        self,
        cell_id: UUID,
        competitor_id: UUID,
        queries: list[str],
        *,
        limit: int,
    ) -> list[Candidate]:
        """Scan page URLs for embedded demos, screenshot each step.

        Only processes queries that are http(s) URLs (search operators are
        skipped — see module docstring). Network/browser errors are caught
        and do not propagate; the method returns whatever succeeded.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error(
                "Playwright not installed. Run: playwright install chromium --with-deps"
            )
            return []

        frame_dir = Path(settings.assets_dir) / "demo_frames"
        frame_dir.mkdir(parents=True, exist_ok=True)

        candidates: list[Candidate] = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True, timeout=_BROWSER_LAUNCH_TIMEOUT_MS
            )
            try:
                candidates = self._collect_from_pages(
                    browser, cell_id, competitor_id, queries, frame_dir, limit
                )
            finally:
                _close_playwright_resource(browser, "browser")

        return candidates

    def _collect_from_pages(
        self,
        browser,
        cell_id: UUID,
        competitor_id: UUID,
        queries: list[str],
        frame_dir: Path,
        limit: int,
    ) -> list[Candidate]:
        candidates: list[Candidate] = []

        for query in queries:
            if len(candidates) >= limit:
                break
            if not _looks_like_url(query):
                logger.debug("interactive_demo live: skipping non-URL query %r", query)
                continue

            url = query.strip()
            self.last_stats["browser_pages"] += 1
            try:
                new = self._scrape_page(
                    browser, url, cell_id, competitor_id, frame_dir,
                    max_frames=limit - len(candidates),
                )
                candidates.extend(new)
            except SoftTimeLimitExceeded:
                raise
            except Exception as exc:  # noqa: BLE001 - page-level error
                logger.warning("interactive_demo scrape failed for %s: %s", url, exc)

        return candidates

    def _scrape_page(
        self,
        browser,
        page_url: str,
        cell_id: UUID,
        competitor_id: UUID,
        frame_dir: Path,
        max_frames: int,
    ) -> list[Candidate]:
        """Open a page, find demo iframes, screenshot steps.

        Fallback: if no known demo-platform iframe is found on the page,
        screenshot the full viewport anyway — gives us general UI screenshots
        from feature pages, help docs with embedded images, etc.
        """
        page = browser.new_page()
        _configure_page_timeouts(page)
        candidates: list[Candidate] = []
        try:
            page.goto(page_url, wait_until="domcontentloaded", timeout=_GOTO_TIMEOUT_MS)

            # Find iframes with known demo-platform src signatures.
            iframe_elements = page.query_selector_all("iframe")
            for iframe_el in iframe_elements:
                src = iframe_el.get_attribute("src") or ""
                platform = _detect_platform(src)
                if not platform:
                    continue

                logger.info(
                    "interactive_demo: found %s demo iframe on %s", platform, page_url
                )
                frames = self._screenshot_demo_steps(
                    page, iframe_el, platform, frame_dir,
                    page_url, cell_id, competitor_id,
                    max_frames=max_frames - len(candidates),
                )
                candidates.extend(frames)
                if len(candidates) >= max_frames:
                    break

            # Fallback: no demo iframe found — screenshot the page itself.
            # Useful for product feature pages, help docs with screenshots, etc.
            if not candidates and max_frames > 0:
                candidates.extend(
                    self._screenshot_page_fallback(
                        page, page_url, frame_dir, cell_id, competitor_id
                    )
                )
        finally:
            _close_playwright_resource(page, "page")

        return candidates

    def _screenshot_page_fallback(
        self,
        page,
        page_url: str,
        frame_dir: Path,
        cell_id: UUID,
        competitor_id: UUID,
    ) -> list[Candidate]:
        """Screenshot the viewport when no demo iframe was found on the page.

        Also extracts visible text from the main content area so the scorer
        can use text-mode scoring as a fallback if the image isn't informative.
        """
        from uuid import uuid4

        try:
            fpath = frame_dir / f"{uuid4().hex[:8]}_page.png"
            page.screenshot(path=str(fpath), full_page=False)

            # Extract visible text for dual-mode scoring.
            text_content = ""
            try:
                text_content = page.evaluate("""() => {
                    const sel = ['main', 'article', '[role="main"]', 'body'];
                    for (const s of sel) {
                        const el = document.querySelector(s);
                        if (el) return el.innerText.slice(0, 800);
                    }
                    return document.body.innerText.slice(0, 800);
                }""") or ""
            except SoftTimeLimitExceeded:
                raise
            except Exception:
                pass

            title = page.title() or page_url[:80]
            return [
                Candidate(
                    cell_id=cell_id,
                    competitor_id=competitor_id,
                    source_url=page_url,
                    source_type=self.source_type,
                    title=title[:200],
                    snippet=text_content[:160],
                    text_content=text_content,
                    image_path=str(fpath),
                    rights_status="third_party_official",
                    evidence_type_hint=EvidenceType.OBSERVED,
                )
            ]
        except SoftTimeLimitExceeded:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("page fallback screenshot failed for %s: %s", page_url, exc)
            return []

    def _screenshot_demo_steps(
        self,
        page,
        iframe_el,
        platform: str,
        frame_dir: Path,
        source_url: str,
        cell_id: UUID,
        competitor_id: UUID,
        max_frames: int,
    ) -> list[Candidate]:
        """Screenshot the visible demo iframe, then advance and repeat."""
        from uuid import uuid4

        candidates: list[Candidate] = []
        session_id = uuid4().hex[:8]

        for step in range(max_frames):
            # Screenshot just the iframe bounding box (not the whole page).
            try:
                bbox = iframe_el.bounding_box()
                if not bbox or bbox["width"] < 10 or bbox["height"] < 10:
                    break
                fpath = frame_dir / f"{session_id}_step_{step:02d}.png"
                page.screenshot(
                    path=str(fpath),
                    clip={
                        "x": bbox["x"], "y": bbox["y"],
                        "width": bbox["width"], "height": bbox["height"],
                    },
                )
            except SoftTimeLimitExceeded:
                raise
            except Exception as exc:  # noqa: BLE001 - screenshot error
                logger.warning("screenshot failed at step %d: %s", step, exc)
                break

            candidates.append(
                Candidate(
                    cell_id=cell_id,
                    competitor_id=competitor_id,
                    source_url=source_url,
                    source_type=self.source_type,
                    title=f"{platform.title()} demo – step {step + 1}",
                    snippet=f"Interactive demo frame {step + 1} from {platform}.",
                    text_content=(
                        f"Demo step {step + 1} of a guided {platform} product tour. "
                        f"capture_context: guided_demo"
                    ),
                    image_path=str(fpath),
                    rights_status="embedded_third_party",
                    evidence_type_hint=EvidenceType.OBSERVED,
                )
            )

            # Try to advance to the next step.
            if step + 1 < max_frames:
                advanced = self._try_advance(page, iframe_el)
                if not advanced:
                    break  # No "next" found; tour is over or structure unknown.
                time.sleep(_STEP_WAIT_S)

        return candidates

    def _try_advance(self, page, iframe_el) -> bool:
        """Try to click a 'next' button inside or near the iframe.

        Returns True if a click was attempted (regardless of whether the demo
        actually advanced), False if no suitable button was found.
        """
        # Try clicking within the iframe's frame context first.
        try:
            frame = iframe_el.content_frame()
            if frame:
                for sel in _NEXT_SELECTORS:
                    btn = frame.query_selector(sel)
                    if btn:
                        btn.click()
                        return True
        except SoftTimeLimitExceeded:
            raise
        except Exception:  # noqa: BLE001
            pass

        # Fallback: keyboard ArrowRight on the page (some demos respond to it).
        try:
            page.keyboard.press("ArrowRight")
            return True
        except SoftTimeLimitExceeded:
            raise
        except Exception:  # noqa: BLE001
            pass

        return False


# ---------------------------------------------------------------------------
# Standalone viewport capture (used by the pipeline's near-threshold rescore).
#
# A text candidate that already reads as the RIGHT product but has no image is
# capped on fidelity/evidence_directness and dies just under the floor. This
# gives the pipeline a way to screenshot such a URL and re-score it in image
# mode, without routing it through the interactive_demo bucket (which would
# change its source_type and subject it to the official-source product gate).
# ---------------------------------------------------------------------------

# A desktop viewport: the default 800x600 crops real product UI out of frame.
_RESCORE_VIEWPORT = {"width": 1440, "height": 900}

# Cap on waiting for the page to settle after DOM ready.
_SETTLE_TIMEOUT_MS = 3_000

# A PNG below this is a blank/error render, not a page. Observed: a failed load
# shot 4 KB, a nav-bar-only shot 43 KB, a real content page 416 KB.
_MIN_USEFUL_PNG_BYTES = 20_000

# Cookie/consent overlays cover the whole viewport on EU-facing doc sites, so
# without dismissing them every screenshot is a picture of a consent dialog.
_CONSENT_SELECTORS = (
    "#onetrust-accept-btn-handler",
    "button#truste-consent-button",
    "button[aria-label='Accept all']",
    "button[aria-label='Accept All']",
    "[data-testid='cookie-accept']",
)


def _dismiss_consent(page) -> None:
    """Best-effort click on a cookie/consent accept button. Never raises."""
    for sel in _CONSENT_SELECTORS:
        try:
            btn = page.query_selector(sel)
            if btn is not None and btn.is_visible():
                btn.click(timeout=1_000)
                return
        except SoftTimeLimitExceeded:
            raise
        except Exception:  # noqa: BLE001 — overlay handling is opportunistic
            continue


def _wait_for_page_settle(page) -> None:
    """Give dynamic content a bounded chance to paint after DOM ready."""
    try:
        page.wait_for_load_state("networkidle", timeout=_SETTLE_TIMEOUT_MS)
    except SoftTimeLimitExceeded:
        raise
    except Exception:  # noqa: BLE001 — a busy page is still screenshotable
        page.wait_for_timeout(_SETTLE_TIMEOUT_MS)


def capture_page_screenshots(urls: list[str]) -> dict[str, str]:
    """Screenshot each URL's viewport. Returns {url: png_path} for successes.

    Best-effort: a URL that fails to load or shoot is simply absent from the
    result. Never raises — a failed capture must leave the original text-mode
    score standing, not break the probe.
    """
    if not urls:
        return {}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error(
            "Playwright not installed. Run: playwright install chromium --with-deps"
        )
        return {}

    from uuid import uuid4

    shot_dir = Path(settings.assets_dir) / "rescore_frames"
    shot_dir.mkdir(parents=True, exist_ok=True)

    out: dict[str, str] = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True, timeout=_BROWSER_LAUNCH_TIMEOUT_MS
        )
        try:
            for url in urls:
                if not _looks_like_url(url):
                    continue
                page = browser.new_page(viewport=_RESCORE_VIEWPORT)
                _configure_page_timeouts(page)
                try:
                    page.goto(
                        url, wait_until="domcontentloaded", timeout=_GOTO_TIMEOUT_MS
                    )
                    _dismiss_consent(page)
                    # Let above-the-fold images/lazy blocks paint. networkidle
                    # never settles on ad-heavy pages, so cap the wait instead.
                    _wait_for_page_settle(page)
                    fpath = shot_dir / f"{uuid4().hex[:8]}_rescore.png"
                    # full_page: the UI screenshot we want usually sits BELOW the
                    # fold (the fold is nav + hero + cookie banner). A viewport
                    # shot of a doc page shows chrome, not the product.
                    page.screenshot(path=str(fpath), full_page=True)
                    if fpath.stat().st_size < _MIN_USEFUL_PNG_BYTES:
                        # Near-blank render (paywall, JS-only shell, load error).
                        # Absent from the result → the text score stands.
                        logger.info("rescore screenshot too empty for %s", url)
                        continue
                    out[url] = str(fpath)
                except SoftTimeLimitExceeded:
                    raise
                except Exception as exc:  # noqa: BLE001 — per-URL, keep going
                    logger.warning("rescore screenshot failed for %s: %s", url, exc)
                finally:
                    _close_playwright_resource(page, "page")
        finally:
            _close_playwright_resource(browser, "browser")
    return out
