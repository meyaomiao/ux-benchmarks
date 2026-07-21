from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.models.m0_registry import DomainLexicon
from app.schemas.m0 import LexiconEntryCreate, LexiconEntryUpdate
from app.core.errors import AppError


def list_lexicon(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    level: str | None = None,
    term_type: str | None = None,
    language: str | None = None,
) -> tuple[list[DomainLexicon], int]:
    """List lexicon entries with optional filtering."""
    query = select(DomainLexicon)

    if level is not None:
        query = query.where(DomainLexicon.level == level)
    if term_type is not None:
        query = query.where(DomainLexicon.term_type == term_type)
    if language is not None:
        query = query.where(DomainLexicon.language == language)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = db.execute(count_query).scalar() or 0

    # Get paginated items
    query = query.limit(limit).offset(offset)
    items = db.execute(query).scalars().all()

    return list(items), total


def get_lexicon_entry(db: Session, entry_id: UUID) -> DomainLexicon | None:
    """Get a single lexicon entry by ID."""
    query = select(DomainLexicon).where(DomainLexicon.id == entry_id)
    return db.execute(query).scalar_one_or_none()


def create_lexicon_entry(db: Session, data: LexiconEntryCreate) -> DomainLexicon:
    """Create a new lexicon entry."""
    # exclude_none=True: let server_default ('[]'::jsonb) apply for
    # omitted valid_for_competitors instead of writing NULL.
    entry = DomainLexicon(**data.model_dump(exclude_none=True))
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def update_lexicon_entry(
    db: Session, entry_id: UUID, data: LexiconEntryUpdate
) -> DomainLexicon:
    """Update an existing lexicon entry."""
    entry = get_lexicon_entry(db, entry_id)

    if not entry:
        raise AppError(
            "NOT_FOUND",
            f"Lexicon entry {entry_id} not found",
            404,
        )

    # Only update fields that are not None
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(entry, field, value)

    db.commit()
    db.refresh(entry)
    return entry


def delete_lexicon_entry(db: Session, entry_id: UUID) -> bool:
    """Delete a lexicon entry. Returns True if deleted."""
    entry = get_lexicon_entry(db, entry_id)

    if not entry:
        raise AppError(
            "NOT_FOUND",
            f"Lexicon entry {entry_id} not found",
            404,
        )

    db.delete(entry)
    db.commit()
    return True
