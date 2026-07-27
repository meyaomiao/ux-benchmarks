"""Offline orchestration tests for run_probe_pipeline.

The pipeline's two DB calls (build_query_bundle, get_mapping_card_by_cell) are
monkeypatched so the fetch -> score -> keep-passers logic is exercised without a
database, using fake adapter/scorer that satisfy the contracts Protocols.
"""
from pathlib import Path
from uuid import uuid4

import pytest
from billiard.exceptions import SoftTimeLimitExceeded

import app.services.m3_collection.pipeline as pipeline_mod
from app.schemas.m3 import QueryBundle
from app.services.m3_collection.adapters.agentic_site import AgenticSiteAdapter
from app.services.m3_collection.agentic_site import (
    ExploredPage,
    ExplorerResult,
    ExplorerStats,
)
from app.services.m3_collection.contracts import (
    Candidate,
    EvidenceType,
    RubricBreakdown,
    Score,
    SourceType,
)
from app.services.m3_collection.pipeline import (
    DEFAULT_SOURCE_BUDGETS,
    MAX_INITIAL_CANDIDATES_PER_PROBE,
    MAX_SEARCH_CALLS_PER_PROBE,
    run_probe_pipeline,
)


class _FakeAdapter:
    source_type = SourceType.HELP_DOCS

    def __init__(self, n):
        self._n = n

    def fetch(self, cell_id, competitor_id, queries, *, limit=10):
        return [
            Candidate(
                cell_id=cell_id,
                competitor_id=competitor_id,
                source_url=f"https://help.example.com/{i}",
                source_type=self.source_type,
                text_content=f"doc {i}",
            )
            for i in range(self._n)
        ]


class _FakeScorer:
    """Scores candidate i as passing when i is even."""

    def score(self, candidate, **kwargs):
        # deterministic: even-indexed URLs pass
        idx = int(candidate.source_url.rsplit("/", 1)[-1])
        val = 0.9 if idx % 2 == 0 else 0.1
        return Score(
            candidate_id=candidate.candidate_id,
            score=val,
            passed=val >= 0.55,
            evidence_type=EvidenceType.OBSERVED,
            rubric=RubricBreakdown(state_match=val),
            reasoning="fake",
        )


def _patch_db(monkeypatch):
    monkeypatch.setattr(
        pipeline_mod, "build_query_bundle",
        lambda db, cell_id, competitor_id: QueryBundle(help_docs=["q1", "q2"]),
    )
    monkeypatch.setattr(
        pipeline_mod, "get_mapping_card_by_cell",
        lambda db, cell_id: None,  # no card => empty intent, fine for orchestration
    )


def test_pipeline_keeps_only_passers(monkeypatch):
    _patch_db(monkeypatch)
    result = run_probe_pipeline(
        db=None, cell_id=uuid4(), competitor_id=uuid4(),
        adapter=_FakeAdapter(4), scorer=_FakeScorer(),
    )
    assert result.candidates_found == 4
    assert len(result.scored) == 4
    assert len(result.passed) == 2          # indexes 0 and 2
    assert result.has_passers is True


def test_pipeline_no_passers(monkeypatch):
    _patch_db(monkeypatch)

    class _AllFail(_FakeScorer):
        def score(self, candidate, **kwargs):
            s = super().score(candidate, **kwargs)
            return Score(
                candidate_id=s.candidate_id, score=0.1, passed=False,
                evidence_type=s.evidence_type, rubric=s.rubric, reasoning="fail",
            )

    result = run_probe_pipeline(
        db=None, cell_id=uuid4(), competitor_id=uuid4(),
        adapter=_FakeAdapter(3), scorer=_AllFail(),
    )
    assert result.candidates_found == 3
    assert result.has_passers is False


def test_pipeline_passers_sorted_desc(monkeypatch):
    _patch_db(monkeypatch)
    result = run_probe_pipeline(
        db=None, cell_id=uuid4(), competitor_id=uuid4(),
        adapter=_FakeAdapter(6), scorer=_FakeScorer(),
    )
    scores = [s.score for _, s in result.passed]
    assert scores == sorted(scores, reverse=True)


def test_pipeline_does_not_swallow_soft_timeout(monkeypatch):
    _patch_db(monkeypatch)

    class _TimedOutAdapter(_FakeAdapter):
        def fetch(self, *_args, **_kwargs):
            raise SoftTimeLimitExceeded()

    with pytest.raises(SoftTimeLimitExceeded):
        run_probe_pipeline(
            db=None,
            cell_id=uuid4(),
            competitor_id=uuid4(),
            adapter=_TimedOutAdapter(0),
            scorer=_FakeScorer(),
        )


