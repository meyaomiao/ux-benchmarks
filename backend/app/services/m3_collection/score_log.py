"""Append-only diagnostics writer for probe scoring (every candidate, not just passers).

``persist_passing`` only stores candidates that cleared ``RELEVANCE_FLOOR``, so a
probe that scored 31 candidates and passed 3 left no trace of the other 28. That
made it impossible to tell a near-miss (0.54) from a total mismatch (0.12), i.e.
impossible to judge whether the floor or the queries need tuning.

This module records the full scored set. It is diagnostics only: nothing in the
coverage math reads it, and a failure here must never fail a probe.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.m1_grid import GridCell
from app.models.m3_probe_log import ProbeScoreLog
from app.services.m3_collection.contracts import Candidate, Score

logger = logging.getLogger(__name__)

_REASONING_MAX = 2000


def log_scored_candidates(
    db: Session,
    cell_id: UUID,
    competitor_id: UUID,
    scored: list[tuple[Candidate, Score]],
    *,
    probe_cycle: int | None = None,
) -> int:
    """Append one ProbeScoreLog row per scored candidate. Returns rows written.

    Best-effort by design: any failure is logged and swallowed, because losing a
    diagnostics row must never turn a successful probe into a failed one.
    """
    if not scored:
        return 0

    try:
        project_id = db.execute(
            select(GridCell.project_id).where(GridCell.id == cell_id)
        ).scalar_one()

        now = datetime.now(timezone.utc)
        for candidate, score in scored:
            db.add(
                ProbeScoreLog(
                    project_id=project_id,
                    cell_id=cell_id,
                    competitor_id=competitor_id,
                    probe_cycle=probe_cycle,
                    source_url=candidate.source_url,
                    source_type=getattr(candidate.source_type, "value", None),
                    has_image=candidate.image_path is not None,
                    score=score.score,
                    passed=score.passed,
                    evidence_type=getattr(score.evidence_type, "value", None),
                    scored_by=score.scored_by,
                    score_breakdown={
                        "state_match": score.rubric.state_match,
                        "product_match": score.rubric.product_match,
                        "version_recency": score.rubric.version_recency,
                        "evidence_directness": score.rubric.evidence_directness,
                        "fidelity": score.rubric.fidelity,
                    },
                    reasoning=(score.reasoning or "")[:_REASONING_MAX] or None,
                    scored_at=now,
                )
            )
        db.commit()
        return len(scored)
    except Exception as exc:  # noqa: BLE001 — diagnostics must not break a probe
        logger.warning(
            "probe score logging failed for %s/%s: %s", cell_id, competitor_id, exc
        )
        db.rollback()
        return 0
