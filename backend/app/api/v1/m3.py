from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.errors import AppError
from app.schemas.m3 import (
    QueueItemRead, QueueListResponse, PinRequest,
    QueryBundle, SourceRegistryListResponse,
)
from app.services.m3_collection.queue_service import enqueue_cell, list_queued
from app.services.m3_collection.query_expansion import build_query_bundle
from app.services.m3_collection import source_registry_service
from app.services.m3_collection.state_machine import Trigger
from app.services.m3_collection.screenshot_service import capture_url

router = APIRouter(prefix="/m3", tags=["M3 · Collection Engine"])


# --- Queue (#14) ---------------------------------------------------------

@router.get("/queue", response_model=QueueListResponse)
async def get_queue_status(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    items = list_queued(db, limit)
    return QueueListResponse(items=items, total=len(items))


@router.post("/queue/pin", response_model=QueueItemRead, status_code=201)
async def manual_pin(data: PinRequest, db: Session = Depends(get_db)):
    # MANUAL_PIN forces (re)collection; option A auto-routes a SATURATED cell
    # through STALE -> QUEUED (see queue_service.enqueue_cell).
    return enqueue_cell(db, data.cell_id, data.competitor_id, Trigger.MANUAL_PIN)


@router.get("/queue/{cell_id}/query-bundle", response_model=QueryBundle)
async def get_query_bundle(
    cell_id: UUID,
    competitor_id: UUID | None = None,
    db: Session = Depends(get_db),
):
    # Expose the expanded query bundle for a cell (#15) — useful for debugging
    # what a probe cycle would search for.
    return build_query_bundle(db, cell_id, competitor_id)


@router.get("/queue/{cell_id}/shortlist")
async def get_shortlist(cell_id: str):
    # Shortlists are produced by adapter fan-out + AI scoring + dedup.
    raise HTTPException(status_code=501, detail="Not implemented — see issues #17-20")


# --- Source registry (#16) ----------------------------------------------

@router.get("/source-registry", response_model=SourceRegistryListResponse)
async def list_source_registry(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    items, total = source_registry_service.list_sources(db, limit, offset)
    return SourceRegistryListResponse(
        items=items, total=total, limit=limit, offset=offset,
        has_next=offset + limit < total,
    )


# --- Manual screenshot (#30) ------------------------------------------------

@router.post("/manual-screenshot", status_code=201)
async def manual_screenshot(data: dict, db: Session = Depends(get_db)):
    """Take a Playwright screenshot of a URL and add it to the shortlist.

    Body: {"url": "https://...", "cell_id": "uuid", "competitor_id": "uuid"}
    Returns the persisted Asset summary.
    """
    url = (data.get("url") or "").strip()
    if not url or not url.startswith("http"):
        raise AppError("BAD_REQUEST", "url must be a valid http(s) URL", 400)
    try:
        cell_id = UUID(str(data.get("cell_id", "")))
        competitor_id = UUID(str(data.get("competitor_id", "")))
    except (ValueError, AttributeError):
        raise AppError("BAD_REQUEST", "cell_id and competitor_id must be valid UUIDs", 400)

    try:
        asset = capture_url(db, url, cell_id, competitor_id)
    except RuntimeError as exc:
        raise AppError("CAPTURE_FAILED", str(exc), 500)

    return {
        "id": str(asset.id),
        "source_url": asset.source_url,
        "title": None,
        "file_path": asset.file_path,
        "ai_score": asset.ai_score,
        "scored_by": (asset.ai_score_breakdown or {}).get("scored_by", "manual"),
        "evidence_type": asset.evidence_type,
        "cell_id": str(asset.cell_id),
        "competitor_id": str(asset.competitor_id),
    }
