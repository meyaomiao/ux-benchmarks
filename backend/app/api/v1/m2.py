from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_project_id
from app.models.m1_grid import GridCell
from app.schemas.m2 import (
    MappingCardCreate, MappingCardUpdate, MappingCardRead, MappingCardListResponse,
)
from app.services.m2_mapping import mapping_service
from app.services.m2_mapping.card_generation_service import generate_card_draft
from app.core.errors import AppError

router = APIRouter(prefix="/m2", tags=["M2 · Mapping Cards"])


@router.post("/mapping-cards/generate")
async def generate_mapping_card(data: dict, db: Session = Depends(get_db)):
    """AI-draft a mapping card from a grid cell's coordinates.

    Body: {"cell_id": "uuid"}. Returns a draft (not persisted) that the user
    reviews and saves via the normal create/update endpoints.
    """
    try:
        cell_id = UUID(str(data.get("cell_id", "")))
    except (ValueError, AttributeError):
        raise AppError("BAD_REQUEST", "cell_id must be a valid UUID", 400)

    cell = db.execute(select(GridCell).where(GridCell.id == cell_id)).scalar_one_or_none()
    if not cell:
        raise AppError("CELL_NOT_FOUND", f"Grid cell {cell_id} not found", 404)

    return generate_card_draft(cell.jtbd, cell.journey_stage, cell.page_state)


@router.get("/mapping-cards", response_model=MappingCardListResponse)
async def list_mapping_cards(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    items, total = mapping_service.list_mapping_cards(db, limit, offset, project_id)
    return MappingCardListResponse(
        items=items, total=total, limit=limit, offset=offset,
        has_next=offset + limit < total,
    )


@router.post("/mapping-cards", response_model=MappingCardRead, status_code=201)
async def create_mapping_card(
    data: MappingCardCreate,
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    return mapping_service.create_mapping_card(db, data, project_id)


@router.get("/mapping-cards/{cell_id}", response_model=MappingCardRead)
async def get_mapping_card(cell_id: UUID, db: Session = Depends(get_db)):
    card = mapping_service.get_mapping_card_by_cell(db, cell_id)
    if not card:
        raise AppError("NOT_FOUND", f"Mapping card for cell {cell_id} not found", 404)
    return card


@router.patch("/mapping-cards/{cell_id}", response_model=MappingCardRead)
async def update_mapping_card(
    cell_id: UUID, data: MappingCardUpdate, db: Session = Depends(get_db)
):
    return mapping_service.update_mapping_card(db, cell_id, data)
