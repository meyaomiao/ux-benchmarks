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


def test_generic_uses_competitor_and_translated_scenario():
    bundle = expand_terms_for_cell(
        jtbd="查看AI提取的条款与风险标记",
        journey_stage="日常审查",
        page_state="风险高亮态",
        lexicon_terms=["风险标记"],
        competitor_names=["ThoughtRiver"],
        official_phrase="Risk Highlight State Routine Review",
    )

    prefix = "ThoughtRiver Risk Highlight State Routine Review "
    assert bundle.generic
    assert all(query.startswith(prefix) for query in bundle.generic)
    assert not any(
        raw_label in query
        for query in bundle.generic
        for raw_label in ("风险高亮态", "日常审查", "查看AI提取的条款与风险标记")
    )


def test_generic_without_competitor_uses_translated_scenario():
    bundle = expand_terms_for_cell(
        jtbd="查看AI提取的条款与风险标记",
        journey_stage="日常审查",
        page_state="风险高亮态",
        lexicon_terms=[],
        competitor_names=[],
        official_phrase="Risk Highlight State Routine Review",
    )

    assert bundle.generic
    assert all(
        query.startswith("Risk Highlight State Routine Review ")
        for query in bundle.generic
    )


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


def test_official_buckets_anchor_to_competitor_domain():
    """help_docs / interactive_demo must `site:`-anchor to the competitor's OWN
    domain (so a rival's docs can't be returned) and use the English scenario
    phrase. Third-party buckets (community/generic) stay un-anchored."""
    bundle = expand_terms_for_cell(
        jtbd="compare versions",
        journey_stage="daily use",
        page_state="版本历史",  # Chinese scenario, as in a real CN project
        lexicon_terms=[],
        competitor_names=["Notion"],
        official_phrase="version history compare",  # pre-translated (build_query_bundle does this)
        competitor_domains={"Notion": ("notion.so/help", "notion.so")},
    )
    # Every official-bucket query is anchored to the competitor's own site AND
    # uses the English phrase (not the Chinese page_state).
    assert bundle.help_docs
    for q in bundle.help_docs:
        assert "site:notion.so" in q
        assert "version history compare" in q
        assert "版本历史" not in q
    # interactive_demo has some competitor-less fallbacks, but the competitor-named
    # ones are anchored.
    named_demo = [q for q in bundle.interactive_demo if "Notion" in q]
    assert named_demo
    for q in named_demo:
        assert "site:notion.so" in q
    # Community stays third-party: never anchored to the competitor's own domain.
    for q in bundle.community:
        assert "site:notion.so" not in q


def test_official_buckets_degrade_without_domains():
    """No stored domain → official buckets fall back to an un-anchored query
    (never emit a broken bare `site:`)."""
    bundle = expand_terms_for_cell(
        jtbd="compare versions",
        journey_stage="daily use",
        page_state="version history",
        lexicon_terms=[],
        competitor_names=["Notion"],
        official_phrase="version history",
        competitor_domains=None,
    )
    for q in bundle.help_docs + bundle.interactive_demo:
        assert "site:" not in q  # no domain known → no anchor at all


def test_no_bucket_uses_or_site_grouping():
    """Serper free accounts REJECT `(site:a OR site:b)` grouping with HTTP 400
    ("Query pattern not allowed for free accounts"), which silently killed every
    anchored/community query. No bucket may emit an OR-grouped site: pattern; a
    single `site:` per query is the only allowed anchored form."""
    bundle = expand_terms_for_cell(
        jtbd="compare versions",
        journey_stage="daily use",
        page_state="版本历史",
        lexicon_terms=[],
        competitor_names=["Notion"],
        official_phrase="version history",
        competitor_domains={"Notion": ("notion.so/help", "notion.so")},
    )
    for q in bundle.all():
        assert " OR " not in q, f"OR grouping is Serper-free-tier-forbidden: {q!r}"
        assert "(site:" not in q, f"grouped site: is forbidden: {q!r}"
        # At most one site: operator per query.
        assert q.count("site:") <= 1, f"multiple site: in one query: {q!r}"


def test_help_docs_prefers_help_center_domain_single_site():
    """help_docs anchors to a SINGLE site:, preferring help_center_domain."""
    bundle = expand_terms_for_cell(
        jtbd="x", journey_stage="y", page_state="z",
        lexicon_terms=[], competitor_names=["Notion"],
        official_phrase="version history",
        competitor_domains={"Notion": ("notion.so/help", "notion.so")},
    )
    assert bundle.help_docs
    for q in bundle.help_docs:
        assert "site:notion.so/help" in q
        assert " OR " not in q
