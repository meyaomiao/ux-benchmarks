import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import TimestampMixin


class Observation(TimestampMixin, Base):
    __tablename__ = "observations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False
    )
    cell_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grid_cells.id"), nullable=False
    )
    competitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("competitor_entities.id"), nullable=False
    )
    surface_confirmed: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ui_elements_present: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list, server_default=text("'[]'::jsonb"))
    labels_verbatim: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list, server_default=text("'[]'::jsonb"))
    control_states: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    role_options_shown: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list, server_default=text("'[]'::jsonb"))
    sequence_context: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    capture_context: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    native_step: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    mapped_journey_stage: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    accepted_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    claims: Mapped[list["Claim"]] = relationship("Claim", back_populates="observation")


class Claim(TimestampMixin, Base):
    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("observations.id"), nullable=False
    )
    claim_type: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    observation: Mapped["Observation"] = relationship("Observation", back_populates="claims")
