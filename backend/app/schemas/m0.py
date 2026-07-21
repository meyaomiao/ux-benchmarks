from datetime import datetime, date
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Lexicon schemas
# ---------------------------------------------------------------------------

class LexiconEntryBase(BaseModel):
    term: str
    term_type: str
    language: str = "en"
    level: str
    valid_for_competitors: Optional[list] = None
    source: Optional[str] = None


class LexiconEntryCreate(LexiconEntryBase):
    pass


class LexiconEntryUpdate(BaseModel):
    term: Optional[str] = None
    term_type: Optional[str] = None
    language: Optional[str] = None
    level: Optional[str] = None
    valid_for_competitors: Optional[list] = None
    source: Optional[str] = None


class LexiconEntryRead(LexiconEntryBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LexiconListResponse(BaseModel):
    items: list[LexiconEntryRead]
    total: int
    limit: int
    offset: int
    has_next: bool


# ---------------------------------------------------------------------------
# Competitor schemas
# ---------------------------------------------------------------------------

class CompetitorBase(BaseModel):
    canonical_name: str
    aliases: Optional[list] = None
    parent_company: Optional[str] = None
    official_domain: Optional[str] = None
    help_center_domain: Optional[str] = None
    video_channels: Optional[list] = None
    app_store_pages: Optional[list] = None
    acquired_from: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    status: str = "confirmed"
    competitor_type: Optional[str] = None


class CompetitorCreate(CompetitorBase):
    pass


class CompetitorUpdate(BaseModel):
    canonical_name: Optional[str] = None
    aliases: Optional[list] = None
    parent_company: Optional[str] = None
    official_domain: Optional[str] = None
    help_center_domain: Optional[str] = None
    video_channels: Optional[list] = None
    app_store_pages: Optional[list] = None
    acquired_from: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    status: Optional[str] = None
    competitor_type: Optional[str] = None


class CompetitorRead(CompetitorBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CompetitorListResponse(BaseModel):
    items: list[CompetitorRead]
    total: int
    limit: int
    offset: int
    has_next: bool
