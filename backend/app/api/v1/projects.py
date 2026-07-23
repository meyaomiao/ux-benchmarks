"""Project API — top-level workspace CRUD."""
from __future__ import annotations

from uuid import UUID

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError
from app.services import project_service

router = APIRouter(prefix="/projects", tags=["Projects"])


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    category: str = Field("", max_length=200)
    description: str = Field("", max_length=2000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    category: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=2000)


class ProjectRead(BaseModel):
    id: UUID
    name: str
    category: str
    description: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[ProjectRead])
async def list_projects(db: Session = Depends(get_db)):
    return project_service.list_projects(db)


@router.post("", response_model=ProjectRead, status_code=201)
async def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    return project_service.create_project(db, data.name, data.category, data.description)


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: UUID, db: Session = Depends(get_db)):
    obj = project_service.get_project(db, project_id)
    if not obj:
        raise AppError("NOT_FOUND", f"Project {project_id} not found", 404)
    return obj


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(project_id: UUID, data: ProjectUpdate, db: Session = Depends(get_db)):
    return project_service.update_project(db, project_id, data.model_dump(exclude_none=True))


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: UUID, db: Session = Depends(get_db)):
    project_service.delete_project(db, project_id)
