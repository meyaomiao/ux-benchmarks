"""Offline tests for bounded, trusted-site agentic exploration."""

from __future__ import annotations

import socket
import sys
import types
from itertools import count
from pathlib import Path

import pytest
from billiard.exceptions import SoftTimeLimitExceeded

from app.core.config import settings
from app.services.m3_collection import agentic_site
from app.services.m3_collection.agentic_site import (
    MAX_CANDIDATES,
    MAX_PAGES,
    MAX_STEPS,
    MAX_TOTAL_SECONDS,
    UrlGuard,
    build_trusted_seeds,
    explore_competitor_site,
    parse_action,
)


def _resolver(addresses: list[str]):
    def resolve(_host, port, *, type):
        assert type == socket.SOCK_STREAM
        return [
            (socket.AF_INET6 if ":" in address else socket.AF_INET, type, 6, "", (address, port))
            for address in addresses
        ]

    return resolve


def test_builds_help_and_official_seeds_without_duplicates():
    seeds, domains = build_trusted_seeds(
        "https://www.example.com/product?ignored=1#fragment",
        "help.example.com/docs",
    )

    assert seeds == [
        "https://help.example.com/docs",
        "https://www.example.com/product",
    ]
    assert domains == {"help.example.com", "www.example.com"}


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/",
        "https://docs.example.com/article",
        "https://help.vendor.test/search?q=roles",
    ],
)
def test_url_guard_allows_trusted_domains_and_subdomains(url):
    guard = UrlGuard(
        {"example.com", "help.vendor.test"},
        resolver=_resolver(["93.184.216.34"]),
    )

    guard.assert_navigation(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com.evil.test/",
        "https://evil-example.com/",
        "http://localhost/admin",
        "http://127.0.0.1/",
        "http://10.0.0.8/",
        "http://169.254.169.254/latest/meta-data/",
        "file:///etc/passwd",
        "data:text/html,pwned",
        "javascript:alert(1)",
        "https://user:pass@example.com/",
        "https://example.com:8443/",
    ],
)
def test_url_guard_rejects_untrusted_or_non_public_targets(url):
    guard = UrlGuard({"example.com"}, resolver=_resolver(["93.184.216.34"]))

    with pytest.raises(ValueError):
        guard.assert_navigation(url)


def test_url_guard_rejects_private_or_mixed_dns_answers():
    for addresses in (["10.1.2.3"], ["93.184.216.34", "192.168.1.5"]):
        guard = UrlGuard({"example.com"}, resolver=_resolver(addresses))
        with pytest.raises(ValueError):
            guard.assert_navigation("https://example.com")


@pytest.mark.parametrize(
    "host",
    ["0177.0.0.1", "127.1", "0x7f.0.0.1", "0300.0250.0001.0001"],
)
def test_url_guard_rejects_noncanonical_numeric_ip_hosts_before_dns(host):
    guard = UrlGuard({host}, resolver=_resolver(["93.184.216.34"]))

    with pytest.raises(ValueError, match="non-canonical"):
        guard.assert_navigation(f"https://{host}/")


def test_url_guard_resolves_again_before_each_request():
    answers = iter((["93.184.216.34"], ["10.1.2.3"]))
    guard = UrlGuard(
        {"example.com"},
        resolver=lambda *_args, **_kwargs: _resolver(next(answers))(*_args, **_kwargs),
    )

    guard.assert_navigation("https://example.com")
    with pytest.raises(ValueError, match="non-public"):
        guard.assert_navigation("https://example.com")


@pytest.mark.parametrize(
    "url",
    [
        "https://www.google.com/search?q=permissions",
        "https://google.co.uk/search?q=permissions",
        "https://www.google.co.uk/search?q=permissions",
        "https://bing.co.uk/search?q=permissions",
        "https://www.bing.com/search?q=permissions",
    ],
)
def test_url_guard_rejects_google_and_bing_web_result_pages(url):
    host = url.split("/", 3)[2]
    guard = UrlGuard({host}, resolver=_resolver(["93.184.216.34"]))

    with pytest.raises(ValueError, match="web search"):
        guard.assert_navigation(url)


