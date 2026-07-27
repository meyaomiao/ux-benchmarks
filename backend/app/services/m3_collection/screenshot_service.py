"""Manual screenshot service — capture any URL via Playwright and persist as Asset.

Unlike the collection pipeline (which runs async via Celery and requires a
mapping card), this is a synchronous best-effort capture intended for manual
URL submission from the UI:

  1. User pastes a competitor page URL into the collect page.
  2. We launch a headless browser, navigate, screenshot the viewport.
  3. We extract visible text to supplement the image (dual-mode scoring).
  4. We create a Candidate + a "manually submitted" Score (score=0.8, OBSERVED)
     and persist via asset_store.persist_candidate().
  5. The Asset lands in the shortlist (status SHORTLIST_READY via coverage) so
     the user can review it in /review immediately.

Playwright must be installed: `playwright install chromium --with-deps`.
The import is lazy so mock mode (settings.use_collection_mock) has no hard
dependency on it — a synthetic PNG is used instead.
"""
from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.m3_collection import Asset
from app.services.m3_collection.asset_store import persist_candidate
from app.services.m3_collection.contracts import (
    Candidate, EvidenceType, RubricBreakdown, Score, SourceType,
)
from app.services.m3_collection.adapters.interactive_demo import (
    _BROWSER_LAUNCH_TIMEOUT_MS,
    _close_playwright_resource,
    _configure_page_timeouts,
    _make_png,
)

logger = logging.getLogger(__name__)

_SCREENSHOT_DIR = "manual_screenshots"
_VIEWPORT = {"width": 1440, "height": 900}
_TIMEOUT_MS = 25_000
_TEXT_CHARS = 800


def _url_slug(url: str) -> str:
    """Short stable slug from a URL for use in filenames."""
    return hashlib.sha1(url.encode()).hexdigest()[:10]


def _manual_score(candidate: Candidate) -> Score:
    """Produce a 'manually submitted, assumed relevant' Score.

    We don't run the AI scorer here — the human submitted this URL so we
    treat it as high-confidence OBSERVED evidence. The user then confirms
    or rejects it via the /review page.
    """
    return Score(
        candidate_id=candidate.candidate_id,
        score=0.8,
        passed=True,
        evidence_type=EvidenceType.OBSERVED,
        rubric=RubricBreakdown(
            state_match=0.8,
            product_match=0.9,
            version_recency=0.7,
            evidence_directness=0.9,
            fidelity=0.8,
        ),
        reasoning="手动提交的 URL，由用户确认为相关证据，已跳过 AI 评分直接进入审核队列。",
        scored_by="manual",
    )


def _mock_capture(
    url: str,
    cell_id: UUID,
    competitor_id: UUID,
    screenshot_dir: Path,
) -> Candidate:
    """Mock capture: write a tiny coloured PNG and return a Candidate."""
    slug = _url_slug(url)
    fpath = screenshot_dir / f"manual_mock_{slug}.png"
    fpath.write_bytes(_make_png(64, 40, (80, 120, 200)))
    return Candidate(
        cell_id=cell_id,
        competitor_id=competitor_id,
        source_url=url,
        source_type=SourceType.INTERACTIVE_DEMO,
        title=f"手动截图（mock）— {url[:60]}",
        snippet="[mock 模式] 模拟截图，不含真实内容。",
        text_content="[mock mode] simulated screenshot, no real content.",
        image_path=str(fpath),
        rights_status="third_party_official",
        evidence_type_hint=EvidenceType.OBSERVED,
    )


def _playwright_capture(
    url: str,
    cell_id: UUID,
    competitor_id: UUID,
    screenshot_dir: Path,
) -> Candidate:
    """Navigate to URL with Playwright and screenshot the viewport."""
    from playwright.sync_api import sync_playwright

    slug = _url_slug(url)
    session_id = uuid4().hex[:6]
    fpath = screenshot_dir / f"manual_{session_id}_{slug}.png"

    title = ""
    text_content = ""

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True, timeout=_BROWSER_LAUNCH_TIMEOUT_MS
        )
        page = None
        try:
            page = browser.new_page(viewport=_VIEWPORT)
            _configure_page_timeouts(page)
            page.goto(url, wait_until="domcontentloaded", timeout=_TIMEOUT_MS)
            # Give JS-heavy pages a moment to render.
            time.sleep(1.5)

            title = page.title() or url
            # Extract visible text from main content area.
            try:
                text_content = page.evaluate("""() => {
                    const sel = ['main', 'article', '[role="main"]', 'body'];
                    for (const s of sel) {
                        const el = document.querySelector(s);
                        if (el) return el.innerText.slice(0, 1200);
                    }
                    return document.body.innerText.slice(0, 1200);
                }""") or ""
            except Exception:
                pass

            page.screenshot(path=str(fpath), full_page=False)
        finally:
            if page is not None:
                _close_playwright_resource(page, "page")
            _close_playwright_resource(browser, "browser")

    return Candidate(
        cell_id=cell_id,
        competitor_id=competitor_id,
        source_url=url,
        source_type=SourceType.INTERACTIVE_DEMO,
        title=title[:200],
        snippet=text_content[:160],
        text_content=text_content[:_TEXT_CHARS],
        image_path=str(fpath),
        rights_status="third_party_official",
        evidence_type_hint=EvidenceType.OBSERVED,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def capture_url(
    db: Session,
    url: str,
    cell_id: UUID,
    competitor_id: UUID,
) -> Asset:
    """Take a Playwright screenshot of `url` and persist it as a shortlist Asset.

    In mock mode, produces a synthetic PNG instead of hitting the network.
    Raises on any unrecoverable error (caller should return 500).
    """
    screenshot_dir = Path(settings.assets_dir) / _SCREENSHOT_DIR
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    if settings.use_collection_mock:
        candidate = _mock_capture(url, cell_id, competitor_id, screenshot_dir)
    else:
        try:
            candidate = _playwright_capture(url, cell_id, competitor_id, screenshot_dir)
        except ImportError:
            raise RuntimeError(
                "Playwright not installed. Run: playwright install chromium --with-deps"
            )
        except Exception as exc:
            logger.warning("screenshot capture failed for %s: %s", url, exc)
            raise RuntimeError(f"截图失败：{exc}") from exc

    score = _manual_score(candidate)
    asset, _created = persist_candidate(db, candidate, score)
    return asset
