"""Human review service layer (#23).

This module is the backend gate between the AI-scored shortlist and the
evidence library.  No Asset becomes an accepted Observation until a human
reviewer explicitly calls accept_asset.

Public API
----------
get_shortlist  -- list non-superseded Assets awaiting review for a cell/competitor
accept_asset   -- promote an Asset to an Observation (human-accept)
reject_asset   -- soft-remove an Asset from the shortlist (is_superseded = True)
flag_asset     -- placeholder flag action (real queue is out of scope for #23)

Internal helper
---------------
_apply_observation_fields  -- apply reviewer-supplied fields to an Observation
                              row via setattr, silently ignoring unknown keys.
                              Extracted as a module-level function so it can be
                              unit-tested without a database.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.m3_collection import Asset
from app.models.m4_annotation import Observation
from app.services.m3_collection.coverage_recompute import recompute_coverage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helper (extracted for testability)
# ---------------------------------------------------------------------------

def _apply_observation_fields(obs: Observation, fields: dict) -> None:
    """Apply reviewer-supplied field values to an Observation instance.

    Only keys that correspond to actual Observation columns (checked via
    ``hasattr``) are applied.  Unknown keys are silently ignored so that the
    caller can forward the raw request dict without pre-filtering.

    Preserves None values: if the caller explicitly passes ``None`` for a
    known field, that None is written to the column (nullable columns accept
    it; non-nullable columns would raise at commit time, which is intentional).

    Parameters
    ----------
    obs:
        The Observation ORM instance to mutate in-place.
    fields:
        Arbitrary key-value mapping from the reviewer's request payload.
    """
    for key, value in fields.items():
        if hasattr(obs, key):
            setattr(obs, key, value)


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------

def get_shortlist(
    db: Session,
    cell_id: UUID,
    competitor_id: UUID,
    project_id: UUID | None = None,
) -> list[Asset]:
    """Return non-superseded Assets for (cell, competitor), ordered by ai_score desc.

    These are the items waiting for human review.  Superseded assets (already
    rejected or replaced by a newer version) are excluded so the reviewer only
    sees actionable candidates.

    ``project_id`` scopes the result so one project's reviewer can never see
    another project's evidence.  None means unscoped (internal callers only).
    """
    query = (
        select(Asset)
        .where(
            Asset.cell_id == cell_id,
            Asset.competitor_id == competitor_id,
            Asset.is_superseded == False,  # noqa: E712 (SQLAlchemy needs ==)
        )
        .order_by(Asset.ai_score.desc().nullslast())
    )
    if project_id is not None:
        query = query.where(Asset.project_id == project_id)
    return list(db.execute(query).scalars().all())


def _load_scoped_asset(
    db: Session,
    asset_id: UUID,
    project_id: UUID | None,
) -> Asset:
    """Fetch an Asset, refusing cross-project access.

    A wrong-project asset is reported as NOT_FOUND rather than FORBIDDEN so the
    caller cannot use the error to probe which ids exist in other projects.
    """
    asset: Asset | None = db.get(Asset, asset_id)
    if asset is None or (project_id is not None and asset.project_id != project_id):
        raise AppError("NOT_FOUND", f"Asset {asset_id} not found", 404)
    return asset


def accept_asset(
    db: Session,
    asset_id: UUID,
    observation_fields: dict,
    accepted_by: str = "reviewer",
    project_id: UUID | None = None,
) -> Observation:
    """Promote an Asset to a human-accepted Observation in the evidence library.

    Steps
    -----
    1. Fetch the Asset; raise AppError NOT_FOUND (404) if missing.
    2. Create an Observation row linked to the asset's (cell, competitor),
       setting ``accepted_by`` and ``accepted_at`` from parameters, and
       applying any known keys from ``observation_fields`` via
       ``_apply_observation_fields``.
    3. Commit and refresh the new Observation.
    4. Trigger ``recompute_coverage`` so coverage metrics stay fresh after
       the human gate is passed.  Accepted Observations feed saturation checks
       in future issues; for now the recompute updates confidence + counts.
    5. Return the committed Observation.

    Parameters
    ----------
    db:
        Active SQLAlchemy session.
    asset_id:
        PK of the Asset being accepted.
    observation_fields:
        Reviewer-supplied values for Observation columns (e.g. surface_confirmed,
        native_step, …).  Unknown keys are silently ignored.  ``accepted_by``
        and ``accepted_at`` are always set from the explicit parameters, even if
        the caller also passes them in ``observation_fields``.
    accepted_by:
        Identity of the reviewer performing the accept action.
    project_id:
        When given, the Asset must belong to this project or the call raises
        NOT_FOUND.
    """
    asset = _load_scoped_asset(db, asset_id, project_id)

    obs = Observation(
        project_id=asset.project_id,
        asset_id=asset.id,
        cell_id=asset.cell_id,
        competitor_id=asset.competitor_id,
        accepted_by=accepted_by,
        accepted_at=datetime.now(timezone.utc),
    )

    # Apply reviewer-supplied fields; accepted_by / accepted_at set above take
    # precedence — _apply_observation_fields will overwrite them if the caller
    # also includes them in observation_fields, so we set them *after* the loop.
    _apply_observation_fields(obs, observation_fields)

    # Re-assert the explicit values so callers cannot accidentally override them
    # via observation_fields (belt-and-suspenders guard).
    obs.accepted_by = accepted_by
    obs.accepted_at = datetime.now(timezone.utc)

    db.add(obs)
    db.commit()
    db.refresh(obs)

    # Trigger coverage recompute so the matrix reflects the freshly accepted
    # Observation.  This is a best-effort side-effect; the Observation is
    # already committed above, so a recompute failure does not roll it back.
    try:
        recompute_coverage(db, asset.cell_id, asset.competitor_id)
    except Exception:
        logger.exception(
            "recompute_coverage failed after accept_asset asset_id=%s; "
            "Observation is committed, coverage metrics may be stale",
            asset_id,
        )

    return obs


def reject_asset(
    db: Session,
    asset_id: UUID,
    reason: Optional[str] = None,
    project_id: UUID | None = None,
) -> Asset:
    """Soft-remove an Asset from the shortlist by marking it superseded.

    Sets ``is_superseded = True`` so the asset no longer appears in
    ``get_shortlist`` results.  The row is retained for audit purposes; no
    data is deleted.

    Parameters
    ----------
    db:
        Active SQLAlchemy session.
    asset_id:
        PK of the Asset to reject.
    reason:
        Optional human-readable rejection reason (logged at INFO level).
    project_id:
        When given, the Asset must belong to this project or the call raises
        NOT_FOUND.
    """
    asset = _load_scoped_asset(db, asset_id, project_id)

    if reason:
        logger.info("reject_asset asset_id=%s reason=%r", asset_id, reason)

    asset.is_superseded = True
    db.commit()
    db.refresh(asset)
    return asset


def flag_asset(
    db: Session,
    asset_id: UUID,
    note: Optional[str] = None,
    project_id: UUID | None = None,
) -> Asset:
    """Flag an Asset for follow-up (placeholder — real flag queue is out of scope).

    Behaves like reject_asset in that ``is_superseded`` is set to True so the
    asset drops off the shortlist.  The note is emitted as a WARNING so it is
    visible in logs without requiring a dedicated flag table.

    The real flag queue (a separate table with per-reviewer assignments, status
    tracking, and resolution workflow) is deferred to a future issue.  This
    function keeps the UI's "Flag" button wired end-to-end without blocking on
    that work.

    Parameters
    ----------
    db:
        Active SQLAlchemy session.
    asset_id:
        PK of the Asset to flag.
    note:
        Optional reviewer note explaining why the asset was flagged.
    project_id:
        When given, the Asset must belong to this project or the call raises
        NOT_FOUND.
    """
    asset = _load_scoped_asset(db, asset_id, project_id)

    logger.warning(
        "flag_asset asset_id=%s note=%r — flagged for follow-up (placeholder behaviour)",
        asset_id,
        note,
    )

    asset.is_superseded = True
    db.commit()
    db.refresh(asset)
    return asset
