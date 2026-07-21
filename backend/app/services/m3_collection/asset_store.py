"""Asset write-once store (#22) + dedup (#20).

Persists a scored ``Candidate`` into the ``Asset`` table under two invariants:

  write-once  an Asset row's content is never UPDATEd once written. A future
              "new version" would be a *new* row with ``supersedes=<old id>``
              (out of scope here — dedup simply returns the existing row).
  rights-governed  ``media_disposition`` is decided deterministically from
              ``rights_status`` via ``rights_policy.disposition_for`` at write
              time, never guessed after the fact.

Dedup (#20) is keyed on a stable content checksum, scoped per (cell, competitor):
the same source_url + same content re-collected later resolves to the existing
row instead of inserting a duplicate.

The scorer's verdict wins: ``evidence_type`` is stored from ``score.evidence_type``
(the scorer's judgement), not the adapter's ``evidence_type_hint``.
"""
from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.m3_collection import Asset
from app.services.m3_collection.contracts import Candidate, Score
from app.services.m3_collection.rights_policy import disposition_for


def compute_checksum(candidate: Candidate) -> str:
    """Stable sha256 hex identifying a candidate's content for dedup.

    Pure (no DB, no network). Keyed on the candidate's identity + payload:
    ``(competitor_id, cell_id, source_url, text_content or image_path)``. Two
    candidates with the same source_url and same content produce the same
    checksum; changing any component changes the checksum.

    ``text_content`` is the primary content signal; when a candidate carries no
    text (image-only capture) ``image_path`` stands in. An empty string is used
    when neither is present so the checksum stays stable and reproducible.
    """
    content = candidate.text_content or candidate.image_path or ""
    parts = [
        str(candidate.competitor_id),
        str(candidate.cell_id),
        candidate.source_url,
        content,
    ]
    # NUL separator: not a valid character in URLs/paths, so parts can't collide
    # by concatenation (e.g. "a" + "bc" vs "ab" + "c").
    joined = "\x00".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def find_by_checksum(
    db: Session,
    cell_id: UUID,
    competitor_id: UUID,
    checksum: str,
) -> Asset | None:
    """Return the existing Asset matching this content checksum, or None.

    Dedup is scoped per (cell, competitor, content): the same content collected
    for a different cell or competitor is a distinct Asset.
    """
    query = select(Asset).where(
        Asset.cell_id == cell_id,
        Asset.competitor_id == competitor_id,
        Asset.checksum == checksum,
    )
    return db.execute(query).scalars().first()


def persist_candidate(
    db: Session,
    candidate: Candidate,
    score: Score,
) -> tuple[Asset, bool]:
    """Persist a (Candidate, Score) as a write-once Asset. Returns (asset, created).

    Dedup first: if an Asset with the same content checksum already exists for
    this (cell, competitor), return it untouched with ``created=False`` (no
    duplicate row, no content mutation). Otherwise insert a new row mapping the
    candidate's capture fields + the scorer's verdict, with the media disposition
    derived deterministically from ``rights_status``.
    """
    checksum = compute_checksum(candidate)

    existing = find_by_checksum(
        db, candidate.cell_id, candidate.competitor_id, checksum
    )
    if existing is not None:
        # DEDUP: write-once — never update existing content, just return it.
        return existing, False

    asset = Asset(
        cell_id=candidate.cell_id,
        competitor_id=candidate.competitor_id,
        source_url=candidate.source_url,
        captured_at=candidate.captured_at,
        product_version=candidate.product_version,
        rights_status=candidate.rights_status,
        media_disposition=disposition_for(candidate.rights_status).value,
        # Scorer's verdict wins over the adapter's evidence_type_hint.
        evidence_type=score.evidence_type.value,
        # These four are optional Asset columns not (yet) on the Candidate
        # contract; getattr keeps the map robust whether or not an adapter
        # supplies them (all default to None, matching the nullable columns).
        capture_context=getattr(candidate, "capture_context", None),
        native_step=getattr(candidate, "native_step", None),
        native_step_index=getattr(candidate, "native_step_index", None),
        mapped_journey_stage=getattr(candidate, "mapped_journey_stage", None),
        file_path=candidate.image_path,
        checksum=checksum,
        ai_score=score.score,
        ai_score_breakdown={
            "state_match": score.rubric.state_match,
            "product_match": score.rubric.product_match,
            "version_recency": score.rubric.version_recency,
            "evidence_directness": score.rubric.evidence_directness,
            "fidelity": score.rubric.fidelity,
            "reasoning": score.reasoning,
            "scored_by": score.scored_by,
        },
        is_superseded=False,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset, True


def persist_passing(
    db: Session,
    cell_id: UUID,
    competitor_id: UUID,
    scored_pairs: list[tuple[Candidate, Score]],
) -> list[Asset]:
    """Persist only the pairs whose ``score.passed`` is True (the shortlist).

    Returns the resulting Assets (created or deduped-existing), preserving input
    order. ``cell_id``/``competitor_id`` are the pipeline's context for this
    batch; per-candidate values on each Candidate are used when writing rows.
    """
    assets: list[Asset] = []
    for candidate, score in scored_pairs:
        if not score.passed:
            continue
        asset, _created = persist_candidate(db, candidate, score)
        assets.append(asset)
    return assets


def list_assets_for_cell(
    db: Session,
    cell_id: UUID,
    competitor_id: UUID,
) -> list[Asset]:
    """List a (cell, competitor)'s Assets ordered by ai_score desc, nulls last."""
    query = (
        select(Asset)
        .where(
            Asset.cell_id == cell_id,
            Asset.competitor_id == competitor_id,
        )
        .order_by(Asset.ai_score.desc().nullslast())
    )
    return list(db.execute(query).scalars().all())
