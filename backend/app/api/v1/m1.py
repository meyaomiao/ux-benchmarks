from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.errors import AppError
from app.schemas.m1 import (
    GridCellCreate, GridCellUpdate, GridCellRead,
    GridCellListResponse, CellChangelogRead,
)
from app.services.m1_grid.cell_service import (
    list_cells, get_cell, create_cell, update_cell, get_cell_changelog,
)

router = APIRouter(prefix="/m1", tags=["M1 · Grid Management"])


@router.get("/cells", response_model=GridCellListResponse)
async def list_cells_endpoint(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    jtbd: str | None = None,
    journey_stage: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    items, total = list_cells(db, limit, offset, jtbd, journey_stage, status)
    return GridCellListResponse(
        items=items, total=total, limit=limit, offset=offset,
        has_next=offset + limit < total,
    )


@router.post("/cells", response_model=GridCellRead, status_code=201)
async def create_cell_endpoint(data: GridCellCreate, db: Session = Depends(get_db)):
    return create_cell(db, data)


@router.get("/cells/{cell_id}", response_model=GridCellRead)
async def get_cell_endpoint(cell_id: UUID, db: Session = Depends(get_db)):
    cell = get_cell(db, cell_id)
    if not cell:
        raise AppError("NOT_FOUND", f"Cell {cell_id} not found", 404)
    return cell


@router.patch("/cells/{cell_id}", response_model=GridCellRead)
async def update_cell_endpoint(
    cell_id: UUID, data: GridCellUpdate, db: Session = Depends(get_db)
):
    return update_cell(db, cell_id, data)


@router.get("/cells/{cell_id}/changelog", response_model=list[CellChangelogRead])
async def get_cell_changelog_endpoint(cell_id: UUID, db: Session = Depends(get_db)):
    # Guard: return 404 if the cell itself doesn't exist, so callers can
    # distinguish "cell not found" from "cell has no changelog entries yet".
    if not get_cell(db, cell_id):
        raise AppError("NOT_FOUND", f"Cell {cell_id} not found", 404)
    return get_cell_changelog(db, cell_id)


@router.get("/inbox")
async def list_unmapped_inbox():
    raise HTTPException(status_code=501, detail="Not implemented — see issue #10")


@router.post("/inbox/{inbox_id}/resolve")
async def resolve_inbox_item(inbox_id: str):
    raise HTTPException(status_code=501, detail="Not implemented — see issue #10")