def test_parse_action_accepts_only_observed_capabilities():
    open_link = parse_action(
        '{"save_current":true,"action":"open_link","link_id":"L2"}',
        valid_link_ids={"L2"},
        search_available=False,
    )
    assert open_link.link_id == "L2"
    assert open_link.save_current is True

    search = parse_action(
        '{"save_current":false,"action":"search","query":"workspace permissions"}',
        valid_link_ids=set(),
        search_available=True,
    )
    assert search.query == "workspace permissions"
    assert search.save_current is False

    legacy_save = parse_action(
        '{"action":"save"}',
        valid_link_ids=set(),
        search_available=False,
    )
    assert legacy_save.action == "save"
    assert legacy_save.save_current is True

    legacy_stop = parse_action(
        '{"action":"stop"}',
        valid_link_ids=set(),
        search_available=False,
    )
    assert legacy_stop.action == "stop"
    assert legacy_stop.save_current is False


@pytest.mark.parametrize("value", ['"yes"', "1", "null", "{}"])
def test_parse_action_rejects_non_boolean_save_current(value):
    with pytest.raises(ValueError, match="save_current must be a boolean"):
        parse_action(
            f'{{"save_current":{value},"action":"stop"}}',
            valid_link_ids=set(),
            search_available=False,
        )


@pytest.mark.parametrize(
    "raw",
    [
        '{"action":"open_link","link_id":"L9"}',
        '{"action":"open_link","link_id":"L0","url":"https://evil.test"}',
        '{"action":"search","query":"https://evil.test"}',
        '{"action":"search","query":"roles"}',
        '{"action":"stop","url":"https://evil.test"}',
        '{"action":"navigate","url":"https://evil.test"}',
        "not-json",
    ],
)
def test_parse_action_rejects_bad_json_unknown_links_and_url_injection(raw):
    with pytest.raises(ValueError):
        parse_action(raw, valid_link_ids={"L0"}, search_available=False)


def test_model_action_uses_existing_gpt_relay_and_vision_model(monkeypatch):
    calls = []

    def chat(system, prompt, **kwargs):
        calls.append((system, prompt, kwargs))
        return '{"action":"stop"}'

    monkeypatch.setattr(agentic_site.gpt_relay, "chat", chat)

    result = agentic_site._request_action(
        "bounded browser prompt",
        timeout=9,
        decision_fn=None,
    )

    assert result == '{"action":"stop"}'
    assert calls == [
        (
            "你是受限的竞品站内浏览器控制器。严格遵守动作 JSON schema，"
            "每个动作都填写布尔 save_current。",
            "bounded browser prompt",
            {
                "max_tokens": 160,
                "timeout": 9,
                "model": settings.gpt_vision_model,
            },
        )
    ]


class _Response:
    headers = {"content-type": "text/html; charset=utf-8"}


class _SearchBox:
    def __init__(self, page):
        self.page = page
        self.filled = None

    @property
    def first(self):
        return self

    def count(self):
        return int(bool(self.page.spec.get("search_url")))

    def fill(self, value):
        self.filled = value

    def press(self, key):
        assert key == "Enter"
        search_url = self.page.spec["search_url"]
        search_spec = self.page.spec.get("search_spec")
        self.page.url = search_url
        self.page.spec = search_spec if search_spec is not None else self.page.specs[search_url]


class _Page:
    def __init__(self, specs):
        self.specs = specs
        self.spec = {}
        self.url = "about:blank"
        self.closed = False
        self.full_page = None
        self.search_box = _SearchBox(self)

    def set_default_timeout(self, _timeout):
        pass

    def set_default_navigation_timeout(self, _timeout):
        pass

    def on(self, _event, _callback):
        pass

    def goto(self, url, **_kwargs):
        self.url = url
        self.spec = self.specs.get(url, {})
        error = self.spec.get("goto_error")
        if error:
            raise error
        self.url = self.spec.get("redirect_url", self.url)
        return _Response()

    def query_selector(self, _selector):
        return None

    def wait_for_load_state(self, _state, timeout=None):
        del timeout

    def wait_for_timeout(self, _timeout):
        pass

    def title(self):
        return self.spec.get("title", self.url)

    def evaluate(self, script, arg=None):
        if "a[href]" in script:
            assert arg == agentic_site.MAX_LINKS_SCANNED
            return self.spec.get("links", [])[:arg]
        return self.spec.get("text", "Rendered product interface")

    def locator(self, _selector):
        return self.search_box

    def screenshot(self, path, *, full_page):
        error = self.spec.get("screenshot_error")
        if error:
            raise error
        self.full_page = full_page
        Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 30_000)

    def close(self):
        self.closed = True


