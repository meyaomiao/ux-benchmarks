"""
Query expansion for M3 collection.

This turns a single grid cell (plus the domain lexicon and competitor aliases)
into a bucketed multi-query bundle that downstream collectors can dispatch to
different search surfaces.

NOTE (theory grounding): this is a plain search-engineering / IR technique --
synonym expansion and site-scoping. It is NOT anchored to any information-seeking
theory; that mapping was cut in review as over-citing. Keep the comments here
about strings and search operators, nothing more.
"""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.m0_registry import CompetitorEntity, DomainLexicon
from app.models.m1_grid import GridCell
from app.schemas.m3 import QueryBundle

# Intent modifiers appended to base queries so we surface task-oriented pages
# (guides, setup docs) rather than only marketing pages.
INTENT_TERMS = ["how to", "setup", "configure", "demo", "walkthrough", "tutorial"]

# Version/recency modifiers so we can bias toward current UI over stale results.
VERSION_TERMS = ["2025", "2026", "latest", "new UI"]

# Per-bucket query cap. Keeps bundles small and deterministic so a single cell
# never explodes into hundreds of near-duplicate searches.
MAX_PER_BUCKET = 8


def _intent_terms() -> list[str]:
    """Return the intent modifier terms (copy, so callers can't mutate the const)."""
    return list(INTENT_TERMS)


def _version_terms() -> list[str]:
    """Return the version/recency modifier terms (copy of the const)."""
    return list(VERSION_TERMS)


