import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Integer, Boolean, Float, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import TimestampMixin


class Asset(TimestampMixin, Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    cell_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grid_cells.id"), nullable=False
    )
    competitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("competitor_entities.id"), nullable=False
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    product_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rights_status: Mapped[str] = mapped_column(String, nullable=False)
    media_disposition: Mapped[str] = mapped_column(String, nullable=False)
    evidence_type: Mapped[str] = mapped_column(String, nullable=False)
    capture_context: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    native_step: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    native_step_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mapped_journey_stage: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    completeness: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    supersedes: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id"), nullable=True
    )
    is_superseded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    ai_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_score_breakdown: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    cell: Mapped["GridCell"] = relationship("GridCell")  # type: ignore[name-defined]
    competitor: Mapped["CompetitorEntity"] = relationship("CompetitorEntity")  # type: ignore[name-defined]


class SourceRegistry(TimestampMixin, Base):
    __tablename__ = "source_registry"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    source_url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    competitor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("competitor_entities.id"), nullable=True
    )
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    supporting_cells: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list, server_default=text("'[]'::jsonb"))
    last_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    competitor: Mapped[Optional["CompetitorEntity"]] = relationship("CompetitorEntity")  # type: ignore[name-defined]
