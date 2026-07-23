"""Generic async job API — start / poll / list long-running AI jobs."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_project_id
from app.core.errors import AppError
from app.services import job_service

router = APIRouter(prefix="/jobs", tags=["Async Jobs"])


class JobCreate(BaseModel):
    job_type: str            # discover | grid_gen | insight_gen | report_compose
    params: dict = {}


class JobRead(BaseModel):
    id: UUID
    project_id: UUID
    job_type: str
    status: str
    params: dict
    result: dict | None
    error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


@router.post("", response_model=JobRead, status_code=201)
async def start_job(
    data: JobCreate,
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    """Create a queued job and dispatch it to a Celery worker (returns instantly)."""
    from app.workers.tasks.run_job import run_job

    job = job_service.create_job(db, project_id, data.job_type, data.params)
    try:
        run_job.delay(str(job.id))
    except Exception as exc:  # noqa: BLE001 — broker down
        raise AppError("DISPATCH_FAILED", f"派发失败（worker/broker 不可用？）：{exc}", 503)
    return job


@router.get("/{job_id}", response_model=JobRead)
async def get_job(job_id: UUID, db: Session = Depends(get_db)):
    job = job_service.get_job(db, job_id)
    if not job:
        raise AppError("NOT_FOUND", f"Job {job_id} not found", 404)
    return job


@router.get("", response_model=list[JobRead])
async def list_jobs(
    job_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    return job_service.list_jobs(db, project_id, job_type, status)
