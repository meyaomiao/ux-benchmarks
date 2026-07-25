"""Operator-only maintenance endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.m3_collection.backfill_scorer import rescore_project_assets

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post("/projects/{project_id}/rescore")
def rescore_project(project_id: UUID, db: Session = Depends(get_db)):
    """Replace one project's historical mock Asset scores with GPT scores."""
    result = rescore_project_assets(db, project_id)
    return {
        "project_id": str(result.project_id),
        "rescored_assets": result.rescored_assets,
        "coverage_pairs": result.coverage_pairs,
    }