class _Context:
    def __init__(self, page):
        self.page = page
        self.closed = False
        self.route_handler = None
        self.web_socket_handler = None

    def route(self, pattern, handler):
        assert pattern == "**/*"
        self.route_handler = handler

    def route_web_socket(self, pattern, handler):
        assert pattern == "**/*"
        self.web_socket_handler = handler

    def new_page(self):
        return self.page

    def close(self):
        self.closed = True


class _Browser:
    def __init__(self, specs):
        self.page = _Page(specs)
        self.context = _Context(self.page)
        self.closed = False
        self.context_kwargs = None

    def new_context(self, **kwargs):
        self.context_kwargs = kwargs
        return self.context

    def close(self):
        self.closed = True


def _install_browser(monkeypatch, specs):
    browser = _Browser(specs)

    class _Chromium:
        def launch(self, *, headless, timeout):
            assert headless is True
            assert timeout == 15_000
            return browser

    class _Playwright:
        chromium = _Chromium()

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.sync_playwright = lambda: _Playwright()
    root = types.ModuleType("playwright")
    root.sync_api = sync_api
    monkeypatch.setitem(sys.modules, "playwright", root)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)
    monkeypatch.setattr(UrlGuard, "_assert_public_host", lambda *_args: None)
    return browser


def _run(monkeypatch, tmp_path, specs, actions):
    monkeypatch.setattr(settings, "assets_dir", tmp_path)
    browser = _install_browser(monkeypatch, specs)
    prompts = []

    def decide(prompt):
        prompts.append(prompt)
        action = actions.pop(0)
        if isinstance(action, BaseException):
            raise action
        return action

    result = explore_competitor_site(
        competitor_name="Acme",
        intent="review workspace permissions",
        official_domain="example.com",
        help_center_domain=None,
        decision_fn=decide,
    )
    return result, browser, prompts


def test_observation_limits_and_deduplicates_trusted_links():
    raw_links = [
        {"href": "/same", "text": "Same"},
        {"href": "/same#details", "text": "Duplicate"},
        {"href": "https://evil.test/out", "text": "External"},
        *[
            {"href": f"/page-{index}", "text": f"Page {index}"}
            for index in range(agentic_site.MAX_LINKS + 5)
        ],
    ]
    page = _Page(
        {
            "https://example.com/": {
                "text": "Help home",
                "links": raw_links,
            }
        }
    )
    page.goto("https://example.com/")
    guard = UrlGuard({"example.com"}, resolver=_resolver(["93.184.216.34"]))

    observation = agentic_site._extract_observation(page, guard)

    assert len(observation.links) == agentic_site.MAX_LINKS
    assert [link.link_id for link in observation.links] == [
        f"L{index}" for index in range(agentic_site.MAX_LINKS)
    ]
    assert observation.links[0].url == "https://example.com/same"
    assert len({agentic_site.canonical_url(link.url) for link in observation.links}) == (
        agentic_site.MAX_LINKS
    )
    assert all("evil.test" not in link.url for link in observation.links)


def test_ai_opens_observed_link_then_saves_dom_and_full_page_image(monkeypatch, tmp_path):
    specs = {
        "https://example.com/": {
            "title": "Acme help",
            "text": "Help home",
            "links": [{"href": "/permissions", "text": "Permissions"}],
        },
        "https://example.com/permissions": {
            "title": "Permission review",
            "text": "Rendered roles table with permission toggles",
        },
    }

    result, browser, prompts = _run(
        monkeypatch,
        tmp_path,
        specs,
        [
            '{"save_current":false,"action":"open_link","link_id":"L0"}',
            '{"save_current":true,"action":"stop"}',
        ],
    )

    assert [page.source_url for page in result.pages] == ["https://example.com/permissions"]
    assert result.pages[0].text_content == "Rendered roles table with permission toggles"
    assert Path(result.pages[0].image_path).stat().st_size > 20_000
    assert browser.page.full_page is True
    assert "目标竞品：Acme" in prompts[0]
    assert "目标交互状态：review workspace permissions" in prompts[0]
    assert "L0: Permissions" in prompts[0]
    assert "save_current 与下一步动作不互斥" in prompts[0]
    assert f"剩余动作次数（含本次）：{MAX_STEPS}" in prompts[0]
    assert f"可再打开页面数：{MAX_PAGES - 1}" in prompts[0]
    assert f"可再保存候选数：{MAX_CANDIDATES}" in prompts[0]
    assert result.stats.stop_reason == "model_stop"
    assert browser.page.closed and browser.context.closed and browser.closed


