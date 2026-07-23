"""L3 Insight — structured output from analysing why a product excels in a scenario.

Each insight is the product of analysing accepted observations against a cell's
mapping card intent, using Claude to articulate:
  - WHAT was observed (claim, must be falsifiable)
  - WHY it works (analysis — mechanism + cost reduction)
  - WHAT TO DO (recommendation — specific action for internal product)
  - THE PRINCIPLE (design_principle — brand-stripped, reusable)
  - WHEN NOT TO (limits — applicability constraints)
"""
import uuid
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class Insight(TimestampMixin, Base):
    __tablename__ = "insights"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    cell_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grid_cells.id"), nullable=False
    )
    competitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("competitor_entities.id"), nullable=False
    )

    # Core claim — must be falsifiable: scenario + pattern + observable result + mechanism.
    # See docs/collection-phase-spec-v2.md §6 洞察标准化.
    claim: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # WHY it works — mechanisms, cognitive/operation/decision cost reductions.
    analysis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # WHAT TO DO — specific action recommendation for the internal product.
    recommendation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # THE PRINCIPLE — brand-stripped, reusable design principle.
    design_principle: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # WHEN NOT TO — applicability constraints and limits.
    limits: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Observation IDs that support this insight (JSONB list of UUID strings).
    source_observation_ids: Mapped[Optional[list]] = mapped_column(
        JSONB, nullable=True, default=list, server_default=text("'[]'::jsonb")
    )

    # Confidence level: "high" | "medium" | "low" | "hypothesis"
    confidence: Mapped[str] = mapped_column(
        String, nullable=False, default="hypothesis",
        server_default=text("'hypothesis'"),
    )

    # "claude" | "human"
    generated_by: Mapped[str] = mapped_column(
        String, nullable=False, default="claude",
        server_default=text("'claude'"),
    )

    # True until human reviews and marks it confirmed.
    is_draft: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
