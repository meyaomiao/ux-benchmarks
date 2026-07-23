"""Generic async job orchestration for long-running AI operations.

create_job persists a QUEUED Job. execute_job (run inside a Celery worker)
dispatches by job_type to the real service, then writes DONE+result or FAILED.
Routes and the Celery task are thin wrappers over these.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.job import Job

logger = logging.getLogger(__name__)

JOB_TYPES = {"discover", "grid_gen", "insight_gen", "report_compose"}


def create_job(db: Session, project_id: UUID, job_type: str, params: dict) -> Job:
    if job_type not in JOB_TYPES:
        raise AppError("BAD_JOB_TYPE", f"未知任务类型：{job_type}", 400)
    job = Job(project_id=project_id, job_type=job_type, status="queued", params=params or {})
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: UUID) -> Job | None:
    return db.get(Job, job_id)


def list_jobs(
    db: Session, project_id: UUID, job_type: str | None = None, status: str | None = None
) -> list[Job]:
    q = select(Job).where(Job.project_id == project_id)
    if job_type:
        q = q.where(Job.job_type == job_type)
    if status:
        q = q.where(Job.status == status)
    return list(db.execute(q.order_by(Job.created_at.desc())).scalars().all())


def execute_job(db: Session, job_id: UUID) -> None:
    """Run the job's work by dispatching on job_type. Always terminal on exit."""
    job = db.get(Job, job_id)
    if not job:
        logger.warning("execute_job: job %s not found", job_id)
        return
    job.status = "running"
    db.commit()
    try:
        result = _dispatch(db, job)
        job.result = result
        job.status = "done"
        db.commit()
    except Exception as exc:  # noqa: BLE001 — record failure, never leave running
        logger.warning("job %s (%s) failed: %s", job_id, job.job_type, exc)
        db.rollback()
        job = db.get(Job, job_id)
        job.status = "failed"
        job.error = str(exc)[:500]
        db.commit()


def _dispatch(db: Session, job: Job) -> dict:
    """Route to the real service by job_type; return a JSON-able result dict."""
    p = job.params or {}
    pid = job.project_id

    if job.job_type == "discover":
        from app.services.m0_registry.discovery_service import discover_competitors
        items = discover_competitors(p.get("category", ""), p.get("known_products", []), p.get("tier"))
        return {"suggestions": [
            {"name": s.name, "tier": s.tier, "tier_label": s.tier_label,
             "rationale": s.rationale, "official_domain": s.official_domain,
             "help_center_domain": s.help_center_domain}
            for s in items
        ]}

    if job.job_type == "grid_gen":
        from app.schemas.m1 import GridGenerationRequest
        from app.services.m1_grid.generation_service import generate_grid
        req = GridGenerationRequest(
            category=p.get("category", ""),
            known_products=p.get("known_products", []),
            language=p.get("language", "zh"),
        )
        return generate_grid(req).model_dump()

    if job.job_type == "insight_gen":
        from app.services.l3_insight.insight_service import generate_insight
        ins = generate_insight(db, UUID(p["cell_id"]), UUID(p["competitor_id"]))
        return {"insight_id": str(ins.id), "claim": ins.claim, "confidence": ins.confidence}

    if job.job_type == "report_compose":
        from app.services.l5_report.report_service import compose_report
        rpt = compose_report(
            db,
            insight_ids=[UUID(i) for i in p.get("insight_ids", [])],
            audience=p.get("audience", "designer"),
            format_type=p.get("format_type", "review_15min"),
            title=p.get("title"),
            project_id=pid,
        )
        return {"report_id": str(rpt.id), "title": rpt.title}

    raise AppError("BAD_JOB_TYPE", f"未知任务类型：{job.job_type}", 400)
