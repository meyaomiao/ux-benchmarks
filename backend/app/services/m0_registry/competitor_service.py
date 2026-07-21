from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.models.m0_registry import CompetitorEntity
from app.schemas.m0 import CompetitorCreate, CompetitorUpdate
from app.core.errors import AppError


def list_competitors(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    competitor_type: str | None = None,
) -> tuple[list[CompetitorEntity], int]:
    """List competitors with optional filtering."""
    query = select(CompetitorEntity)

    if status is not None:
        query = query.where(CompetitorEntity.status == status)
    if competitor_type is not None:
        query = query.where(CompetitorEntity.competitor_type == competitor_type)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = db.execute(count_query).scalar() or 0

    # Get paginated items
    query = query.limit(limit).offset(offset)
    items = db.execute(query).scalars().all()

    return list(items), total


def get_competitor(db: Session, competitor_id: UUID) -> CompetitorEntity | None:
    """Get a single competitor by ID."""
    query = select(CompetitorEntity).where(CompetitorEntity.id == competitor_id)
    return db.execute(query).scalar_one_or_none()


def create_competitor(db: Session, data: CompetitorCreate) -> CompetitorEntity:
    """Create a new competitor."""
    # Check uniqueness of canonical_name
    existing = db.execute(
        select(CompetitorEntity).where(
            CompetitorEntity.canonical_name == data.canonical_name
        )
    ).scalar_one_or_none()

    if existing:
        raise AppError(
            "DUPLICATE_NAME",
            f"Competitor with canonical_name '{data.canonical_name}' already exists",
            409,
        )

    competitor = CompetitorEntity(**data.model_dump())
    db.add(competitor)
    db.commit()
    db.refresh(competitor)
    return competitor


def update_competitor(
    db: Session, competitor_id: UUID, data: CompetitorUpdate
) -> CompetitorEntity:
    """Update an existing competitor."""
    competitor = get_competitor(db, competitor_id)

    if not competitor:
        raise AppError(
            "NOT_FOUND",
            f"Competitor {competitor_id} not found",
            404,
        )

    # Only update fields that are not None
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(competitor, field, value)

    db.commit()
    db.refresh(competitor)
    return competitor
