"""Multi-source web adapter — collects from community / knowledge / generic web.

The user asked from day one to gather evidence beyond official sites: forums,
Q&A, knowledge communities, blogs, review sites, social. The query bundle
already produces `community` / `video` / `generic` buckets, but nothing consumed
them. This adapter does: parameterised by source_type, it consumes the matching
bucket, resolves queries → URLs, and fetches MAIN text via the shared
content_fetch (nav/footer stripped) so the scorer sees real content.

One class, instantiated per source_type:
    WebSourceAdapter(SourceType.COMMUNITY)   # forums / Q&A / knowledge communities
    WebSourceAdapter(SourceType.GENERIC)     # blogs / articles / everything else
"""
from __future__ import annotations

import logging
from uuid import UUID

from app.core.config import settings
from app.services.m3_collection.contracts import Candidate, EvidenceType, SourceType
from app.services.m3_collection.content_fetch import fetch_main_text

logger = logging.getLogger(__name__)

# Text that reads like a concrete walkthrough → OBSERVED, else CLAIMED.
_STEP_MARKERS = (
    "step 1", "step 2", "click", "select", "navigate", "go to", "tap",
    "第一步", "第二步", "点击", "选择", "进入", "打开", "设置",
    "how to", "follow these", "here's how",
)


def _classify(text: str) -> EvidenceType:
    lowered = text.lower()
    return EvidenceType.OBSERVED if any(m in lowered for m in _STEP_MARKERS) else EvidenceType.CLAIMED


class WebSourceAdapter:
    """Fetches main-content evidence for one source_type bucket."""

    def __init__(self, source_type: SourceType):
        self.source_type = source_type

    def fetch(
        self,
        cell_id: UUID,
        competitor_id: UUID,
        queries: list[str],
        limit: int = 5,
    ) -> list[Candidate]:
        # Mock mode: adapters return nothing here (fixtures live elsewhere); the
        # real value of this adapter is live fetching. Keep it a no-op offline.
        if settings.use_collection_mock:
            return []

        # `queries` are already resolved to URLs by the pipeline (it calls
        # resolve_queries_to_urls before invoking adapters in live mode).
        candidates: list[Candidate] = []
        for url in queries:
            if len(candidates) >= limit:
                break
            if not url.startswith("http"):
                continue
            try:
                got = fetch_main_text(url)
            except Exception as exc:  # noqa: BLE001
                logger.debug("web_source fetch failed %s: %s", url[:60], exc)
                continue
            if not got:
                continue  # SPA shell / binary / blocked — skip
            title, text = got
            candidates.append(
                Candidate(
                    cell_id=cell_id,
                    competitor_id=competitor_id,
                    source_url=url,
                    source_type=self.source_type,
                    title=title,
                    snippet=text[:160],
                    text_content=text,
                    image_path=None,
                    rights_status="third_party",
                    evidence_type_hint=_classify(text),
                )
            )
        return candidates
