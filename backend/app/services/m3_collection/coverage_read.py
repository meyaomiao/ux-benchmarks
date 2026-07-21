"""Read-side service for coverage data (M5 matrix / cell drill-in).

Returns plain dicts; the route layer is responsible for shaping the HTTP response.
No state mutation here.
"""
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.m5_coverage import CoverageSnapshot


def _to_dict(snapshot: CoverageSnapshot) -> dict:
    """Project a CoverageSnapshot into the coverage read shape."""
    return {
        "cell_id": snapshot.cell_id,
        "competitor_id": snapshot.competitor_id,
        "status": snapshot.status,
        "independent_source_count": snapshot.independent_source_count,
        "latest_captured_at": snapshot.latest_captured_at,
        "coverage_confidence": snapshot.coverage_confidence,
        "evidence_type_breakdown": snapshot.evidence_type_breakdown,
        "tier": snapshot.tier,
    }


def get_matrix(db: Session, competitor_ids: list | None = None) -> list[dict]:
    """Return one row per CoverageSnapshot, optionally filtered by competitor_ids."""
    query = db.query(CoverageSnapshot)
    if competitor_ids:
        query = query.filter(CoverageSnapshot.competitor_id.in_(competitor_ids))
    return [_to_dict(s) for s in query.all()]


def get_cell_coverage(
    db: Session, cell_id: UUID, competitor_id: UUID
) -> dict | None:
    """Return the single snapshot for (cell, competitor) as a dict, or None."""
    snapshot = (
        db.query(CoverageSnapshot)
        .filter(
            CoverageSnapshot.cell_id == cell_id,
            CoverageSnapshot.competitor_id == competitor_id,
        )
        .one_or_none()
    )
    if snapshot is None:
        return None
    return _to_dict(snapshot)
