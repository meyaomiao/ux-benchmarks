from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.models.m2_mapping import MappingCard
from app.models.m1_grid import GridCell
from app.schemas.m2 import MappingCardCreate, MappingCardUpdate
from app.core.errors import AppError


def list_mapping_cards(
    db: Session, limit: int = 20, offset: int = 0
) -> tuple[list[MappingCard], int]:
    """List mapping cards with pagination."""
    query = select(MappingCard)

    count_query = select(func.count()).select_from(query.subquery())
    total = db.execute(count_query).scalar() or 0

    query = query.limit(limit).offset(offset)
    items = db.execute(query).scalars().all()

    return list(items), total


def get_mapping_card_by_cell(db: Session, cell_id: UUID) -> MappingCard | None:
    """Get a single mapping card by its cell_id (unique)."""
    query = select(MappingCard).where(MappingCard.cell_id == cell_id)
    return db.execute(query).scalar_one_or_none()


def create_mapping_card(db: Session, data: MappingCardCreate) -> MappingCard:
    """Create a new mapping card for a grid cell."""
    # Verify the referenced grid cell exists
    cell = db.execute(
        select(GridCell).where(GridCell.id == data.cell_id)
    ).scalar_one_or_none()
    if not cell:
        raise AppError(
            "CELL_NOT_FOUND",
            f"Grid cell {data.cell_id} not found",
            404,
        )

    # Enforce one-card-per-cell (cell_id is unique)
    existing = get_mapping_card_by_cell(db, data.cell_id)
    if existing:
        raise AppError(
            "MAPPING_CARD_EXISTS",
            f"A mapping card already exists for cell {data.cell_id}",
            409,
        )

    card = MappingCard(**data.model_dump(exclude_none=True))
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


def update_mapping_card(
    db: Session, cell_id: UUID, data: MappingCardUpdate
) -> MappingCard:
    """Update an existing mapping card, bumping its version."""
    card = get_mapping_card_by_cell(db, cell_id)
    if not card:
        raise AppError(
            "NOT_FOUND",
            f"Mapping card for cell {cell_id} not found",
            404,
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(card, field, value)

    card.version += 1

    db.commit()
    db.refresh(card)
    return card


def is_cell_mappable(db: Session, cell_id: UUID) -> bool:
    """M3 enqueue gate: True only if a card exists and is complete."""
    card = get_mapping_card_by_cell(db, cell_id)
    return bool(card and card.is_complete)
