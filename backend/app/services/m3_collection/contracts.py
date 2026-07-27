"""Shared contracts for the collection pipeline: adapters -> scorer -> shortlist.

These types are the fixed interface between:
  - adapters (#17 help docs, #18 interactive demo, ...) which PRODUCE Candidates
  - the AI scorer (#19) which CONSUMES a Candidate + MappingCard and returns a Score
  - dedup/shortlist (#20) which ranks scored candidates

Keeping them in one module means an adapter and the scorer can be built
independently without drifting on field names.

Design note: real implementations hit the network (httpx/Playwright) and Claude
Vision. Both sit behind the Protocols below and have mock fallbacks so the whole
chain runs offline / without an API key (mirrors the frontend mock mode).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional, Protocol
from uuid import UUID, uuid4


class SourceType(StrEnum):
    HELP_DOCS = "help_docs"
    INTERACTIVE_DEMO = "interactive_demo"
    VIDEO = "video"
    COMMUNITY = "community"
    GENERIC = "generic"


class EvidenceType(StrEnum):
    """How direct the evidence is. observed > claimed > inferred.

    (Graded by directness — see docs/theory-grounding.md; anchored to
    GRADE-directness / hearsay distinction, NOT the EBM study-design pyramid.)
    """
    OBSERVED = "observed"     # we can see the actual UI/state in the artifact
    CLAIMED = "claimed"       # vendor asserts it (marketing/pricing copy) — no UI shown
    INFERRED = "inferred"     # deduced from indirect signals


@dataclass
class Candidate:
    """One piece of raw evidence produced by an adapter, before human accept.

    An adapter fills the capture fields; the scorer fills nothing here (it emits
    a separate Score). `image_path`/`text_content` are what the scorer inspects.
    """
    cell_id: UUID
    competitor_id: UUID
    source_url: str
    source_type: SourceType
    title: str = ""
    snippet: str = ""
    text_content: str = ""          # extracted region/page text the scorer reads
    image_path: Optional[str] = None  # screenshot path the scorer inspects (VLM)
    product_version: Optional[str] = None
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    candidate_id: UUID = field(default_factory=uuid4)
    # provenance / rights hints the adapter can pre-fill (finalised at accept time)
    rights_status: str = "unknown"
    evidence_type_hint: EvidenceType = EvidenceType.INFERRED


@dataclass
class RubricBreakdown:
    """Per-dimension sub-scores (0-1). See spec §6 AI relevance rubric."""
    state_match: float = 0.0      # shows the target page/state UI (not just mentions it)
    product_match: float = 0.0    # is the target product, not a competitor/generic
    version_recency: float = 0.0  # current UI generation vs stale
    evidence_directness: float = 0.0  # observed vs claimed
    fidelity: float = 0.0         # resolution/clarity good enough to be a benchmark asset


@dataclass
class Score:
    """The scorer's verdict on one Candidate against a cell's mapping card."""
    candidate_id: UUID
    score: float                      # 0-1 overall relevance
    passed: bool                      # score >= threshold
    evidence_type: EvidenceType
    rubric: RubricBreakdown
    reasoning: str = ""               # short human-readable justification
    scored_by: str = "mock"           # "claude-vision" | "mock"


# Default relevance floor (spec §6): below this, a candidate is dropped and
# never reaches the human shortlist.
RELEVANCE_FLOOR = 0.55


class Adapter(Protocol):
    """Produces Candidates for a (cell, competitor) from a set of queries."""
    source_type: SourceType

    def fetch(
        self,
        cell_id: UUID,
        competitor_id: UUID,
        queries: list[str],
        *,
        limit: int = 10,
    ) -> list[Candidate]:
        ...


class Scorer(Protocol):
    """Scores one Candidate against the cell's mapping-card intent + anchor."""

    def score(
        self,
        candidate: Candidate,
        *,
        intent_definition: str,
        inclusion_criteria: str = "",
        exclusion_criteria: str = "",
        anchor_image_path: Optional[str] = None,
        product_name: str = "",
    ) -> Score:
        ...
