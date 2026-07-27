"""Browser-rendered candidate fetching without real network or API calls."""
from __future__ import annotations

import io
import json
import sys
import types
import urllib.request
from pathlib import Path
from uuid import uuid4

import pytest
from billiard.exceptions import SoftTimeLimitExceeded

from app.core.config import settings
from app.services.m3_collection import content_fetch
from app.services.m3_collection.adapters import web_source
from app.services.m3_collection.adapters.web_source import WebSourceAdapter
from app.services.m3_collection.content_fetch import (
    FetchedPage,
    RenderBudget,
    fetch_candidate_pages,
)
from app.services.m3_collection.contracts import SourceType
from app.services.m3_collection.scoring.relevance_scorer import RelevanceScorer


class _FakeResponse:
    def __init__(self, content_type: str = "text/html; charset=utf-8") -> None:
        self.headers = {"content-type": content_type}


class _FakePage:
    def __init__(self, spec: dict, viewport: dict | None) -> None:
        self.spec = spec
        self.viewport = viewport
        self.default_timeout = None
        self.navigation_timeout = None
        self.goto_kwargs = None
        self.load_state = None
        self.load_state_timeout = None
        self.fallback_wait = None
        self.full_page = None
        self.closed = False

    def set_default_timeout(self, timeout: int) -> None:
        self.default_timeout = timeout

    def set_default_navigation_timeout(self, timeout: int) -> None:
        self.navigation_timeout = timeout

    def goto(self, url: str, **kwargs):
        self.url = url
        self.goto_kwargs = kwargs
        failure = self.spec.get("goto_error")
        if failure is not None:
            raise failure
        return _FakeResponse(self.spec.get("content_type", "text/html"))

    def query_selector(self, _selector: str):
        return None

    def wait_for_load_state(self, state: str, timeout: int | None = None) -> None:
        self.load_state = state
        self.load_state_timeout = timeout
        if self.spec.get("networkidle_error"):
            raise RuntimeError("page stayed busy")

    def wait_for_timeout(self, timeout: int) -> None:
        self.fallback_wait = timeout

    def title(self) -> str:
        return self.spec.get("title", "Rendered title")

    def evaluate(self, _script: str) -> str:
        return self.spec.get("text", "Rendered SPA controls and current product state")

    def screenshot(self, path: str, full_page: bool = False) -> None:
        self.full_page = full_page
        png_bytes = self.spec.get("png_bytes", 30_000)
        Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * png_bytes)

    def close(self) -> None:
        self.closed = True


class _FakeBrowser:
    def __init__(self, specs: list[dict]) -> None:
        self.specs = list(specs)
        self.pages: list[_FakePage] = []
        self.launch_timeout = None
        self.closed = False

    def new_page(self, viewport: dict | None = None) -> _FakePage:
        spec = self.specs[len(self.pages)] if len(self.pages) < len(self.specs) else {}
        page = _FakePage(spec, viewport)
        self.pages.append(page)
        return page

    def close(self) -> None:
        self.closed = True


def _install_fake_playwright(monkeypatch, specs: list[dict]) -> _FakeBrowser:
    browser = _FakeBrowser(specs)

    class _Chromium:
        @staticmethod
        def launch(*, headless: bool, timeout: int):
            assert headless is True
            browser.launch_timeout = timeout
            return browser

    class _Playwright:
        chromium = _Chromium()

        def __enter__(self):
            return self

        def __exit__(self, *_exc) -> bool:
            return False

    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.sync_playwright = lambda: _Playwright()
    root = types.ModuleType("playwright")
    root.sync_api = sync_api
    monkeypatch.setitem(sys.modules, "playwright", root)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)
    return browser


def _http_fallback(monkeypatch, values: dict[str, tuple[str, str]], calls: list[list[str]]):
    def fake_fetch_many(urls: list[str], max_workers: int = 8):
        assert max_workers == 8
        calls.append(urls)
        return {url: values[url] for url in urls if url in values}

    monkeypatch.setattr(content_fetch, "fetch_many", fake_fetch_many)


