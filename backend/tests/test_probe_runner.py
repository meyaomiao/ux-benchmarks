"""Unit tests for run_probe's terminal-state choice and score logging.

Pure unit tests: every collaborator (pipeline, asset store, coverage, state
machine) is stubbed, so no DB or network is involved.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from billiard.exceptions import SoftTimeLimitExceeded

from app.services.m3_collection import probe_runner
from app.services.m3_collection.pipeline import ProbeResult
from app.services.m3_collection.state_machine import CellState


def _wire(monkeypatch, *, result: ProbeResult, live_evidence: bool):
    """Stub every collaborator of run_probe. Returns the recorded transitions."""
    transitions: list[CellState] = []

    def fake_enqueue_cell(_db, _cell_id, _competitor_id, _trigger):
        return SimpleNamespace(status=CellState.QUEUED, probe_cycles=1)

    def fake_transition(_db, _cell_id, _competitor_id, to_state, *, note=None):
        transitions.append(to_state)
        return SimpleNamespace(status=to_state, probe_cycles=2)

    monkeypatch.setattr(probe_runner, "enqueue_cell", fake_enqueue_cell)
    monkeypatch.setattr(probe_runner, "transition_state", fake_transition)
    monkeypatch.setattr(
        probe_runner, "run_probe_pipeline", lambda *_args, **_kwargs: result
    )
    monkeypatch.setattr(
        probe_runner,
        "recompute_coverage",
        lambda *_args: SimpleNamespace(
            status=CellState.SHORTLIST_READY, probe_cycles=2
        ),
    )
    monkeypatch.setattr(
        probe_runner, "has_live_evidence", lambda *_args: live_evidence
    )
    monkeypatch.setattr(
        probe_runner, "log_scored_candidates", lambda *_args, **_kwargs: 0
    )
    return transitions


def _empty_result(cell_id, competitor_id, candidates_found: int) -> ProbeResult:
    return ProbeResult(
        cell_id=cell_id,
        competitor_id=competitor_id,
        candidates_found=candidates_found,
        scored=[],
        passed=[],
    )


def test_no_passers_but_live_evidence_keeps_pair_out_of_rejected_empty(monkeypatch):
    cell_id, competitor_id = uuid4(), uuid4()
    transitions = _wire(
        monkeypatch,
        result=_empty_result(cell_id, competitor_id, 12),
        live_evidence=True,
    )

    out = probe_runner.run_probe(object(), cell_id, competitor_id)

    assert transitions == [CellState.PROBING]
    assert out["state"] == CellState.SHORTLIST_READY
    assert out["passed"] == 0
    assert out["persisted"] == 0


def test_no_passers_and_no_live_evidence_becomes_rejected_empty(monkeypatch):
    cell_id, competitor_id = uuid4(), uuid4()
    transitions = _wire(
        monkeypatch,
        result=_empty_result(cell_id, competitor_id, 12),
        live_evidence=False,
    )

    out = probe_runner.run_probe(object(), cell_id, competitor_id)

    assert transitions == [CellState.PROBING, CellState.REJECTED_EMPTY]
    assert out["state"] == CellState.REJECTED_EMPTY


def test_every_scored_candidate_is_logged_with_the_probe_cycle(monkeypatch):
    cell_id, competitor_id = uuid4(), uuid4()
    scored = [("cand-a", "score-a"), ("cand-b", "score-b")]
    _wire(
        monkeypatch,
        result=ProbeResult(
            cell_id=cell_id,
            competitor_id=competitor_id,
            candidates_found=2,
            scored=scored,
            passed=[],
        ),
        live_evidence=False,
    )
    logged: list[tuple] = []
    monkeypatch.setattr(
        probe_runner,
        "log_scored_candidates",
        lambda _db, _cid, _kid, rows, *, probe_cycle=None: logged.append(
            (rows, probe_cycle)
        ),
    )

    probe_runner.run_probe(object(), cell_id, competitor_id)

    assert logged == [(scored, 2)]


def test_pipeline_failure_still_lands_on_rejected_empty(monkeypatch):
    cell_id, competitor_id = uuid4(), uuid4()
    transitions = _wire(
        monkeypatch,
        result=_empty_result(cell_id, competitor_id, 0),
        live_evidence=True,
    )

    def boom(*_args, **_kwargs):
        raise RuntimeError("ssl handshake failed")

    monkeypatch.setattr(probe_runner, "run_probe_pipeline", boom)
    monkeypatch.setattr(
        probe_runner,
        "log_scored_candidates",
        lambda *_args, **_kwargs: pytest.fail("nothing was scored"),
    )

    out = probe_runner.run_probe(object(), cell_id, competitor_id)

    assert transitions == [CellState.PROBING, CellState.REJECTED_EMPTY]
    assert out["error"].startswith("ssl handshake failed")


def test_soft_timeout_lands_on_rejected_empty_and_propagates(monkeypatch):
    cell_id, competitor_id = uuid4(), uuid4()
    transitions = _wire(
        monkeypatch,
        result=_empty_result(cell_id, competitor_id, 0),
        live_evidence=True,
    )

    def timeout(*_args, **_kwargs):
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(probe_runner, "run_probe_pipeline", timeout)

    with pytest.raises(SoftTimeLimitExceeded):
        probe_runner.run_probe(object(), cell_id, competitor_id)

    assert transitions == [CellState.PROBING, CellState.REJECTED_EMPTY]
