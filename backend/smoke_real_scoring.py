"""One-off smoke test: real Claude relevance scoring (NOT pytest).

Forces live mode and scores two hand-built candidates against one intent:
  A) a step-by-step doc that SHOWS the target permission UI  -> should PASS high
  B) marketing copy that merely MENTIONS permissions          -> should FAIL low

Run:  cd backend && DATABASE_URL="sqlite://" python smoke_real_scoring.py
Reads key + base_url from .env. Prints scores; does not touch the DB.
"""
from app.core.config import settings

# Force the real path for this run only.
settings.use_collection_mock = False

from app.services.m3_collection.contracts import Candidate, EvidenceType, SourceType
from app.services.m3_collection.scoring.relevance_scorer import RelevanceScorer
from uuid import uuid4

INTENT = "为新成员分配访问权限时，逐条查看每个角色能做什么（权限矩阵/角色权限对照）"
INCLUSION = "显示角色与权限的对应关系、权限编辑界面、成员邀请时的角色选择"
EXCLUSION = "纯计费/定价页、与权限无关的功能介绍"

SHOWS = Candidate(
    cell_id=uuid4(), competitor_id=uuid4(),
    source_url="https://help.example.com/docs/roles-permissions",
    source_type=SourceType.HELP_DOCS,
    title="管理成员角色与权限 - 帮助中心",
    text_content=(
        "在设置 > 成员页面，点击某个成员旁的角色下拉菜单。选择角色后，"
        "右侧会展开该角色的权限清单：可查看、可编辑、可删除、可管理成员，"
        "逐条以开关形式列出。管理员可以自定义角色，勾选每一项权限。"
        "邀请新成员时，在邀请弹窗中先选择角色，即可预览其权限范围。"
    ),
    evidence_type_hint=EvidenceType.OBSERVED,
)

MENTIONS = Candidate(
    cell_id=uuid4(), competitor_id=uuid4(),
    source_url="https://example.com/features",
    source_type=SourceType.HELP_DOCS,
    title="强大的团队协作 - 产品官网",
    text_content=(
        "我们的平台支持灵活的权限管理，让团队协作更高效。"
        "无论多大的团队都能轻松管理。立即注册，体验更好的协作方式。"
    ),
    evidence_type_hint=EvidenceType.CLAIMED,
)


def _run(label, cand):
    s = RelevanceScorer().score(
        cand,
        intent_definition=INTENT,
        inclusion_criteria=INCLUSION,
        exclusion_criteria=EXCLUSION,
    )
    print(f"\n=== {label} ===")
    print(f"scored_by : {s.scored_by}")
    print(f"score     : {s.score:.3f}   passed={s.passed}")
    print(f"evidence  : {s.evidence_type}")
    print(f"rubric    : state={s.rubric.state_match:.2f} product={s.rubric.product_match:.2f} "
          f"recency={s.rubric.version_recency:.2f} direct={s.rubric.evidence_directness:.2f} "
          f"fidelity={s.rubric.fidelity:.2f}")
    print(f"reasoning : {s.reasoning[:300]}")
    return s


if __name__ == "__main__":
    print(f"use_collection_mock = {settings.use_collection_mock}")
    print(f"base_url set        = {bool(settings.anthropic_base_url)}")
    print(f"key present         = {bool(settings.anthropic_api_key)}")
    a = _run("A: SHOWS the permission UI (expect PASS)", SHOWS)
    b = _run("B: only MENTIONS permissions (expect FAIL)", MENTIONS)
    print("\n---")
    ok = a.scored_by == "claude-vision" and a.passed and not b.passed
    print("VERDICT:", "✅ real model correctly separated shows vs mentions"
          if ok else "⚠️ check output above (fell back to mock, or ranking unexpected)")
