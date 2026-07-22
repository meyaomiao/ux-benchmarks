from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ShortlistItem(BaseModel):
    id: UUID
    cell_id: UUID
    competitor_id: UUID
    source_url: str
    # source_type, title, snippet are not yet columns on Asset; they default to
    # None here so from_attributes mode does not blow up when an ORM Asset is
    # passed that lacks these attributes (they are placeholders for future columns
    # or view-layer enrichment by the route handler).
    source_type: Optional[str] = None
    title: Optional[str] = None
    snippet: Optional[str] = None
    evidence_type: str
    ai_score: Optional[float] = None
    ai_score_breakdown: Optional[dict] = None
    rights_status: str
    media_disposition: str
    captured_at: datetime
    image_path_available: bool

    model_config = ConfigDict(from_attributes=True)


class ShortlistResponse(BaseModel):
    items: list[ShortlistItem]
    total: int


class AcceptRequest(BaseModel):
    asset_id: UUID
    # Free-form key-value pairs that the reviewer filled in for the Observation.
    # Known Observation column names are applied via setattr; unknown keys are
    # silently ignored.
    observation_fields: dict = {}


class RejectRequest(BaseModel):
    asset_id: UUID
    reason: Optional[str] = None


class FlagRequest(BaseModel):
    asset_id: UUID
    note: Optional[str] = None


class ObservationRead(BaseModel):
    id: UUID
    asset_id: UUID
    cell_id: UUID
    competitor_id: UUID
    surface_confirmed: Optional[str] = None
    accepted_by: Optional[str] = None
    accepted_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# L3 Insight schemas
# ---------------------------------------------------------------------------

class InsightGenerateRequest(BaseModel):
    cell_id: UUID
    competitor_id: UUID


class InsightRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cell_id: UUID
    competitor_id: UUID
    claim: str
    analysis: Optional[str] = None
    recommendation: Optional[str] = None
    design_principle: Optional[str] = None
    limits: Optional[str] = None
    source_observation_ids: list = []
    confidence: str
    generated_by: str
    is_draft: bool
    created_at: datetime
    updated_at: datetime


class InsightUpdate(BaseModel):
    claim: Optional[str] = None
    analysis: Optional[str] = None
    recommendation: Optional[str] = None
    design_principle: Optional[str] = None
    limits: Optional[str] = None
    confidence: Optional[str] = None
    is_draft: Optional[bool] = None
