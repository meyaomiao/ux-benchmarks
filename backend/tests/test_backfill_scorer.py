from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.core.config import settings
from app.services.m3_collection.backfill_scorer import rescore_project_assets
from app.services.m3_collection.contracts import EvidenceType, RubricBreakdown, Score


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self.rows


class _Session:
    def __init__(self, pages):
        self._pages = iter(pages)
        self.commits = 0
        self.rollbacks = 0

    def execute(self, _statement):
        return _Result(next(self._pages))

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_rescore_project_assets_writes_gpt_score_and_recomputes_coverage(monkeypatch):
    project_id = uuid4()
    asset = SimpleNamespace(
        id=uuid4(),
        cell_id=uuid4(),
        competitor_id=uuid4(),
        source_url="https://example.com/help/setup",
        capture_context="Configure the billing setup workflow",
        native_step=None,
        mapped_journey_stage=None,
        product_version="2026",
        file_path=None,
        captured_at=object(),
        rights_status="third_party_official",
        evidence_type="observed",
        ai_score=0.1,
        ai_score_breakdown={"scored_by": "mock"},
    )
    session = _Session([[], [asset], []])
    gpt_score = Score(
        candidate_id=asset.id,
        score=0.91,
        passed=True,
        evidence_type=EvidenceType.OBSERVED,
        rubric=RubricBreakdown(
            state_match=0.9,
            product_match=0.8,
            version_recency=0.7,
            evidence_directness=1.0,
            fidelity=0.8,
        ),
        reasoning="Relevant UI evidence.",
        scored_by="gpt:gpt-test",
    )
    scorer = Mock()
    scorer.score.return_value = gpt_score
    recompute = Mock(return_value=1)

    monkeypatch.setattr(settings, "use_collection_mock", False)
    monkeypatch.setattr(
        "app.services.m3_collection.backfill_scorer.recompute_project_coverage",
        recompute,
    )

    result = rescore_project_assets(session, project_id, scorer=scorer)

    assert result.rescored_assets == 1
    assert result.coverage_pairs == 1
    assert asset.ai_score == 0.91
    assert asset.ai_score_breakdown["scored_by"] == "gpt:gpt-test"
    assert asset.ai_score_breakdown["state_match"] == 0.9
    assert session.commits == 1
    recompute.assert_called_once_with(session, project_id)
