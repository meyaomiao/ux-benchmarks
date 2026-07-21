import uuid
from typing import Optional
from sqlalchemy import String, Integer, Boolean, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import TimestampMixin


class MappingCard(TimestampMixin, Base):
    __tablename__ = "mapping_cards"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    cell_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grid_cells.id"), unique=True, nullable=False
    )
    intent_definition: Mapped[str] = mapped_column(String(150), nullable=False)
    inclusion_criteria: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    exclusion_criteria: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    anchor_screenshot_asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", use_alter=True, name="fk_mapping_card_anchor_asset"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    created_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_complete: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        server_default=text("NULL"),
        comment="Computed: intent_definition IS NOT NULL AND anchor_screenshot_asset_id IS NOT NULL",
    )

    cell: Mapped["GridCell"] = relationship("GridCell")  # type: ignore[name-defined]
