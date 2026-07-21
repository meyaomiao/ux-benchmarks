"""Pure unit tests for M3 query expansion (no DB)."""
from app.schemas.m3 import QueryBundle
from app.services.m3_collection.query_expansion import (
    MAX_PER_BUCKET,
    expand_terms_for_cell,
)


def _sample_bundle() -> QueryBundle:
    return expand_terms_for_cell(
        jtbd="find a plan that fits my team",
        journey_stage="evaluation",
        page_state="pricing page",
        lexicon_terms=["subscription tiers", "billing"],
        competitor_names=["Acme", "Acme Corp", "AcmeApp"],
    )


def test_buckets_non_empty():
    bundle = _sample_bundle()
    assert bundle.help_docs
    assert bundle.interactive_demo
    assert bundle.video
    assert bundle.community
    assert bundle.generic


def test_lexicon_terms_appear():
    bundle = _sample_bundle()
    joined = " || ".join(bundle.all())
    assert "subscription tiers" in joined


def test_competitor_aliases_appear():
    bundle = _sample_bundle()
    joined = " || ".join(bundle.all())
    # A non-canonical alias should surface in the expansion.
    assert "AcmeApp" in joined


def test_each_bucket_respects_cap():
    # Feed oversized inputs so every bucket would overflow without the cap.
    bundle = expand_terms_for_cell(
        jtbd="do the job",
        journey_stage="onboarding",
        page_state="signup",
        lexicon_terms=[f"term{i}" for i in range(30)],
        competitor_names=[f"Comp{i}" for i in range(30)],
    )
    for bucket in (
        bundle.help_docs,
        bundle.interactive_demo,
        bundle.video,
        bundle.community,
        bundle.generic,
    ):
        assert len(bucket) <= MAX_PER_BUCKET


def test_all_dedups():
    bundle = QueryBundle(
        help_docs=["a", "b"],
        interactive_demo=["b", "c"],
        video=["c"],
        community=["a"],
        generic=["d", "d"],
    )
    result = bundle.all()
    assert result == ["a", "b", "c", "d"]
    assert len(result) == len(set(result))
