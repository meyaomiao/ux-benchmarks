"""Text-only ceiling: a screenshot-less candidate can pass, but its score is
capped by TEXT_ONLY_CEILING so the screenshot > text-description hierarchy stays
honest. Deterministic (mock mode), no network.
"""
import pytest

from app.core.config import settings
from app.services.m3_collection.contracts import Candidate, EvidenceType, SourceType
from app.services.m3_collection.scoring.relevance_scorer import (
    RelevanceScorer,
    TEXT_ONLY_CEILING,
)
from uuid import uuid4


@pytest.fixture(autouse=True)
def _force_mock(monkeypatch):
    monkeypatch.setattr(settings, "use_collection_mock", True)


def _text_candidate(text: str, hint=EvidenceType.OBSERVED) -> Candidate:
    return Candidate(
        cell_id=uuid4(),
        competitor_id=uuid4(),
        source_url="https://help.example.com/doc",
        source_type=SourceType.HELP_DOCS,
        title="",
        text_content=text,
        image_path=None,  # text-only
        evidence_type_hint=hint,
    )


def test_text_only_score_capped_at_ceiling():
    # Engineer maximum mock overlap: intent+inclusion tokens all present,
    # a recency token, long enough text, observed hint. Uncapped this would
    # combine to ~0.96; the ceiling must clamp it.
    intent = "role permission matrix editor"
    inclusion = "toggle assign member invite"
    text = (
        "role permission matrix editor toggle assign member invite latest 2026 "
    ) * 8  # ensure length >> 300 for full text fidelity
    score = RelevanceScorer().score(
        _text_candidate(text),
        intent_definition=intent,
        inclusion_criteria=inclusion,
    )
    assert score.score <= TEXT_ONLY_CEILING + 1e-9
    # And such a strong procedural match should still clear the floor.
    assert score.passed is True


def test_vague_text_still_fails_under_ceiling():
    score = RelevanceScorer().score(
        _text_candidate("we offer great flexible collaboration for teams"),
        intent_definition="role permission matrix editor",
        inclusion_criteria="toggle assign member invite",
    )
    assert score.passed is False
