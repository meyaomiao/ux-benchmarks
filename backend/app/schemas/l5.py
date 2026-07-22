"""Pydantic schemas for L5 report endpoints."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ReportCompose(BaseModel):
    """Request body for POST /reports."""
    insight_ids: list[UUID] = Field(..., min_length=1, max_length=20)
    audience: str = Field("designer", pattern="^(management|designer|pm)$")
    format_type: str = Field(
        "review_15min",
        pattern="^(summary_5min|review_15min|onepager|full)$",
    )
    title: Optional[str] = Field(None, max_length=200)


class ReportRead(BaseModel):
    """Response schema for a single report."""
    id: UUID
    title: str
    audience: str
    format_type: str
    source_insight_ids: list[str]
    body_markdown: str
    generated_by: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