def _dedup(items: list[str]) -> list[str]:
    """Deduplicate while preserving first-seen order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _cap(items: list[str]) -> list[str]:
    """Dedup then cap a bucket at MAX_PER_BUCKET queries."""
    return _dedup(items)[:MAX_PER_BUCKET]


def expand_terms_for_cell(
    jtbd: str,
    journey_stage: str,
    page_state: str,
    lexicon_terms: list[str],
    competitor_names: list[str],
) -> QueryBundle:
    """Build a bucketed QueryBundle for one grid cell. Pure -- no DB access.

    The base phrase combines the cell's page_state and journey_stage keywords.
    Lexicon terms (synonyms / UI vocabulary) and competitor names (canonical +
    aliases) widen the surface, and intent/version modifiers steer toward
    task-oriented and current results. Each bucket is deduplicated and capped
    at MAX_PER_BUCKET for determinism.
    """
    # Base keywords: page_state + journey_stage form the semantic core; jtbd
    # gives a fuller natural-language phrasing.
    base = _dedup([page_state, journey_stage, jtbd])
    # A single combined phrase used as a query seed across buckets.
    base_phrase = " ".join(t for t in (page_state, journey_stage) if t).strip()

    lexicon = _dedup(lexicon_terms)
    competitors = _dedup(competitor_names)
    intents = _intent_terms()
    versions = _version_terms()

    # help_docs: competitor-scoped, doc-seeking queries. Lead with the product
    # NAME, then the scenario phrase, then EXPLICIT documentation keywords
    # (not vague "help"/"docs" which matched marketing pages). These words steer
    # Google (Serper) toward real help-center / user-guide pages. Junk domains
    # (youtube, press releases, social) are filtered downstream in search_service.
    # Competitor-less queries are useless (won't match a specific product), so
    # only emit them when we have no competitor at all.
    _DOC_TERMS = ["documentation", "user guide", "help center", "support article"]
    help_docs: list[str] = []
    if competitors:
        for name in competitors:
            for doc in _DOC_TERMS:
                help_docs.append(f"{name} {base_phrase} {doc}")
            help_docs.append(f"{name} {base_phrase} how to")
    else:
        for doc in _DOC_TERMS:
            help_docs.append(f"{base_phrase} {doc}")

    # interactive_demo: demo/tour phrasing, optionally prefixed by competitor.
    interactive_demo: list[str] = []
    for demo_kind in ("interactive demo", "product tour"):
        interactive_demo.append(f"{base_phrase} {demo_kind}")
        for name in competitors:
            interactive_demo.append(f"{name} {base_phrase} {demo_kind}")

    # video: video/walkthrough phrasing, optionally prefixed by competitor.
    video: list[str] = []
    for video_kind in ("demo video", "walkthrough"):
        video.append(f"{base_phrase} {video_kind}")
        for name in competitors:
            video.append(f"{name} {base_phrase} {video_kind}")

    # community: actively target real forums / knowledge communities — BOTH
    # Chinese and international. Uses Google/Serper `(site:a OR site:b ...)`
    # grouping so ONE search covers many sites, staying within the per-probe
    # search budget (a per-site query would blow past MAX_PER_BUCKET and the
    # search cap, so most sites would never actually run).
    #   CN: 知乎 / 少数派 / CSDN / 掘金 / V2EX / 小红书
    #   EN: reddit(old.) / stackoverflow / stackexchange / producthunt / HN
    _CN_GROUP = "(site:zhihu.com OR site:sspai.com OR site:csdn.net OR site:juejin.cn OR site:v2ex.com OR site:xiaohongshu.com)"
    _EN_GROUP = "(site:old.reddit.com OR site:stackoverflow.com OR site:stackexchange.com OR site:producthunt.com OR site:news.ycombinator.com)"
    community: list[str] = []
    for name in competitors:
        community.append(f"{name} {base_phrase} {_CN_GROUP}")   # 中文社群一网打尽
        community.append(f"{name} {base_phrase} {_EN_GROUP}")   # 国外社群一网打尽
        community.append(f"{name} {base_phrase} 使用体验 评价")  # 兜底：不限站点
    if not competitors:
        community.append(f"{base_phrase} {_CN_GROUP}")
        community.append(f"{base_phrase} {_EN_GROUP}")

    # generic: base terms crossed with intent and version modifiers.
    generic: list[str] = list(base)
    for intent in intents:
        generic.append(f"{base_phrase} {intent}")
    for version in versions:
        generic.append(f"{base_phrase} {version}")

    return QueryBundle(
        help_docs=_cap(help_docs),
        interactive_demo=_cap(interactive_demo),
        video=_cap(video),
        community=_cap(community),
        generic=_cap(generic),
    )


def build_query_bundle(
    db: Session,
    cell_id: UUID,
    competitor_id: UUID | None = None,
) -> QueryBundle:
    """Load a cell + lexicon + competitor names from the DB and expand.

    Raises AppError CELL_NOT_FOUND (404) if the cell does not exist. Lexicon
    terms are loaded broadly for now (all entries); competitor names are the
    canonical name plus aliases for either the single requested competitor or
    all confirmed competitors.
    """
    cell = db.execute(
        select(GridCell).where(GridCell.id == cell_id)
    ).scalar_one_or_none()
    if cell is None:
        raise AppError("CELL_NOT_FOUND", f"Grid cell {cell_id} not found", 404)

    # Lexicon: load all terms for now (category- + project-level). Filtering by
    # level/competitor can be layered on later without changing the pure core.
    lexicon_terms = [
        row.term
        for row in db.execute(select(DomainLexicon)).scalars().all()
    ]

    # Competitors: one specific entity, or every confirmed competitor.
    comp_query = select(CompetitorEntity)
    if competitor_id is not None:
        comp_query = comp_query.where(CompetitorEntity.id == competitor_id)
    else:
        comp_query = comp_query.where(CompetitorEntity.status == "confirmed")

    competitor_names: list[str] = []
    for comp in db.execute(comp_query).scalars().all():
        if comp.canonical_name:
            competitor_names.append(comp.canonical_name)
        if comp.aliases:
            competitor_names.extend(a for a in comp.aliases if a)

    return expand_terms_for_cell(
        jtbd=cell.jtbd,
        journey_stage=cell.journey_stage,
        page_state=cell.page_state,
        lexicon_terms=lexicon_terms,
        competitor_names=competitor_names,
    )
