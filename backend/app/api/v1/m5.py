from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.errors import AppError
from app.services.m3_collection.coverage_read import get_matrix, get_cell_coverage
from app.services.m3_collection.coverage_recompute import recompute_coverage as _recompute

router = APIRouter(prefix="/m5", tags=["M5 · Coverage Dashboard"])


# --- Coverage read (#27) -------------------------------------------------

@router.get("/coverage")
async def get_coverage_matrix(
    competitor_id: list[UUID] | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Coverage matrix rows (optionally filtered by competitor_id, repeatable)."""
    return get_matrix(db, competitor_id)


@router.get("/coverage/{cell_id}/{competitor_id}")
async def get_cell_coverage_endpoint(
    cell_id: UUID, competitor_id: UUID, db: Session = Depends(get_db)
):
    row = get_cell_coverage(db, cell_id, competitor_id)
    if row is None:
        raise AppError("NOT_FOUND", f"No coverage for cell {cell_id} / competitor {competitor_id}", 404)
    return row


# --- Coverage recompute (#26) --------------------------------------------

@router.post("/coverage/{cell_id}/{competitor_id}/recompute")
async def recompute_coverage_endpoint(
    cell_id: UUID, competitor_id: UUID, db: Session = Depends(get_db)
):
    """Recompute a cell's coverage snapshot from its persisted Assets.

    Drives state as far as SHORTLIST_READY; never SATURATED (human gate, #23/#24).
    """
    snapshot = _recompute(db, cell_id, competitor_id)
    return get_cell_coverage(db, cell_id, competitor_id) or {"status": snapshot.status}


# --- Reports (#30, not yet implemented) ----------------------------------

@router.get("/reports")
async def list_reports():
    raise HTTPException(status_code=501, detail="Not implemented — see issue #30")


@router.post("/reports/generate")
async def generate_report():
    raise HTTPException(status_code=501, detail="Not implemented — see issue #30")