def test_ai_saves_current_page_before_opening_next_link(monkeypatch, tmp_path):
    specs = {
        "https://example.com/": {
            "text": "Rendered permission review with highlighted changes",
            "links": [{"href": "/next", "text": "Next"}],
        },
        "https://example.com/next": {"text": "Next help page"},
    }

    result, browser, _ = _run(
        monkeypatch,
        tmp_path,
        specs,
        [
            '{"save_current":true,"action":"open_link","link_id":"L0"}',
            '{"save_current":false,"action":"stop"}',
        ],
    )

    assert [page.source_url for page in result.pages] == ["https://example.com/"]
    assert [entry["action"] for entry in result.trace] == ["save", "open_link", "stop"]
    assert result.trace[0]["page_url"] == result.trace[1]["page_url"]
    assert browser.page.url == "https://example.com/next"


def test_identified_site_search_can_reach_and_save_same_domain_result(monkeypatch, tmp_path):
    specs = {
        "https://example.com/": {
            "search_url": "https://example.com/search?q=roles",
            "text": "Help home",
        },
        "https://example.com/search?q=roles": {
            "title": "Search results",
            "text": "Roles and permission review results",
        },
    }

    result, browser, _ = _run(
        monkeypatch,
        tmp_path,
        specs,
        [
            '{"save_current":false,"action":"search","query":"roles"}',
            '{"save_current":true,"action":"stop"}',
        ],
    )

    assert result.pages[0].source_url == "https://example.com/search?q=roles"
    assert browser.page.search_box.filled == "roles"
    assert result.stats.pages_opened == 2


def test_same_url_ajax_site_search_can_make_progress(monkeypatch, tmp_path):
    specs = {
        "https://example.com/": {
            "search_url": "https://example.com/",
            "search_spec": {
                "title": "Search results",
                "text": "Roles and permission review results",
            },
            "text": "Help home",
        }
    }

    result, _, _ = _run(
        monkeypatch,
        tmp_path,
        specs,
        [
            '{"save_current":false,"action":"search","query":"roles"}',
            '{"save_current":true,"action":"stop"}',
        ],
    )

    assert [page.text_content for page in result.pages] == ["Roles and permission review results"]
    assert result.stats.stop_reason == "model_stop"


def test_external_redirect_is_rejected_before_model_action(monkeypatch, tmp_path):
    result, browser, prompts = _run(
        monkeypatch,
        tmp_path,
        {"https://example.com/": {"redirect_url": "https://evil.test/landing"}},
        [],
    )

    assert result.pages == ()
    assert result.stats.stop_reason == "page_failure"
    assert prompts == []
    assert browser.page.closed and browser.context.closed and browser.closed


def test_duplicate_url_stops_without_second_navigation(monkeypatch, tmp_path):
    specs = {
        "https://example.com/": {
            "links": [{"href": "#same-page", "text": "Current"}],
        }
    }
    result, _, _ = _run(
        monkeypatch,
        tmp_path,
        specs,
        ['{"action":"open_link","link_id":"L0"}'],
    )
    assert result.stats.stop_reason == "duplicate_url"
    assert result.stats.pages_opened == 1


def test_repeated_save_stops_for_no_progress(monkeypatch, tmp_path):
    result, _, _ = _run(
        monkeypatch,
        tmp_path,
        {"https://example.com/": {"text": "Same page"}},
        ['{"action":"save"}', '{"action":"save"}'],
    )
    assert result.stats.stop_reason == "no_progress"
    assert result.stats.candidates_saved == 1


