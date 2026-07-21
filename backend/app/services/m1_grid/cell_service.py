import re
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.models.m1_grid import GridCell, CellChangelog
from app.schemas.m1 import GridCellCreate, GridCellUpdate
from app.core.errors import AppError


def _auto_key(jtbd: str, journey_stage: str, page_state: str) -> str:
    def slug(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return f"{slug(jtbd)}.{slug(journey_stage)}.{slug(page_state)}"


def list_cells(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    jtbd: str | None = None,
    journey_stage: str | None = None,
    status: str | None = None,
) -> tuple[list[GridCell], int]:
    q = select(GridCell)
    if jtbd:
        q = q.where(GridCell.jtbd.ilike(f"%{jtbd}%"))
    if journey_stage:
        q = q.where(GridCell.journey_stage == journey_stage)
    if status:
        q = q.where(GridCell.status == status)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    items = list(db.scalars(q.offset(offset).limit(limit)).all())
    return items, total or 0


def get_cell(db: Session, cell_id: UUID) -> GridCell | None:
    return db.get(GridCell, cell_id)


def get_cell_by_key(db: Session, cell_key: str) -> GridCell | None:
    return db.scalar(select(GridCell).where(GridCell.cell_key == cell_key))


def create_cell(db: Session, data: GridCellCreate) -> GridCell:
    key = data.cell_key or _auto_key(data.jtbd, data.journey_stage, data.page_state)
    if get_cell_by_key(db, key):
        raise AppError("DUPLICATE_CELL_KEY", f"Cell key '{key}' already exists", 409)
    cell = GridCell(
        cell_key=key,
        jtbd=data.jtbd,
        journey_stage=data.journey_stage,
        page_state=data.page_state,
        value_score=data.value_score,
    )
    db.add(cell)
    db.flush()
    db.add(CellChangelog(cell_id=cell.id, operation="ADD", change_note="Cell created"))
    db.commit()
    db.refresh(cell)
    return cell


def update_cell(db: Session, cell_id: UUID, data: GridCellUpdate) -> GridCell:
    cell = db.get(GridCell, cell_id)
    if not cell:
        raise AppError("NOT_FOUND", f"Cell {cell_id} not found", 404)
    previous: dict = {}
    if data.value_score is not None:
        previous["value_score"] = cell.value_score
        cell.value_score = data.value_score
    if data.status is not None:
        previous["status"] = cell.status
        cell.status = data.status
    if previous:
        op = "DEPRECATE" if data.status == "deprecated" else "UPDATE"
        db.add(CellChangelog(cell_id=cell.id, operation=op, previous_values=previous))
    db.commit()
    db.refresh(cell)
    return cell


def get_cell_changelog(db: Session, cell_id: UUID) -> list[CellChangelog]:
    return list(
        db.scalars(
            select(CellChangelog)
            .where(CellChangelog.cell_id == cell_id)
            .order_by(CellChangelog.created_at.desc())
        ).all()
    )