def test_spa_render_returns_dom_text_and_full_page_screenshot(monkeypatch, tmp_path):
    url = "https://example.com/app/settings"
    monkeypatch.setattr(settings, "assets_dir", tmp_path)
    browser = _install_fake_playwright(
        monkeypatch,
        [{
            "title": "Workspace settings",
            "text": "Rendered after JavaScript: members roles permissions save changes",
            "png_bytes": 40_000,
            "networkidle_error": True,
        }],
    )
    calls: list[list[str]] = []
    _http_fallback(monkeypatch, {}, calls)

    result = fetch_candidate_pages([url], render_limit=2)

    assert result[url].title == "Workspace settings"
    assert "Rendered after JavaScript" in result[url].text_content
    assert result[url].image_path is not None
    assert Path(result[url].image_path).is_file()
    assert calls == [[]]

    page = browser.pages[0]
    assert page.viewport == {"width": 1440, "height": 900}
    assert page.default_timeout == 5_000
    assert page.navigation_timeout == 25_000
    assert page.goto_kwargs == {"wait_until": "domcontentloaded", "timeout": 25_000}
    assert page.load_state == "networkidle"
    assert page.load_state_timeout == 3_000
    assert page.fallback_wait == 3_000
    assert page.full_page is True
    assert page.closed is True
    assert browser.launch_timeout == 15_000
    assert browser.closed is True


def test_near_blank_render_falls_back_to_http_candidate(monkeypatch, tmp_path):
    url = "https://example.com/blank-shell"
    monkeypatch.setattr(settings, "assets_dir", tmp_path)
    _install_fake_playwright(monkeypatch, [{"png_bytes": 4_000}])
    calls: list[list[str]] = []
    _http_fallback(
        monkeypatch,
        {url: ("HTTP title", "HTTP extracted body remains available to scoring")},
        calls,
    )

    result = fetch_candidate_pages([url], render_limit=1)

    assert result[url] == FetchedPage(
        title="HTTP title",
        text_content="HTTP extracted body remains available to scoring",
    )
    assert calls == [[url]]
    assert list((tmp_path / "candidate_pages").glob("*.png")) == []


def test_page_error_falls_back_without_losing_candidate_and_closes_resources(
    monkeypatch, tmp_path
):
    url = "https://example.com/navigation-error"
    monkeypatch.setattr(settings, "assets_dir", tmp_path)
    browser = _install_fake_playwright(
        monkeypatch, [{"goto_error": RuntimeError("navigation failed")}]
    )
    calls: list[list[str]] = []
    _http_fallback(monkeypatch, {url: ("Fallback", "Fallback body")}, calls)

    result = fetch_candidate_pages([url], render_limit=1)

    assert result[url].text_content == "Fallback body"
    assert result[url].image_path is None
    assert calls == [[url]]
    assert browser.pages[0].closed is True
    assert browser.closed is True


def test_non_html_response_falls_back_before_screenshot(monkeypatch, tmp_path):
    url = "https://example.com/manual.pdf"
    monkeypatch.setattr(settings, "assets_dir", tmp_path)
    browser = _install_fake_playwright(
        monkeypatch, [{"content_type": "application/pdf"}]
    )
    calls: list[list[str]] = []
    _http_fallback(monkeypatch, {url: ("Manual", "Extracted manual text")}, calls)

    result = fetch_candidate_pages([url], render_limit=1)

    assert result[url].title == "Manual"
    assert result[url].image_path is None
    assert browser.pages[0].full_page is None
    assert calls == [[url]]


def test_soft_time_limit_is_not_swallowed(monkeypatch, tmp_path):
    url = "https://example.com/slow"
    monkeypatch.setattr(settings, "assets_dir", tmp_path)
    browser = _install_fake_playwright(
        monkeypatch, [{"goto_error": SoftTimeLimitExceeded()}]
    )
    calls: list[list[str]] = []
    _http_fallback(monkeypatch, {url: ("unused", "unused")}, calls)

    with pytest.raises(SoftTimeLimitExceeded):
        fetch_candidate_pages([url], render_limit=1)

    assert calls == []
    assert browser.pages[0].closed is True
    assert browser.closed is True


