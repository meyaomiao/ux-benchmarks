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
    project_id: UUID | None = None,
) -> tuple[list[CompetitorEntity], int]:
    """List competitors with optional filtering, scoped to a project."""
    query = select(CompetitorEntity)

    if project_id is not None:
        query = query.where(CompetitorEntity.project_id == project_id)
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


def create_competitor(db: Session, data: CompetitorCreate, project_id: UUID) -> CompetitorEntity:
    """Create a new competitor within a project."""
    # Uniqueness is per-project (canonical_name unique within the project).
    existing = db.execute(
        select(CompetitorEntity).where(
            CompetitorEntity.project_id == project_id,
            CompetitorEntity.canonical_name == data.canonical_name,
        )
    ).scalar_one_or_none()

    if existing:
        raise AppError(
            "DUPLICATE_NAME",
            f"本项目已存在竞品 '{data.canonical_name}'",
            409,
        )

    # exclude_none=True: let server_default (e.g. '[]'::jsonb) apply for
    # omitted JSONB array fields instead of explicitly writing NULL.
    competitor = CompetitorEntity(project_id=project_id, **data.model_dump(exclude_none=True))
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


def delete_competitor(db: Session, competitor_id: UUID) -> dict:
    """Delete a competitor.

    Hard-delete when nothing references it; otherwise soft-delete (mark
    status='excluded') so downstream coverage/insight rows stay intact.
    Returns {"mode": "hard"|"soft"}.
    """
    from app.models.m5_coverage import CoverageSnapshot
    from app.models.l3_insight import Insight

    competitor = get_competitor(db, competitor_id)
    if not competitor:
        raise AppError("NOT_FOUND", f"Competitor {competitor_id} not found", 404)

    referenced = db.execute(
        select(func.count())
        .select_from(CoverageSnapshot)
        .where(CoverageSnapshot.competitor_id == competitor_id)
    ).scalar() or 0
    referenced += db.execute(
        select(func.count())
        .select_from(Insight)
        .where(Insight.competitor_id == competitor_id)
    ).scalar() or 0

    if referenced > 0:
        competitor.status = "excluded"
        db.commit()
        return {"mode": "soft"}

    db.delete(competitor)
    db.commit()
    return {"mode": "hard"}
