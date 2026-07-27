"""L5 report API routes."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_project_id
from app.core.errors import AppError
from app.schemas.l5 import ReportCompose, ReportRead
from app.services.l5_report import report_service

router = APIRouter(prefix="/reports", tags=["L5 · Reports"])


@router.post("", response_model=ReportRead, status_code=201)
async def compose_report(
    data: ReportCompose,
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    """重组选定的洞察，生成指定受众/格式的 Markdown 报告。"""
    return report_service.compose_report(
        db,
        insight_ids=data.insight_ids,
        audience=data.audience,
        format_type=data.format_type,
        title=data.title,
        project_id=project_id,
    )


@router.get("", response_model=list[ReportRead])
async def list_reports(
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    return report_service.list_reports(db, project_id)


@router.get("/{report_id}", response_model=ReportRead)
async def get_report(
    report_id: UUID,
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    obj = report_service.get_report(db, report_id, project_id)
    if not obj:
        raise AppError("NOT_FOUND", f"Report {report_id} not found", 404)
    return obj


@router.delete("/{report_id}", status_code=204)
async def delete_report(
    report_id: UUID,
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    report_service.delete_report(db, report_id, project_id)
