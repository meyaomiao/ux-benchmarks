import uuid
from datetime import date, datetime
from typing import Optional
from sqlalchemy import String, text, Date, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.models.base import TimestampMixin


class CompetitorEntity(TimestampMixin, Base):
    __tablename__ = "competitor_entities"
    # canonical_name is unique per project, not globally (multi-project #45).
    __table_args__ = (
        UniqueConstraint("project_id", "canonical_name", name="uq_competitor_project_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    canonical_name: Mapped[str] = mapped_column(String, nullable=False)
    aliases: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list, server_default=text("'[]'::jsonb"))
    parent_company: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    official_domain: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    help_center_domain: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    video_channels: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list, server_default=text("'[]'::jsonb"))
    app_store_pages: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list, server_default=text("'[]'::jsonb"))
    acquired_from: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="confirmed", server_default=text("'confirmed'"))
    competitor_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class DomainLexicon(TimestampMixin, Base):
    __tablename__ = "domain_lexicon"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    term: Mapped[str] = mapped_column(String, nullable=False)
    term_type: Mapped[str] = mapped_column(String, nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False, default="en", server_default=text("'en'"))
    level: Mapped[str] = mapped_column(String, nullable=False)
    valid_for_competitors: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list, server_default=text("'[]'::jsonb"))
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)
