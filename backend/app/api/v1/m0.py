from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_project_id
from app.schemas.m0 import (
    CompetitorCreate, CompetitorUpdate, CompetitorRead, CompetitorListResponse,
    LexiconEntryCreate, LexiconEntryUpdate, LexiconEntryRead, LexiconListResponse,
)
from app.services.m0_registry.competitor_service import (
    list_competitors, get_competitor, create_competitor, update_competitor,
    delete_competitor,
)
from app.services.m0_registry import lexicon_service
from app.services.m0_registry.discovery_service import discover_competitors
from app.core.errors import AppError

router = APIRouter(prefix="/m0", tags=["M0 · Competitor Registry"])


@router.get("/competitors", response_model=CompetitorListResponse)
async def list_competitors_endpoint(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = None,
    competitor_type: str | None = None,
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    items, total = list_competitors(db, limit, offset, status, competitor_type, project_id)
    return CompetitorListResponse(
        items=items, total=total, limit=limit, offset=offset,
        has_next=offset + limit < total,
    )


@router.post("/competitors", response_model=CompetitorRead, status_code=201)
async def create_competitor_endpoint(
    data: CompetitorCreate,
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    return create_competitor(db, data, project_id)


@router.get("/competitors/{competitor_id}", response_model=CompetitorRead)
async def get_competitor_endpoint(competitor_id: UUID, db: Session = Depends(get_db)):
    obj = get_competitor(db, competitor_id)
    if not obj:
        raise AppError("NOT_FOUND", f"Competitor {competitor_id} not found", 404)
    return obj


@router.patch("/competitors/{competitor_id}", response_model=CompetitorRead)
async def update_competitor_endpoint(
    competitor_id: UUID, data: CompetitorUpdate, db: Session = Depends(get_db)
):
    return update_competitor(db, competitor_id, data)


@router.delete("/competitors/{competitor_id}")
async def delete_competitor_endpoint(competitor_id: UUID, db: Session = Depends(get_db)):
    """Delete a competitor (hard if unreferenced, else soft-excluded)."""
    return delete_competitor(db, competitor_id)


# Issue #6 — Lexicon routes
@router.get("/lexicon", response_model=LexiconListResponse)
async def list_lexicon(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    level: str | None = Query(default=None),
    term_type: str | None = Query(default=None),
    language: str | None = Query(default=None),
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    items, total = lexicon_service.list_lexicon(
        db, limit=limit, offset=offset, level=level, term_type=term_type,
        language=language, project_id=project_id,
    )
    return LexiconListResponse(
        items=items, total=total, limit=limit, offset=offset,
        has_next=offset + limit < total,
    )


@router.post("/lexicon", response_model=LexiconEntryRead, status_code=201)
async def create_lexicon_entry(
    data: LexiconEntryCreate,
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    return lexicon_service.create_lexicon_entry(db, data, project_id)


@router.get("/lexicon/{entry_id}", response_model=LexiconEntryRead)
async def get_lexicon_entry(entry_id: UUID, db: Session = Depends(get_db)):
    entry = lexicon_service.get_lexicon_entry(db, entry_id)
    if not entry:
        raise AppError("NOT_FOUND", f"Lexicon entry {entry_id} not found", 404)
    return entry


@router.patch("/lexicon/{entry_id}", response_model=LexiconEntryRead)
async def update_lexicon_entry(
    entry_id: UUID, data: LexiconEntryUpdate, db: Session = Depends(get_db)
):
    return lexicon_service.update_lexicon_entry(db, entry_id, data)


@router.delete("/lexicon/{entry_id}", status_code=204)
async def delete_lexicon_entry(entry_id: UUID, db: Session = Depends(get_db)):
    lexicon_service.delete_lexicon_entry(db, entry_id)


# B · Competitor auto-discovery
@router.post("/discover")
async def discover_competitors_endpoint(
    data: dict,
    db: Session = Depends(get_db),
):
    """AI-powered competitor discovery.

    Body: {"category": "项目管理工具", "known_products": ["Linear", "Notion"]}
    Returns a list of DiscoverySuggestion objects grouped by tier.
    """
    category = (data.get("category") or "").strip()
    if not category:
        raise AppError("BAD_REQUEST", "category is required", 400)
    known = data.get("known_products") or []
    suggestions = discover_competitors(category, known)
    return [
        {
            "name": s.name,
            "tier": s.tier,
            "tier_label": s.tier_label,
            "rationale": s.rationale,
            "official_domain": s.official_domain,
            "help_center_domain": s.help_center_domain,
        }
        for s in suggestions
    ]
