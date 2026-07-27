"""Unit tests for the interaction-pattern abstraction (no network, no DB)."""
import io
import json
import urllib.request

import app.services.m3_collection.interaction_pattern as ip_mod
from app.core.config import settings
from app.services.m3_collection.interaction_pattern import (
    abstract_interaction_pattern,
    abstracted_intent,
    needs_abstraction,
)


def _fake_relay(content: str):
    def _urlopen(req, timeout=None):  # noqa: ARG001
        payload = {"choices": [{"message": {"content": content}}]}
        return io.BytesIO(json.dumps(payload).encode())
    return _urlopen


def test_needs_abstraction_only_for_non_direct():
    assert needs_abstraction("indirect") is True
    assert needs_abstraction("cross_industry") is True
    assert needs_abstraction("CROSS_INDUSTRY ") is True
    assert needs_abstraction("direct") is False
    assert needs_abstraction("") is False
    assert needs_abstraction(None) is False


def test_abstraction_returns_empty_without_key(monkeypatch):
    abstract_interaction_pattern.cache_clear()
    monkeypatch.setattr(settings, "gpt_api_key", "", raising=False)
    assert abstract_interaction_pattern("风险高亮态", "日常审查") == ""


def test_abstraction_returns_empty_without_seed(monkeypatch):
    abstract_interaction_pattern.cache_clear()
    monkeypatch.setattr(settings, "gpt_api_key", "k", raising=False)
    assert abstract_interaction_pattern("", "") == ""


def test_abstraction_uses_relay_phrase(monkeypatch):
    abstract_interaction_pattern.cache_clear()
    monkeypatch.setattr(settings, "gpt_api_key", "k", raising=False)
    monkeypatch.setattr(
        urllib.request, "urlopen",
        _fake_relay('"inline anomaly markers on a long scrollable document"'),
    )
    out = abstract_interaction_pattern("风险高亮态", "日常审查", "查看条款风险")
    assert out == "inline anomaly markers on a long scrollable document"


def test_abstraction_clips_overlong_relay_output(monkeypatch):
    abstract_interaction_pattern.cache_clear()
    monkeypatch.setattr(settings, "gpt_api_key", "k", raising=False)
    monkeypatch.setattr(
        urllib.request, "urlopen", _fake_relay(" ".join(f"w{i}" for i in range(40))),
    )
    out = abstract_interaction_pattern("状态", "阶段")
    assert len(out.split()) == ip_mod._MAX_WORDS


def test_abstraction_swallows_relay_failure(monkeypatch):
    abstract_interaction_pattern.cache_clear()
    monkeypatch.setattr(settings, "gpt_api_key", "k", raising=False)

    def _boom(req, timeout=None):  # noqa: ARG001
        raise OSError("relay down")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    assert abstract_interaction_pattern("状态", "阶段") == ""


def test_abstracted_intent_leads_with_pattern_and_keeps_background():
    out = abstracted_intent("side-by-side diff review", "对比两个合同版本")
    assert out.startswith("side-by-side diff review")
    assert "对比两个合同版本" in out
    assert "不要求行业术语" in out


def test_abstracted_intent_without_original():
    out = abstracted_intent("progress checklist before submit", "")
    assert out.startswith("progress checklist before submit")
    assert "原始场景" not in out
