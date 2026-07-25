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
import logging
import re
from functools import lru_cache
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.models.m0_registry import CompetitorEntity, DomainLexicon
from app.models.m1_grid import GridCell
from app.schemas.m3 import QueryBundle

logger = logging.getLogger(__name__)

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


def _base_phrase(page_state: str, journey_stage: str) -> str:
    """The scenario seed phrase (page_state + journey_stage). Shared by expand
    and build_query_bundle so the two never drift."""
    return " ".join(t for t in (page_state, journey_stage) if t).strip()


_CJK_RE = re.compile(r"[一-鿿]")


def _bare_domain(raw: str | None) -> str:
    """Strip scheme + trailing slash from a stored domain so it can go straight
    into a Google/Serper `site:` operator. Keeps any path (e.g. 'notion.so/help'
    → site: honours path prefixes). Returns '' for empty/None."""
    if not raw:
        return ""
    d = re.sub(r"^https?://", "", raw.strip(), flags=re.IGNORECASE)
    return d.strip("/")


def _site_anchor(
    domains: dict[str, tuple[str | None, str | None]] | None,
    name: str,
    prefer: str,
) -> str:
    """Build a `site:` anchor for a competitor's OWN domains, or '' if none known.

    `prefer` picks which domain leads: "help" (help-center first, for help_docs)
    or "official" (marketing site first, for interactive_demo). The other domain
    is kept as a secondary `site:` so a single query covers both. This is what
    stops help_docs from pulling a rival's docs — the search can only return
    pages on the competitor's own site.
    """
    if not domains:
        return ""
    pair = domains.get(name)
    if not pair:
        return ""
    help_d, official_d = _bare_domain(pair[0]), _bare_domain(pair[1])
    # ONE site: only. Serper free accounts reject `(site:a OR site:b)` grouping
    # ("Query pattern not allowed for free accounts", HTTP 400), which silently
    # killed every anchored query. A single `site:` (even with a path, e.g.
    # `site:notion.so/help`) is accepted. Pick the preferred domain; fall back to
    # the other if the preferred one is missing.
    ordered = ([help_d, official_d] if prefer == "help" else [official_d, help_d])
    for d in ordered:
        if d:
            return f"site:{d}"
    return ""


