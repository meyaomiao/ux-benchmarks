"""Adapter for bounded AI-guided exploration of trusted competitor sites."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from billiard.exceptions import SoftTimeLimitExceeded

from app.core.config import settings
from app.services.m3_collection.agentic_site import (
    ExplorerResult,
    ExplorerStats,
    explore_competitor_site,
)
from app.services.m3_collection.contracts import Candidate, EvidenceType, SourceType


class AgenticSiteAdapter:
    """Convert AI-saved official pages into candidates for the existing scorer."""

    source_type = SourceType.AGENTIC_SITE
    uses_search_queries = False

    def __init__(
        self,
        *,
        competitor_name: str,
        intent: str,
        official_domain: str | None,
        help_center_domain: str | None,
        explorer: Callable[..., ExplorerResult] = explore_competitor_site,
    ) -> None:
        self._competitor_name = competitor_name
        self._intent = intent
        self._official_domain = official_domain
        self._help_center_domain = help_center_domain
        self._explorer = explorer
        self.last_stats = ExplorerStats(stop_reason="not_run").to_dict()

    def fetch(
        self,
        cell_id: UUID,
        competitor_id: UUID,
        queries: list[str],
        *,
        limit: int = 10,
    ) -> list[Candidate]:
        del queries
        if settings.use_collection_mock:
            self.last_stats = ExplorerStats(stop_reason="mock_mode").to_dict()
            return []

        try:
            result = self._explorer(
                competitor_name=self._competitor_name,
                intent=self._intent,
                official_domain=self._official_domain,
                help_center_domain=self._help_center_domain,
            )
        except SoftTimeLimitExceeded:
            self.last_stats = ExplorerStats(stop_reason="soft_time_limit").to_dict()
            raise
        except Exception:
            self.last_stats = ExplorerStats(stop_reason="adapter_failure").to_dict()
            raise
        self.last_stats = result.stats.to_dict()
        return [
            Candidate(
                cell_id=cell_id,
                competitor_id=competitor_id,
                source_url=page.source_url,
                source_type=self.source_type,
                title=page.title,
                snippet=page.text_content[:160],
                text_content=page.text_content,
                image_path=page.image_path,
                rights_status="third_party_official",
                evidence_type_hint=EvidenceType.OBSERVED,
            )
            for page in result.pages[:limit]
        ]
