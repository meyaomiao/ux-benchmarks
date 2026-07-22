"""AI-powered scene grid generation from a product category.

Calls Claude to produce JTBD tasks, journey stages and key (page, state) cells.
Falls back to a deterministic mock when use_collection_mock=True or the API key
is empty — same fallback pattern as the relevance scorer.
"""
import json
import logging
import re

from app.core.config import settings
from app.schemas.m1 import GeneratedCell, GridGenerationRequest, GridGenerationResponse

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-opus-4-8"

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
        GeneratedCell(jtbd="邀请协作者+权限分级", journey_stage="首次配置", page_state="角色选择页", value_score=0.9),
        GeneratedCell(jtbd="邀请协作者+权限分级", journey_stage="首次配置", page_state="权限冲突提示（异常态）", value_score=0.85),
        GeneratedCell(jtbd="邀请协作者+权限分级", journey_stage="首次配置", page_state="邀请弹窗（空状态）", value_score=0.8),
        GeneratedCell(jtbd="创建首个项目/工作区", journey_stage="首次配置", page_state="空状态引导页", value_score=0.8),
        GeneratedCell(jtbd="追踪任务进度", journey_stage="日常使用", page_state="看板视图", value_score=0.6),
        GeneratedCell(jtbd="追踪任务进度", journey_stage="异常处理", page_state="数据加载失败态", value_score=0.75),
        GeneratedCell(jtbd="设置通知与提醒", journey_stage="首次配置", page_state="通知权限请求", value_score=0.7),
    ],
    total=7,
    generated_by="mock",
)


def _prompt(req: GridGenerationRequest) -> str:
    products_hint = ""
    if req.known_products:
        products_hint = f"\n已知代表性产品：{', '.join(req.known_products)}"
    lang = "中文" if req.language == "zh" else "English"
    return f"""分析产品品类：{req.category}{products_hint}

生成一个用于竞品 UX 设计标杆研究的场景网格。请用{lang}返回。

要求：
- 8-12 个 JTBD 任务（用意图语言，如"邀请协作者+权限分级"，不是功能名）
- 4-6 个旅程阶段（如"首次配置/日常使用/异常处理/规模化管理"）
- 每个有意义的 JTBD×阶段组合生成 1-3 个关键页面/状态，优先包括非 happy-path（空状态/错误态/权限边界/数据边界）
- value_score(0-1)：格子对标杆研究的价值，非 happy-path 和差异化程度高的格子分更高

返回纯 JSON（无代码块）：
{{"jtbd_tasks":["..."],"journey_stages":["..."],"cells":[{{"jtbd":"...","journey_stage":"...","page_state":"...","value_score":0.8}}]}}"""


def generate_grid(req: GridGenerationRequest) -> GridGenerationResponse:
    """Generate a scene grid from a product category using Claude.

    Falls back to a deterministic mock when the API key is absent or mock mode
    is enabled — never raises, always returns a usable response.
    """
    use_mock = settings.use_collection_mock or not settings.anthropic_api_key
    if use_mock:
        resp = _MOCK.model_copy(deep=True)
        resp.category = req.category
        return resp

    try:
        import anthropic  # lazy import — only needed on the real path

        kw: dict = {"api_key": settings.anthropic_api_key}
        if settings.anthropic_base_url:
            kw["base_url"] = settings.anthropic_base_url
        client = anthropic.Anthropic(**kw)

        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=_SYSTEM,
            messages=[{"role": "user", "content": _prompt(req)}],
        )
        raw = "".join(b.text for b in msg.content if b.type == "text")
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(match.group(0) if match else raw)

        cells = [GeneratedCell(**c) for c in data.get("cells", [])]
        return GridGenerationResponse(
            category=req.category,
            jtbd_tasks=data.get("jtbd_tasks", []),
            journey_stages=data.get("journey_stages", []),
            cells=cells,
            total=len(cells),
            generated_by="claude",
        )

    except Exception as exc:
        logger.warning("Grid generation failed, returning mock: %s", exc)
        resp = _MOCK.model_copy(deep=True)
        resp.category = req.category
        return resp
