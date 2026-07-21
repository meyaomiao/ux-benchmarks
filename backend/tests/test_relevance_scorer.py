"""Offline, deterministic tests for the AI relevance scorer (spec §6).

Mock mode is forced (settings.use_collection_mock=True) so nothing touches the
network and every assertion is reproducible. The key behaviour under test:
an artifact that SHOWS the target state passes; one that merely MENTIONS the
feature does not.
"""
import math
from uuid import uuid4

import pytest

from app.services.m3_collection.contracts import (
    Candidate,
    EvidenceType,
    RELEVANCE_FLOOR,
    RubricBreakdown,
    SourceType,
)
from app.services.m3_collection.scoring.relevance_scorer import (
    W_EVIDENCE_DIRECTNESS,
    W_FIDELITY,
    W_PRODUCT_MATCH,
    W_STATE_MATCH,
    W_VERSION_RECENCY,
    RelevanceScorer,
    _combine,
    score_from_text,
)


@pytest.fixture(autouse=True)
def _force_mock(monkeypatch):
    """Every test in this module runs the deterministic mock brain."""
    from app.services.m3_collection.scoring import relevance_scorer

    monkeypatch.setattr(relevance_scorer.settings, "use_collection_mock", True)
    monkeypatch.setattr(relevance_scorer.settings, "anthropic_api_key", "")


def _candidate(
    *,
    title="",
    snippet="",
    text_content="",
    image_path=None,
    evidence_hint=EvidenceType.OBSERVED,
):
    return Candidate(
        cell_id=uuid4(),
        competitor_id=uuid4(),
        source_url="https://example.com/help/checkout",
        source_type=SourceType.HELP_DOCS,
        title=title,
        snippet=snippet,
        text_content=text_content,
        image_path=image_path,
        evidence_type_hint=evidence_hint,
    )


INTENT = "the guest checkout payment confirmation screen"
INCLUSION = "guest checkout payment confirmation order summary"


def test_strong_match_passes():
    """An artifact that clearly shows the target state scores high, passes."""
    cand = _candidate(
        title="Guest checkout payment confirmation",
        text_content=(
            "This screenshot shows the guest checkout payment confirmation "
            "screen with the order summary. Latest 2026 redesign."
        ),
        image_path="/tmp/shot.png",
        evidence_hint=EvidenceType.OBSERVED,
    )
    score = RelevanceScorer().score(
        cand,
        intent_definition=INTENT,
        inclusion_criteria=INCLUSION,
    )
    assert score.scored_by == "mock"
    assert score.passed is True
    assert score.score >= RELEVANCE_FLOOR


def test_vague_mention_fails():
    """THE key test: merely MENTIONING the feature is below floor."""
    cand = _candidate(
        title="Our platform",
        text_content=(
            "We support many features. Sign up to explore what our product "
            "offers across the board."
        ),
        image_path=None,
        evidence_hint=EvidenceType.INFERRED,
    )
    score = RelevanceScorer().score(
        cand,
        intent_definition=INTENT,
        inclusion_criteria=INCLUSION,
    )
    assert score.passed is False
    assert score.score < RELEVANCE_FLOOR


def test_exclusion_terms_lower_score():
    """Exclusion terms appearing in the text drag the score down."""
    base_text = (
        "The guest checkout payment confirmation order summary screen, "
        "shown in the latest 2026 build."
    )
    clean = _candidate(
        text_content=base_text,
        image_path="/tmp/a.png",
        evidence_hint=EvidenceType.OBSERVED,
    )
    dirty = _candidate(
        text_content=base_text + " Also includes an error modal and a spinner.",
        image_path="/tmp/a.png",
        evidence_hint=EvidenceType.OBSERVED,
    )
    scorer = RelevanceScorer()
    clean_score = scorer.score(
        clean,
        intent_definition=INTENT,
        inclusion_criteria=INCLUSION,
        exclusion_criteria="error modal spinner",
    )
    dirty_score = scorer.score(
        dirty,
        intent_definition=INTENT,
        inclusion_criteria=INCLUSION,
        exclusion_criteria="error modal spinner",
    )
    assert dirty_score.score < clean_score.score


def test_evidence_directness_ordering():
    """observed > claimed > inferred, all else equal."""
    text = (
        "The guest checkout payment confirmation order summary screen, "
        "latest 2026."
    )
    kwargs = dict(
        intent=INTENT,
        inclusion=INCLUSION,
        has_image=True,
    )
    observed, _ = score_from_text(text, evidence_hint=EvidenceType.OBSERVED, **kwargs)
    claimed, _ = score_from_text(text, evidence_hint=EvidenceType.CLAIMED, **kwargs)
    inferred, _ = score_from_text(text, evidence_hint=EvidenceType.INFERRED, **kwargs)

    assert observed.evidence_directness > claimed.evidence_directness
    assert claimed.evidence_directness > inferred.evidence_directness
    assert _combine(observed) > _combine(claimed) > _combine(inferred)


def test_combine_weights_sum_to_one():
    total = (
        W_STATE_MATCH
        + W_PRODUCT_MATCH
        + W_VERSION_RECENCY
        + W_EVIDENCE_DIRECTNESS
        + W_FIDELITY
    )
    assert math.isclose(total, 1.0, rel_tol=1e-9, abs_tol=1e-9)


def test_combine_all_ones_is_one():
    perfect = RubricBreakdown(
        state_match=1.0,
        product_match=1.0,
        version_recency=1.0,
        evidence_directness=1.0,
        fidelity=1.0,
    )
    assert math.isclose(_combine(perfect), 1.0, rel_tol=1e-9, abs_tol=1e-9)
