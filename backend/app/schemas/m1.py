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


# ---------------------------------------------------------------------------
# AI grid generation schemas
# ---------------------------------------------------------------------------

class GridGenerationRequest(BaseModel):
    category: str = Field(
        min_length=1, max_length=200,
        description='产品品类或具体产品名称，如"项目管理工具"或"Linear"',
    )
    known_products: list[str] = Field(
        default_factory=list,
        description="可选：已知竞品名称，帮助 AI 聚焦",
    )
    language: str = Field(default="zh", description="返回语言 zh=中文 en=英文")


class GeneratedCell(BaseModel):
    jtbd: str
    journey_stage: str
    page_state: str  # short label (<=10 chars), used in search queries
    # Full scenario description — feeds the mapping-card intent (used for AI
    # relevance scoring), NOT the search query. Keeps search terms clean.
    scenario_detail: str = ""
    value_score: float = Field(default=0.5, ge=0.0, le=1.0)


class GridGenerationResponse(BaseModel):
    category: str
    jtbd_tasks: list[str]
    journey_stages: list[str]
    cells: list[GeneratedCell]
    total: int
    generated_by: str  # "gpt" | "mock"
