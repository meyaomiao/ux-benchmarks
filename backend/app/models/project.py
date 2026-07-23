"""Project — top-level container that scopes all research data.

Each project studies a different subject (e.g. one project researches
"项目管理工具", another "CRM"). Competitors, grid cells, mapping cards,
assets, observations, coverage, insights and reports all belong to exactly
one project, so switching projects shows a fully isolated workspace.
"""
import uuid

from sqlalchemy import String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Display name, e.g. "内部项目管理工具改版" or "2026 CRM 竞品研究".
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # The product category / subject this project researches.
    category: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
