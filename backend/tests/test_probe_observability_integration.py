"""PostgreSQL round-trip for the M3 probe run ledger."""

import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

pytest.importorskip("psycopg2", reason="psycopg2 not installed")

from app.schemas.m3 import ProbeRunRead
from app.services.m3_collection.probe_observability import (
    ProbeTelemetry,
    list_probe_runs,
    log_probe_run,
    summarize_probe_runs,
)

_TEST_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/ux_benchmarks_test",
)


@pytest.fixture(scope="module")
def db():
    try:
        engine = create_engine(_TEST_URL)
        connection = engine.connect()
        connection.close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"postgres not reachable: {type(exc).__name__}")

    import app.models  # noqa: F401
    from app.core.database import Base

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _seed_pair(db, project_name):
    from app.models.m0_registry import CompetitorEntity
    from app.models.m1_grid import GridCell
    from app.models.project import Project

    suffix = uuid.uuid4().hex[:8]
    project = Project(name=f"{project_name}-{suffix}")
    db.add(project)
    db.flush()
    cell = GridCell(
        project_id=project.id,
        cell_key=f"probe.run.{suffix}",
        jtbd="review permissions",
        journey_stage="review",
        page_state="permissions",
        value_score=0.8,
    )
    competitor = CompetitorEntity(
        project_id=project.id,
        canonical_name=f"Competitor-{suffix}",
    )
    db.add_all([cell, competitor])
    db.commit()
    return project.id, cell.id, competitor.id


def _write_run(db, cell_id, competitor_id, strategy, *, passed):
    telemetry = ProbeTelemetry(strategy_version=strategy)
    telemetry.source_stats = {
        "help_docs": {
            "search_calls": 2,
            "browser_pages": 1,
            "candidates_found": 3,
        }
    }
    telemetry.agentic_stats = {"model_calls": 1, "stop_reason": "model_stop"}
    telemetry.scoring_calls = 3
    return log_probe_run(
        db,
        cell_id,
        competitor_id,
        telemetry,
        probe_cycle=1,
        outcome="completed",
        final_state="SHORTLIST_READY" if passed else "REJECTED_EMPTY",
        candidates_found=3,
        scored_count=3,
        passed_count=1 if passed else 0,
        persisted_count=1 if passed else 0,
    )


def test_probe_run_roundtrip_is_project_scoped_and_grouped_by_strategy(db):
    project_a, cell_a, competitor_a = _seed_pair(db, "Probe ledger A")
    project_b, cell_b, competitor_b = _seed_pair(db, "Probe ledger B")
    run_a1 = _write_run(db, cell_a, competitor_a, "strategy-a", passed=True)
    run_a2 = _write_run(db, cell_a, competitor_a, "strategy-b", passed=False)
    _write_run(db, cell_b, competitor_b, "strategy-a", passed=True)

    rows, total = list_probe_runs(
        db,
        project_a,
        limit=10,
        offset=0,
        cell_id=cell_a,
        competitor_id=competitor_a,
    )

    assert total == 2
    assert {row.id for row in rows} == {run_a1.id, run_a2.id}
    assert all(row.project_id == project_a for row in rows)
    assert ProbeRunRead.model_validate(rows[0]).source_stats["help_docs"][
        "candidates_found"
    ] == 3

    strategy_rows, strategy_total = list_probe_runs(
        db,
        project_a,
        limit=1,
        offset=0,
        strategy_version="strategy-a",
    )
    assert strategy_total == 1
    assert [row.id for row in strategy_rows] == [run_a1.id]

    summary = {row["strategy_version"]: row for row in summarize_probe_runs(db, project_a)}
    assert set(summary) == {"strategy-a", "strategy-b"}
    assert summary["strategy-a"]["run_success_rate"] == 1.0
    assert summary["strategy-a"]["candidate_pass_rate"] == pytest.approx(1 / 3)
    assert summary["strategy-a"]["avg_scoring_calls"] == 3.0
    assert summary["strategy-b"]["run_success_rate"] == 0.0
