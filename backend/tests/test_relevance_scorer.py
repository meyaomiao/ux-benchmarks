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
    source_type=SourceType.HELP_DOCS,
):
    return Candidate(
        cell_id=uuid4(),
        competitor_id=uuid4(),
        source_url="https://example.com/help/checkout",
        source_type=source_type,
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


def test_product_match_gate_rejects_off_competitor_evidence():
    """A doc that shows the right FEATURE but for the WRONG product is hard-failed
    when a target product_name is supplied — even though its overall score clears
    the floor. This is the competitor-scoping guarantee: a Notion cell must not
    hold Adobe evidence. (The mock scorer sets product_match=0.4 when the text
    reads like a competitor/comparison piece, which is below PRODUCT_MATCH_GATE.)
    """
    cand = _candidate(
        title="Guest checkout payment confirmation",
        text_content=(
            "This comparison shows the guest checkout payment confirmation "
            "screen with the order summary. Latest 2026 redesign."
        ),
        evidence_hint=EvidenceType.OBSERVED,
    )

    # Without a product name, the gate is inert and the strong feature match passes.
    no_name = RelevanceScorer().score(
        cand, intent_definition=INTENT, inclusion_criteria=INCLUSION,
    )
    assert no_name.rubric.product_match < 0.5  # mock flagged it competitor-ish
    assert no_name.score >= RELEVANCE_FLOOR
    assert no_name.passed is True

    # With a product name, the same low product_match hard-fails the candidate,
    # while the numeric score (and every rubric dim) is preserved for auditing.
    gated = RelevanceScorer().score(
        cand, intent_definition=INTENT, inclusion_criteria=INCLUSION,
        product_name="Notion",
    )
    assert gated.score == no_name.score  # score unchanged — only the verdict flips
    assert gated.passed is False
    assert "off-product" in gated.reasoning


def test_product_match_gate_keeps_on_product_evidence():
    """The gate must NOT punish legitimate target-product evidence: a strong,
    non-competitor doc (mock product_match=1.0) still passes with a product_name.
    """
    cand = _candidate(
        title="Guest checkout payment confirmation",
        text_content=(
            "This screenshot shows the guest checkout payment confirmation "
            "screen with the order summary. Latest 2026 redesign."
        ),
        image_path="/tmp/shot.png",
        evidence_hint=EvidenceType.OBSERVED,
    )
    scored = RelevanceScorer().score(
        cand, intent_definition=INTENT, inclusion_criteria=INCLUSION,
        product_name="Notion",
    )
    assert scored.rubric.product_match >= 0.5
    assert scored.passed is True


def test_product_match_zero_hardfails_every_source(monkeypatch):
    """product_match ≈ 0 (model certain it's a DIFFERENT product, never mentions
    the target) hard-fails EVERY source type — including community/generic, which
    are otherwise exempt from the 0.5 gate. Closes the generic-bucket hole where an
    off-product doc (a JetBrains page in a Notion cell) passed on overall alone."""
    from app.services.m3_collection.scoring import relevance_scorer

    # Strong on every dimension EXCEPT product_match=0.0 → overall clears the floor,
    # so only the zero-gate can reject it.
    strong_zero = RubricBreakdown(
        state_match=1.0, product_match=0.0, version_recency=1.0,
        evidence_directness=1.0, fidelity=1.0,
    )
    monkeypatch.setattr(
        relevance_scorer, "score_from_text",
        lambda **kw: (strong_zero, "[mock] forced product=0"),
    )

    for st in (SourceType.COMMUNITY, SourceType.GENERIC, SourceType.HELP_DOCS):
        cand = _candidate(text_content="something", source_type=st)
        scored = RelevanceScorer().score(
            cand, intent_definition=INTENT, product_name="Notion",
        )
        assert scored.score >= RELEVANCE_FLOOR   # would pass on overall score alone
        assert scored.passed is False            # ...but the zero-gate rejects it
        assert "off-product" in scored.reasoning


def test_product_match_gate_spares_community_sources():
    """Third-party sources (community/generic) are NOT hard-failed by the 0.5 gate.

    A community post that reads like a comparison drops mock product_match to 0.4
    (< PRODUCT_MATCH_GATE), which WOULD hard-fail an official source — but a Reddit
    "Notion vs Coda" thread is legitimate Notion evidence, so community sources are
    judged on overall score alone.
    """
    text = (
        "This comparison shows the guest checkout payment confirmation "
        "screen with the order summary. Latest 2026 redesign."
    )

    official = _candidate(
        title="Guest checkout payment confirmation",
        text_content=text,
        evidence_hint=EvidenceType.OBSERVED,
        source_type=SourceType.HELP_DOCS,
    )
    community = _candidate(
        title="Guest checkout payment confirmation",
        text_content=text,
        evidence_hint=EvidenceType.OBSERVED,
        source_type=SourceType.COMMUNITY,
    )

    off = RelevanceScorer().score(
        official, intent_definition=INTENT, inclusion_criteria=INCLUSION,
        product_name="Notion",
    )
    comm = RelevanceScorer().score(
        community, intent_definition=INTENT, inclusion_criteria=INCLUSION,
        product_name="Notion",
    )

    # Identical low product_match, identical overall score...
    assert off.rubric.product_match < 0.5
    assert comm.rubric.product_match < 0.5
    assert off.score == comm.score
    # ...but only the OFFICIAL source is gated out; community survives on score.
    assert off.passed is False
    assert comm.passed is True
    assert "off-product" not in comm.reasoning
