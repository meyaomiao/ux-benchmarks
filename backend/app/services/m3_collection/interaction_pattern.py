"""Abstract a scenario into an interaction-pattern phrase for non-direct competitors.

Direct competitors share our domain vocabulary, so a cell's raw scenario phrase
("风险高亮态 日常审查") is exactly the right thing to search for AND to score
against. Indirect and cross-industry competitors do not share it: Vercel has no
"contract risk", so a query carrying that noun finds nothing, and a rubric that
demands it rejects everything that IS found.

So for those competitor types we strip the industry nouns and keep only the
interaction STRUCTURE ("inline anomaly markers on a long scrollable document").
Both the query side and the scoring side read the SAME cached phrase, because
abstracting only the search would just turn empty results into passed=0 —
the rubric would still measure the artifact against the industry intent.

Best-effort by design: no GPT key, no CJK, or any failure returns "" and every
caller falls back to its existing non-abstracted behaviour.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from app.core.config import settings

logger = logging.getLogger(__name__)

# Competitor types whose evidence lives outside our domain vocabulary. `direct`
# is deliberately absent: abstracting a direct competitor would throw away the
# domain terms that make its evidence findable and checkable.
ABSTRACT_TYPES = frozenset({"indirect", "cross_industry"})

# Keep the abstraction short — it is used as a search phrase, and a long sentence
# turns into a zero-result query.
_MAX_WORDS = 12


def needs_abstraction(competitor_type: str | None) -> bool:
    """True for indirect / cross-industry competitors."""
    return (competitor_type or "").strip().lower() in ABSTRACT_TYPES


@lru_cache(maxsize=512)
def abstract_interaction_pattern(
    page_state: str,
    journey_stage: str,
    jtbd: str = "",
) -> str:
    """Render one cell as a domain-free English interaction-pattern phrase.

    Cached per (page_state, journey_stage, jtbd) so a probe's query building and
    its scoring cannot drift apart, and so a grid row costs one relay call.
    Returns "" when abstraction is unavailable — callers must treat that as
    "behave exactly as before".
    """
    seed = " ".join(t for t in (page_state, journey_stage) if t).strip()
    if not seed or not settings.gpt_api_key:
        return ""
    try:
        import json
        import urllib.request

        prompt = (
            "你在为跨行业竞品调研构造检索词。下面是某个行业产品的界面场景，"
            "请抽象成与行业无关的「交互结构」英文短语：\n"
            f"- 页面状态：{page_state}\n"
            f"- 旅程阶段：{journey_stage}\n"
            f"- 用户目标：{jtbd or '（未提供）'}\n\n"
            "要求：\n"
            "1. 去掉所有行业/领域名词（如合同、法律、条款、保单、病历）；\n"
            "2. 只保留界面与交互特征（如 inline annotations on a long document、"
            "side-by-side diff review、progress checklist before submit）；\n"
            f"3. 不超过 {_MAX_WORDS} 个英文单词；\n"
            "4. 只返回该英文短语，不要引号、不要解释、不要句号。"
        )
        body = json.dumps({
            "model": settings.gpt_scorer_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }).encode()
        req = urllib.request.Request(
            f"{settings.gpt_base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {settings.gpt_api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.load(resp)
        out = (payload["choices"][0]["message"]["content"] or "").strip().strip('"')
        # A relay that ignores the word budget would produce a query that matches
        # nothing, so clip rather than trust.
        return " ".join(out.split()[:_MAX_WORDS])
    except Exception as exc:  # never block a probe
        logger.warning(
            "interaction-pattern abstraction failed for %r/%r: %r",
            page_state, journey_stage, exc,
        )
        return ""


def abstracted_intent(pattern: str, original_intent: str) -> str:
    """The rubric context for an abstracted pair.

    The pattern LEADS so state_match is judged on interaction structure, and the
    original intent is kept as background only — without it the model has no idea
    what the operator was actually looking for.
    """
    return (
        f"{pattern}"
        "（跨行业/间接竞品：只判断交互结构是否匹配，"
        "不要求行业术语或业务领域一致"
        f"{f'；原始场景仅供背景参考：{original_intent}' if original_intent else ''}）"
    )
