"""AI-powered mapping card draft generation (#35).

Given a grid cell's coordinates (jtbd × journey_stage × page_state), the model
drafts the three mapping-card fields so the user only fine-tunes instead of
writing from scratch:

  - intent_definition : one sentence, ≤150 chars, what the user wants here
  - inclusion_criteria: what a screenshot/doc must show to count as a hit
  - exclusion_criteria: what does NOT count (marketing/pricing/unrelated)

Falls back to a deterministic template when mock mode is on or the API key is
absent — never raises, always returns a usable draft.
"""
from __future__ import annotations

import logging

from app.core.config import settings
from app.utils import gpt_relay
from app.utils.robust_json import extract_json

logger = logging.getLogger(__name__)


_SYSTEM = (
    "你是 UX 竞品研究方法专家。给定一个场景网格格子（用户任务 × 旅程阶段 × "
    "页面/状态），你能写出精确的采集映射卡：定义采集意图、命中标准、排除标准，"
    "让后续的证据采集能准确判断'一张截图/一段文档是否命中这个场景'。"
)


def _mock_draft(jtbd: str, journey_stage: str, page_state: str) -> dict:
    return {
        "intent_definition": f"在「{journey_stage}」阶段完成「{jtbd}」时，用户在{page_state}的体验",
        "inclusion_criteria": f"展示 {page_state} 真实界面的截图或分步文档；能看到与「{jtbd}」相关的具体操作、控件或状态",
        "exclusion_criteria": "纯营销/定价页；与该场景无关的功能介绍；只提到功能名但不展示界面的内容",
    }


def _call_llm(jtbd: str, journey_stage: str, page_state: str) -> dict:
    prompt = (
        f"场景格子坐标：\n"
        f"- 用户任务(JTBD)：{jtbd}\n"
        f"- 旅程阶段：{journey_stage}\n"
        f"- 页面/状态：{page_state}\n\n"
        "请为这个格子生成采集映射卡草稿：\n"
        "- intent_definition：一句话（≤150字），描述用户在这个场景里想完成什么、"
        "关注什么体验\n"
        "- inclusion_criteria：什么样的截图/文档算命中？描述必须能看到的界面元素、"
        "操作步骤或状态\n"
        "- exclusion_criteria：什么不算命中？（如纯营销文案、定价页、只提功能名不展示界面）\n\n"
        "返回纯 JSON（无代码块）：\n"
        '{"intent_definition":"...","inclusion_criteria":"...","exclusion_criteria":"..."}'
    )
    raw = gpt_relay.chat(system=_SYSTEM, prompt=prompt, max_tokens=1024)
    return extract_json(raw)


def generate_card_draft(jtbd: str, journey_stage: str, page_state: str) -> dict:
    """Return a mapping-card draft dict for the given cell coordinates.

    Keys: intent_definition, inclusion_criteria, exclusion_criteria.
    Uses the GPT relay when available; otherwise a deterministic template.
    """
    use_mock = settings.use_collection_mock or not gpt_relay.relay_available()
    if use_mock:
        return _mock_draft(jtbd, journey_stage, page_state)
    try:
        draft = _call_llm(jtbd, journey_stage, page_state)
        # Enforce the intent length cap the schema requires.
        intent = str(draft.get("intent_definition", ""))[:150]
        return {
            "intent_definition": intent,
            "inclusion_criteria": draft.get("inclusion_criteria", ""),
            "exclusion_criteria": draft.get("exclusion_criteria", ""),
        }
    except Exception as exc:
        logger.warning("Mapping card draft generation failed, using mock: %s", exc)
        return _mock_draft(jtbd, journey_stage, page_state)
