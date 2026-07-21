"""Recompute a CoverageSnapshot's metrics + state from persisted Assets.

This is the M3 -> M5 bridge: it reads the non-superseded Assets collected for a
(cell x competitor) pair and folds them into the pair's CoverageSnapshot.

HONESTY / HUMAN-GATE CONSTRAINT (do not remove):
Persisted Assets from the collection pipeline are NOT yet human-accepted. Per the
design's human gate, a cell only becomes SATURATED after a human accepts evidence
into an Observation (issues #23/#24, out of scope here). So this recompute NEVER
sets SATURATED. The strongest state it will drive is SHORTLIST_READY, meaning
"evidence found, awaiting review". Informational metrics (counts, freshness,
breakdown, confidence) are always computed from Assets so the matrix shows real
numbers, but the STATE stays at SHORTLIST_READY (or unchanged) until human review
exists downstream.
"""
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.m3_collection import Asset
from app.models.m5_coverage import CoverageSnapshot
from app.services.m3_collection.coverage_state_service import (
    get_or_create_snapshot,
    transition_state,
)
from app.services.m3_collection.state_machine import CellState, can_transition

# Assets of this evidence_type never count toward coverage (per spec). They may
# still exist as rows, but are excluded from the independent-source count.
CLAIMED_EVIDENCE_TYPE = "claimed"
# Evidence_type treated as first-party "observed" evidence for the confidence heuristic.
OBSERVED_EVIDENCE_TYPE = "observed"


def confidence_score(independent_source_count: int, observed_fraction: float) -> float:
    """Pure coverage-confidence heuristic, returns a value in [0, 1].

    ENGINEERING HEURISTIC, NOT A THEORETICAL MODEL: we reward independent
    corroboration (more distinct sources, saturating at 3) and weight it by how
    much of the evidence is directly observed rather than secondary. Concretely:

        min(1.0, independent_source_count / 3.0) * clamp(observed_fraction, 0, 1)

    - 0 sources                 -> 0.0
    - 3+ sources, all observed  -> ~1.0
    - 3 sources, half observed  -> ~0.5 (reduced)

    Both factors live in [0, 1], so the product is always in [0, 1].
    """
    source_factor = min(1.0, max(0, independent_source_count) / 3.0)
    obs = min(1.0, max(0.0, observed_fraction))
    return source_factor * obs


def recompute_coverage(
    db: Session, cell_id: UUID, competitor_id: UUID
) -> CoverageSnapshot:
    """Recompute the snapshot for (cell, competitor) from its non-superseded Assets.

    Metrics (counts, freshness, breakdown, confidence) always reflect the current
    Assets. State is only ever advanced as far as SHORTLIST_READY, and only via a
    safe state-machine transition. SATURATED is never set here (human gate).
    """
    assets = (
        db.query(Asset)
        .filter(
            Asset.cell_id == cell_id,
            Asset.competitor_id == competitor_id,
            Asset.is_superseded == False,  # noqa: E712 (SQLAlchemy needs ==)
        )
        .all()
    )

    # evidence_type breakdown over all non-superseded assets (incl. 'claimed').
    evidence_type_breakdown: dict[str, int] = {}
    for a in assets:
        key = a.evidence_type
        evidence_type_breakdown[key] = evidence_type_breakdown.get(key, 0) + 1

    # 'claimed' evidence never counts toward coverage.
    counting_assets = [a for a in assets if a.evidence_type != CLAIMED_EVIDENCE_TYPE]

    # Distinct source_url among counting assets.
    independent_source_count = len({a.source_url for a in counting_assets})

    # Freshness: newest capture across all non-superseded assets (or None).
    captured_times = [a.captured_at for a in assets if a.captured_at is not None]
    latest_captured_at = max(captured_times) if captured_times else None

    # Observed fraction over counting assets (basis for the confidence heuristic).
    if counting_assets:
        observed = sum(
            1 for a in counting_assets if a.evidence_type == OBSERVED_EVIDENCE_TYPE
        )
        observed_fraction = observed / len(counting_assets)
    else:
        observed_fraction = 0.0

    coverage_confidence = confidence_score(independent_source_count, observed_fraction)

    snapshot = get_or_create_snapshot(db, cell_id, competitor_id)

    # Set informational metrics regardless of state.
    snapshot.independent_source_count = independent_source_count
    snapshot.latest_captured_at = latest_captured_at
    snapshot.coverage_confidence = coverage_confidence
    snapshot.evidence_type_breakdown = evidence_type_breakdown

    # STATE: at least one non-superseded, non-claimed asset means "evidence found,
    # awaiting review" -> aim for SHORTLIST_READY, but only via a safe transition.
    # We deliberately do NOT fight the state machine: if the current status does
    # not permit the move, we keep the metrics update and leave the status alone.
    # SATURATED is never a target here (human gate lives in issues #23/#24).
    has_passing_asset = len(counting_assets) >= 1
    if has_passing_asset:
        if can_transition(snapshot.status, CellState.SHORTLIST_READY):
            # transition_state validates + commits; metric fields set above ride along.
            snapshot = transition_state(
                db,
                cell_id,
                competitor_id,
                CellState.SHORTLIST_READY,
                note="recompute: evidence found, awaiting review",
            )
            # Re-apply metrics onto the (same) refreshed snapshot to be explicit.
            snapshot.independent_source_count = independent_source_count
            snapshot.latest_captured_at = latest_captured_at
            snapshot.coverage_confidence = coverage_confidence
            snapshot.evidence_type_breakdown = evidence_type_breakdown
        elif snapshot.status in (
            CellState.PARTIAL,
            CellState.SHORTLIST_READY,
            CellState.SATURATED,
        ):
            # Already at or beyond SHORTLIST_READY; leave the state as-is.
            pass
        else:
            # Transition not allowed from here (e.g. UNPROBED/QUEUED). Prefer not to
            # fight the state machine: keep the metric update and leave status.
            pass
    # 0 counting assets -> leave current state unchanged (never downgrade).

    db.commit()
    db.refresh(snapshot)
    return snapshot