@lru_cache(maxsize=512)
def _to_english(phrase: str) -> str:
    """Translate a short scenario phrase to English via the GPT relay (luna).

    Official-source docs (help centres, product tours) for our benchmark set are
    English-first, but the scenario phrase comes from the project's language
    (usually Chinese). We translate ONCE per phrase (cached) so help_docs /
    interactive_demo query English pages effectively.

    Best-effort: returns the phrase unchanged when it has no CJK, when no GPT key
    is set, or on any failure — never blocks or crashes query building.
    """
    if not phrase or not _CJK_RE.search(phrase) or not settings.gpt_api_key:
        return phrase
    try:
        import json
        import urllib.request

        prompt = (
            "把下面的产品界面/场景短语翻译成简洁的英文检索词，"
            "只返回英文，不要引号、不要解释、不要句号：\n" + phrase
        )
        body = json.dumps({
            "model": settings.gpt_scorer_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }).encode()
        req = urllib.request.Request(
            f"{settings.gpt_base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {settings.gpt_api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.load(resp)
        out = (payload["choices"][0]["message"]["content"] or "").strip()
        return out or phrase
    except Exception as exc:  # never block query building
        logger.warning("scenario translation failed for %r: %r", phrase, exc)
        return phrase


def expand_terms_for_cell(
    jtbd: str,
    journey_stage: str,
    page_state: str,
    lexicon_terms: list[str],
    competitor_names: list[str],
    official_phrase: str | None = None,
    competitor_domains: dict[str, tuple[str | None, str | None]] | None = None,
) -> QueryBundle:
    """Build a bucketed QueryBundle for one grid cell. Pure -- no DB access.

    The base phrase combines the cell's page_state and journey_stage keywords.
    Competitor names (canonical + aliases) widen the surface, and intent/version
    modifiers steer toward task-oriented and current results. Each bucket is
    deduplicated and capped at MAX_PER_BUCKET for determinism.

    Official-source buckets (help_docs, interactive_demo) are treated differently
    from third-party ones:
      * ``official_phrase`` — an English rendering of the scenario, used INSTEAD of
        the (usually Chinese) base_phrase for those buckets, because the benchmark
        set's help centres / product tours are English-first. Falls back to
        base_phrase when not supplied.
      * ``competitor_domains`` — maps each competitor name (canonical AND every
        alias) to its ``(help_center_domain, official_domain)``. When known, the
        official buckets are ``site:``-anchored to the competitor's OWN domain, so
        a search can only return that product's pages (not a rival's docs on the
        same feature). Missing domains degrade gracefully to an un-anchored query.
    """
    # A single combined phrase used as a query seed across buckets.
    base_phrase = _base_phrase(page_state, journey_stage)
    # Official (help/demo) buckets query English pages; fall back to base_phrase.
    off_phrase = (official_phrase or base_phrase).strip()

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
            anchor = _site_anchor(competitor_domains, name, prefer="help")
            # `site:notion.so/help {phrase} documentation` — anchored to the
            # competitor's OWN docs domain so a rival's page can't be returned.
            for doc in _DOC_TERMS:
                help_docs.append(
                    f"{anchor} {name} {off_phrase} {doc}".strip()
                )
            help_docs.append(f"{anchor} {name} {off_phrase} how to".strip())
    else:
        for doc in _DOC_TERMS:
            help_docs.append(f"{off_phrase} {doc}")

    # interactive_demo: demo/tour phrasing, prefixed by competitor and anchored to
    # the competitor's own marketing site when known.
    interactive_demo: list[str] = []
    for demo_kind in ("interactive demo", "product tour"):
        interactive_demo.append(f"{off_phrase} {demo_kind}")
        for name in competitors:
            anchor = _site_anchor(competitor_domains, name, prefer="official")
            interactive_demo.append(
                f"{anchor} {name} {off_phrase} {demo_kind}".strip()
            )

    # video: video/walkthrough phrasing, optionally prefixed by competitor.
    video: list[str] = []
    for video_kind in ("demo video", "walkthrough"):
        video.append(f"{base_phrase} {video_kind}")
        for name in competitors:
            video.append(f"{name} {base_phrase} {video_kind}")

    # community: real user voice from forums / knowledge communities.
    #
    # We DO NOT `site:`-anchor here. Serper free accounts reject the
    # `(site:a OR site:b ...)` grouping we'd need to cover many sites in one query
    # (HTTP 400 "Query pattern not allowed for free accounts"), and a per-site
    # query would blow past the search budget. Instead we use plain
    # community-signal keywords — a mix of CN and EN forum-voice terms — and let
    # Google surface reddit / 知乎 / stackoverflow etc. naturally. Those domains
    # are explicitly NOT in the junk filter, so their results survive downstream.
    _CN_COMMUNITY_TERMS = "使用体验 评价 讨论 吐槽"
    _EN_COMMUNITY_TERMS = "review discussion reddit forum"
    community: list[str] = []
    for name in competitors:
        community.append(f"{name} {base_phrase} {_CN_COMMUNITY_TERMS}")  # 中文社群声音
        community.append(f"{name} {base_phrase} {_EN_COMMUNITY_TERMS}")  # 国外社群声音
    if not competitors:
        community.append(f"{base_phrase} {_CN_COMMUNITY_TERMS}")
        community.append(f"{base_phrase} {_EN_COMMUNITY_TERMS}")

    # generic: product + translated scenario + search intent. Raw cell labels are
    # internal taxonomy, not useful search terms, and caused unrelated results.
    generic: list[str] = []
    for name in competitors:
        for intent in intents:
            generic.append(f"{name} {off_phrase} {intent}")
        for version in versions:
            generic.append(f"{name} {off_phrase} {version}")
    if not competitors:
        for intent in intents:
            generic.append(f"{off_phrase} {intent}")

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

    # Collect names AND a name→(help_center_domain, official_domain) map so the
    # official buckets can `site:`-anchor to each competitor's own domain. Every
    # alias shares the parent's domains (downstream iterates the flat name list,
    # so aliases must resolve too).
    competitor_names: list[str] = []
    competitor_domains: dict[str, tuple[str | None, str | None]] = {}
    for comp in db.execute(comp_query).scalars().all():
        pair = (comp.help_center_domain, comp.official_domain)
        if comp.canonical_name:
            competitor_names.append(comp.canonical_name)
            competitor_domains[comp.canonical_name] = pair
        if comp.aliases:
            for a in comp.aliases:
                if a:
                    competitor_names.append(a)
                    competitor_domains[a] = pair

    # Official-source buckets query English pages (help centres / product tours in
    # our benchmark set are English-first), so translate the scenario phrase once.
    official_phrase = _to_english(_base_phrase(cell.page_state, cell.journey_stage))

    return expand_terms_for_cell(
        jtbd=cell.jtbd,
        journey_stage=cell.journey_stage,
        page_state=cell.page_state,
        lexicon_terms=lexicon_terms,
        competitor_names=competitor_names,
        official_phrase=official_phrase,
        competitor_domains=competitor_domains,
    )
