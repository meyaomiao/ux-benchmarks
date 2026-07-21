from uuid import UUID
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict, Field


class GridCellBase(BaseModel):
    jtbd: str
    journey_stage: str
    page_state: str
    value_score: float = Field(default=0.5, ge=0.0, le=1.0)


class GridCellCreate(GridCellBase):
    cell_key: Optional[str] = None  # auto-generated if not provided


class GridCellUpdate(BaseModel):
    # Only value_score and status are patchable via API.
    # jtbd/journey_stage changes require SPLIT (issue #36).
    value_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    status: Optional[str] = None  # active | deprecated


class GridCellRead(GridCellBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cell_key: str
    version: int
    status: str
    requires_review: bool
    created_at: datetime
    updated_at: datetime


class GridCellListResponse(BaseModel):
    items: list[GridCellRead]
    total: int
    limit: int
    offset: int
    has_next: bool


class CellChangelogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cell_id: UUID
    operation: str
    changed_by: Optional[str] = None
    change_note: Optional[str] = None
    previous_values: Optional[Any] = None
    created_at: datetime
