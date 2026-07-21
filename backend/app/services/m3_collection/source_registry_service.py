"""Source registry dedup index service.

Pure engineering dedup/caching layer: before a probe fetches a URL, check if it
is already registered (and fresh); if so reuse it instead of re-fetching. Track
which grid cells each source supports.

``supporting_cells`` is stored as a JSONB list of stringified UUIDs. SQLAlchemy's
default JSONB mutation tracking does not observe in-place ``list.append`` calls,
so the list must be reassigned wholesale for the change to be flushed.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.m3_collection import SourceRegistry
from app.core.errors import AppError


def _merge_cell(cells: list[str], cell_id: str) -> list[str]:
    """Return a new list with ``cell_id`` appended if not already present.

    Pure helper (no DB). None-safe, dedups, and preserves existing order.
    Always returns a fresh list so the caller can reassign it for JSONB
    mutation tracking.
    """
    existing = list(cells) if cells else []
    if cell_id in existing:
        return existing
    return existing + [cell_id]


def get_by_url(db: Session, source_url: str) -> SourceRegistry | None:
    """Look up a registered source by its (unique) URL."""
    query = select(SourceRegistry).where(SourceRegistry.source_url == source_url)
    return db.execute(query).scalar_one_or_none()


def register_source(
    db: Session,
    source_url: str,
    competitor_id: UUID | None,
    cell_id: UUID,
) -> SourceRegistry:
    """Register a source URL, tracking which cell it supports.

    If the URL already exists, append ``cell_id`` to ``supporting_cells`` (unless
    already present) and return the existing row. Otherwise create a new row with
    ``discovered_at=now`` and ``supporting_cells=[str(cell_id)]``.
    """
    cell_str = str(cell_id)
    existing = get_by_url(db, source_url)

    if existing is not None:
        # Reassign the list (not .append) so JSONB mutation tracking fires.
        existing.supporting_cells = _merge_cell(existing.supporting_cells, cell_str)
        db.commit()
        db.refresh(existing)
        return existing

    source = SourceRegistry(
        source_url=source_url,
        competitor_id=competitor_id,
        discovered_at=datetime.now(timezone.utc),
        supporting_cells=[cell_str],
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def is_fresh(db: Session, source_url: str, max_age_days: int = 30) -> bool:
    """Return True if a registered source exists and was seen within max_age_days.

    Uses ``last_fetched_at`` when available, else ``discovered_at``. Handles both
    naive and aware timestamps safely by comparing in UTC.
    """
    source = get_by_url(db, source_url)
    if source is None:
        return False

    reference = source.last_fetched_at or source.discovered_at
    if reference is None:
        return False

    # Normalize to aware UTC to compare naive/aware timestamps safely.
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    return reference >= cutoff


def mark_fetched(db: Session, source_url: str) -> SourceRegistry:
    """Stamp ``last_fetched_at=now`` on a registered source.

    Raises AppError NOT_FOUND (404) if the URL is not registered.
    """
    source = get_by_url(db, source_url)
    if source is None:
        raise AppError(
            "NOT_FOUND",
            f"Source '{source_url}' not found in registry",
            404,
        )

    source.last_fetched_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(source)
    return source


def list_sources(
    db: Session,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[SourceRegistry], int]:
    """List registered sources with pagination."""
    query = select(SourceRegistry)

    count_query = select(func.count()).select_from(query.subquery())
    total = db.execute(count_query).scalar() or 0

    query = query.limit(limit).offset(offset)
    items = db.execute(query).scalars().all()

    return list(items), total
