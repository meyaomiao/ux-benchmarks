"""The GPT relay must not depend on an Anthropic API key."""
from uuid import uuid4

from app.core.config import settings
from app.services.m3_collection.contracts import (
    Candidate,
    EvidenceType,
    RubricBreakdown,
    SourceType,
)
from app.services.m3_collection.scoring.relevance_scorer import RelevanceScorer


def test_gpt_route_does_not_require_anthropic_key(monkeypatch):
    monkeypatch.setattr(settings, "use_collection_mock", False)
    monkeypatch.setattr(settings, "gpt_api_key", "test-gpt-key")
    monkeypatch.setattr(settings, "gpt_scorer_model", "gpt-test")
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    def fake_gpt_score(_self, **_kwargs):
        return RubricBreakdown(
            state_match=0.9,
            product_match=0.8,
            version_recency=0.7,
            evidence_directness=0.6,
            fidelity=0.5,
        ), "GPT relay response"

    monkeypatch.setattr(RelevanceScorer, "_score_with_gpt", fake_gpt_score)
    candidate = Candidate(
        cell_id=uuid4(),
        competitor_id=uuid4(),
        source_url="https://example.com/help",
        source_type=SourceType.HELP_DOCS,
        title="中文素材",
        text_content="这里是中文素材正文。",
        evidence_type_hint=EvidenceType.CLAIMED,
    )

    score = RelevanceScorer().score(candidate, intent_definition="中文目标场景")

    assert score.scored_by == "gpt:gpt-test"
    assert score.rubric.state_match == 0.9
