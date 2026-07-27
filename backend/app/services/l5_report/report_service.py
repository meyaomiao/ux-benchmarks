"""L5 report service — 重组而非重生.

Composes a markdown report from a selection of existing Insights, tailored to
a target audience and format. L4 "module extraction" is done here in-memory:
the Insight fields (claim / analysis / recommendation / design_principle /
limits) become the reusable modules that get weaved into the final report.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.models.l3_insight import Insight
from app.models.l5_report import Report
from app.utils.robust_json import extract_json

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-opus-4-8"

_AUDIENCE_DESC = {
    "management": "管理层决策者（非设计师），关注业务影响和行动建议，不需要机制细节",
    "designer": "UX/产品设计师，关注设计原则、机制和可迁移的模式",
    "pm": "产品经理，关注具体建议、实现难点和适用限制",
}

_FORMAT_DESC = {
    "summary_5min": "5分钟摘要：3~5个核心发现 + 每条一句话建议，简洁直接",
    "review_15min": "15分钟设计评审文档：分章节展开每条洞察，有背景/机制/建议/限制",
    "onepager": "单页总览：标题 + 核心洞察列表 + 一段设计原则汇总，适合打印或放进 PPT",
    "full": "完整报告：每条洞察的所有字段全展开，可作为工作留底",
}

_MOCK_BODY = """\
# 竞品设计标杆报告（示例）

## 核心洞察概览

共分析 **{count}** 条洞察，覆盖以下场景：

---

### 洞察 1 · 权限分配——角色选择与权限预览同屏联动

**结论**
在为新成员分配访问权限的场景中，将角色选择与该角色权限明细的实时展开绑定在同一视图内，
使分配者在不离开当前决策上下文的情况下完成「角色→具体能力」的核对，页面跳转次数为 0。

**设计原则**
决策触发点与决策依据信息同屏共置（Inline Consequence Preview）：凡用户在做选择前需要
查阅该选项的后果/属性，就应将该信息直接内联展示在选择控件旁。

**建议**
在角色/权限分配的选择控件旁，绑定一个随选中项实时刷新的权限明细区，用离散开关逐条列出关键能力。

**适用限制**
权限项超过 20 条时逐条展开可能增加扫描负担；角色权限完全不可修改时须用只读样式避免歧义。

---

## 可复用设计原则汇总

1. **Inline Consequence Preview** — 在选择控件旁同步渲染该选项展开后的离散能力清单
2. **Zero-Jump Decision Flow** — 决策所需信息与决策动作在同一容器内，消除上下文切换

---

*本报告由 UX 设计标杆工具自动生成，基于已采集的真实证据。*
"""


def _build_context_block(insights: list[Insight]) -> str:
    """L4 虚拟模块提取：把每条 Insight 的结构化字段提炼为纯文本上下文块。"""
    parts: list[str] = []
    for i, ins in enumerate(insights, 1):
        lines = [f"【洞察 {i}】"]
        if ins.claim:
            lines.append(f"结论：{ins.claim}")
        if ins.analysis:
            lines.append(f"机制分析：{ins.analysis}")
        if ins.recommendation:
            lines.append(f"建议：{ins.recommendation}")
        if ins.design_principle:
            lines.append(f"设计原则：{ins.design_principle}")
        if ins.limits:
            lines.append(f"限制：{ins.limits}")
        lines.append(f"置信度：{ins.confidence}")
        parts.append("\n".join(lines))
    return "\n\n---\n\n".join(parts)


def _call_claude(context: str, audience: str, format_type: str, title: str) -> str:
    """Call Claude to compose a markdown report from insight modules."""
    import anthropic

    kw: dict = {"api_key": settings.anthropic_api_key}
    if settings.anthropic_base_url:
        kw["base_url"] = settings.anthropic_base_url
    client = anthropic.Anthropic(**kw)

    system = (
        "你是 UX 竞品洞察专家，擅长将结构化洞察重组为面向不同受众的可读报告。"
        "报告必须基于输入的洞察内容，不能凭空增加证据或结论。"
        "输出纯 Markdown，不要有任何前言或解释。"
    )
    prompt = (
        f"报告标题：{title}\n"
        f"目标受众：{_AUDIENCE_DESC.get(audience, audience)}\n"
        f"格式要求：{_FORMAT_DESC.get(format_type, format_type)}\n\n"
        f"以下是所有洞察内容（L4 模块）：\n\n{context}\n\n"
        "请将以上内容重组为符合目标受众和格式要求的 Markdown 报告。\n"
        "要求：\n"
        "- 重组而非重生：结论和证据必须来自上方洞察内容，不能自行发明新证据\n"
        "- 根据受众调整措辞和详细程度\n"
        "- 输出纯 Markdown，从标题（#）开始\n"
    )
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=3000,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in msg.content if b.type == "text").strip()


def _auto_title(audience: str, format_type: str) -> str:
    fmt_labels = {
        "summary_5min": "5分钟摘要",
        "review_15min": "设计评审",
        "onepager": "单页总览",
        "full": "完整报告",
    }
    aud_labels = {"management": "管理层", "designer": "设计师", "pm": "产品经理"}
    now = datetime.now(timezone.utc).strftime("%m/%d")
    return f"竞品设计标杆 · {fmt_labels.get(format_type, format_type)} · {aud_labels.get(audience, audience)} · {now}"


# ---- public API ------------------------------------------------------------

def compose_report(
    db: Session,
    insight_ids: list[UUID],
    audience: str,
    format_type: str,
    title: Optional[str] = None,
    project_id: Optional[UUID] = None,
) -> Report:
    """主入口：从选定的洞察中重组生成报告（限定在项目内）。"""
    q = select(Insight).where(Insight.id.in_(insight_ids))
    if project_id is not None:
        q = q.where(Insight.project_id == project_id)
    insights = list(db.execute(q).scalars().all())
    if not insights:
        raise AppError("NOT_FOUND", "没有找到指定洞察", 404)

    final_title = title or _auto_title(audience, format_type)
    use_mock = settings.use_collection_mock or not settings.anthropic_api_key

    if use_mock:
        body = _MOCK_BODY.format(count=len(insights))
        generated_by = "mock"
    else:
        try:
            context = _build_context_block(insights)
            body = _call_claude(context, audience, format_type, final_title)
            generated_by = "claude"
        except Exception as exc:
            logger.warning("Report compose failed, using mock: %s", exc)
            body = _MOCK_BODY.format(count=len(insights))
            generated_by = "mock"

    # project_id from the insights (authoritative), falling back to the arg.
    resolved_pid = project_id or insights[0].project_id
    report = Report(
        project_id=resolved_pid,
        title=final_title,
        audience=audience,
        format_type=format_type,
        source_insight_ids=[str(i) for i in insight_ids],
        body_markdown=body,
        generated_by=generated_by,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def list_reports(db: Session, project_id: Optional[UUID] = None) -> list[Report]:
    q = select(Report)
    if project_id is not None:
        q = q.where(Report.project_id == project_id)
    return list(db.execute(q.order_by(Report.created_at.desc())).scalars().all())


def get_report(
    db: Session, report_id: UUID, project_id: Optional[UUID] = None
) -> Report | None:
    report = db.get(Report, report_id)
    if report is None or (project_id is not None and report.project_id != project_id):
        return None
    return report


def delete_report(
    db: Session, report_id: UUID, project_id: Optional[UUID] = None
) -> bool:
    report = db.get(Report, report_id)
    if report is None or (project_id is not None and report.project_id != project_id):
        raise AppError("NOT_FOUND", f"Report {report_id} not found", 404)
    db.delete(report)
    db.commit()
    return True
