from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Queue schemas (probe queue — #14)
# ---------------------------------------------------------------------------

class QueueItemRead(BaseModel):
    """A (cell x competitor) coverage snapshot as it appears in the probe queue."""

    id: UUID
    cell_id: UUID
    competitor_id: UUID
    status: str
    probe_cycles: int
    last_probed_at: Optional[datetime] = None
    tier: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class QueueListResponse(BaseModel):
    items: list[QueueItemRead]
    total: int


class PinRequest(BaseModel):
    """Force-enqueue a (cell x competitor) pair (trigger = MANUAL_PIN)."""

    cell_id: UUID
    competitor_id: UUID


# ---------------------------------------------------------------------------
# Source Registry schemas (dedup index)
# ---------------------------------------------------------------------------

class SourceRegistryRead(BaseModel):
    id: UUID
    source_url: str
    competitor_id: Optional[UUID] = None
    discovered_at: datetime
    supporting_cells: list = []
    last_fetched_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SourceRegistryListResponse(BaseModel):
    items: list[SourceRegistryRead]
    total: int
    limit: int
    offset: int
    has_next: bool


# ---------------------------------------------------------------------------
# Query expansion schemas (M3 collection)
# ---------------------------------------------------------------------------

class QueryBundle(BaseModel):
    """Bucketed multi-query bundle for a single grid cell.

    Each bucket targets a different source type so downstream collectors can
    route queries to the right search surface (help centres, demo galleries,
    video platforms, community/forum sites, or generic web search).
    """

    help_docs: list[str] = []
    interactive_demo: list[str] = []
    video: list[str] = []
    community: list[str] = []
    generic: list[str] = []

    def all(self) -> list[str]:
        """Flatten every bucket into one deduplicated list, preserving order."""
        seen: set[str] = set()
        ordered: list[str] = []
        for bucket in (
            self.help_docs,
            self.interactive_demo,
            self.video,
            self.community,
            self.generic,
        ):
            for query in bucket:
                if query not in seen:
                    seen.add(query)
                    ordered.append(query)
        return ordered


# ---------------------------------------------------------------------------
# Probe observability
# ---------------------------------------------------------------------------

class ProbeRunRead(BaseModel):
    id: UUID
    project_id: UUID
    cell_id: UUID
    competitor_id: UUID
    probe_cycle: Optional[int] = None
    strategy_version: str
    outcome: str
    final_state: Optional[str] = None
    candidates_found: int
    scored_count: int
    passed_count: int
    persisted_count: int
    search_calls: int
    browser_pages: int
    scoring_calls: int
    agentic_model_calls: int
    duration_ms: int
    source_budgets: Optional[dict] = None
    source_stats: Optional[dict] = None
    agentic_stats: Optional[dict] = None
    agentic_trace: Optional[list] = None
    error_type: Optional[str] = None
    started_at: datetime
    finished_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProbeRunListResponse(BaseModel):
    items: list[ProbeRunRead]
    total: int
    limit: int
    offset: int
    has_next: bool


class ProbeRunSummary(BaseModel):
    strategy_version: str
    runs: int
    runs_with_passers: int
    candidates_found: int
    scored_count: int
    passed_count: int
    persisted_count: int
    run_success_rate: float
    candidate_pass_rate: float
    candidate_persist_rate: float
    avg_duration_ms: float
    avg_search_calls: float
    avg_browser_pages: float
    avg_scoring_calls: float
    avg_agentic_model_calls: float
    avg_model_calls: float
