"""Project-scoped GPT rescoring for Assets created with historical mock scores."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.m2_mapping import MappingCard
from app.models.m3_collection import Asset
from app.services.m3_collection.contracts import Candidate, EvidenceType, Score, SourceType
from app.services.m3_collection.coverage_recompute import recompute_project_coverage
from app.services.m3_collection.scoring.relevance_scorer import RelevanceScorer

PAGE_SIZE = 20


@dataclass(frozen=True)
class BackfillResult:
    project_id: UUID
    rescored_assets: int
    coverage_pairs: int


def _candidate_from_asset(asset: Asset) -> Candidate:
    """Rebuild the scorer input from the persisted evidence available on an Asset."""
    try:
        evidence_hint = EvidenceType(asset.evidence_type)
    except ValueError:
        evidence_hint = EvidenceType.INFERRED

    image_path = asset.file_path if asset.file_path and Path(asset.file_path).is_file() else None
    text = "\n".join(
        value
        for value in (
            asset.capture_context,
            asset.native_step,
            asset.mapped_journey_stage,
            asset.product_version,
        )
        if value
    )
    return Candidate(
        candidate_id=asset.id,
        cell_id=asset.cell_id,
        competitor_id=asset.competitor_id,
        source_url=asset.source_url,
        source_type=SourceType.INTERACTIVE_DEMO if image_path else SourceType.GENERIC,
        title=asset.source_url,
        text_content=text,
        image_path=image_path,
        product_version=asset.product_version,
        captured_at=asset.captured_at,
        rights_status=asset.rights_status,
        evidence_type_hint=evidence_hint,
    )


def _breakdown(score: Score) -> dict[str, float | str]:
    return {
        "state_match": score.rubric.state_match,
        "product_match": score.rubric.product_match,
        "version_recency": score.rubric.version_recency,
        "evidence_directness": score.rubric.evidence_directness,
        "fidelity": score.rubric.fidelity,
        "reasoning": score.reasoning,
        "scored_by": score.scored_by,
    }


def rescore_project_assets(
    db: Session,
    project_id: UUID,
    *,
    scorer: RelevanceScorer | None = None,
) -> BackfillResult:
    """Rescore every Asset in one project and then refresh its coverage snapshots.

    The explicit project scope is the safety boundary for this maintenance task.
    A scorer instance is created once and reused for all pages. GPT fallbacks are
    rejected so this job can never replace a historical mock result with another
    mock result while claiming a successful backfill.
    """
    if settings.use_collection_mock:
        raise RuntimeError("USE_COLLECTION_MOCK must be false for GPT rescoring")

    scorer = scorer or RelevanceScorer()
    cards = {
        card.cell_id: card
        for card in db.execute(
            select(MappingCard).where(MappingCard.project_id == project_id)
        ).scalars()
    }

    rescored_assets = 0
    offset = 0
    try:
        while True:
            assets = list(
                db.execute(
                    select(Asset)
                    .where(Asset.project_id == project_id)
                    .order_by(Asset.created_at, Asset.id)
                    .limit(PAGE_SIZE)
                    .offset(offset)
                ).scalars()
            )
            if not assets:
                break

            for asset in assets:
                card = cards.get(asset.cell_id)
                score = scorer.score(
                    _candidate_from_asset(asset),
                    intent_definition=card.intent_definition if card else "",
                    inclusion_criteria=(card.inclusion_criteria if card else "") or "",
                    exclusion_criteria=(card.exclusion_criteria if card else "") or "",
                )
                if not score.scored_by.startswith("gpt:"):
                    raise RuntimeError(
                        f"GPT scoring failed for asset {asset.id}; got {score.scored_by!r}"
                    )

                asset.ai_score = score.score
                asset.ai_score_breakdown = _breakdown(score)
                rescored_assets += 1

            offset += len(assets)

        db.commit()
    except Exception:
        db.rollback()
        raise

    coverage_pairs = recompute_project_coverage(db, project_id)
    return BackfillResult(
        project_id=project_id,
        rescored_assets=rescored_assets,
        coverage_pairs=coverage_pairs,
    )
