"""Search coverage report service (#30).

Generates a structured markdown report of the current evidence collection state,
covering search scope, product coverage, evidence quality, and unresolved gaps.
"""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.m0_registry import CompetitorEntity
from app.models.m1_grid import GridCell
from app.models.m3_collection import Asset
from app.models.m4_annotation import Observation
from app.models.m5_coverage import CoverageSnapshot


def generate_coverage_report(db: Session, project_id: UUID | None = None) -> dict:
    """Return a structured report dict (also rendered as Markdown).

    ``project_id`` scopes every underlying count so two projects never see the
    same competitor list; None means unscoped (internal callers only).
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    def scoped(query, model):
        return query if project_id is None else query.where(model.project_id == project_id)

    # Competitors
    competitors = list(db.execute(scoped(select(CompetitorEntity).where(
        CompetitorEntity.status.in_(["confirmed", "pending"])
    ), CompetitorEntity)).scalars().all())
    confirmed = [c for c in competitors if c.status == "confirmed"]
    pending = [c for c in competitors if c.status == "pending"]

    # Grid cells
    cells = list(db.execute(scoped(
        select(GridCell).where(GridCell.status == "active"), GridCell
    )).scalars().all())
    jtbd_list = list({c.jtbd for c in cells})

    # Coverage snapshots
    snap_counts: dict[str, int] = {}
    rows = db.execute(scoped(
        select(CoverageSnapshot.status, func.count(CoverageSnapshot.id)),
        CoverageSnapshot,
    ).group_by(CoverageSnapshot.status)).all()
    for status, count in rows:
        snap_counts[status] = count
    total_pairs = sum(snap_counts.values())

    # Evidence
    total_assets = db.scalar(scoped(
        select(func.count(Asset.id)).where(Asset.is_superseded == False),  # noqa: E712
        Asset,
    )) or 0
    observed_assets = db.scalar(scoped(
        select(func.count(Asset.id)).where(
            Asset.is_superseded == False,  # noqa: E712
            Asset.evidence_type == "observed",
        ),
        Asset,
    )) or 0
    claimed_assets = db.scalar(scoped(
        select(func.count(Asset.id)).where(
            Asset.is_superseded == False,  # noqa: E712
            Asset.evidence_type == "claimed",
        ),
        Asset,
    )) or 0
    total_observations = db.scalar(scoped(
        select(func.count(Observation.id)), Observation
    )) or 0

    # Unresolved items
    missing_mapping = db.scalar(scoped(
        select(func.count(GridCell.id)).where(GridCell.status == "active"), GridCell
    )) or 0  # simplified — full check needs join with MappingCard
    walled_pairs = snap_counts.get("REJECTED_EMPTY", 0)

    report = {
        "generated_at": now,
        "search_scope": {
            "tracked_competitors": len(confirmed),
            "pending_confirmation": len(pending),
            "competitor_names": [c.canonical_name for c in confirmed],
            "active_cells": len(cells),
            "jtbd_tasks": len(jtbd_list),
            "jtbd_list": jtbd_list,
        },
        "product_coverage": {
            "total_cell_competitor_pairs": total_pairs,
            "by_status": snap_counts,
            "shortlist_ready": snap_counts.get("SHORTLIST_READY", 0),
            "saturated": snap_counts.get("SATURATED", 0),
            "unprobed": snap_counts.get("UNPROBED", 0),
        },
        "evidence_quality": {
            "total_assets": total_assets,
            "observed_assets": observed_assets,
            "claimed_only_assets": claimed_assets,
            "observed_fraction": round(observed_assets / total_assets, 2) if total_assets else 0.0,
            "total_accepted_observations": total_observations,
        },
        "unresolved": {
            "rejected_empty_pairs": walled_pairs,
            "note": "REJECTED_EMPTY pairs had no usable public evidence found during probing.",
        },
    }
    return report


def report_to_markdown(report: dict) -> str:
    """Render the report dict as a Markdown string for download."""
    r = report
    scope = r["search_scope"]
    cov = r["product_coverage"]
    ev = r["evidence_quality"]
    unres = r["unresolved"]

    lines = [
        f"# UX 证据采集覆盖报告",
        f"",
        f"生成时间：{r['generated_at']}",
        f"",
        f"---",
        f"",
        f"## 搜索范围",
        f"",
        f"- 已确认竞品：{scope['tracked_competitors']} 个（{', '.join(scope['competitor_names'])}）",
        f"- 待确认竞品：{scope['pending_confirmation']} 个",
        f"- 活跃场景格子：{scope['active_cells']} 个",
        f"- JTBD 任务：{scope['jtbd_tasks']} 个",
        f"",
        f"## 产品覆盖",
        f"",
        f"- 总计格子×竞品对：{cov['total_cell_competitor_pairs']}",
        f"- SHORTLIST_READY（待审核）：{cov['shortlist_ready']}",
        f"- SATURATED（已饱和）：{cov['saturated']}",
        f"- UNPROBED（未探测）：{cov['unprobed']}",
        f"",
        f"### 各状态分布",
        f"",
    ]
    for status, count in sorted(cov["by_status"].items()):
        lines.append(f"- {status}: {count}")

    lines += [
        f"",
        f"## 证据质量",
        f"",
        f"- 总资产数：{ev['total_assets']}",
        f"- 已观测（observed）：{ev['observed_assets']} ({ev['observed_fraction']*100:.0f}%)",
        f"- 仅声称（claimed）：{ev['claimed_only_assets']}",
        f"- 已人工接受观察：{ev['total_accepted_observations']}",
        f"",
        f"## 未覆盖项",
        f"",
        f"- REJECTED_EMPTY（采集无结果）对数：{unres['rejected_empty_pairs']}",
        f"- 说明：{unres['note']}",
    ]
    return "\n".join(lines)
