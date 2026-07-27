from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.database import get_db
from app.core.deps import get_project_id
from app.core.errors import AppError
from app.models.m1_grid import GridCell
from app.services.m3_collection.coverage_read import get_matrix, get_cell_coverage
from app.services.m3_collection.coverage_recompute import recompute_coverage as _recompute

router = APIRouter(prefix="/m5", tags=["M5 · Coverage Dashboard"])


def _assert_cell_in_project(db: Session, cell_id: UUID, project_id: UUID) -> None:
    """Reject a recompute request for a cell owned by another project.

    Reported as NOT_FOUND so the error cannot be used to probe other projects.
    """
    owner = db.execute(
        select(GridCell.project_id).where(GridCell.id == cell_id)
    ).scalar_one_or_none()
    if owner is None or owner != project_id:
        raise AppError("NOT_FOUND", f"Cell {cell_id} not found", 404)


# --- Coverage read (#27) -------------------------------------------------

@router.get("/coverage")
async def get_coverage_matrix(
    competitor_id: list[UUID] | None = Query(default=None),
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    """Coverage matrix rows (scoped to project, optionally filtered by competitor_id)."""
    return get_matrix(db, competitor_id, project_id)


@router.get("/coverage/{cell_id}/{competitor_id}")
async def get_cell_coverage_endpoint(
    cell_id: UUID,
    competitor_id: UUID,
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    row = get_cell_coverage(db, cell_id, competitor_id, project_id)
    if row is None:
        raise AppError("NOT_FOUND", f"No coverage for cell {cell_id} / competitor {competitor_id}", 404)
    return row


# --- Coverage recompute (#26) --------------------------------------------

@router.post("/coverage/{cell_id}/{competitor_id}/recompute")
async def recompute_coverage_endpoint(
    cell_id: UUID,
    competitor_id: UUID,
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    """Recompute a cell's coverage snapshot from its persisted Assets.

    Drives state as far as SHORTLIST_READY; never SATURATED (human gate, #23/#24).
    """
    _assert_cell_in_project(db, cell_id, project_id)
    snapshot = _recompute(db, cell_id, competitor_id)
    return get_cell_coverage(db, cell_id, competitor_id, project_id) or {
        "status": snapshot.status
    }


# --- Reports + Metrics (#29 #30) -------------------------------------------

from app.services.m5_coverage.metrics_service import get_pipeline_metrics  # noqa: E402
from app.services.m5_coverage.report_service import (  # noqa: E402
    generate_coverage_report,
    report_to_markdown,
)
from fastapi.responses import PlainTextResponse  # noqa: E402


@router.get("/metrics")
async def coverage_metrics(
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    """Pipeline health metrics: adoption rate, coverage confidence, status counts."""
    return get_pipeline_metrics(db, project_id)


@router.get("/reports")
async def list_reports():
    """Placeholder — report history not yet implemented."""
    return []


@router.post("/reports/generate")
async def generate_report(
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    """Generate a structured coverage report (JSON + Markdown)."""
    return generate_coverage_report(db, project_id)


@router.get("/reports/export.md", response_class=PlainTextResponse)
async def export_report_markdown(
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    """Download the coverage report as Markdown."""
    report = generate_coverage_report(db, project_id)
    return report_to_markdown(report)