class _CaptureScorer:
    """Records the scoring context handed to the scorer."""

    def __init__(self):
        self.kwargs = None

    def score(self, candidate, **kwargs):
        self.kwargs = kwargs
        return Score(
            candidate_id=candidate.candidate_id,
            score=0.9, passed=True,
            evidence_type=EvidenceType.OBSERVED,
            rubric=RubricBreakdown(state_match=0.9),
            reasoning="capture",
        )


class _FakeCard:
    intent_definition = "用户在风险高亮态审查合同条款"
    inclusion_criteria = "必须出现合同风险标记"
    exclusion_criteria = "排除营销页"


class _FakeComp:
    canonical_name = "Vercel"

    def __init__(self, competitor_type):
        self.competitor_type = competitor_type


class _FakeCell:
    page_state = "风险高亮态"
    journey_stage = "日常审查"
    jtbd = "查看AI提取的条款与风险标记"


class _FakeDB:
    """Returns the competitor first, then the grid cell — the pipeline's order."""

    def __init__(self, competitor_type):
        self._rows = [_FakeComp(competitor_type), _FakeCell()]

    def execute(self, _stmt):
        row = self._rows.pop(0) if self._rows else None

        class _Res:
            def scalar_one_or_none(self_inner):
                return row

        return _Res()


def _patch_context(monkeypatch, pattern="side-by-side diff review"):
    monkeypatch.setattr(
        pipeline_mod, "build_query_bundle",
        lambda db, cell_id, competitor_id: QueryBundle(help_docs=["q1"]),
    )
    monkeypatch.setattr(
        pipeline_mod, "get_mapping_card_by_cell", lambda db, cell_id: _FakeCard(),
    )
    monkeypatch.setattr(
        pipeline_mod, "abstract_interaction_pattern",
        lambda page_state, journey_stage, jtbd="": pattern,
    )
    # Keep these tests offline: live mode would resolve query strings through the
    # real search API before the fake adapter ever runs.
    monkeypatch.setattr(
        pipeline_mod, "resolve_queries_to_urls",
        lambda queries, max_total=0: list(queries),
    )


def test_cross_industry_pair_is_scored_on_interaction_pattern(monkeypatch):
    _patch_context(monkeypatch)
    scorer = _CaptureScorer()
    run_probe_pipeline(
        db=_FakeDB("cross_industry"), cell_id=uuid4(), competitor_id=uuid4(),
        adapter=_FakeAdapter(1), scorer=scorer,
    )
    assert scorer.kwargs["intent_definition"].startswith("side-by-side diff review")
    # Domain-language criteria would re-impose the filter the pattern removed.
    assert scorer.kwargs["inclusion_criteria"] == ""
    assert scorer.kwargs["exclusion_criteria"] == ""
    assert scorer.kwargs["product_name"] == "Vercel"


def test_direct_pair_keeps_domain_context(monkeypatch):
    _patch_context(monkeypatch)
    scorer = _CaptureScorer()
    run_probe_pipeline(
        db=_FakeDB("direct"), cell_id=uuid4(), competitor_id=uuid4(),
        adapter=_FakeAdapter(1), scorer=scorer,
    )
    assert scorer.kwargs["intent_definition"] == _FakeCard.intent_definition
    assert scorer.kwargs["inclusion_criteria"] == _FakeCard.inclusion_criteria
    assert scorer.kwargs["exclusion_criteria"] == _FakeCard.exclusion_criteria


def test_unavailable_abstraction_falls_back_to_domain_context(monkeypatch):
    _patch_context(monkeypatch, pattern="")
    scorer = _CaptureScorer()
    run_probe_pipeline(
        db=_FakeDB("indirect"), cell_id=uuid4(), competitor_id=uuid4(),
        adapter=_FakeAdapter(1), scorer=scorer,
    )
    assert scorer.kwargs["intent_definition"] == _FakeCard.intent_definition
    assert scorer.kwargs["inclusion_criteria"] == _FakeCard.inclusion_criteria


