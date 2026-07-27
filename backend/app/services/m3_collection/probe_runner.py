"""Synchronous probe implementation owned by the browser Celery worker.

The Celery task calls this function inline after it has acquired one browser
worker slot. HTTP entry points enqueue that task and never call this module
directly, keeping every production probe under the same concurrency and timeout
limits.

Returns a plain dict of counts + final state.
"""
from __future__ import annotations

import logging
from uuid import UUID

from billiard.exceptions import SoftTimeLimitExceeded
from sqlalchemy.orm import Session

from app.services.m3_collection.asset_store import persist_passing
from app.services.m3_collection.coverage_recompute import (
    has_live_evidence,
    recompute_coverage,
)
from app.services.m3_collection.coverage_state_service import (
    get_or_create_snapshot,
    transition_state,
)
from app.services.m3_collection.queue_service import enqueue_cell
from app.services.m3_collection.pipeline import run_probe_pipeline
from app.services.m3_collection.score_log import log_scored_candidates
from app.services.m3_collection.state_machine import CellState, Trigger

logger = logging.getLogger(__name__)


def run_probe(db: Session, cell_id: UUID, competitor_id: UUID) -> dict:
    """Run one full probe cycle synchronously for a (cell, competitor) pair.

    0. normalise to QUEUED (MANUAL_PIN handles any prior state: REJECTED_EMPTY,
       PARTIAL, SATURATED→STALE→QUEUED, etc.) — PROBING is only reachable from
       QUEUED per the state machine.
    1. QUEUED -> PROBING
    2. query expansion -> adapter fetch -> AI scoring (pipeline)
    3. log EVERY scored candidate (diagnostics, incl. rejects)
    4a. passers  -> persist Assets + recompute coverage (-> SHORTLIST_READY)
    4b. no passers -> recompute coverage from whatever Assets already exist, so
        the pair's metrics never keep stale numbers from an earlier cycle. Only
        a pair with no live evidence at all becomes REJECTED_EMPTY.

    Never raises for a normal empty result; genuine errors propagate to caller.
    """
    cid, kid = cell_id, competitor_id
    # Force re-collection from whatever state the pair is in → QUEUED.
    snap = enqueue_cell(db, cid, kid, Trigger.MANUAL_PIN)
    if snap.status != CellState.QUEUED:
        # Already PROBING (a concurrent run) — bail politely.
        return {
            "cell_id": str(cid), "competitor_id": str(kid), "state": snap.status,
            "probe_cycles": snap.probe_cycles, "candidates_found": 0,
            "passed": 0, "persisted": 0,
        }
    probing = transition_state(
        db, str(cid), str(kid), CellState.PROBING, note="probe-cycle"
    )

    # A probe must ALWAYS reach a terminal state, even if the pipeline throws.
    # Recover the state first, then preserve the failure for Celery/API callers.
    try:
        result = run_probe_pipeline(db, cid, kid)
    except SoftTimeLimitExceeded:
        transition_state(
            db,
            str(cid),
            str(kid),
            CellState.REJECTED_EMPTY,
            note="probe-cycle: soft time limit exceeded",
        )
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("probe pipeline failed for %s/%s: %s", cid, kid, exc)
        transition_state(
            db, str(cid), str(kid), CellState.REJECTED_EMPTY,
            note=f"probe-cycle: pipeline error: {str(exc)[:120]}",
        )
        raise

    log_scored_candidates(
        db, cid, kid, result.scored, probe_cycle=probing.probe_cycles
    )

    if result.has_passers:
        assets = persist_passing(db, cid, kid, result.passed)
        snapshot = recompute_coverage(db, cid, kid)
        persisted = len(assets)
    else:
        # This cycle found nothing NEW — that does not mean the pair has no
        # evidence. Recompute from the Assets already on file first: it refreshes
        # the metrics (so an earlier cycle's confidence can't linger) and re-aims
        # the state at SHORTLIST_READY when live evidence exists.
        snapshot = recompute_coverage(db, cid, kid)
        if not has_live_evidence(db, cid, kid):
            snapshot = transition_state(
                db, str(cid), str(kid), CellState.REJECTED_EMPTY,
                note="probe-cycle: no passing evidence",
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
        "agentic_stats": result.agentic_stats,
    }
