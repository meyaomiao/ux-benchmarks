"""Near-threshold rescore: screenshot right-product text near-misses, re-score.

A text candidate is structurally capped on fidelity + evidence_directness, so one
that already reads as the target product and lands just under RELEVANCE_FLOOR is
a missing screenshot away from passing. These tests pin the qualification rules
and the audit trail, offline (no browser, no network).
"""
from uuid import uuid4

import app.services.m3_collection.pipeline as pipeline_mod
from app.schemas.m3 import QueryBundle
from app.services.m3_collection.contracts import (
    RELEVANCE_FLOOR,
    Candidate,
    EvidenceType,
    RubricBreakdown,
    Score,
    SourceType,
)
from app.services.m3_collection.pipeline import run_probe_pipeline

NEAR_MISS = RELEVANCE_FLOOR - 0.01   # inside the band
FAR_MISS = RELEVANCE_FLOOR - 0.40    # outside the band


class _OneCandidateAdapter:
    """Emits a single text-only candidate (no image_path)."""

    source_type = SourceType.GENERIC

    def fetch(self, cell_id, competitor_id, queries, *, limit=10):
        return [
            Candidate(
                cell_id=cell_id,
                competitor_id=competitor_id,
                source_url="https://experienceleague.adobe.com/acrobat-ai",
                source_type=self.source_type,
                text_content="Adobe Acrobat AI Assistant analyses uploaded PDFs.",
            )
        ]


class _BandScorer:
    """Text mode scores `text_score`; image mode passes.

    Mirrors the real asymmetry: the same page scores higher once a screenshot
    lets the scorer judge fidelity and directness directly.
    """

    def __init__(self, text_score, product_match=0.95):
        self._text_score = text_score
        self._product_match = product_match
        self.image_calls = 0

    def score(self, candidate, **kwargs):
        if candidate.image_path:
            self.image_calls += 1
            return Score(
                candidate_id=candidate.candidate_id,
                score=0.72, passed=True,
                evidence_type=EvidenceType.OBSERVED,
                rubric=RubricBreakdown(
                    state_match=0.7, product_match=self._product_match, fidelity=0.8,
                ),
                reasoning="image mode",
            )
        return Score(
            candidate_id=candidate.candidate_id,
            score=self._text_score, passed=False,
            evidence_type=EvidenceType.CLAIMED,
            rubric=RubricBreakdown(
                state_match=0.45, product_match=self._product_match, fidelity=0.3,
            ),
            reasoning="text mode",
        )


def _patch(monkeypatch, *, shots):
    monkeypatch.setattr(
        pipeline_mod, "build_query_bundle",
        lambda db, cell_id, competitor_id: QueryBundle(generic=["q1"]),
    )
    monkeypatch.setattr(
        pipeline_mod, "get_mapping_card_by_cell", lambda db, cell_id: None,
    )
    captured: list[list[str]] = []

    def fake_capture(urls):
        captured.append(list(urls))
        return shots

    monkeypatch.setattr(pipeline_mod, "capture_page_screenshots", fake_capture)
    # Keep the test offline: live mode would resolve query strings through the
    # real search API before the fake adapter ever runs.
    monkeypatch.setattr(
        pipeline_mod, "resolve_queries_to_urls",
        lambda queries, max_total=0, allow_unanchored_fallback=True: list(queries),
    )
    return captured


def _run(scorer):
    return run_probe_pipeline(
        db=None, cell_id=uuid4(), competitor_id=uuid4(),
        adapter=_OneCandidateAdapter(), scorer=scorer,
    )


def test_near_miss_gets_rescored(monkeypatch):
    url = "https://experienceleague.adobe.com/acrobat-ai"
    captured = _patch(monkeypatch, shots={url: "/tmp/shot.png"})
    scorer = _BandScorer(NEAR_MISS)

    result = _run(scorer)

    assert captured == [[url]]
    assert scorer.image_calls == 1
    assert result.has_passers is True
    # Both verdicts are retained, so the diagnostics log explains the upgrade.
    assert len(result.scored) == 2
    assert {s.scored_by for _, s in result.scored} == {"mock"}
    assert [s.passed for _, s in result.scored] == [False, True]


def test_far_miss_is_not_screenshotted(monkeypatch):
    """Well below the floor a screenshot can't rescue it — don't spend the call."""
    captured = _patch(monkeypatch, shots={})
    scorer = _BandScorer(FAR_MISS)

    result = _run(scorer)

    assert captured == []
    assert scorer.image_calls == 0
    assert result.has_passers is False
    assert len(result.scored) == 1


def test_off_product_near_miss_is_not_screenshotted(monkeypatch):
    """Below the product gate the candidate is the wrong product entirely."""
    captured = _patch(monkeypatch, shots={})
    scorer = _BandScorer(NEAR_MISS, product_match=0.1)

    result = _run(scorer)

    assert captured == []
    assert scorer.image_calls == 0
    assert result.has_passers is False


def test_failed_capture_leaves_original_score(monkeypatch):
    """No screenshot available => the text verdict stands, probe still succeeds."""
    captured = _patch(monkeypatch, shots={})
    scorer = _BandScorer(NEAR_MISS)

    result = _run(scorer)

    assert captured == [["https://experienceleague.adobe.com/acrobat-ai"]]
    assert scorer.image_calls == 0
    assert len(result.scored) == 1
    assert result.has_passers is False