def test_agentic_failure_degrades_to_existing_adapter(monkeypatch):
    _patch_db(monkeypatch)
    monkeypatch.setattr(pipeline_mod.settings, "use_collection_mock", False)
    monkeypatch.setattr(
        pipeline_mod,
        "resolve_queries_to_urls",
        lambda queries, **_kwargs: list(queries),
    )

    def fail_explorer(**_kwargs):
        raise RuntimeError("browser launch failed")

    agentic = AgenticSiteAdapter(
        competitor_name="Acme",
        intent="permissions",
        official_domain="example.com",
        help_center_domain="help.example.com",
        explorer=fail_explorer,
    )
    result = run_probe_pipeline(
        db=None,
        cell_id=uuid4(),
        competitor_id=uuid4(),
        adapters=[agentic, _FakeAdapter(1)],
        scorer=_FakeScorer(),
    )

    assert result.candidates_found == 1
    assert len(result.scored) == 1
    assert result.agentic_stats["stop_reason"] == "adapter_failure"


def test_default_live_pipeline_wires_domains_and_keeps_all_existing_adapters(monkeypatch):
    cell_id, competitor_id = uuid4(), uuid4()
    created = {}
    fetched = []
    fetch_limits = []
    resolved_sources = []

    class _Competitor:
        canonical_name = "Acme"
        competitor_type = "direct"
        official_domain = "www.example.com"
        help_center_domain = "help.example.com"

    class _DB:
        def execute(self, _stmt):
            class _Result:
                def scalar_one_or_none(self):
                    return _Competitor()

            return _Result()

    class _AllPassScorer:
        def score(self, candidate, **_kwargs):
            return Score(
                candidate_id=candidate.candidate_id,
                score=0.9,
                passed=True,
                evidence_type=EvidenceType.OBSERVED,
                rubric=RubricBreakdown(state_match=0.9),
                reasoning="default adapter coverage",
            )

    class _RecordedAdapter:
        uses_search_queries = True

        def __init__(self, source_type):
            self.source_type = source_type

        def fetch(self, got_cell_id, got_competitor_id, queries, *, limit=10):
            assert got_cell_id == cell_id
            assert got_competitor_id == competitor_id
            assert queries
            fetched.append(self.source_type.value)
            fetch_limits.append((self.source_type, limit))
            return [
                Candidate(
                    cell_id=cell_id,
                    competitor_id=competitor_id,
                    source_url=f"https://sources.example/{self.source_type.value}",
                    source_type=self.source_type,
                    text_content=self.source_type.value,
                )
            ]

    class _Agentic:
        source_type = SourceType.AGENTIC_SITE
        uses_search_queries = False

        def __init__(self, **kwargs):
            created.update(kwargs)
            self.last_stats = {"stop_reason": "not_run"}

        def fetch(self, got_cell_id, got_competitor_id, queries, *, limit=10):
            del got_cell_id, got_competitor_id
            assert queries == []
            fetched.append(self.source_type.value)
            fetch_limits.append((self.source_type, limit))
            self.last_stats = {"stop_reason": "adapter_failure"}
            raise RuntimeError("agentic browser failed")

    class _Help(_RecordedAdapter):
        def __init__(self, **_kwargs):
            super().__init__(SourceType.HELP_DOCS)

    class _Interactive(_RecordedAdapter):
        def __init__(self):
            super().__init__(SourceType.INTERACTIVE_DEMO)

    class _Web(_RecordedAdapter):
        def __init__(self, source_type, **_kwargs):
            super().__init__(source_type)

    monkeypatch.setattr(pipeline_mod.settings, "use_collection_mock", False)
    monkeypatch.setattr(
        pipeline_mod,
        "build_query_bundle",
        lambda *_args: QueryBundle(
            help_docs=["help query"],
            interactive_demo=["demo query"],
            community=["community query"],
            generic=["generic query"],
        ),
    )
    monkeypatch.setattr(pipeline_mod, "get_mapping_card_by_cell", lambda *_args: None)
    monkeypatch.setattr(pipeline_mod, "AgenticSiteAdapter", _Agentic)
    monkeypatch.setattr(pipeline_mod, "HelpDocsAdapter", _Help)
    monkeypatch.setattr(pipeline_mod, "InteractiveDemoAdapter", _Interactive)
    monkeypatch.setattr(pipeline_mod, "WebSourceAdapter", _Web)

    def resolve(queries, **kwargs):
        resolved_sources.append((list(queries), kwargs))
        return [f"https://resolved.example/{len(resolved_sources)}"]

    monkeypatch.setattr(pipeline_mod, "resolve_queries_to_urls", resolve)

    result = run_probe_pipeline(
        db=_DB(),
        cell_id=cell_id,
        competitor_id=competitor_id,
        scorer=_AllPassScorer(),
    )

    assert created == {
        "competitor_name": "Acme",
        "intent": "",
        "official_domain": "www.example.com",
        "help_center_domain": "help.example.com",
    }
    assert fetched == [
        "agentic_site",
        "interactive_demo",
        "help_docs",
        "community",
        "generic",
    ]
    assert resolved_sources == [
        (["demo query"], {
            "max_total": 6,
            "max_searches": 3,
            "allow_unanchored_fallback": False,
        }),
        (["help query"], {
            "max_total": 12,
            "max_searches": 2,
            "allow_unanchored_fallback": False,
        }),
        (["community query"], {
            "max_total": 8,
            "max_searches": 2,
            "allow_unanchored_fallback": True,
        }),
        (["generic query"], {
            "max_total": 10,
            "max_searches": 3,
            "allow_unanchored_fallback": True,
        }),
    ]
    assert fetch_limits == [
        (source_type, DEFAULT_SOURCE_BUDGETS[source_type].max_candidates)
        for source_type in (
            SourceType.AGENTIC_SITE,
            SourceType.INTERACTIVE_DEMO,
            SourceType.HELP_DOCS,
            SourceType.COMMUNITY,
            SourceType.GENERIC,
        )
    ]
    assert result.candidates_found == 4
    assert result.agentic_stats == {"stop_reason": "adapter_failure"}