def test_render_limit_deduplicates_urls_and_uses_unique_paths(monkeypatch, tmp_path):
    first = "https://example.com/first"
    second = "https://example.com/second"
    third = "https://example.com/third"
    monkeypatch.setattr(settings, "assets_dir", tmp_path)
    browser = _install_fake_playwright(monkeypatch, [{}, {}])
    calls: list[list[str]] = []
    _http_fallback(monkeypatch, {third: ("Third", "HTTP-only third body")}, calls)

    result = fetch_candidate_pages([first, first, second, third], render_limit=2)

    assert list(result) == [first, second, third]
    assert len(browser.pages) == 2
    assert calls == [[third]]
    assert result[first].image_path != result[second].image_path
    assert result[third].image_path is None


def test_shared_render_budget_caps_attempts_across_adapters():
    budget = RenderBudget(3)

    assert budget.reserve(2) == 2
    assert budget.reserve(2) == 1
    assert budget.reserve(2) == 0
    assert budget.remaining == 0


def test_adapters_dedupe_before_consuming_shared_render_budget(monkeypatch):
    monkeypatch.setattr(settings, "use_collection_mock", False)
    calls: list[tuple[list[str], int]] = []

    def fake_fetch(urls: list[str], *, render_limit: int):
        calls.append((urls, render_limit))
        return {}

    monkeypatch.setattr(web_source, "fetch_candidate_pages", fake_fetch)
    budget = RenderBudget(3)
    first = WebSourceAdapter(
        SourceType.COMMUNITY, render_limit=2, render_budget=budget
    )
    second = WebSourceAdapter(
        SourceType.GENERIC, render_limit=2, render_budget=budget
    )
    third = WebSourceAdapter(
        SourceType.GENERIC, render_limit=2, render_budget=budget
    )

    first.fetch(uuid4(), uuid4(), ["https://a", "https://a", "https://b"])
    second.fetch(uuid4(), uuid4(), ["https://c", "https://d"])
    third.fetch(uuid4(), uuid4(), ["https://e"])

    assert calls == [
        (["https://a", "https://b"], 2),
        (["https://c", "https://d"], 1),
        (["https://e"], 0),
    ]


def test_rendered_candidate_uses_existing_vision_relay_path(monkeypatch, tmp_path):
    url = "https://example.com/app/permissions"
    image_path = tmp_path / "rendered.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 30_000)
    rendered = FetchedPage(
        title="Permissions",
        text_content="Member roles permission matrix",
        image_path=str(image_path),
    )
    monkeypatch.setattr(settings, "use_collection_mock", False)
    monkeypatch.setattr(settings, "gpt_api_key", "fake-relay-key")
    monkeypatch.setattr(settings, "gpt_vision_model", "vision-test-model")
    monkeypatch.setattr(settings, "gpt_scorer_model", "text-test-model")
    monkeypatch.setattr(
        web_source,
        "fetch_candidate_pages",
        lambda _urls, *, render_limit: {url: rendered},
    )

    candidate = WebSourceAdapter(SourceType.GENERIC).fetch(
        uuid4(), uuid4(), [url], limit=1
    )[0]
    payloads: list[dict] = []

    def fake_urlopen(request, timeout: int):
        assert timeout == 60
        payloads.append(json.loads(request.data))
        response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "state_match": 0.9,
                        "product_match": 0.9,
                        "version_recency": 0.8,
                        "evidence_directness": 0.9,
                        "fidelity": 0.9,
                        "reasoning": "rendered UI",
                    })
                }
            }]
        }
        return io.BytesIO(json.dumps(response).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    score = RelevanceScorer().score(
        candidate,
        intent_definition="member role permission matrix",
    )

    assert candidate.text_content == rendered.text_content
    assert candidate.image_path == str(image_path)
    assert score.scored_by == "gpt:vision-test-model"
    assert payloads[0]["model"] == "vision-test-model"
    content = payloads[0]["messages"][0]["content"]
    assert isinstance(content, list)
    assert content[1]["type"] == "image_url"
