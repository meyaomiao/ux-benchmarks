"""L3 insight service — generate and manage structured design insights.

Insights are produced from accepted Observations for a (cell, competitor) pair.
The model analyses what the evidence tells us about WHY a product's design is effective
in that specific scenario, producing a falsifiable claim + mechanism + principle.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.models.l3_insight import Insight
from app.utils import gpt_relay
from app.utils.robust_json import extract_json
from app.models.m4_annotation import Observation
from app.models.m3_collection import Asset
from app.models.m0_registry import CompetitorEntity
from app.services.m2_mapping.mapping_service import get_mapping_card_by_cell
from app.services.m3_collection.asset_store import list_assets_for_cell

logger = logging.getLogger(__name__)


_SYSTEM = (
    "你是 UX 竞品洞察专家。基于真实采集的证据，分析为什么某竞品在某个具体场景"
    "表现领先，并提炼出可迁移的设计洞察。洞察必须可证伪、必须给出机制而非泛泛评价。"
)

_MOCK_INSIGHT = {
    "claim": (
        "在权限配置场景下，Linear 在角色选择时实时展示权限清单（选中即展开），"
        "使用户在授权决策前即可预览后果，降低误授权概率。"
    ),
    "analysis": (
        "认知成本降低：无需在帮助文档和配置界面之间切换。"
        "决策成本降低：授权行为的后果在执行前可见，从被动操作变为知情操作。"
        "Fitts 定律的逆用：信息呈现在决策点旁边，减少视觉扫描成本。"
    ),
    "recommendation": (
        "在成员设置页面，角色下拉选择时右侧面板实时展示该角色的权限清单"
        "（可见/可编辑/可删除各项以开关形式列出）。"
    ),
    "design_principle": (
        "让不可逆的授权决策，在执行前所见即所得。"
        "适用于任何涉及权限/危险操作的配置流程。"
    ),
    "limits": (
        "角色数 ≤ 6 时效果最佳；角色过多时清单过长反而增加认知负担，"
        "需考虑分组或折叠。仅适用于用户需要比较角色差异的场景。"
    ),
    "confidence": "medium",
}


def list_insights(
    db: Session,
    cell_id: Optional[UUID] = None,
    competitor_id: Optional[UUID] = None,
    is_draft: Optional[bool] = None,
    project_id: Optional[UUID] = None,
) -> list[Insight]:
    q = select(Insight)
    if project_id is not None:
        q = q.where(Insight.project_id == project_id)
    if cell_id is not None:
        q = q.where(Insight.cell_id == cell_id)
    if competitor_id is not None:
        q = q.where(Insight.competitor_id == competitor_id)
    if is_draft is not None:
        q = q.where(Insight.is_draft == is_draft)
    q = q.order_by(Insight.created_at.desc())
    return list(db.execute(q).scalars().all())


def _load_scoped_insight(
    db: Session, insight_id: UUID, project_id: Optional[UUID]
) -> Insight:
    """Fetch an Insight, refusing cross-project access.

    Reported as NOT_FOUND rather than FORBIDDEN so the error cannot be used to
    probe which insight ids exist in other projects.
    """
    insight = db.get(Insight, insight_id)
    if insight is None or (project_id is not None and insight.project_id != project_id):
        raise AppError("NOT_FOUND", f"Insight {insight_id} not found", 404)
    return insight


def get_insight(
    db: Session, insight_id: UUID, project_id: Optional[UUID] = None
) -> Insight | None:
    insight = db.get(Insight, insight_id)
    if insight is None or (project_id is not None and insight.project_id != project_id):
        return None
    return insight


def update_insight(
    db: Session, insight_id: UUID, data: dict, project_id: Optional[UUID] = None
) -> Insight:
    insight = _load_scoped_insight(db, insight_id, project_id)
    for k, v in data.items():
        if v is not None and hasattr(insight, k):
            setattr(insight, k, v)
    db.commit()
    db.refresh(insight)
    return insight


def delete_insight(
    db: Session, insight_id: UUID, project_id: Optional[UUID] = None
) -> bool:
    insight = _load_scoped_insight(db, insight_id, project_id)
    db.delete(insight)
    db.commit()
    return True


def generate_insight(
    db: Session,
    cell_id: UUID,
    competitor_id: UUID,
    project_id: Optional[UUID] = None,
) -> Insight:
    """Generate a draft insight from accepted evidence for (cell, competitor).

    Uses the GPT relay when a key is configured and mock mode is off; otherwise returns
    a deterministic Chinese mock insight so the UI is fully functional offline.
    """
    if project_id is not None:
        from app.models.m1_grid import GridCell

        cell_project_id = db.execute(
            select(GridCell.project_id).where(GridCell.id == cell_id)
        ).scalar_one_or_none()
        if cell_project_id is None or cell_project_id != project_id:
            raise AppError("NOT_FOUND", f"Cell {cell_id} not found", 404)

    use_mock = settings.use_collection_mock or not gpt_relay.relay_available()

    # Load context: mapping card + accepted observations + competitor name.
    card = get_mapping_card_by_cell(db, cell_id)
    intent = card.intent_definition if card else ""

    assets = list_assets_for_cell(db, cell_id, competitor_id)
    asset_ids = {str(a.id) for a in assets}

    obs_rows = list(
        db.execute(
            select(Observation).where(Observation.asset_id.in_(asset_ids))
        ).scalars().all()
    ) if asset_ids else []

    competitor = db.get(CompetitorEntity, competitor_id)
    comp_name = competitor.canonical_name if competitor else str(competitor_id)[:8]

    obs_texts = []
    for obs in obs_rows[:10]:
        parts = [
            obs.surface_confirmed,
            " ".join(obs.labels_verbatim or []),
            obs.sequence_context.get("description", "") if isinstance(obs.sequence_context, dict) else "",
        ]
        text = " ".join(p for p in parts if p).strip()
        if text:
            obs_texts.append(text)

    if use_mock:
        mock = dict(_MOCK_INSIGHT)
        mock["claim"] = mock["claim"].replace("Linear", comp_name)
        return _save_insight(db, cell_id, competitor_id, mock, [], generated_by="mock")

    # Evidence gate (#6): in real mode, refuse to fabricate an insight when no
    # evidence has been accepted for this (cell, competitor). An insight with no
    # source observations is meaningless — the user must review evidence first.
    if not obs_rows:
        raise AppError(
            "NO_EVIDENCE",
            "该场景×竞品还没有已审核通过的证据，无法生成洞察。请先在采集/审核环节接受证据。",
            409,
        )

    try:
        content = _call_llm(intent, comp_name, obs_texts)
        obs_ids = [str(obs.id) for obs in obs_rows]
        return _save_insight(db, cell_id, competitor_id, content, obs_ids, generated_by="gpt")
    except Exception as exc:
        logger.warning("Insight generation failed, falling back to mock: %s", exc)
        mock = dict(_MOCK_INSIGHT)
        mock["claim"] = mock["claim"].replace("Linear", comp_name)
        return _save_insight(db, cell_id, competitor_id, mock, [], generated_by="mock")


def _call_llm(intent: str, comp_name: str, obs_texts: list[str]) -> dict:
    obs_block = "\n".join(f"- {t}" for t in obs_texts) if obs_texts else "（无已接受观察记录）"
    prompt = (
        f"竞品：{comp_name}\n"
        f"场景意图：{intent or '（未填写映射卡）'}\n\n"
        f"已接受的观察记录：\n{obs_block}\n\n"
        "请基于以上证据生成一条结构化设计洞察。\n"
        "要求：\n"
        "- claim 必须可证伪，格式：场景 + 模式 + 可观测结果 + 机制\n"
        "- analysis 给出因果机制，说明如何降低认知/操作/决策成本\n"
        "- design_principle 去品牌化，可直接复用到其他产品\n"
        "- confidence 取 high/medium/low/hypothesis 之一\n\n"
        "返回纯 JSON（无代码块）：\n"
        '{"claim":"...","analysis":"...","recommendation":"...","design_principle":"...","limits":"...","confidence":"medium"}'
    )
    raw = gpt_relay.chat(system=_SYSTEM, prompt=prompt, max_tokens=2048)
    return extract_json(raw)


def _save_insight(
    db: Session,
    cell_id: UUID,
    competitor_id: UUID,
    data: dict,
    obs_ids: list[str],
    generated_by: str,
) -> Insight:
    # project_id derived from the cell (authoritative) so insights stay scoped.
    from app.models.m1_grid import GridCell
    project_id = db.execute(
        select(GridCell.project_id).where(GridCell.id == cell_id)
    ).scalar_one()
    insight = Insight(
        project_id=project_id,
        cell_id=cell_id,
        competitor_id=competitor_id,
        claim=data.get("claim", ""),
        analysis=data.get("analysis"),
        recommendation=data.get("recommendation"),
        design_principle=data.get("design_principle"),
        limits=data.get("limits"),
        source_observation_ids=obs_ids,
        confidence=data.get("confidence", "hypothesis"),
        generated_by=generated_by,
        is_draft=True,
    )
    db.add(insight)
    db.commit()
    db.refresh(insight)
    return insight
