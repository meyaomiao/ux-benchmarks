"""Tests for the interactive demo adapter (#18).

All tests run in mock mode (no network, no Playwright). The critical assertion
unique to this adapter: mock Candidates must carry a real, openable image_path
— not None — so the AI scorer exercises its strict IMAGE mode rather than the
text-only path.
"""
import os
import struct
import zlib
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import settings
from app.services.m3_collection.adapters.interactive_demo import (
    InteractiveDemoAdapter,
    _detect_platform,
    _looks_like_url,
    _make_png,
    DEMO_PLATFORM_SIGNATURES,
)
from app.services.m3_collection.contracts import EvidenceType, SourceType


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch, tmp_path):
    """Force mock mode and redirect assets_dir to a temp directory."""
    monkeypatch.setattr(settings, "use_collection_mock", True)
    monkeypatch.setattr(settings, "assets_dir", tmp_path)


# ── _make_png ──────────────────────────────────────────────────────────────

def test_make_png_is_valid_png():
    data = _make_png()
    # PNG magic bytes
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_make_png_different_colours_differ():
    a = _make_png(rgb=(255, 0, 0))
    b = _make_png(rgb=(0, 0, 255))
    assert a != b


def test_make_png_openable_by_stdlib(tmp_path):
    """The bytes must form a file that can be opened (no Pillow needed here —
    just check the file is non-empty and starts with the right magic)."""
    fpath = tmp_path / "test.png"
    fpath.write_bytes(_make_png())
    assert fpath.stat().st_size > 50
    assert fpath.read_bytes()[:4] == b"\x89PNG"


# ── _detect_platform ───────────────────────────────────────────────────────

@pytest.mark.parametrize("url,expected", [
    ("https://app.navattic.com/demo/abc", "navattic"),
    ("https://demo.storylane.io/demo/xyz", "storylane"),
    ("https://app.arcade.software/share/abc", "arcade"),
    ("https://demostack.com/v/test", "demostack"),
    ("https://app.supademo.com/demo/1", "supademo"),
    ("https://walnut.io/share/demo", "walnut"),
    ("https://totally-unrelated.com/page", None),
])
def test_detect_platform(url, expected):
    assert _detect_platform(url) == expected


def test_all_signatures_covered():
    """Every entry in DEMO_PLATFORM_SIGNATURES should be detectable."""
    for platform, sigs in DEMO_PLATFORM_SIGNATURES.items():
        assert _detect_platform(f"https://{sigs[0]}/demo") == platform


# ── _looks_like_url ────────────────────────────────────────────────────────

def test_looks_like_url_real():
    assert _looks_like_url("https://help.example.com/docs") is True


def test_looks_like_url_search_op():
    assert _looks_like_url("site:help.* permission editor") is False


# ── mock fetch: THE key test for #18 ──────────────────────────────────────

def test_mock_fetch_returns_candidates():
    adapter = InteractiveDemoAdapter()
    cell_id, competitor_id = uuid4(), uuid4()
    results = adapter.fetch(cell_id, competitor_id, ["q1", "q2", "q3"])
    assert len(results) >= 1


def test_mock_candidates_have_image_path():
    """Each mock Candidate MUST carry a real image_path.

    This is the core invariant for #18: unlike the help-docs adapter (text-only),
    the demo adapter feeds the scorer's IMAGE mode. If image_path were None, the
    scorer would fall back to text mode and the upgrade in evidence quality from
    screenshots would be lost.
    """
    adapter = InteractiveDemoAdapter()
    candidates = adapter.fetch(uuid4(), uuid4(), ["q1", "q2"])
    for cand in candidates:
        assert cand.image_path is not None, "demo adapter must set image_path"
        assert Path(cand.image_path).exists(), f"image_path must point to a real file: {cand.image_path}"


def test_mock_image_is_valid_png():
    """The created PNG must be openable (PNG magic bytes present)."""
    adapter = InteractiveDemoAdapter()
    candidates = adapter.fetch(uuid4(), uuid4(), ["q1"])
    fpath = Path(candidates[0].image_path)
    assert fpath.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_mock_source_type_is_interactive_demo():
    adapter = InteractiveDemoAdapter()
    for cand in adapter.fetch(uuid4(), uuid4(), ["q1"]):
        assert cand.source_type == SourceType.INTERACTIVE_DEMO


def test_mock_evidence_type_is_observed():
    """Demo frames should be OBSERVED — we can see the actual UI."""
    adapter = InteractiveDemoAdapter()
    for cand in adapter.fetch(uuid4(), uuid4(), ["q1"]):
        assert cand.evidence_type_hint == EvidenceType.OBSERVED


def test_mock_respects_limit():
    adapter = InteractiveDemoAdapter()
    results = adapter.fetch(uuid4(), uuid4(), ["q1", "q2", "q3"], limit=2)
    assert len(results) <= 2


def test_mock_candidates_have_cell_and_competitor_ids():
    cell_id, competitor_id = uuid4(), uuid4()
    adapter = InteractiveDemoAdapter()
    for cand in adapter.fetch(cell_id, competitor_id, ["q1"]):
        assert cand.cell_id == cell_id
        assert cand.competitor_id == competitor_id


# ── scorer sees image mode for demo candidates ─────────────────────────────

def test_scorer_uses_image_mode_for_demo_candidate(monkeypatch):
    """When a demo Candidate has image_path, the scorer must branch into image
    mode — we verify it by checking `has_image` inside score_from_text is True
    (which raises fidelity to 0.8 instead of the text heuristic ceiling)."""
    from app.services.m3_collection.scoring.relevance_scorer import RelevanceScorer
    monkeypatch.setattr(settings, "use_collection_mock", True)

    adapter = InteractiveDemoAdapter()
    cand = adapter.fetch(uuid4(), uuid4(), ["q1"], limit=1)[0]

    scorer = RelevanceScorer()
    score = scorer.score(
        cand,
        intent_definition="role permission matrix editor toggle",
        inclusion_criteria="assign member invite",
    )
    # Image mode: fidelity should be 0.8 (not the text-based heuristic)
    assert score.rubric.fidelity == pytest.approx(0.8, abs=0.01)
    # And scored_by must be "mock" (not "claude-vision" — no real key in test)
    assert score.scored_by == "mock"
