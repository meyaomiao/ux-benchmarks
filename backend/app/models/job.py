"""Async job — generic background task record for long-running AI operations.

Collection (probe) already runs async via Celery + coverage state. This table
covers the OTHER long ops (discovery / grid gen / insight gen / report compose)
so they run server-side and their progress/result survive page navigation.

Flow: POST creates a Job (QUEUED) + dispatches a Celery task → worker runs it,
writes RUNNING then DONE/FAILED with result JSON → frontend polls GET /jobs/{id}.
On page load, GET /jobs?type=&status=running lets the UI resume in-flight jobs.
"""
import uuid
from typing import Optional

from sqlalchemy import String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    # "discover" | "grid_gen" | "insight_gen" | "report_compose"
    job_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # "queued" | "running" | "done" | "failed"
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="queued", server_default=text("'queued'")
    )
    # Input params (echoed back so the UI can label the job).
    params: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # Result payload when done (shape depends on job_type).
    result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Error message when failed.
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
