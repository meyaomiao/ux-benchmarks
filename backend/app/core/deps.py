"""Shared FastAPI dependencies."""
from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError
from app.models.project import Project


def get_project_id(
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
    db: Session = Depends(get_db),
) -> UUID:
    """Resolve the active project from the X-Project-Id header.

    Every scoped read/write goes through this so data from one project never
    leaks into another. Raises 400 if the header is missing/invalid, 404 if the
    project doesn't exist.
    """
    if not x_project_id:
        raise AppError("NO_PROJECT", "缺少 X-Project-Id 请求头，请先选择项目", 400)
    try:
        pid = UUID(x_project_id)
    except (ValueError, TypeError):
        raise AppError("BAD_PROJECT", "X-Project-Id 不是合法 UUID", 400)
    if not db.get(Project, pid):
        raise AppError("PROJECT_NOT_FOUND", f"项目 {pid} 不存在", 404)
    return pid
