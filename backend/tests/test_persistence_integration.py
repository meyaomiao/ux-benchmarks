"""End-to-end persistence integration test (#22/#20/#26/#27).

Drives the real DB round-trip: persist passing candidates as Assets -> recompute
coverage -> read it back. Uses PostgreSQL because the models use PG-only types
(JSONB, UUID, gen_random_uuid()).

SKIPS cleanly when Postgres is unreachable (e.g. local box without psycopg2 or
without a test DB), so it never fabricates a green locally — but runs for real in
CI, where a postgres service + psycopg2-binary are available.
"""
import os
import uuid
from datetime import datetime, timezone

import pytest

# --- skip guard: need psycopg2 + a reachable postgres -----------------------
psycopg2 = pytest.importorskip("psycopg2", reason="psycopg2 not installed (local)")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_TEST_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/ux_benchmarks_test",
)


def _engine_or_skip():
    try:
        eng = create_engine(_TEST_URL)
        conn = eng.connect()
        conn.close()
        return eng
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"postgres not reachable at {_TEST_URL}: {type(e).__name__}")


@pytest.fixture(scope="module")
def db():
    eng = _engine_or_skip()
    from app.core.database import Base
    import app.models  # noqa: F401 — register all tables

    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _seed_cell_and_competitor(db):
    """Insert the FK parents (grid_cell + competitor) this test needs."""
    from app.models.m1_grid import GridCell
    from app.models.m0_registry import CompetitorEntity
    from app.models.project import Project

    suffix = uuid.uuid4().hex[:8]
    project = Project(name=f"Persistence test {suffix}")
    db.add(project)
    db.flush()
    cell = GridCell(
        project_id=project.id,
        cell_key=f"test.persist.{suffix}",
        jtbd="invite + permissions",
        journey_stage="first-setup",
        page_state="role-select",
        value_score=0.9,
    )
    comp = CompetitorEntity(
        project_id=project.id,
        canonical_name=f"TestCo-{suffix}",
    )
    db.add(cell)
    db.add(comp)
    db.commit()
    db.refresh(cell)
    db.refresh(comp)
    return cell.id, comp.id


def _candidate(cell_id, competitor_id, url, text, hint):
    from app.services.m3_collection.contracts import Candidate, SourceType
    return Candidate(
        cell_id=cell_id,
        competitor_id=competitor_id,
        source_url=url,
        source_type=SourceType.HELP_DOCS,
        text_content=text,
        captured_at=datetime.now(timezone.utc),
        rights_status="third_party_official",
        evidence_type_hint=hint,
    )


def _score(candidate, passed, evidence, value):
    from app.services.m3_collection.contracts import Score, RubricBreakdown
    return Score(
        candidate_id=candidate.candidate_id,
        score=value,
        passed=passed,
        evidence_type=evidence,
        rubric=RubricBreakdown(state_match=value),
        reasoning="integration",
        scored_by="mock",
    )


def test_persist_recompute_read_roundtrip(db):
    from app.services.m3_collection.contracts import EvidenceType
    from app.services.m3_collection.asset_store import persist_passing, list_assets_for_cell
    from app.services.m3_collection.coverage_recompute import recompute_coverage
    from app.services.m3_collection.coverage_read import get_cell_coverage
    from app.services.m3_collection.state_machine import CellState
    from app.services.m3_collection.coverage_state_service import get_or_create_snapshot

    cell_id, competitor_id = _seed_cell_and_competitor(db)

    # Move the snapshot to PROBING first (recompute only advances to SHORTLIST_READY
    # from a state that permits it, mirroring the real probe_cycle path).
    snap = get_or_create_snapshot(db, cell_id, competitor_id)
    from app.services.m3_collection.coverage_state_service import transition_state
    transition_state(db, cell_id, competitor_id, CellState.QUEUED)
    transition_state(db, cell_id, competitor_id, CellState.PROBING)

    c1 = _candidate(cell_id, competitor_id, "https://help.co/roles", "step by step role editor", EvidenceType.OBSERVED)
    c2 = _candidate(cell_id, competitor_id, "https://help.co/invite", "invite dialog role dropdown", EvidenceType.OBSERVED)
    # duplicate of c1 (same url + content) -> must dedup
    c1_dupe = _candidate(cell_id, competitor_id, "https://help.co/roles", "step by step role editor", EvidenceType.OBSERVED)

    scored = [
        (c1, _score(c1, True, EvidenceType.OBSERVED, 0.8)),
        (c2, _score(c2, True, EvidenceType.OBSERVED, 0.7)),
        (c1_dupe, _score(c1_dupe, True, EvidenceType.OBSERVED, 0.8)),
    ]

    assets = persist_passing(db, cell_id, competitor_id, scored)
    # 3 passing pairs but c1_dupe dedups -> 2 distinct rows
    stored = list_assets_for_cell(db, cell_id, competitor_id)
    assert len(stored) == 2, f"dedup failed: {len(stored)} rows"

    snapshot = recompute_coverage(db, cell_id, competitor_id)

    # Honesty invariant: evidence found -> SHORTLIST_READY, NEVER SATURATED.
    assert snapshot.status == CellState.SHORTLIST_READY
    assert snapshot.status != CellState.SATURATED

    # Metrics reflect the 2 distinct observed sources.
    assert snapshot.independent_source_count == 2
    assert snapshot.coverage_confidence > 0.0

    # Read-side returns the same numbers.
    row = get_cell_coverage(db, cell_id, competitor_id)
    assert row["independent_source_count"] == 2
    assert row["status"] == CellState.SHORTLIST_READY


def test_claimed_evidence_excluded_from_count(db):
    from app.services.m3_collection.contracts import EvidenceType
    from app.services.m3_collection.asset_store import persist_passing
    from app.services.m3_collection.coverage_recompute import recompute_coverage
    from app.services.m3_collection.coverage_state_service import (
        get_or_create_snapshot, transition_state,
    )
    from app.services.m3_collection.state_machine import CellState

    cell_id, competitor_id = _seed_cell_and_competitor(db)
    get_or_create_snapshot(db, cell_id, competitor_id)
    transition_state(db, cell_id, competitor_id, CellState.QUEUED)
    transition_state(db, cell_id, competitor_id, CellState.PROBING)

    observed = _candidate(cell_id, competitor_id, "https://help.co/x", "role permission editor toggle", EvidenceType.OBSERVED)
    claimed = _candidate(cell_id, competitor_id, "https://mkt.co/y", "flexible permissions", EvidenceType.CLAIMED)

    persist_passing(db, cell_id, competitor_id, [
        (observed, _score(observed, True, EvidenceType.OBSERVED, 0.8)),
        (claimed, _score(claimed, True, EvidenceType.CLAIMED, 0.6)),
    ])
    snapshot = recompute_coverage(db, cell_id, competitor_id)

    # claimed never counts toward coverage
    assert snapshot.independent_source_count == 1
