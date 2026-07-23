from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_project_id
from app.core.errors import AppError
from app.schemas.m4 import (
    ShortlistItem, ShortlistResponse,
    AcceptRequest, RejectRequest, FlagRequest, ObservationRead,
)
from app.services.m4_annotation import review_service

router = APIRouter(prefix="/m4", tags=["M4 · Asset Review & Annotation"])


def _to_shortlist_item(asset) -> ShortlistItem:
    """Map an Asset ORM row to ShortlistItem, computing the derived field."""
    return ShortlistItem(
        id=asset.id,
        cell_id=asset.cell_id,
        competitor_id=asset.competitor_id,
        source_url=asset.source_url,
        source_type=getattr(asset, "source_type", None),
        title=getattr(asset, "title", None),
        snippet=getattr(asset, "snippet", None),
        evidence_type=asset.evidence_type,
        ai_score=asset.ai_score,
        ai_score_breakdown=asset.ai_score_breakdown,
        rights_status=asset.rights_status,
        media_disposition=asset.media_disposition,
        captured_at=asset.captured_at,
        # Derived — Asset model stores file_path, not image_path_available.
        image_path_available=bool(asset.file_path),
    )


# --- Shortlist (#23) --------------------------------------------------------

@router.get("/shortlist/{cell_id}/{competitor_id}", response_model=ShortlistResponse)
async def get_shortlist(
    cell_id: UUID, competitor_id: UUID, db: Session = Depends(get_db)
):
    """Assets awaiting human review for a (cell, competitor) pair."""
    assets = review_service.get_shortlist(db, cell_id, competitor_id)
    items = [_to_shortlist_item(a) for a in assets]
    return ShortlistResponse(items=items, total=len(items))


@router.post("/shortlist/accept", response_model=ObservationRead, status_code=201)
async def accept_asset(data: AcceptRequest, db: Session = Depends(get_db)):
    """Accept an Asset — creates an Observation and triggers coverage recompute."""
    return review_service.accept_asset(
        db, data.asset_id, data.observation_fields
    )


@router.post("/shortlist/reject", response_model=dict, status_code=200)
async def reject_asset(data: RejectRequest, db: Session = Depends(get_db)):
    """Soft-remove an Asset from the shortlist (is_superseded = True)."""
    asset = review_service.reject_asset(db, data.asset_id, data.reason)
    return {"asset_id": str(asset.id), "is_superseded": asset.is_superseded}


@router.post("/shortlist/flag", response_model=dict, status_code=200)
async def flag_asset(data: FlagRequest, db: Session = Depends(get_db)):
    """Flag an Asset for follow-up (placeholder — real queue is a future issue)."""
    asset = review_service.flag_asset(db, data.asset_id, data.note)
    return {"asset_id": str(asset.id), "flagged": True}


# --- Observations (#24, stubs) ----------------------------------------------

@router.get("/observations")
async def list_observations():
    raise HTTPException(status_code=501, detail="Not implemented — see issue #24")


@router.get("/observations/{observation_id}")
async def get_observation(observation_id: str):
    raise HTTPException(status_code=501, detail="Not implemented — see issue #24")


@router.post("/observations/{observation_id}/claims", status_code=201)
async def add_claim(observation_id: str):
    raise HTTPException(status_code=501, detail="Not implemented — see issue #25")


# --- L3 Insights -----------------------------------------------------------

from app.schemas.m4 import InsightGenerateRequest, InsightRead, InsightUpdate  # noqa: E402
from app.services.l3_insight import insight_service  # noqa: E402


@router.get("/insights", response_model=list[InsightRead])
async def list_insights(
    cell_id: UUID | None = None,
    competitor_id: UUID | None = None,
    is_draft: bool | None = None,
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    return insight_service.list_insights(db, cell_id, competitor_id, is_draft, project_id)


@router.post("/insights/generate", response_model=InsightRead, status_code=201)
async def generate_insight(data: InsightGenerateRequest, db: Session = Depends(get_db)):
    """Generate a draft L3 insight from accepted evidence using Claude (mock fallback)."""
    return insight_service.generate_insight(db, data.cell_id, data.competitor_id)


@router.get("/insights/{insight_id}", response_model=InsightRead)
async def get_insight(insight_id: UUID, db: Session = Depends(get_db)):
    obj = insight_service.get_insight(db, insight_id)
    if not obj:
        raise AppError("NOT_FOUND", f"Insight {insight_id} not found", 404)
    return obj


@router.patch("/insights/{insight_id}", response_model=InsightRead)
async def update_insight(
    insight_id: UUID, data: InsightUpdate, db: Session = Depends(get_db)
):
    return insight_service.update_insight(db, insight_id, data.model_dump(exclude_none=True))


@router.delete("/insights/{insight_id}", status_code=204)
async def delete_insight(insight_id: UUID, db: Session = Depends(get_db)):
    insight_service.delete_insight(db, insight_id)
