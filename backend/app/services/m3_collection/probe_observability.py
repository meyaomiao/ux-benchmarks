"""Append-only telemetry for comparing M3 probe recall and cost."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from billiard.exceptions import SoftTimeLimitExceeded
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.m1_grid import GridCell
from app.models.m3_probe_log import ProbeRunLog

logger = logging.getLogger(__name__)

STRATEGY_VERSION = "m3-agentic-ui-v1"


def _rollback_quietly(db: Session) -> None:
    try:
        db.rollback()
    except Exception as exc:  # noqa: BLE001 - logging cleanup is also best-effort
        logger.warning("probe run logging rollback failed: %s", exc)


@dataclass
class ProbeTelemetry:
    """Mutable counters shared by the probe runner and pipeline."""

    strategy_version: str = STRATEGY_VERSION
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_budgets: dict[str, dict[str, int]] = field(default_factory=dict)
    source_stats: dict[str, dict] = field(default_factory=dict)
    agentic_stats: dict[str, int | str] = field(default_factory=dict)
    agentic_trace: list[dict] = field(default_factory=list)
    scoring_calls: int = 0
    rescore_render_attempts: int = 0
    finished_at: datetime | None = None
    duration_ms: int | None = None
    _started_monotonic: float = field(default_factory=time.monotonic, repr=False)

    @property
    def search_calls(self) -> int:
        return sum(int(stats.get("search_calls", 0)) for stats in self.source_stats.values())

    @property
    def browser_pages(self) -> int:
        source_pages = sum(
            int(stats.get("browser_pages", 0)) for stats in self.source_stats.values()
        )
        return source_pages + self.rescore_render_attempts

    @property
    def agentic_model_calls(self) -> int:
        return int(self.agentic_stats.get("model_calls", 0))

    def elapsed_ms(self) -> int:
        if self.duration_ms is not None:
            return self.duration_ms
        return max(0, int((time.monotonic() - self._started_monotonic) * 1000))

    def finish(self) -> datetime:
        if self.finished_at is None:
            self.finished_at = datetime.now(timezone.utc)
            self.duration_ms = self.elapsed_ms()
        return self.finished_at

    def summary(self) -> dict[str, int | str]:
        return {
            "strategy_version": self.strategy_version,
            "search_calls": self.search_calls,
            "browser_pages": self.browser_pages,
            "agentic_model_calls": self.agentic_model_calls,
            "scoring_calls": self.scoring_calls,
            "duration_ms": self.elapsed_ms(),
        }


def log_probe_run(
    db: Session,
    cell_id: UUID,
    competitor_id: UUID,
    telemetry: ProbeTelemetry,
    *,
    probe_cycle: int | None,
    outcome: str,
    final_state: str | None,
    candidates_found: int = 0,
    scored_count: int = 0,
    passed_count: int = 0,
    persisted_count: int = 0,
    error_type: str | None = None,
) -> ProbeRunLog | None:
    """Persist one run without ever changing the probe's business result."""
    try:
        project_id = db.execute(
            select(GridCell.project_id).where(GridCell.id == cell_id)
        ).scalar_one()
        finished_at = telemetry.finish()
        row = ProbeRunLog(
            id=uuid4(),
            project_id=project_id,
            cell_id=cell_id,
            competitor_id=competitor_id,
            probe_cycle=probe_cycle,
            strategy_version=telemetry.strategy_version,
            outcome=outcome,
            final_state=final_state,
            candidates_found=candidates_found,
            scored_count=scored_count,
            passed_count=passed_count,
            persisted_count=persisted_count,
            search_calls=telemetry.search_calls,
            browser_pages=telemetry.browser_pages,
            scoring_calls=telemetry.scoring_calls,
            agentic_model_calls=telemetry.agentic_model_calls,
            duration_ms=telemetry.elapsed_ms(),
            source_budgets=telemetry.source_budgets or None,
            source_stats=telemetry.source_stats or None,
            agentic_stats=telemetry.agentic_stats or None,
            agentic_trace=telemetry.agentic_trace or None,
            error_type=error_type,
            started_at=telemetry.started_at,
            finished_at=finished_at,
        )
        db.add(row)
        db.commit()
        return row
    except SoftTimeLimitExceeded:
        _rollback_quietly(db)
        raise
    except Exception as exc:  # noqa: BLE001 - observability must not fail a probe
        logger.warning("probe run logging failed for %s/%s: %s", cell_id, competitor_id, exc)
        _rollback_quietly(db)
        return None


