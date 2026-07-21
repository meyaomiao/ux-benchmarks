from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Mapping Card schemas
# ---------------------------------------------------------------------------

class MappingCardBase(BaseModel):
    intent_definition: str = Field(max_length=150)
    inclusion_criteria: Optional[str] = None
    exclusion_criteria: Optional[str] = None
    anchor_screenshot_asset_id: Optional[UUID] = None
    created_by: Optional[str] = None
    reviewed_by: Optional[str] = None


class MappingCardCreate(MappingCardBase):
    cell_id: UUID


class MappingCardUpdate(BaseModel):
    intent_definition: Optional[str] = Field(default=None, max_length=150)
    inclusion_criteria: Optional[str] = None
    exclusion_criteria: Optional[str] = None
    anchor_screenshot_asset_id: Optional[UUID] = None
    reviewed_by: Optional[str] = None


class MappingCardRead(MappingCardBase):
    id: UUID
    cell_id: UUID
    version: int
    is_complete: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MappingCardListResponse(BaseModel):
    items: list[MappingCardRead]
    total: int
    limit: int
    offset: int
    has_next: bool
