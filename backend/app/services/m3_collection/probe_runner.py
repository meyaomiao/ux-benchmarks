"""Synchronous probe runner — shared by the Celery worker and the HTTP endpoint.

Extracts the end-to-end probe orchestration (state transitions + pipeline +
persistence + coverage recompute) so it can run either:
  - async via Celery worker (app/workers/tasks/probe_cycle.py), or
  - synchronously via POST /m3/probe-now (when no worker is running, so the
    user gets immediate collection progress in the UI).

Returns a plain dict of counts + final state.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.m3_collection.asset_store import persist_passing
from app.services.m3_collection.coverage_recompute import recompute_coverage
from app.services.m3_collection.coverage_state_service import transition_state
from app.services.m3_collection.pipeline import run_probe_pipeline
from app.services.m3_collection.state_machine import CellState

logger = logging.getLogger(__name__)


def run_probe(db: Session, cell_id: UUID, competitor_id: UUID) -> dict:
    """Run one full probe cycle synchronously for a (cell, competitor) pair.

    1. -> PROBING
    2. query expansion -> adapter fetch -> AI scoring (pipeline)
    3a. passers  -> persist Assets + recompute coverage (-> SHORTLIST_READY)
    3b. no passers -> REJECTED_EMPTY

    Never raises for a normal empty result; genuine errors propagate to caller.
    """
    cid, kid = cell_id, competitor_id
    transition_state(db, str(cid), str(kid), CellState.PROBING, note="probe-now")

    result = run_probe_pipeline(db, cid, kid)

    if result.has_passers:
        assets = persist_passing(db, cid, kid, result.passed)
        snapshot = recompute_coverage(db, cid, kid)
        persisted = len(assets)
    else:
        snapshot = transition_state(
            db, str(cid), str(kid), CellState.REJECTED_EMPTY,
            note="probe-now: no passing evidence",
        )
        persisted = 0

    return {
        "cell_id": str(cid),
        "competitor_id": str(kid),
        "state": snapshot.status,
        "probe_cycles": snapshot.probe_cycles,
        "candidates_found": result.candidates_found,
        "passed": len(result.passed),
        "persisted": persisted,
    }