def list_probe_runs(
    db: Session,
    project_id: UUID,
    *,
    limit: int,
    offset: int,
    cell_id: UUID | None = None,
    competitor_id: UUID | None = None,
    strategy_version: str | None = None,
) -> tuple[list[ProbeRunLog], int]:
    filters = [ProbeRunLog.project_id == project_id]
    if cell_id is not None:
        filters.append(ProbeRunLog.cell_id == cell_id)
    if competitor_id is not None:
        filters.append(ProbeRunLog.competitor_id == competitor_id)
    if strategy_version:
        filters.append(ProbeRunLog.strategy_version == strategy_version)

    total = db.execute(
        select(func.count()).select_from(ProbeRunLog).where(*filters)
    ).scalar_one()
    rows = db.execute(
        select(ProbeRunLog)
        .where(*filters)
        .order_by(ProbeRunLog.started_at.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return list(rows), total


def summarize_probe_runs(db: Session, project_id: UUID) -> list[dict]:
    """Aggregate recall and cost by explicit strategy version."""
    rows = db.execute(
        select(
            ProbeRunLog.strategy_version,
            func.count(ProbeRunLog.id).label("runs"),
            func.sum(ProbeRunLog.candidates_found).label("candidates_found"),
            func.sum(ProbeRunLog.scored_count).label("scored_count"),
            func.sum(ProbeRunLog.passed_count).label("passed_count"),
            func.sum(ProbeRunLog.persisted_count).label("persisted_count"),
            func.sum(
                case((ProbeRunLog.passed_count > 0, 1), else_=0)
            ).label("runs_with_passers"),
            func.avg(ProbeRunLog.duration_ms).label("avg_duration_ms"),
            func.avg(ProbeRunLog.search_calls).label("avg_search_calls"),
            func.avg(ProbeRunLog.browser_pages).label("avg_browser_pages"),
            func.avg(ProbeRunLog.scoring_calls).label("avg_scoring_calls"),
            func.avg(ProbeRunLog.agentic_model_calls).label(
                "avg_agentic_model_calls"
            ),
            func.avg(
                ProbeRunLog.scoring_calls + ProbeRunLog.agentic_model_calls
            ).label("avg_model_calls"),
        )
        .where(ProbeRunLog.project_id == project_id)
        .group_by(ProbeRunLog.strategy_version)
        .order_by(ProbeRunLog.strategy_version)
    ).all()

    summaries = []
    for row in rows:
        candidates = int(row.candidates_found or 0)
        runs = int(row.runs or 0)
        summaries.append(
            {
                "strategy_version": row.strategy_version,
                "runs": runs,
                "runs_with_passers": int(row.runs_with_passers or 0),
                "candidates_found": candidates,
                "scored_count": int(row.scored_count or 0),
                "passed_count": int(row.passed_count or 0),
                "persisted_count": int(row.persisted_count or 0),
                "run_success_rate": (
                    float(row.runs_with_passers or 0) / runs if runs else 0.0
                ),
                "candidate_pass_rate": (
                    float(row.passed_count or 0) / candidates if candidates else 0.0
                ),
                "candidate_persist_rate": (
                    float(row.persisted_count or 0) / candidates if candidates else 0.0
                ),
                "avg_duration_ms": float(row.avg_duration_ms or 0),
                "avg_search_calls": float(row.avg_search_calls or 0),
                "avg_browser_pages": float(row.avg_browser_pages or 0),
                "avg_scoring_calls": float(row.avg_scoring_calls or 0),
                "avg_agentic_model_calls": float(row.avg_agentic_model_calls or 0),
                "avg_model_calls": float(row.avg_model_calls or 0),
            }
        )
    return summaries