@pytest.mark.parametrize(
    ("constant", "value", "actions", "expected"),
    [
        (
            "MAX_CANDIDATES",
            1,
            ['{"save_current":true,"action":"stop"}'],
            "candidate_budget",
        ),
    ],
)
def test_fixed_exploration_budgets(monkeypatch, tmp_path, constant, value, actions, expected):
    assert {"MAX_STEPS": MAX_STEPS, "MAX_CANDIDATES": MAX_CANDIDATES, "MAX_PAGES": MAX_PAGES}[
        constant
    ] > value
    monkeypatch.setattr(agentic_site, constant, value)
    specs = {
        "https://example.com/": {
            "links": [{"href": "/next", "text": "Next"}],
        },
        "https://example.com/next": {"text": "Next page"},
    }
    result, _, _ = _run(monkeypatch, tmp_path, specs, actions)
    assert result.stats.stop_reason == expected


def test_last_allowed_page_can_be_saved_but_cannot_navigate(monkeypatch, tmp_path):
    monkeypatch.setattr(agentic_site, "MAX_PAGES", 1)
    specs = {
        "https://example.com/": {
            "text": "Rendered review comparison with highlighted changes",
            "links": [{"href": "/next", "text": "Next"}],
            "search_url": "https://example.com/search?q=review",
        },
        "https://example.com/next": {"text": "Next page"},
    }

    result, browser, prompts = _run(
        monkeypatch,
        tmp_path,
        specs,
        ['{"save_current":true,"action":"stop"}'],
    )

    assert [page.source_url for page in result.pages] == ["https://example.com/"]
    assert result.stats.pages_opened == 1
    assert result.stats.stop_reason == "model_stop"
    assert len(prompts) == 1
    assert "可再打开页面数：0" in prompts[0]
    assert "页面导航预算已耗尽，本次 action 只能是 stop" in prompts[0]
    assert '{"action":"open_link"' not in prompts[0]
    assert '{"action":"search"' not in prompts[0]
    assert browser.page.url == "https://example.com/"


def test_last_action_can_save_current_page_and_stop(monkeypatch, tmp_path):
    monkeypatch.setattr(agentic_site, "MAX_STEPS", 1)

    result, _, prompts = _run(
        monkeypatch,
        tmp_path,
        {"https://example.com/": {"text": "Rendered review comparison"}},
        ['{"save_current":true,"action":"stop"}'],
    )

    assert [page.source_url for page in result.pages] == ["https://example.com/"]
    assert result.stats.stop_reason == "model_stop"
    assert "动作预算只剩本次，不能再导航，本次 action 只能是 stop" in prompts[0]


def test_last_allowed_page_rejects_model_navigation(monkeypatch, tmp_path):
    monkeypatch.setattr(agentic_site, "MAX_PAGES", 1)
    specs = {
        "https://example.com/": {
            "links": [{"href": "/next", "text": "Next"}],
        },
        "https://example.com/next": {"text": "Next page"},
    }

    result, browser, _ = _run(
        monkeypatch,
        tmp_path,
        specs,
        ['{"action":"open_link","link_id":"L0"}'],
    )

    assert result.pages == ()
    assert result.stats.pages_opened == 1
    assert result.stats.stop_reason == "model_invalid"
    assert browser.page.url == "https://example.com/"


def test_last_action_rejects_navigation_without_a_followup_save_step(monkeypatch, tmp_path):
    monkeypatch.setattr(agentic_site, "MAX_STEPS", 1)
    specs = {
        "https://example.com/": {
            "links": [{"href": "/next", "text": "Next"}],
        },
        "https://example.com/next": {"text": "Next page"},
    }

    result, browser, prompts = _run(
        monkeypatch,
        tmp_path,
        specs,
        ['{"action":"open_link","link_id":"L0"}'],
    )

    assert result.pages == ()
    assert result.stats.pages_opened == 1
    assert result.stats.stop_reason == "model_invalid"
    assert "动作预算只剩本次，不能再导航" in prompts[0]
    assert '{"action":"open_link"' not in prompts[0]
    assert browser.page.url == "https://example.com/"


def test_production_exploration_budget_is_explicitly_bounded():
    assert (MAX_STEPS, MAX_PAGES, MAX_CANDIDATES, MAX_TOTAL_SECONDS) == (9, 7, 4, 150)


