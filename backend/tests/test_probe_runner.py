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
    monkeypatch.setattr(
        probe_runner,
        "log_probe_run",
        lambda *_args, **_kwargs: SimpleNamespace(id=uuid4()),
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


def test_completed_probe_logs_run_counts_and_returns_same_summary(monkeypatch):
    cell_id, competitor_id = uuid4(), uuid4()
    scored = [("cand-a", "score-a"), ("cand-b", "score-b")]
    result = ProbeResult(
        cell_id=cell_id,
        competitor_id=competitor_id,
        candidates_found=2,
        scored=scored,
        passed=[scored[0]],
    )
    _wire(monkeypatch, result=result, live_evidence=True)
    monkeypatch.setattr(probe_runner, "persist_passing", lambda *_args: [object()])
    calls = []

    def capture(_db, _cid, _kid, telemetry, **kwargs):
        telemetry.scoring_calls = 2
        telemetry.finish()
        calls.append(kwargs)
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(probe_runner, "log_probe_run", capture)

    out = probe_runner.run_probe(object(), cell_id, competitor_id)

    assert calls == [
        {
            "probe_cycle": 2,
            "outcome": "completed",
            "final_state": CellState.SHORTLIST_READY,
            "candidates_found": 2,
            "scored_count": 2,
            "passed_count": 1,
            "persisted_count": 1,
        }
    ]
    assert out["run_id"]
    assert out["run_stats"]["scoring_calls"] == 2


def test_pipeline_failure_lands_on_rejected_empty_and_propagates(monkeypatch):
    cell_id, competitor_id = uuid4(), uuid4()
    transitions = _wire(
        monkeypatch,
        result=_empty_result(cell_id, competitor_id, 0),
        live_evidence=True,
    )

    def boom(*_args, **kwargs):
        telemetry = kwargs["telemetry"]
        telemetry.candidates_found = 5
        telemetry.scored_count = 2
        telemetry.passed_count = 1
        telemetry.scored_candidates = [("cand-a", "score-a")]
        raise RuntimeError("ssl handshake failed")

    monkeypatch.setattr(probe_runner, "run_probe_pipeline", boom)
    partial_logs = []
    monkeypatch.setattr(
        probe_runner,
        "log_scored_candidates",
        lambda _db, _cid, _kid, rows, *, probe_cycle=None: partial_logs.append(
            (rows, probe_cycle)
        ),
    )
    run_logs = []
    monkeypatch.setattr(
        probe_runner,
        "log_probe_run",
        lambda *_args, **kwargs: run_logs.append(kwargs),
    )

    with pytest.raises(RuntimeError, match="ssl handshake failed"):
        probe_runner.run_probe(object(), cell_id, competitor_id)

    assert transitions == [CellState.PROBING, CellState.REJECTED_EMPTY]
    assert run_logs[0]["outcome"] == "failed"
    assert run_logs[0]["candidates_found"] == 5
    assert run_logs[0]["scored_count"] == 2
    assert run_logs[0]["passed_count"] == 1
    assert run_logs[0]["error_type"] == "RuntimeError"
    assert partial_logs == [([("cand-a", "score-a")], 2)]


def test_soft_timeout_lands_on_rejected_empty_and_propagates(monkeypatch):
    cell_id, competitor_id = uuid4(), uuid4()
    transitions = _wire(
        monkeypatch,
        result=_empty_result(cell_id, competitor_id, 0),
        live_evidence=True,
    )

    def timeout(*_args, **kwargs):
        telemetry = kwargs["telemetry"]
        telemetry.candidates_found = 4
        telemetry.scored_count = 1
        telemetry.scored_candidates = [("cand-a", "score-a")]
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(probe_runner, "run_probe_pipeline", timeout)
    partial_logs = []
    monkeypatch.setattr(
        probe_runner,
        "log_scored_candidates",
        lambda _db, _cid, _kid, rows, *, probe_cycle=None: partial_logs.append(
            (rows, probe_cycle)
        ),
    )
    run_logs = []
    monkeypatch.setattr(
        probe_runner,
        "log_probe_run",
        lambda *_args, **kwargs: run_logs.append(kwargs),
    )

    with pytest.raises(SoftTimeLimitExceeded):
        probe_runner.run_probe(object(), cell_id, competitor_id)

    assert transitions == [CellState.PROBING, CellState.REJECTED_EMPTY]
    assert run_logs[0]["outcome"] == "soft_timeout"
    assert run_logs[0]["candidates_found"] == 4
    assert run_logs[0]["scored_count"] == 1
    assert run_logs[0]["passed_count"] == 0
    assert run_logs[0]["error_type"] == "SoftTimeLimitExceeded"
    assert partial_logs == [([("cand-a", "score-a")], 2)]


def test_probe_result_exposes_minimal_agentic_stats(monkeypatch):
    cell_id, competitor_id = uuid4(), uuid4()
    result = _empty_result(cell_id, competitor_id, 0)
    result.agentic_stats = {
        "steps": 3,
        "pages_opened": 2,
        "candidates_saved": 1,
        "stop_reason": "model_stop",
    }
    _wire(monkeypatch, result=result, live_evidence=False)

    out = probe_runner.run_probe(object(), cell_id, competitor_id)

    assert out["agentic_stats"] == result.agentic_stats
