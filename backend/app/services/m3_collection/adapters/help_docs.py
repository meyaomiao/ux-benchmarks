"""Help-docs collection adapter (#17).

Produces `Candidate`s from third-party help / documentation pages for a given
(cell, competitor) and a set of queries. It implements the `Adapter` Protocol
from `..contracts` and always sets `source_type = SourceType.HELP_DOCS`.

Two modes, selected by `settings.use_collection_mock`:

  * mock (default ON): `_mock_fetch` synthesises 2-3 deterministic fixture
    Candidates from the queries with NO network access, so the whole collection
    chain can run offline / in CI.
  * live (flag OFF): `_live_fetch` uses httpx + BeautifulSoup to fetch and parse
    real help pages.

Screenshots: real screenshotting needs a browser (Playwright) and is out of
scope for this issue — that belongs to #18. Here we always set
`image_path=None` and rely on `text_content`; help docs are text-rich, so the
scorer has enough to work with from text alone.

Rights: help docs are third-party official material, so `rights_status` is
always "third_party_official".

Evidence-type heuristic (kept deliberately simple, see `_classify_evidence`):
help docs *can* be OBSERVED (they show real step-by-step UI in text/screenshots)
but since we only capture text here we are conservative — text that reads like a
step-by-step doc is treated as OBSERVED, otherwise (marketing-like copy) CLAIMED.
"""
from __future__ import annotations

import logging
from urllib.parse import quote_plus, urlparse
from uuid import UUID

from app.core.config import settings

from ..contracts import Candidate, EvidenceType, SourceType
from ..content_fetch import fetch_many

logger = logging.getLogger(__name__)

# How much extracted page text we keep as `text_content` / `snippet`.
_TEXT_CONTENT_CHARS = 500
_SNIPPET_CHARS = 160

# Live-mode HTTP settings. A realistic UA reduces trivial bot-blocking; the
# timeout keeps a slow/hung server from stalling the whole collection run.
_HTTP_TIMEOUT_SECONDS = 6.0
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0 Safari/537.36 ux-benchmarks-collector/1.0"
)

# Words that make a doc read like a task-oriented, step-by-step guide (=> we can
# treat the text as OBSERVED evidence of real UI/steps). Anything else is copy
# we can only take as CLAIMED. Deliberately a tiny keyword heuristic — the AI
# scorer (#19) makes the real call; this is only a pre-fill hint.
_STEP_MARKERS = (
    "step", "click", "select", "navigate", "go to", "choose",
    "how to", "setup", "set up", "configure", "enable", "settings",
)


def _classify_evidence(text: str) -> EvidenceType:
    """OBSERVED if the text reads like a step-by-step doc, else CLAIMED.

    Conservative on purpose: we only captured text (no screenshot), so we never
    over-claim. See module docstring.
    """
    lowered = text.lower()
    if any(marker in lowered for marker in _STEP_MARKERS):
        return EvidenceType.OBSERVED
    return EvidenceType.CLAIMED


