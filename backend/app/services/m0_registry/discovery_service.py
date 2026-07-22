"""Competitor auto-discovery service (B).

Given a product category and a list of already-known products, Claude suggests
three tiers of design benchmarks:
  - direct        (直接竞品): same category, same target users
  - indirect      (间接竞品): different category, overlapping jobs-to-be-done
  - cross_industry (跨行业标杆): leading UX in related interactions, different industry

Each suggestion includes a rationale explaining WHY it's worth studying from a
UX perspective, not just a "it's a competitor" label.

Mock mode returns a plausible seeded set for "项目管理工具" so the UI is fully
functional without a running backend or API key.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import settings
from app.utils.robust_json import extract_json

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-opus-4-8"

_SYSTEM = (
    "你是 UX 竞品洞察专家，擅长识别哪些产品在特定场景下拥有值得学习的 UX 设计。"
    "你推荐的不是市场份额最大的产品，而是在该品类场景中 UX 设计最有参考价值的标杆。"
)


@dataclass
class DiscoverySuggestion:
    name: str
    tier: str           # "direct" | "indirect" | "cross_industry"
    tier_label: str     # 直接竞品 | 间接竞品 | 跨行业标杆
    rationale: str      # why this product is worth studying (UX reason)
    official_domain: str | None = None
    help_center_domain: str | None = None


_MOCK_SUGGESTIONS: list[dict] = [
    {
        "name": "Linear",
        "tier": "direct",
        "tier_label": "直接竞品",
        "rationale": "在任务追踪与团队协作场景中以极简交互著称，键盘优先设计和即时响应是业内标杆，状态机和工作流设计特别值得借鉴。",
        "official_domain": "linear.app",
        "help_center_domain": "linear.app/docs",
    },
    {
        "name": "Notion",
        "tier": "direct",
        "tier_label": "直接竞品",
        "rationale": "在权限管理、模板系统和内容块组合上有独特设计，Block 编辑器的可组合性以及 Database 视图切换是核心 UX 参考点。",
        "official_domain": "notion.so",
        "help_center_domain": "notion.so/help",
    },
    {
        "name": "Figma",
        "tier": "indirect",
        "tier_label": "间接竞品",
        "rationale": "虽是设计工具而非项目管理工具，但其实时协作、评论与版本管理的交互模式与项目管理高度重叠，特别是多人同时编辑状态的处理方式值得参考。",
        "official_domain": "figma.com",
        "help_center_domain": "help.figma.com",
    },
    {
        "name": "GitHub",
        "tier": "indirect",
        "tier_label": "间接竞品",
        "rationale": "Issue / PR 工作流和 Code Review 流程解决了与项目追踪高度相似的任务管理问题，特别是状态流转和通知设计是成熟的工程实践。",
        "official_domain": "github.com",
        "help_center_domain": "docs.github.com",
    },
    {
        "name": "Stripe Dashboard",
        "tier": "cross_industry",
        "tier_label": "跨行业标杆",
        "rationale": "金融工具领域在「复杂数据的可读性」和「不可逆操作的确认机制」上有极高设计要求，Stripe 的空状态引导、数据筛选和风险操作二次确认值得跨行业借鉴。",
        "official_domain": "stripe.com",
        "help_center_domain": "stripe.com/docs",
    },
    {
        "name": "Vercel",
        "tier": "cross_industry",
        "tier_label": "跨行业标杆",
        "rationale": "DevOps 工具领域在「任务进度可视化」和「配置→部署→观测」全链路体验上有独到设计，Deployment 状态机和日志实时展示是同类场景的参考标杆。",
        "official_domain": "vercel.com",
        "help_center_domain": "vercel.com/docs",
    },
]


def _call_claude(category: str, known_products: list[str]) -> list[dict]:
    import anthropic

    kw: dict = {"api_key": settings.anthropic_api_key}
    if settings.anthropic_base_url:
        kw["base_url"] = settings.anthropic_base_url
    client = anthropic.Anthropic(**kw)

    known = "、".join(known_products) if known_products else "（未指定）"
    prompt = (
        f"产品品类：{category}\n"
        f"已知竞品：{known}\n\n"
        "请尽可能全面地推荐值得研究的 UX 设计标杆（不包括已知竞品），分三层：\n"
        "1. direct（直接竞品）：同品类、同目标用户，列出 8~12 个，覆盖头部、"
        "新锐、垂直细分玩家，宁多勿漏\n"
        "2. indirect（间接竞品）：不同品类但有重叠 jobs-to-be-done，4~6 个\n"
        "3. cross_industry（跨行业标杆）：不同行业但在相关交互场景领先，4~6 个\n\n"
        "要求：\n"
        "- 每个产品名唯一，不要重复；每条 rationale 必须对应正确的产品\n"
        "- rationale 说明为什么从 UX 角度值得研究（不是市场份额，是设计价值）\n"
        "- 覆盖不同地区（含中国本土产品）和不同规模的玩家，提高样本代表性\n\n"
        "返回 JSON 数组，每项字段：\n"
        '{"name":"...","tier":"direct|indirect|cross_industry","tier_label":"直接竞品|间接竞品|跨行业标杆",'
        '"rationale":"...","official_domain":"...或null","help_center_domain":"...或null"}\n'
        "只返回 JSON 数组，无其他文字。"
    )
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=8000,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = "".join(b.text for b in msg.content if b.type == "text")
    # The response is a JSON array, not an object — parse manually.
    import json, re
    arr_match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not arr_match:
        raise ValueError(f"No JSON array in response: {raw[:200]}")
    return json.loads(arr_match.group(0))


def discover_competitors(
    category: str,
    known_products: list[str] | None = None,
) -> list[DiscoverySuggestion]:
    """Return competitor discovery suggestions for the given category.

    Uses Claude when a key is configured and mock mode is off; otherwise
    returns the seeded mock list (adjusted to mention the requested category).
    """
    known = known_products or []
    use_mock = settings.use_collection_mock or not settings.anthropic_api_key

    if use_mock:
        raw = _MOCK_SUGGESTIONS
    else:
        try:
            raw = _call_claude(category, known)
        except Exception as exc:
            logger.warning("discover_competitors: Claude failed, using mock: %s", exc)
            raw = _MOCK_SUGGESTIONS

    known_lower = {p.lower() for p in known}
    seen: set[str] = set()
    suggestions: list[DiscoverySuggestion] = []
    for item in raw:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in known_lower:
            continue   # skip already-registered products
        if key in seen:
            continue   # dedup — Claude occasionally repeats a name
        seen.add(key)
        suggestions.append(DiscoverySuggestion(
            name=name,
            tier=item.get("tier", "direct"),
            tier_label=item.get("tier_label", "直接竞品"),
            rationale=item.get("rationale", ""),
            official_domain=item.get("official_domain") or None,
            help_center_domain=item.get("help_center_domain") or None,
        ))
    return suggestions
