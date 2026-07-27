"""Project CRUD — the top-level workspace container.

Deleting a project cascades to all its scoped data (probe diagnostics,
competitors, cells, mapping cards, assets, observations, coverage, insights,
reports) via raw deletes in FK-safe order, since those tables carry project_id.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.project import Project


def list_projects(db: Session) -> list[Project]:
    return list(
        db.execute(select(Project).order_by(Project.created_at.desc())).scalars().all()
    )


def get_project(db: Session, project_id: UUID) -> Project | None:
    return db.get(Project, project_id)


def create_project(db: Session, name: str, category: str = "", description: str = "") -> Project:
    if not name.strip():
        raise AppError("BAD_REQUEST", "项目名称不能为空", 400)
    project = Project(name=name.strip(), category=category.strip(), description=description.strip())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def update_project(db: Session, project_id: UUID, data: dict) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise AppError("NOT_FOUND", f"Project {project_id} not found", 404)
    for k, v in data.items():
        if v is not None and hasattr(project, k):
            setattr(project, k, v)
    db.commit()
    db.refresh(project)
    return project


# Tables carrying project_id, deleted leaves-first for FK safety.
_SCOPED_TABLES = [
    "probe_run_logs",
    "probe_score_logs",
    "reports",
    "insights",
    "observations",
    "assets",
    "coverage_snapshots",
    "mapping_cards",
    "grid_cells",
    "domain_lexicon",
    "competitor_entities",
]


def delete_project(db: Session, project_id: UUID) -> bool:
    project = db.get(Project, project_id)
    if not project:
        raise AppError("NOT_FOUND", f"Project {project_id} not found", 404)
    pid = {"pid": str(project_id)}
    # Internal child tables (no project_id) — delete via their parent scope first.
    db.execute(text(
        "DELETE FROM claims WHERE observation_id IN "
        "(SELECT o.id FROM observations o WHERE o.project_id = :pid)"
    ), pid)
    db.execute(text(
        "DELETE FROM cell_changelogs WHERE cell_id IN "
        "(SELECT g.id FROM grid_cells g WHERE g.project_id = :pid)"
    ), pid)
    # Then all project_id-scoped tables, leaves first.
    for table in _SCOPED_TABLES:
        db.execute(text(f"DELETE FROM {table} WHERE project_id = :pid"), pid)
    db.delete(project)
    db.commit()
    return True
