from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.m3 import (
    QueueItemRead, QueueListResponse, PinRequest,
    QueryBundle, SourceRegistryListResponse,
)
from app.services.m3_collection.queue_service import enqueue_cell, list_queued
from app.services.m3_collection.query_expansion import build_query_bundle
from app.services.m3_collection import source_registry_service
from app.services.m3_collection.state_machine import Trigger

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
