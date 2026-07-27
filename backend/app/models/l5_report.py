"""L5 Report — assembled output from composing insight modules into a target format.

L4 (模块化拆解) is virtual: insight fields (claim/analysis/recommendation/
design_principle/limits) ARE the modules. No separate table is needed.

L5 (报告重组) persists the assembled result: a markdown body produced by Claude
from a selection of insights, tailored to an audience and format.

This realises "重组而非重生": the same evidence/claims appear in different
reports without regenerating from source observations.
"""
import uuid
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class Report(TimestampMixin, Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )

    # Human-readable title, auto-generated if not supplied.
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    # Target audience: "management" | "designer" | "pm"
    audience: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'designer'")
    )

    # Report format: "summary_5min" | "review_15min" | "onepager" | "full"
    format_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'review_15min'")
    )

    # UUIDs of Insight records used as source material (JSONB list of strings).
    source_insight_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    # The generated markdown report body.
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # "gpt" | "mock"
    generated_by: Mapped[str] = mapped_column(
        String(32), nullable=False, default="claude", server_default=text("'claude'")
    )