def test_default_source_budgets_bound_total_probe_cost():
    assert MAX_SEARCH_CALLS_PER_PROBE == 10
    assert MAX_INITIAL_CANDIDATES_PER_PROBE == 40


def test_agentic_image_candidate_enters_existing_scorer(monkeypatch, tmp_path):
    _patch_db(monkeypatch)
    monkeypatch.setattr(pipeline_mod.settings, "use_collection_mock", False)
    image_path = tmp_path / "permission-review.png"
    image_path.write_bytes(b"valid image fixture")

    def explorer(**_kwargs):
        return ExplorerResult(
            pages=(
                ExploredPage(
                    source_url="https://example.com/permissions",
                    title="Permission review",
                    text_content="Rendered roles table and permission toggles",
                    image_path=str(image_path),
                ),
            ),
            stats=ExplorerStats(
                steps=2,
                pages_opened=2,
                candidates_saved=1,
                stop_reason="model_stop",
            ),
        )

    class _VisionCaptureScorer:
        def __init__(self):
            self.candidates = []

        def score(self, candidate, **_kwargs):
            self.candidates.append(candidate)
            assert candidate.image_path == str(image_path)
            assert Path(candidate.image_path).read_bytes() == b"valid image fixture"
            return Score(
                candidate_id=candidate.candidate_id,
                score=0.9,
                passed=True,
                evidence_type=EvidenceType.OBSERVED,
                rubric=RubricBreakdown(state_match=0.9),
                reasoning="vision candidate",
            )

    scorer = _VisionCaptureScorer()
    agentic = AgenticSiteAdapter(
        competitor_name="Acme",
        intent="permissions",
        official_domain="example.com",
        help_center_domain=None,
        explorer=explorer,
    )
    result = run_probe_pipeline(
        db=None,
        cell_id=uuid4(),
        competitor_id=uuid4(),
        adapters=[agentic],
        scorer=scorer,
    )

    assert len(scorer.candidates) == 1
    assert scorer.candidates[0].source_type == SourceType.AGENTIC_SITE
    assert result.agentic_stats["candidates_saved"] == 1


def test_cross_adapter_url_dedup_prefers_image_then_richer_text():
    cell_id, competitor_id = uuid4(), uuid4()
    text_only = Candidate(
        cell_id=cell_id,
        competitor_id=competitor_id,
        source_url="https://EXAMPLE.com/permissions/#overview",
        source_type=SourceType.HELP_DOCS,
        text_content="long text " * 100,
    )
    image = Candidate(
        cell_id=cell_id,
        competitor_id=competitor_id,
        source_url="https://example.com/permissions",
        source_type=SourceType.AGENTIC_SITE,
        text_content="short",
        image_path="/tmp/permission.png",
    )
    richer_image = Candidate(
        cell_id=cell_id,
        competitor_id=competitor_id,
        source_url="https://example.com/settings/",
        source_type=SourceType.AGENTIC_SITE,
        text_content="complete rendered settings page",
        image_path="/tmp/settings-rich.png",
    )
    sparse_image = Candidate(
        cell_id=cell_id,
        competitor_id=competitor_id,
        source_url="https://example.com/settings",
        source_type=SourceType.INTERACTIVE_DEMO,
        text_content="settings",
        image_path="/tmp/settings-sparse.png",
    )

    deduped = pipeline_mod._dedupe_candidates(
        [text_only, image, richer_image, sparse_image]
    )

    assert deduped == [image, richer_image]