def _looks_like_url(query: str) -> bool:
    """True if a query string is an http(s) URL we could fetch in live mode."""
    parsed = urlparse(query.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


class HelpDocsAdapter:
    """Adapter that turns queries into help-doc `Candidate`s.

    Satisfies the `Adapter` Protocol in `..contracts`.
    """

    source_type: SourceType = SourceType.HELP_DOCS

    def fetch(
        self,
        cell_id: UUID,
        competitor_id: UUID,
        queries: list[str],
        *,
        limit: int = 10,
    ) -> list[Candidate]:
        """Return up to `limit` help-doc Candidates for this (cell, competitor).

        Dispatches to the mock or live implementation based on
        `settings.use_collection_mock`.
        """
        if settings.use_collection_mock:
            return self._mock_fetch(cell_id, competitor_id, queries, limit=limit)
        return self._live_fetch(cell_id, competitor_id, queries, limit=limit)

    def _mock_fetch(
        self,
        cell_id: UUID,
        competitor_id: UUID,
        queries: list[str],
        *,
        limit: int,
    ) -> list[Candidate]:
        """Deterministic offline fixtures — no network.

        For the first ~3 queries we synthesise a Candidate with a plausible
        help.<domain>/docs URL, a title derived from the query, and a short fake
        doc paragraph mentioning the query terms. `image_path` stays None.
        Evidence-type is varied via the same heuristic used in live mode so the
        downstream chain sees a realistic mix.
        """
        candidates: list[Candidate] = []
        # Cap at 3 fixtures, then also honour the caller's limit.
        selected = [q for q in queries if q][: min(3, limit)]

        for idx, query in enumerate(selected):
            # Build a slug from the query's alphanumeric words for a stable URL.
            words = [w for w in query.replace("/", " ").split() if w.isalnum()]
            slug = "-".join(words[:6]).lower() or f"topic-{idx}"
            # A plausible third-party help domain, deterministic per index.
            domain = f"help.competitor{idx}.example.com"
            source_url = f"https://{domain}/docs/{slug}"

            title = f"{query.strip().title()} - Help Center"

            # Fake doc paragraph. Alternate between a step-like body and a
            # marketing-like body so `_classify_evidence` yields a varied mix
            # (OBSERVED for even indexes, CLAIMED for odd).
            if idx % 2 == 0:
                text_content = (
                    f"How to {query.strip()}: follow these steps. "
                    f"1. Navigate to the settings page. 2. Select the option "
                    f"related to {query.strip()}. 3. Click Save to configure it. "
                    "This walkthrough shows the current UI for the feature."
                )
            else:
                text_content = (
                    f"Our platform makes {query.strip()} effortless and delightful. "
                    f"Discover why teams love using {query.strip()} to get more done. "
                    "Learn more about the benefits on this overview page."
                )

            candidates.append(
                Candidate(
                    cell_id=cell_id,
                    competitor_id=competitor_id,
                    source_url=source_url,
                    source_type=self.source_type,
                    title=title,
                    snippet=text_content[:_SNIPPET_CHARS],
                    text_content=text_content[:_TEXT_CONTENT_CHARS],
                    image_path=None,  # no screenshots in this adapter (see #18)
                    product_version=None,
                    rights_status="third_party_official",
                    evidence_type_hint=_classify_evidence(text_content),
                )
            )

        return candidates

    def _live_fetch(
        self,
        cell_id: UUID,
        competitor_id: UUID,
        queries: list[str],
        *,
        limit: int,
    ) -> list[Candidate]:
        """Fetch + parse real help pages with httpx + BeautifulSoup.

        One fetch per query URL — no recursive crawling. Queries that are not
        http(s) URLs are skipped: this adapter does not integrate a search
        engine, so it cannot turn a search string (e.g. "site:help.* setup")
        into a page. Real search integration is out of scope for #17; upstream
        query expansion produces search operators, not URLs, so in practice
        live mode is only useful when callers pass concrete doc URLs.

        Network / parse errors are logged and skipped; the method returns
        whatever succeeded (possibly []).
        """
        # Concurrent main-content fetch: trafilatura extracts real doc body
        # (nav/footer stripped, 12s + retry), fetch_many runs all URLs in a
        # thread pool. Fixes both the nav-text-to-scorer bug and serial slowness.
        candidates: list[Candidate] = []
        urls = [q.strip() for q in queries if _looks_like_url(q)][: max(limit * 2, limit)]
        fetched = fetch_many(urls)  # {url: (title, text)}

        for url in urls:  # preserve search-rank order
            if len(candidates) >= limit:
                break
            got = fetched.get(url)
            if not got:
                continue  # SPA shell / binary / blocked — no usable text

            title, text = got
            candidates.append(
                Candidate(
                    cell_id=cell_id,
                    competitor_id=competitor_id,
                    source_url=url,
                    source_type=self.source_type,
                    title=title,
                    snippet=text[:_SNIPPET_CHARS],
                    text_content=text,
                    image_path=None,  # no screenshots in this adapter (see #18)
                    product_version=None,
                    rights_status="third_party_official",
                    evidence_type_hint=_classify_evidence(text),
                )
            )

        return candidates

    @staticmethod
    def _extract_version(soup, text: str) -> str | None:
        """Best-effort product/version extraction. Optional — None if not found.

        Looks for common version/last-updated meta tags, then a "Last updated"
        phrase in the body text. Intentionally shallow; a miss just means None.
        """
        for meta_name in ("version", "product-version", "og:updated_time", "article:modified_time"):
            tag = soup.find("meta", attrs={"name": meta_name}) or soup.find(
                "meta", attrs={"property": meta_name}
            )
            if tag and tag.get("content"):
                return tag["content"].strip()[:64]

        lowered = text.lower()
        marker = "last updated"
        pos = lowered.find(marker)
        if pos != -1:
            # Grab a short window after the marker as a human-readable hint.
            return text[pos : pos + 48].strip()

        return None
