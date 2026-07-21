import uuid
from typing import Optional
from sqlalchemy import String, Float, Integer, Boolean, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import TimestampMixin


class GridCell(TimestampMixin, Base):
    __tablename__ = "grid_cells"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    cell_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    jtbd: Mapped[str] = mapped_column(String, nullable=False)
    journey_stage: Mapped[str] = mapped_column(String, nullable=False)
    page_state: Mapped[str] = mapped_column(String, nullable=False)
    value_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.5, server_default=text("0.5"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    status: Mapped[str] = mapped_column(String, nullable=False, default="active", server_default=text("'active'"))
    requires_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))

    changelogs: Mapped[list["CellChangelog"]] = relationship("CellChangelog", back_populates="cell")


class CellChangelog(TimestampMixin, Base):
    __tablename__ = "cell_changelogs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    cell_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grid_cells.id"), nullable=False
    )
    operation: Mapped[str] = mapped_column(String, nullable=False)
    changed_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    change_note: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    previous_values: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    cell: Mapped["GridCell"] = relationship("GridCell", back_populates="changelogs")
