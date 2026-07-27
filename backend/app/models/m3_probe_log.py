import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class ProbeScoreLog(TimestampMixin, Base):
    """Every scored candidate of a probe pass, passing or not.

    Assets only ever hold candidates that cleared RELEVANCE_FLOOR, so the
    rejected ones used to vanish with the request. Without them there is no way
    to tell whether the floor is too strict or the queries are simply wrong.
    This table is append-only diagnostics: never read by the coverage math.
    """

    __tablename__ = "probe_score_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    cell_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grid_cells.id"), nullable=False, index=True
    )
    competitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("competitor_entities.id"), nullable=False, index=True
    )
    probe_cycle: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    has_image: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    evidence_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    scored_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    score_breakdown: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProbeRunLog(TimestampMixin, Base):
    """One append-only observability row for a complete probe attempt."""

    __tablename__ = "probe_run_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    cell_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grid_cells.id"), nullable=False, index=True
    )
    competitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("competitor_entities.id"), nullable=False, index=True
    )
    probe_cycle: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    strategy_version: Mapped[str] = mapped_column(String, nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    final_state: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    candidates_found: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    scored_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    passed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    persisted_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    search_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    browser_pages: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    scoring_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    agentic_model_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    duration_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    source_budgets: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    source_stats: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    agentic_stats: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    agentic_trace: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    error_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
