import logging
from uuid import UUID

from celery.exceptions import (
    BackendError,
    OperationalError,
    TimeLimitExceeded,
    TimeoutError as CeleryTimeoutError,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_project_id
from app.core.errors import AppError
from app.schemas.m3 import (
    QueueItemRead, QueueListResponse, PinRequest,
    QueryBundle, SourceRegistryListResponse,
)
from app.services.m3_collection.queue_service import (
    count_queued,
    enqueue_cell,
    list_queued,
    reclaim_stuck_probing,
    stop_queued,
)
from app.services.m3_collection.query_expansion import build_query_bundle
from app.services.m3_collection import source_registry_service
from app.services.m3_collection.state_machine import CellState, Trigger
from app.services.m3_collection.screenshot_service import capture_url
from app.workers.tasks.probe_cycle import PROBE_HARD_TIME_LIMIT, run_probe_cycle
from app.models.m1_grid import GridCell
from app.models.m0_registry import CompetitorEntity
from sqlalchemy import select

router = APIRouter(prefix="/m3", tags=["M3 · Collection Engine"])
logger = logging.getLogger(__name__)

BROWSER_QUEUE = "browser"
PROBE_NOW_RESULT_TIMEOUT = PROBE_HARD_TIME_LIMIT + 60
_PROBE_RESULT_FIELDS = {
    "cell_id",
    "competitor_id",
    "state",
    "probe_cycles",
    "candidates_found",
    "passed",
    "persisted",
}


# --- Queue (#14) ---------------------------------------------------------

@router.get("/queue", response_model=QueueListResponse)
async def get_queue_status(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    items = list_queued(db, limit, project_id)
    # total = TRUE queued count (not len(items), which is capped by `limit`).
    return QueueListResponse(items=items, total=count_queued(db, project_id))


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
def manual_screenshot(data: dict, db: Session = Depends(get_db)):
    """Take a Playwright screenshot of a URL and add it to the shortlist.

    Sync def (not async) so Playwright sync API runs in a threadpool without
    an event loop. Body: {"url", "cell_id", "competitor_id"}. Returns Asset.
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


# --- Batch enqueue (#4) -----------------------------------------------------

@router.post("/queue/enqueue-all")
async def enqueue_all(
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    """Queue every (active cell × confirmed competitor) pair in this project.

    One click instead of pinning pairs one by one. Already-queued/probing
    pairs are no-ops. Returns how many pairs were newly queued.
    """
    cells = list(db.execute(
        select(GridCell).where(
            GridCell.status == "active", GridCell.project_id == project_id
        )
    ).scalars().all())
    comps = list(db.execute(
        select(CompetitorEntity).where(
            CompetitorEntity.status == "confirmed", CompetitorEntity.project_id == project_id
        )
    ).scalars().all())

    queued = 0
    for cell in cells:
        for comp in comps:
            snap = enqueue_cell(db, cell.id, comp.id, Trigger.COVERAGE_GAP)
            if snap.status == "QUEUED":
                queued += 1
    return {
        "cells": len(cells),
        "competitors": len(comps),
        "pairs_total": len(cells) * len(comps),
        "newly_queued": queued,
    }


# --- Async batch dispatch (#51) --------------------------------------------

@router.post("/dispatch-queued")
async def dispatch_queued(
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    """Dispatch every QUEUED pair in this project to the browser queue.

    Returns immediately with how many were dispatched. The workers run each
    probe server-side and write results to the DB, so progress survives page
    navigation / tab close — the frontend just polls /m5/metrics for counts.
    """
    from app.models.m5_coverage import CoverageSnapshot
    rows = list(db.execute(
        select(CoverageSnapshot).where(
            CoverageSnapshot.project_id == project_id,
            CoverageSnapshot.status == "QUEUED",
        )
    ).scalars().all())

    dispatched = 0
    for r in rows:
        try:
            run_probe_cycle.apply_async(
                args=(str(r.cell_id), str(r.competitor_id)),
                queue=BROWSER_QUEUE,
            )
            dispatched += 1
        except Exception as exc:  # noqa: BLE001 — broker down etc.
            raise AppError("DISPATCH_FAILED", f"派发失败（worker/broker 不可用？）：{exc}", 503)
    return {"dispatched": dispatched}


@router.post("/stop-collection")
async def stop_collection(
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    """Cancel pending collection: reset QUEUED pairs → UNPROBED (cooperative).

    Pending tasks still in the broker skip cheaply when they fire (the task
    guards on QUEUED status). In-flight PROBING tasks (≤ worker concurrency)
    finish naturally. Returns how many pending pairs were stopped.
    """
    stopped = stop_queued(db, project_id)
    return {"stopped": stopped}


@router.post("/reclaim-stuck")
async def reclaim_stuck(
    db: Session = Depends(get_db),
    project_id: UUID = Depends(get_project_id),
):
    """Release pairs abandoned in PROBING by a crashed worker task.

    PROBING is only reachable from QUEUED, so an abandoned worker task can never be
    re-queued on its own and drops out of collection silently. Returns how many
    pairs were released.
    """
    return {"reclaimed": reclaim_stuck_probing(db, project_id)}


# --- Queue-backed probe with synchronous response (#5) ---------------------

@router.post("/probe-now")
def probe_now(data: dict, db: Session = Depends(get_db)):
    """Queue one probe on the isolated browser worker and wait for its result.

    Body: {"cell_id": "uuid", "competitor_id": "uuid"}
    This remains a sync endpoint so waiting does not block the ASGI event loop;
    Chromium and the probe pipeline run only in the browser Celery worker.
    """
    try:
        cell_id = UUID(str(data.get("cell_id", "")))
        competitor_id = UUID(str(data.get("competitor_id", "")))
    except (ValueError, AttributeError):
        raise AppError("BAD_REQUEST", "cell_id and competitor_id must be valid UUIDs", 400)

    snapshot = enqueue_cell(db, cell_id, competitor_id, Trigger.MANUAL_PIN)
    if snapshot.status == CellState.PROBING:
        raise AppError("PROBE_ALREADY_RUNNING", "该采集任务已在运行", 409)
    if snapshot.status != CellState.QUEUED:
        raise AppError("PROBE_NOT_QUEUEABLE", f"当前状态无法采集：{snapshot.status}", 409)

    try:
        async_result = run_probe_cycle.apply_async(
            args=(str(cell_id), str(competitor_id)),
            queue=BROWSER_QUEUE,
        )
    except Exception as exc:  # noqa: BLE001 - broker/client implementations vary
        logger.warning(
            "probe-now dispatch failed for %s/%s: %s", cell_id, competitor_id, exc
        )
        raise AppError(
            "PROBE_DISPATCH_FAILED", "采集队列不可用，请稍后重试", 503
        ) from exc

    try:
        result = async_result.get(timeout=PROBE_NOW_RESULT_TIMEOUT, propagate=True)
    except CeleryTimeoutError as exc:
        logger.warning("probe-now wait timed out for %s/%s", cell_id, competitor_id)
        raise AppError(
            "PROBE_WAIT_TIMEOUT",
            "等待采集结果超时；队列中的任务不会被标记为空结果",
            504,
        ) from exc
    except TimeLimitExceeded as exc:
        logger.warning("probe-now worker hard timeout for %s/%s", cell_id, competitor_id)
        raise AppError("PROBE_EXECUTION_TIMEOUT", "采集 worker 执行超时", 504) from exc
    except (BackendError, OperationalError) as exc:
        logger.warning(
            "probe-now result backend failed for %s/%s: %s",
            cell_id,
            competitor_id,
            exc,
        )
        raise AppError(
            "PROBE_RESULT_UNAVAILABLE", "采集结果服务不可用，请稍后重试", 503
        ) from exc
    except Exception as exc:  # noqa: BLE001 - task failures preserve their original types
        logger.warning("probe-now worker failed for %s/%s: %s", cell_id, competitor_id, exc)
        raise AppError("PROBE_EXECUTION_FAILED", "采集 worker 执行失败", 502) from exc

    if not isinstance(result, dict):
        raise AppError("PROBE_INVALID_RESULT", "采集 worker 返回了无效结果", 502)

    status = result.get("status")
    if status in {"timeout", "recovered"}:
        raise AppError("PROBE_EXECUTION_TIMEOUT", "采集 worker 执行超时", 504)
    if status == "skipped":
        raise AppError("PROBE_ALREADY_RUNNING", "采集任务已由另一请求处理", 409)
    if status != "done" or not _PROBE_RESULT_FIELDS.issubset(result):
        raise AppError("PROBE_INVALID_RESULT", "采集 worker 返回字段不完整", 502)
    return result
