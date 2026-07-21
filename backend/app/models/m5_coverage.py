import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Float, Integer, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import TimestampMixin


class CoverageSnapshot(TimestampMixin, Base):
    __tablename__ = "coverage_snapshots"
    __table_args__ = (
        UniqueConstraint("cell_id", "competitor_id", name="uq_coverage_cell_competitor"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    cell_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grid_cells.id"), nullable=False
    )
    competitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("competitor_entities.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    independent_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    latest_captured_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    coverage_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default=text("0.0"))
    probe_cycles: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    last_probed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    tier: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    evidence_type_breakdown: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