def test_bad_model_output_and_model_failure_stop_cleanly(monkeypatch, tmp_path):
    invalid, browser, _ = _run(monkeypatch, tmp_path, {"https://example.com/": {}}, ["not-json"])
    assert invalid.stats.stop_reason == "model_invalid"
    assert browser.page.closed and browser.context.closed and browser.closed

    failed, _, _ = _run(
        monkeypatch,
        tmp_path,
        {"https://example.com/": {}},
        [RuntimeError("relay unavailable")],
    )
    assert failed.stats.stop_reason == "model_failure"


def test_page_and_screenshot_failures_degrade_to_empty(monkeypatch, tmp_path):
    page_failed, browser, _ = _run(
        monkeypatch,
        tmp_path,
        {"https://example.com/": {"goto_error": RuntimeError("blocked")}},
        [],
    )
    assert page_failed.pages == ()
    assert page_failed.stats.stop_reason == "page_failure"
    assert browser.page.closed and browser.context.closed and browser.closed

    shot_failed, _, _ = _run(
        monkeypatch,
        tmp_path,
        {"https://example.com/": {"screenshot_error": RuntimeError("disk full")}},
        ['{"action":"save"}'],
    )
    assert shot_failed.pages == ()
    assert shot_failed.stats.stop_reason == "no_progress"


def test_soft_time_limit_propagates_after_all_browser_resources_close(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "assets_dir", tmp_path)
    clock = count(start=100, step=1)
    monkeypatch.setattr(agentic_site.time, "monotonic", lambda: next(clock))
    browser = _install_browser(monkeypatch, {"https://example.com/": {}})

    with pytest.raises(SoftTimeLimitExceeded) as exc_info:
        explore_competitor_site(
            competitor_name="Acme",
            intent="permissions",
            official_domain="example.com",
            help_center_domain=None,
            decision_fn=lambda _prompt: (_ for _ in ()).throw(SoftTimeLimitExceeded()),
        )

    assert browser.page.closed and browser.context.closed and browser.closed
    assert exc_info.value.agentic_stats["pages_opened"] == 1
    assert exc_info.value.agentic_stats["model_calls"] == 1
    assert exc_info.value.agentic_stats["stop_reason"] == "soft_time_limit"
    assert exc_info.value.agentic_stats["duration_ms"] > 0
    assert exc_info.value.agentic_trace == ()


def test_expired_total_budget_stops_before_navigation(monkeypatch, tmp_path):
    monkeypatch.setattr(agentic_site, "_remaining_seconds", lambda _deadline: 0)
    result, browser, _ = _run(monkeypatch, tmp_path, {"https://example.com/": {}}, [])
    assert result.stats.stop_reason == "total_timeout"
    assert result.stats.pages_opened == 0
    assert browser.page.closed and browser.context.closed and browser.closed


class _Request:
    def __init__(self, url, *, navigation):
        self.url = url
        self._navigation = navigation

    def is_navigation_request(self):
        return self._navigation


class _Route:
    def __init__(self, url, *, navigation):
        self.request = _Request(url, navigation=navigation)
        self.aborted = False
        self.continued = False

    def abort(self):
        self.aborted = True

    def continue_(self):
        self.continued = True


class _WebSocketRoute:
    def __init__(self):
        self.closed = None

    def close(self, *, code=None, reason=None):
        self.closed = (code, reason)


def test_route_handler_blocks_external_navigation_and_private_resources():
    guard = UrlGuard({"example.com"}, resolver=_resolver(["93.184.216.34"]))
    external = _Route("https://evil.test/landing", navigation=True)
    private = _Route("http://169.254.169.254/latest/meta-data", navigation=False)
    public_asset = _Route("https://cdn.example.net/app.js", navigation=False)

    agentic_site._route_request(external, guard)
    agentic_site._route_request(private, guard)
    agentic_site._route_request(public_asset, guard)

    assert external.aborted and not external.continued
    assert private.aborted and not private.continued
    assert public_asset.continued and not public_asset.aborted


def test_browser_context_blocks_web_sockets(monkeypatch, tmp_path):
    _, browser, _ = _run(
        monkeypatch,
        tmp_path,
        {"https://example.com/": {}},
        ['{"action":"stop"}'],
    )
    route = _WebSocketRoute()

    browser.context.web_socket_handler(route)

    assert route.closed == (1008, "WebSockets are disabled")
