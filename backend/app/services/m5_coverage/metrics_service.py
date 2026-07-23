"""Coverage metrics service (#29).

Computes aggregate stats about the evidence collection pipeline:
  - shortlist adoption rate (accepted / total shortlisted)
  - coverage confidence distribution
  - cell/competitor pair counts by status

These numbers help gauge pipeline quality and flag when the AI scoring
threshold or query strategy needs tuning.
"""
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.m3_collection import Asset
from app.models.m4_annotation import Observation
from app.models.m5_coverage import CoverageSnapshot


def get_pipeline_metrics(db: Session, project_id: UUID | None = None) -> dict:
    """Return aggregate pipeline metrics, scoped to a project."""
    def _p(model):
        # helper: project filter clause for a model, or always-true when unscoped
        return (model.project_id == project_id) if project_id is not None else (1 == 1)

    # Total non-superseded assets (the pool the reviewer sees)
    total_assets = db.scalar(
        select(func.count(Asset.id)).where(Asset.is_superseded == False, _p(Asset))  # noqa: E712
    ) or 0

    # Accepted assets = number of Observations (each accept creates one)
    total_accepted = db.scalar(
        select(func.count(Observation.id)).where(_p(Observation))
    ) or 0

    # Rejected = superseded assets that have no Observation
    # (proxy: superseded but no matching observation)
    total_rejected = db.scalar(
        select(func.count(Asset.id)).where(Asset.is_superseded == True, _p(Asset))  # noqa: E712
    ) or 0

    # Adoption rate = accepted / (accepted + rejected) if reviewed items exist
    reviewed = total_accepted + total_rejected
    adoption_rate = (total_accepted / reviewed) if reviewed > 0 else None

    # Coverage snapshot stats
    snap_counts: dict[str, int] = {}
    rows = db.execute(
        select(CoverageSnapshot.status, func.count(CoverageSnapshot.id))
        .where(_p(CoverageSnapshot))
        .group_by(CoverageSnapshot.status)
    ).all()
    for status, count in rows:
        snap_counts[status] = count

    total_pairs = sum(snap_counts.values())
    shortlist_ready = snap_counts.get("SHORTLIST_READY", 0)
    saturated = snap_counts.get("SATURATED", 0)

    # Average coverage confidence (excluding UNPROBED / zero-confidence)
    avg_confidence = db.scalar(
        select(func.avg(CoverageSnapshot.coverage_confidence)).where(
            CoverageSnapshot.coverage_confidence > 0, _p(CoverageSnapshot)
        )
    )

    return {
        "pipeline": {
            "total_assets_in_shortlist": total_assets,
            "total_accepted": total_accepted,
            "total_rejected": total_rejected,
            "adoption_rate": round(adoption_rate, 3) if adoption_rate is not None else None,
            "adoption_rate_healthy": adoption_rate is not None and adoption_rate >= 0.40,
        },
        "coverage": {
            "total_cell_competitor_pairs": total_pairs,
            "shortlist_ready": shortlist_ready,
            "saturated": saturated,
            "by_status": snap_counts,
            "avg_confidence": round(float(avg_confidence), 3) if avg_confidence else 0.0,
        },
    }
