"""End-to-end REAL relay validation (方向 A) — NOT pytest.

Validates the core value hypothesis across all three analysis stages, using the
real GPT relay endpoint (deepkey), with NO database dependency:

  1. 网格生成   generate_grid(category) — does the model produce a sensible grid?
  2. 相关性打分 RelevanceScorer.score — can it tell "shows" from "mentions"?
  3. 洞察生成   insight _call_llm — does it produce a credible, non-generic insight?

Run:  cd backend && python smoke_e2e_real.py
Reads key + base_url from .env. Prints raw outputs for human judgement.
"""
from app.core.config import settings

# Force the real path for this whole run.
settings.use_collection_mock = False

from uuid import uuid4

SEP = "=" * 72


def stage1_grid():
    from app.schemas.m1 import GridGenerationRequest
    from app.services.m1_grid.generation_service import generate_grid

    print(SEP)
    print("STAGE 1 · 网格生成（真实 GPT relay）")
    print(SEP)
    req = GridGenerationRequest(
        category="项目管理工具",
        known_products=["Linear", "Asana", "Notion"],
        language="zh",
    )
    resp = generate_grid(req)
    print(f"generated_by : {resp.generated_by}")
    print(f"JTBD 任务数   : {len(resp.jtbd_tasks)}")
    print(f"旅程阶段      : {resp.journey_stages}")
    print(f"格子数        : {resp.total}")
    print("\n前 8 个格子:")
    for c in resp.cells[:8]:
        print(f"  [{c.value_score:.2f}] {c.jtbd} × {c.journey_stage} × {c.page_state}")
    # Quality signal: are non-happy-path states present?
    non_happy = [c for c in resp.cells if any(
        k in c.page_state for k in ("空", "错误", "异常", "失败", "冲突", "边界", "拒绝", "空状态")
    )]
    print(f"\n非 happy-path 格子数: {len(non_happy)} / {resp.total}"
          f"  {'✓ 覆盖了边界态' if non_happy else '⚠ 未覆盖边界态'}")
    return resp.generated_by == "gpt"


def stage2_scoring():
    from app.services.m3_collection.contracts import Candidate, EvidenceType, SourceType
    from app.services.m3_collection.scoring.relevance_scorer import RelevanceScorer

    print("\n" + SEP)
    print("STAGE 2 · 相关性打分（真实 GPT relay）· 展示 vs 提到")
    print(SEP)
    intent = "为新成员分配访问权限时，逐条查看每个角色能做什么（权限矩阵/角色权限对照）"
    inclusion = "显示角色与权限的对应关系、权限编辑界面、成员邀请时的角色选择"
    exclusion = "纯计费/定价页、与权限无关的功能介绍"

    shows = Candidate(
        cell_id=uuid4(), competitor_id=uuid4(),
        source_url="https://help.example.com/docs/roles",
        source_type=SourceType.HELP_DOCS,
        title="管理成员角色与权限",
        text_content=(
            "在设置 > 成员页面，点击成员旁的角色下拉菜单。选择角色后，右侧展开该角色的"
            "权限清单：可查看、可编辑、可删除、可管理成员，逐条以开关列出。邀请新成员时，"
            "在邀请弹窗中先选角色，即可预览其权限范围。"
        ),
        evidence_type_hint=EvidenceType.OBSERVED,
    )
    mentions = Candidate(
        cell_id=uuid4(), competitor_id=uuid4(),
        source_url="https://example.com/features",
        source_type=SourceType.HELP_DOCS,
        title="强大的团队协作",
        text_content="我们的平台支持灵活的权限管理，让团队协作更高效。立即注册体验。",
        evidence_type_hint=EvidenceType.CLAIMED,
    )
    scorer = RelevanceScorer()
    for label, cand, expect in [("A 展示了UI（期望 PASS）", shows, True),
                                 ("B 仅提到（期望 FAIL）", mentions, False)]:
        s = scorer.score(cand, intent_definition=intent,
                         inclusion_criteria=inclusion, exclusion_criteria=exclusion)
        verdict = "✓" if s.passed == expect else "✗ 意外"
        print(f"\n{label}  {verdict}")
        print(f"  scored_by={s.scored_by}  score={s.score:.3f}  passed={s.passed}")
        print(f"  reasoning: {s.reasoning[:200]}")
    return scorer.score(shows, intent_definition=intent).scored_by.startswith("gpt:")


def stage3_insight():
    from app.services.l3_insight.insight_service import _call_llm

    print("\n" + SEP)
    print("STAGE 3 · 洞察生成（真实 GPT relay）")
    print(SEP)
    intent = "为新成员分配访问权限时，逐条查看每个角色能做什么"
    comp = "Linear"
    obs = [
        "角色选择下拉菜单，选中角色后右侧实时展开该角色的权限开关清单（可见/可编辑/可删除/可管理成员）",
        "邀请弹窗中先选择角色，弹窗内即预览该角色权限范围",
        "权限项以开关(toggle)形式逐条列出，管理员可自定义角色勾选每一项",
    ]
    result = _call_llm(intent, comp, obs)
    for field in ["claim", "analysis", "recommendation", "design_principle", "limits", "confidence"]:
        val = result.get(field, "(缺失)")
        print(f"\n【{field}】\n  {val}")
    # Quality signal: is the claim falsifiable (not generic praise)?
    claim = result.get("claim", "")
    generic = any(w in claim for w in ["简洁", "流畅", "美观", "友好", "优秀"]) and len(claim) < 40
    print(f"\n结论具体性: {'⚠ 疑似空话' if generic else '✓ 具体、含机制'}")
    return bool(result.get("claim"))


if __name__ == "__main__":
    print(f"use_collection_mock = {settings.use_collection_mock}")
    print(f"base_url = {settings.gpt_base_url}\n")
    results = {}
    for name, fn in [("网格生成", stage1_grid), ("相关性打分", stage2_scoring), ("洞察生成", stage3_insight)]:
        try:
            results[name] = fn()
        except Exception as e:
            print(f"\n✗ {name} 失败: {type(e).__name__}: {str(e)[:200]}")
            results[name] = False
    print("\n" + SEP)
    print("真实 GPT relay 端到端验证结果")
    print(SEP)
    for k, v in results.items():
        print(f"  {k}: {'✓ 走了真实 Claude' if v else '✗ 回退 mock 或失败'}")
