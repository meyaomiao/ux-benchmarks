"""Bounded AI-guided exploration of a competitor's trusted web properties."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import socket
import time
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit
from uuid import uuid4

from billiard.exceptions import SoftTimeLimitExceeded

from app.core.config import settings
from app.services.m3_collection.adapters.interactive_demo import (
    _BROWSER_LAUNCH_TIMEOUT_MS,
    _MIN_USEFUL_PNG_BYTES,
    _RESCORE_VIEWPORT,
    _close_playwright_resource,
    _configure_page_timeouts,
    _dismiss_consent,
    _wait_for_page_settle,
)
from app.services.m3_collection.content_fetch import _rendered_main_text
from app.utils import gpt_relay

logger = logging.getLogger(__name__)

# One exploration is deliberately small. The total-time guard is authoritative;
# the other caps keep a fast site from consuming an unbounded number of actions.
MAX_STEPS = 9
MAX_PAGES = 7
MAX_CANDIDATES = 4
MAX_LINKS = 24
MAX_LINKS_SCANNED = MAX_LINKS * 4
MAX_NO_PROGRESS = 2
MAX_TOTAL_SECONDS = 150
ACTION_TIMEOUT_SECONDS = 20
NAVIGATION_TIMEOUT_MS = 20_000

_SEARCH_SELECTOR = (
    "input[type='search'], form[role='search'] input, "
    "input[aria-label*='search' i], input[placeholder*='search' i]"
)


def _is_general_web_search(url_host: str, path: str) -> bool:
    """Reject Google/Bing web SERPs while preserving product help search pages."""
    normalized_path = path.rstrip("/").lower()
    if normalized_path != "/search":
        return False
    is_google_web = url_host.startswith("google.") or ".google." in url_host
    is_bing_web = url_host.startswith("bing.") or ".bing." in url_host
    return is_google_web or is_bing_web


def _looks_like_noncanonical_ip(host: str) -> bool:
    """Reject legacy numeric hosts whose browser and DNS meanings can differ."""
    labels = host.split(".")
    return bool(labels) and all(
        label.isdigit()
        or (
            label.lower().startswith("0x")
            and len(label) > 2
            and all(char in "0123456789abcdef" for char in label[2:].lower())
        )
        for label in labels
    )


@dataclass(frozen=True)
class LinkOption:
    link_id: str
    url: str
    text: str


@dataclass(frozen=True)
class ExplorerAction:
    action: str
    link_id: str | None = None
    query: str | None = None


@dataclass(frozen=True)
class PageObservation:
    url: str
    title: str
    text_content: str
    links: tuple[LinkOption, ...]
    search_available: bool


@dataclass(frozen=True)
class ExploredPage:
    source_url: str
    title: str
    text_content: str
    image_path: str


@dataclass
class ExplorerStats:
    steps: int = 0
    pages_opened: int = 0
    candidates_saved: int = 0
    model_calls: int = 0
    page_failures: int = 0
    links_considered: int = 0
    stop_reason: str = "not_started"
    duration_ms: int = 0

    def to_dict(self) -> dict[str, int | str]:
        return asdict(self)


@dataclass(frozen=True)
class ExplorerResult:
    pages: tuple[ExploredPage, ...]
    stats: ExplorerStats
    trace: tuple[dict, ...] = ()


def canonical_url(url: str) -> str:
    """Normalize a URL for loop detection and cross-adapter deduplication."""
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").rstrip(".").lower()
    if not scheme or not host:
        return url.strip()
    try:
        port = parsed.port
    except ValueError:
        return url.strip()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def _seed_from_value(value: str | None) -> tuple[str, str] | None:
    raw = (value or "").strip()
    if not raw:
        return None
    candidate = raw if "://" in raw else f"https://{raw}"
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    if parsed.username or parsed.password or not parsed.hostname:
        return None
    if port not in {None, 80, 443}:
        return None
    try:
        host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None
    netloc = f"[{host}]" if ":" in host else host
    if port:
        netloc = f"{netloc}:{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", "", "")), host


def build_trusted_seeds(
    official_domain: str | None,
    help_center_domain: str | None,
) -> tuple[list[str], set[str]]:
    """Build ordered help/official seed URLs and their exact domain scope."""
    seeds: list[str] = []
    domains: set[str] = set()
    for value in (help_center_domain, official_domain):
        parsed = _seed_from_value(value)
        if parsed is None:
            continue
        seed, host = parsed
        if canonical_url(seed) not in {canonical_url(item) for item in seeds}:
            seeds.append(seed)
        domains.add(host)
    return seeds, domains


class UrlGuard:
    """Validate trusted navigations and reject non-public network targets."""

    def __init__(
        self,
        allowed_domains: Iterable[str],
        *,
        resolver: Callable[..., list] = socket.getaddrinfo,
    ) -> None:
        self.allowed_domains = {
            domain.rstrip(".").encode("idna").decode("ascii").lower()
            for domain in allowed_domains
            if domain
        }
        self._resolver = resolver

    def assert_navigation(self, url: str) -> None:
        self._assert_url(url, require_trusted_domain=True)

    def assert_public_resource(self, url: str) -> None:
        self._assert_url(url, require_trusted_domain=False)

    def is_navigation_allowed(self, url: str) -> bool:
        try:
            self.assert_navigation(url)
            return True
        except ValueError:
            return False

    def _assert_url(self, url: str, *, require_trusted_domain: bool) -> None:
        try:
            parsed = urlsplit(url)
            port = parsed.port
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid URL") from exc
        if parsed.scheme.lower() not in {"http", "https"}:
            raise ValueError("only http(s) URLs are allowed")
        if parsed.username or parsed.password or not parsed.hostname:
            raise ValueError("URL credentials and missing hosts are forbidden")
        if port not in {None, 80, 443}:
            raise ValueError("only standard HTTP(S) ports are allowed")
        try:
            host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ValueError("invalid hostname") from exc
        if _is_general_web_search(host, parsed.path):
            raise ValueError("general web search result pages are forbidden")
        if require_trusted_domain and not any(
            host == domain or host.endswith(f".{domain}") for domain in self.allowed_domains
        ):
            raise ValueError("navigation left the trusted competitor domains")
        self._assert_public_host(host, port or (443 if parsed.scheme == "https" else 80))

    def _assert_public_host(self, host: str, port: int) -> None:
        allowed = False
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            if host == "localhost" or host.endswith(".localhost") or "." not in host:
                raise ValueError("local hostnames are forbidden")
            if _looks_like_noncanonical_ip(host):
                raise ValueError("non-canonical IP literals are forbidden")
            try:
                answers = self._resolver(host, port, type=socket.SOCK_STREAM)
            except OSError as exc:
                raise ValueError("hostname did not resolve") from exc
            addresses = {answer[4][0] for answer in answers if len(answer) >= 5 and answer[4]}
            if addresses:
                try:
                    allowed = all(ipaddress.ip_address(address).is_global for address in addresses)
                except ValueError:
                    allowed = False
        else:
            allowed = literal.is_global

        if not allowed:
            raise ValueError("host resolves to a non-public address")


def parse_action(
    raw: str,
    *,
    valid_link_ids: set[str],
    search_available: bool,
) -> ExplorerAction:
    """Parse the exact action schema; extra fields (especially URLs) fail closed."""
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("model action is not valid JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("action"), str):
        raise ValueError("model action must be a JSON object")

    action = data["action"]
    if action == "open_link":
        if set(data) != {"action", "link_id"}:
            raise ValueError("open_link only accepts link_id")
        link_id = data.get("link_id")
        if not isinstance(link_id, str) or link_id not in valid_link_ids:
            raise ValueError("unknown link id")
        return ExplorerAction(action=action, link_id=link_id)
    if action == "search":
        if set(data) != {"action", "query"} or not search_available:
            raise ValueError("site search is unavailable or malformed")
        query = data.get("query")
        if (
            not isinstance(query, str)
            or not query.strip()
            or len(query.strip()) > 120
            or "://" in query
            or query.lstrip().startswith("//")
            or "\x00" in query
        ):
            raise ValueError("invalid site-search query")
        return ExplorerAction(action=action, query=query.strip())
    if action in {"save", "stop"}:
        if set(data) != {"action"}:
            raise ValueError(f"{action} does not accept extra fields")
        return ExplorerAction(action=action)
    raise ValueError("unknown model action")


def _remaining_seconds(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def _route_request(route, guard: UrlGuard) -> None:
    request = route.request
    try:
        if request.is_navigation_request():
            guard.assert_navigation(request.url)
        else:
            guard.assert_public_resource(request.url)
    except ValueError:
        route.abort()
        return
    route.continue_()


def _block_web_socket(route) -> None:
    """Keep the exploration context limited to HTTP(S) network traffic."""
    route.close(code=1008, reason="WebSockets are disabled")


def _extract_observation(page, guard: UrlGuard) -> PageObservation:
    current_url = page.url
    guard.assert_navigation(current_url)
    title = (page.title() or current_url).strip()[:200]
    text_content = _rendered_main_text(page) or title
    raw_links = page.evaluate(
        """limit => Array.from(document.querySelectorAll('a[href]'))
            .filter(a => a.getClientRects().length && a.getAttribute('aria-hidden') !== 'true')
            .slice(0, limit)
            .map(a => ({
                href: a.getAttribute('href') || '',
                text: (a.innerText || a.getAttribute('aria-label') || a.title || '').trim()
            }))""",
        MAX_LINKS_SCANNED,
    )
    links: list[LinkOption] = []
    seen: set[str] = set()
    for raw in raw_links or []:
        if len(links) >= MAX_LINKS or not isinstance(raw, dict):
            break
        target = urljoin(current_url, str(raw.get("href") or "").strip())
        normalized = canonical_url(target)
        if normalized in seen or not guard.is_navigation_allowed(target):
            continue
        seen.add(normalized)
        label = " ".join(str(raw.get("text") or "").split())[:160]
        links.append(LinkOption(f"L{len(links)}", target, label or target))
    search_available = page.locator(_SEARCH_SELECTOR).count() > 0
    return PageObservation(
        url=current_url,
        title=title,
        text_content=text_content,
        links=tuple(links),
        search_available=search_available,
    )


def _action_prompt(
    observation: PageObservation,
    *,
    competitor_name: str,
    intent: str,
    already_saved: bool,
    remaining_steps: int,
    remaining_pages: int,
    remaining_candidates: int,
    navigation_available: bool,
) -> str:
    links = (
        "\n".join(f"- {link.link_id}: {link.text} [{link.url}]" for link in observation.links)
        or "（无可用同域链接）"
    )
    if navigation_available:
        actions = (
            '{"action":"open_link","link_id":"L0"}，或 '
            '{"action":"search","query":"站内检索词"}，或 '
            '{"action":"save"}，或 {"action":"stop"}。'
        )
        navigation_rule = ""
    else:
        actions = '{"action":"save"}，或 {"action":"stop"}。'
        navigation_rule = (
            "页面导航预算已耗尽，本次只能 save 或 stop。"
            if remaining_pages <= 0
            else "动作预算只剩本次，不能再导航，本次只能 save 或 stop。"
        )
    return (
        f"目标竞品：{competitor_name}\n"
        f"目标交互状态：{intent}\n"
        f"当前页：{observation.title}\nURL：{observation.url}\n"
        f"当前页已保存：{'是' if already_saved else '否'}\n"
        f"剩余动作次数（含本次）：{remaining_steps}\n"
        f"可再打开页面数：{remaining_pages}\n"
        f"可再保存候选数：{remaining_candidates}\n"
        f"正文摘要：{observation.text_content[:2600]}\n"
        f"站内搜索可用：{'是' if observation.search_available else '否'}\n"
        f"候选链接：\n{links}\n\n"
        f"只返回一个严格 JSON 动作，不要 Markdown：{actions}"
        "只能选择上面的 link_id；不得输出 URL。"
        "只有页面真实展示目标状态时才 save；save 只保存当前页，不会结束探索。"
        "如果当前页已经展示目标状态，必须在离开前先 save，不要把保存推迟到最后。"
        f"{navigation_rule}"
    )


def _request_action(
    prompt: str,
    *,
    timeout: int,
    decision_fn: Callable[[str], str] | None,
) -> str:
    if decision_fn is not None:
        return decision_fn(prompt)
    return gpt_relay.chat(
        "你是受限的竞品站内浏览器控制器。严格遵守动作 JSON schema。",
        prompt,
        max_tokens=160,
        timeout=timeout,
        model=settings.gpt_vision_model,
    )


def _save_page(observation: PageObservation, page) -> ExploredPage | None:
    shot_dir = Path(settings.assets_dir) / "agentic_site"
    shot_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(observation.url.encode()).hexdigest()[:12]
    image_path = shot_dir / f"{digest}_{uuid4().hex[:12]}.png"
    try:
        page.screenshot(path=str(image_path), full_page=True)
        if image_path.stat().st_size < _MIN_USEFUL_PNG_BYTES:
            image_path.unlink(missing_ok=True)
            return None
    except SoftTimeLimitExceeded:
        image_path.unlink(missing_ok=True)
        raise
    except Exception:  # noqa: BLE001 - an unusable screenshot is not evidence
        image_path.unlink(missing_ok=True)
        return None
    return ExploredPage(
        source_url=observation.url,
        title=observation.title,
        text_content=observation.text_content,
        image_path=str(image_path),
    )


def explore_competitor_site(
    *,
    competitor_name: str,
    intent: str,
    official_domain: str | None,
    help_center_domain: str | None,
    decision_fn: Callable[[str], str] | None = None,
) -> ExplorerResult:
    """Explore trusted competitor pages in Chromium and return saved evidence."""
    started = time.monotonic()
    deadline = started + MAX_TOTAL_SECONDS
    stats = ExplorerStats()
    saved_pages: list[ExploredPage] = []
    trace: list[dict] = []
    seeds, allowed_domains = build_trusted_seeds(official_domain, help_center_domain)
    if not seeds:
        stats.stop_reason = "no_trusted_seeds"
        stats.duration_ms = int((time.monotonic() - started) * 1000)
        return ExplorerResult((), stats, ())
    if decision_fn is None and not gpt_relay.relay_available():
        stats.stop_reason = "model_unavailable"
        stats.duration_ms = int((time.monotonic() - started) * 1000)
        return ExplorerResult((), stats, ())

    guard = UrlGuard(allowed_domains)
    pending_seeds = deque(seeds)
    visited: set[str] = set()
    saved_urls: set[str] = set()
    last_fingerprint = ""
    no_progress = 0
    target_url = pending_seeds.popleft()
    loaded = False

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = None
            context = None
            page = None
            try:
                browser = pw.chromium.launch(headless=True, timeout=_BROWSER_LAUNCH_TIMEOUT_MS)
                context = browser.new_context(
                    viewport=_RESCORE_VIEWPORT,
                    service_workers="block",
                    accept_downloads=False,
                )
                context.route("**/*", lambda route: _route_request(route, guard))
                context.route_web_socket("**/*", _block_web_socket)
                page = context.new_page()
                _configure_page_timeouts(page)
                page.on("popup", lambda popup: _close_playwright_resource(popup, "popup"))

                while stats.steps < MAX_STEPS:
                    if _remaining_seconds(deadline) <= 0:
                        stats.stop_reason = "total_timeout"
                        break

                    if not loaded:
                        if stats.pages_opened >= MAX_PAGES:
                            stats.stop_reason = "page_budget"
                            break
                        normalized_target = canonical_url(target_url)
                        if normalized_target in visited:
                            stats.stop_reason = "duplicate_url"
                            break
                        try:
                            guard.assert_navigation(target_url)
                            stats.pages_opened += 1
                            response = page.goto(
                                target_url,
                                wait_until="domcontentloaded",
                                timeout=max(
                                    1,
                                    min(
                                        NAVIGATION_TIMEOUT_MS,
                                        int(_remaining_seconds(deadline) * 1000),
                                    ),
                                ),
                            )
                            headers = getattr(response, "headers", {}) or {}
                            content_type = str(headers.get("content-type", "")).lower()
                            if content_type and "html" not in content_type:
                                raise ValueError("navigation returned non-HTML content")
                            guard.assert_navigation(page.url)
                            _dismiss_consent(page)
                            _wait_for_page_settle(page)
                            final_url = canonical_url(page.url)
                            if final_url in visited:
                                stats.stop_reason = "duplicate_url"
                                break
                            visited.add(final_url)
                            loaded = True
                        except SoftTimeLimitExceeded:
                            raise
                        except Exception as exc:  # noqa: BLE001 - try the other trusted seed
                            stats.page_failures += 1
                            trace.append(
                                {
                                    "event": "page_failure",
                                    "url": canonical_url(target_url),
                                    "error_type": type(exc).__name__,
                                }
                            )
                            logger.info("agentic navigation failed for %s: %s", target_url, exc)
                            loaded = False
                            if pending_seeds:
                                target_url = pending_seeds.popleft()
                                continue
                            stats.stop_reason = "page_failure"
                            break

                    try:
                        observation = _extract_observation(page, guard)
                    except SoftTimeLimitExceeded:
                        raise
                    except Exception as exc:  # noqa: BLE001
                        stats.page_failures += 1
                        trace.append(
                            {
                                "event": "page_failure",
                                "url": canonical_url(page.url),
                                "error_type": type(exc).__name__,
                            }
                        )
                        logger.info("agentic page extraction failed for %s: %s", page.url, exc)
                        stats.stop_reason = "page_failure"
                        break

                    stats.links_considered += len(observation.links)
                    fingerprint = hashlib.sha256(
                        (
                            observation.title
                            + observation.text_content[:1600]
                            + "".join(link.url for link in observation.links)
                        ).encode()
                    ).hexdigest()
                    if fingerprint == last_fingerprint:
                        no_progress += 1
                    else:
                        no_progress = 0
                        last_fingerprint = fingerprint
                    if no_progress >= MAX_NO_PROGRESS:
                        stats.stop_reason = "no_progress"
                        break

                    remaining_steps = MAX_STEPS - stats.steps
                    remaining_pages = MAX_PAGES - stats.pages_opened
                    navigation_available = remaining_pages > 0 and remaining_steps > 1
                    prompt = _action_prompt(
                        observation,
                        competitor_name=competitor_name,
                        intent=intent,
                        already_saved=canonical_url(observation.url) in saved_urls,
                        remaining_steps=remaining_steps,
                        remaining_pages=remaining_pages,
                        remaining_candidates=MAX_CANDIDATES - len(saved_pages),
                        navigation_available=navigation_available,
                    )
                    stats.steps += 1
                    stats.model_calls += 1
                    try:
                        raw_action = _request_action(
                            prompt,
                            timeout=max(
                                1, min(ACTION_TIMEOUT_SECONDS, int(_remaining_seconds(deadline)))
                            ),
                            decision_fn=decision_fn,
                        )
                        action = parse_action(
                            raw_action,
                            valid_link_ids=(
                                {link.link_id for link in observation.links}
                                if navigation_available
                                else set()
                            ),
                            search_available=(
                                observation.search_available and navigation_available
                            ),
                        )
                    except SoftTimeLimitExceeded:
                        raise
                    except ValueError as exc:
                        trace.append(
                            {
                                "step": stats.steps,
                                "page_url": canonical_url(observation.url),
                                "action": "invalid",
                                "error_type": type(exc).__name__,
                            }
                        )
                        logger.info("agentic model action rejected: %s", exc)
                        stats.stop_reason = "model_invalid"
                        break
                    except Exception as exc:  # noqa: BLE001
                        trace.append(
                            {
                                "step": stats.steps,
                                "page_url": canonical_url(observation.url),
                                "action": "model_failure",
                                "error_type": type(exc).__name__,
                            }
                        )
                        logger.info("agentic model call failed: %s", exc)
                        stats.stop_reason = "model_failure"
                        break

                    if action.action == "stop":
                        trace.append(
                            {
                                "step": stats.steps,
                                "page_url": canonical_url(observation.url),
                                "action": "stop",
                            }
                        )
                        stats.stop_reason = "model_stop"
                        break
                    if action.action == "open_link":
                        selected = next(
                            link for link in observation.links if link.link_id == action.link_id
                        )
                        if canonical_url(selected.url) in visited:
                            stats.stop_reason = "duplicate_url"
                            break
                        trace.append(
                            {
                                "step": stats.steps,
                                "page_url": canonical_url(observation.url),
                                "action": "open_link",
                                "target_url": canonical_url(selected.url),
                                "link_text": selected.text,
                            }
                        )
                        target_url = selected.url
                        loaded = False
                        continue
                    if action.action == "search":
                        if stats.pages_opened >= MAX_PAGES:
                            stats.stop_reason = "page_budget"
                            break
                        try:
                            trace.append(
                                {
                                    "step": stats.steps,
                                    "page_url": canonical_url(observation.url),
                                    "action": "search",
                                    "query": action.query,
                                }
                            )
                            stats.pages_opened += 1
                            search_box = page.locator(_SEARCH_SELECTOR).first
                            search_box.fill(action.query)
                            search_box.press("Enter")
                            page.wait_for_load_state(
                                "domcontentloaded",
                                timeout=max(
                                    1, min(5_000, int(_remaining_seconds(deadline) * 1000))
                                ),
                            )
                            _wait_for_page_settle(page)
                            guard.assert_navigation(page.url)
                            final_url = canonical_url(page.url)
                            current_url = canonical_url(observation.url)
                            if final_url in visited and final_url != current_url:
                                stats.stop_reason = "duplicate_url"
                                break
                            if final_url not in visited:
                                visited.add(final_url)
                            loaded = True
                            continue
                        except SoftTimeLimitExceeded:
                            raise
                        except Exception as exc:  # noqa: BLE001
                            stats.page_failures += 1
                            logger.info("agentic site search failed: %s", exc)
                            stats.stop_reason = "page_failure"
                            break

                    current = canonical_url(observation.url)
                    if current in saved_urls:
                        no_progress += 1
                        continue
                    captured = _save_page(observation, page)
                    trace.append(
                        {
                            "step": stats.steps,
                            "page_url": current,
                            "action": "save",
                            "saved": captured is not None,
                        }
                    )
                    if captured is None:
                        no_progress += 1
                        if no_progress >= MAX_NO_PROGRESS:
                            stats.stop_reason = "no_progress"
                            break
                        continue
                    saved_pages.append(captured)
                    saved_urls.add(current)
                    stats.candidates_saved = len(saved_pages)
                    if len(saved_pages) >= MAX_CANDIDATES:
                        stats.stop_reason = "candidate_budget"
                        break
                else:
                    stats.stop_reason = "step_budget"
            finally:
                try:
                    if page is not None:
                        _close_playwright_resource(page, "agentic page")
                finally:
                    try:
                        if context is not None:
                            _close_playwright_resource(context, "agentic context")
                    finally:
                        if browser is not None:
                            _close_playwright_resource(browser, "agentic browser")
    except SoftTimeLimitExceeded as exc:
        stats.stop_reason = "soft_time_limit"
        stats.duration_ms = int((time.monotonic() - started) * 1000)
        setattr(exc, "agentic_stats", stats.to_dict())
        setattr(exc, "agentic_trace", tuple(trace))
        raise
    except ImportError:
        stats.stop_reason = "playwright_unavailable"
    except Exception as exc:  # noqa: BLE001 - agentic channel degrades independently
        logger.warning("agentic browser failed: %s", exc)
        stats.stop_reason = "browser_failure"
    finally:
        stats.duration_ms = int((time.monotonic() - started) * 1000)

    return ExplorerResult(tuple(saved_pages), stats, tuple(trace))
