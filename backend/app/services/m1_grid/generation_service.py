"""AI-powered scene grid generation from a product category.

Calls the GPT relay to produce JTBD tasks, journey stages and key (page, state) cells.
Falls back to a deterministic mock when use_collection_mock=True or the API key
is empty — same fallback pattern as the relevance scorer.
"""
import json
import logging
import re

from app.core.config import settings
from app.schemas.m1 import GeneratedCell, GridGenerationRequest, GridGenerationResponse
from app.utils import gpt_relay
from app.utils.robust_json import extract_json

logger = logging.getLogger(__name__)


_SYSTEM = (
    "你是 UX 场景分析专家，专门分析产品品类的用户体验设计标杆。"
    "当给出一个产品品类或具体产品时，你能生成一个高质量的场景网格用于竞品 UX 研究。"
    "场景网格的原子单位是：用户任务(JTBD) × 旅程阶段 × 关键页面/状态。"
)

_MOCK = GridGenerationResponse(
    category="mock",
    jtbd_tasks=["邀请协作者+权限分级", "创建首个项目/工作区", "追踪任务进度", "设置通知与提醒"],
    journey_stages=["首次配置", "日常使用", "异常处理"],
    cells=[
        GeneratedCell(jtbd="邀请协作者+权限分级", journey_stage="首次配置", page_state="角色权限页", scenario_detail="邀请成员时选择角色并查看各角色权限对照", value_score=0.9),
        GeneratedCell(jtbd="邀请协作者+权限分级", journey_stage="首次配置", page_state="邀请成员页", scenario_detail="发起邀请、填写邮箱、分配角色的主流程页面", value_score=0.8),
        GeneratedCell(jtbd="创建首个项目/工作区", journey_stage="首次配置", page_state="空状态引导", scenario_detail="首次进入无项目时的空状态与引导创建", value_score=0.8),
        GeneratedCell(jtbd="追踪任务进度", journey_stage="日常使用", page_state="看板视图", scenario_detail="任务看板的列/卡片布局与拖拽交互", value_score=0.7),
        GeneratedCell(jtbd="追踪任务进度", journey_stage="日常使用", page_state="任务详情页", scenario_detail="单个任务的详情、字段、评论与状态流转", value_score=0.65),
        GeneratedCell(jtbd="设置通知与提醒", journey_stage="首次配置", page_state="通知设置页", scenario_detail="配置各类通知渠道与提醒规则的设置界面", value_score=0.6),
    ],
    total=6,
    generated_by="mock",
)


def _prompt(req: GridGenerationRequest) -> str:
    lang = "中文" if req.language == "zh" else "English"

    if req.known_products:
        # Grounded mode: derive JTBDs from what these products actually do,
        # and CONVERGE — don't emit one JTBD per feature.
        grounding = (
            f"参考产品：{', '.join(req.known_products)}\n"
            "基于这些产品的真实核心流程提炼 JTBD，聚焦它们在 UX 上有差异化、"
            "最值得研究的场景。不要为每个功能都生成一个 JTBD——要收敛到少数"
            "真正核心、且这些产品体验各有高下的任务。"
        )
    else:
        # Category-only mode: force grounding on real products to avoid
        # generic / hallucinated JTBDs. Make the model name concrete products
        # FIRST and derive JTBDs strictly from their real flows.
        grounding = (
            "只给了品类、没有具体产品。请严格按以下步骤，不要跳过：\n"
            "第一步：明确列出该品类里你最熟悉的 3-5 个真实主流产品（用真名）。\n"
            "第二步：只基于这些真实产品实际都有的核心流程来提炼 JTBD——每个 JTBD "
            "都必须能对应到上面某个真实产品里确实存在的功能，不能凭空臆测、"
            "不能是行业套话（如'提升效率''优化体验'），不能罗列边缘任务。\n"
            "第三步：只保留你高度确信是该品类核心、且主流产品体验各有高下的 JTBD，"
            "宁缺毋滥。\n"
            "把第一步想到的产品名一并放进返回 JSON 的 grounded_products 字段。"
        )

    return f"""分析产品品类：{req.category}

{grounding}

生成一个用于竞品 UX 设计标杆研究的场景网格。请用{lang}返回。

原则：质量优先，覆盖其次。宁可少而准，不要多而杂。

要求：
- 5-7 个 JTBD 任务，聚焦最核心、最值得做标杆研究的任务（用意图语言，
  如"邀请协作者+权限分级"，不是功能名如"成员管理"）
- 3-5 个旅程阶段（如"首次配置/日常使用/异常处理/规模化管理"）
- 整个网格总计 12-18 个格子，不要超过 18 个

【场景粒度——非常重要】
这些场景要能用公开网页（帮助文档/功能页/产品演示）研究到，所以：
- 大多数格子应是**主流程/核心页面**（如"角色权限设置页""看板视图""邀请成员页"），
  这些有公开文档、能被搜索到、也最能体现产品 UX 差异
- 少量（不超过 1/3）可以是**关键边界态**（空状态/常见错误态），但要克制
- 不要生成过度具体的深层异常态（如"含加密文件的部分导入失败态"）——这种公开
  网页几乎查不到，只能靠手动截图，不适合作为默认自动采集的场景

【page_state 字段格式——必须遵守】
- page_state 必须是**简短标签，≤10 个字**，如"角色权限页""批量导入页""空状态引导"
- 不要把整句描述塞进 page_state
- 详细的场景说明放进 scenario_detail 字段（可以写具体，供后续分析用）

- value_score(0-1)：格子对标杆研究的价值，核心且差异化程度高的分更高

返回纯 JSON（无代码块）：
{{"jtbd_tasks":["..."],"journey_stages":["..."],"cells":[{{"jtbd":"...","journey_stage":"...","page_state":"短标签≤10字","scenario_detail":"这个场景/状态的详细说明","value_score":0.8}}]}}"""


def generate_grid(req: GridGenerationRequest) -> GridGenerationResponse:
    """Generate a scene grid from a product category via the GPT relay.

    Falls back to a deterministic mock when the API key is absent or mock mode
    is enabled — never raises, always returns a usable response.
    """
    use_mock = settings.use_collection_mock or not gpt_relay.relay_available()
    if use_mock:
        resp = _MOCK.model_copy(deep=True)
        resp.category = req.category
        return resp

    try:
        raw = gpt_relay.chat(system=_SYSTEM, prompt=_prompt(req), max_tokens=4096)
        data = extract_json(raw)

        cells = [GeneratedCell(**c) for c in data.get("cells", [])]
        return GridGenerationResponse(
            category=req.category,
            jtbd_tasks=data.get("jtbd_tasks", []),
            journey_stages=data.get("journey_stages", []),
            cells=cells,
            total=len(cells),
            generated_by="gpt",
        )

    except Exception as exc:
        logger.warning("Grid generation failed, returning mock: %s", exc)
        resp = _MOCK.model_copy(deep=True)
        resp.category = req.category
        return resp
