// Mock data — used when NEXT_PUBLIC_USE_MOCK !== "false" (default: on).
// Lets the UI render fully without a running backend.

import type { Competitor, LexiconEntry, GridCell, CoverageRow, MappingCard, ShortlistItem, Report, Insight } from "./types";

const now = "2026-07-21T10:00:00Z";

export const mockCompetitors: Competitor[] = [
  {
    id: "c1000000-0000-0000-0000-000000000001",
    canonical_name: "Linear",
    aliases: ["Linear.app"],
    parent_company: "Linear Orbit Inc.",
    official_domain: "linear.app",
    help_center_domain: "linear.app/docs",
    video_channels: ["https://youtube.com/@linear"],
    app_store_pages: [],
    acquired_from: null,
    valid_from: null,
    valid_to: null,
    status: "confirmed",
    competitor_type: "direct",
    created_at: now,
    updated_at: now,
  },
  {
    id: "c1000000-0000-0000-0000-000000000002",
    canonical_name: "Asana",
    aliases: [],
    parent_company: "Asana, Inc.",
    official_domain: "asana.com",
    help_center_domain: "help.asana.com",
    video_channels: ["https://youtube.com/@asana"],
    app_store_pages: ["https://apps.apple.com/app/asana"],
    acquired_from: null,
    valid_from: null,
    valid_to: null,
    status: "confirmed",
    competitor_type: "direct",
    created_at: now,
    updated_at: now,
  },
  {
    id: "c1000000-0000-0000-0000-000000000003",
    canonical_name: "Notion",
    aliases: ["Notion.so"],
    parent_company: "Notion Labs, Inc.",
    official_domain: "notion.so",
    help_center_domain: "notion.so/help",
    video_channels: [],
    app_store_pages: [],
    acquired_from: null,
    valid_from: null,
    valid_to: null,
    status: "confirmed",
    competitor_type: "indirect",
    created_at: now,
    updated_at: now,
  },
  {
    id: "c1000000-0000-0000-0000-000000000004",
    canonical_name: "Figma",
    aliases: [],
    parent_company: "Figma, Inc.",
    official_domain: "figma.com",
    help_center_domain: "help.figma.com",
    video_channels: ["https://youtube.com/@figma"],
    app_store_pages: [],
    acquired_from: null,
    valid_from: null,
    valid_to: null,
    status: "confirmed",
    competitor_type: "cross_industry",
    created_at: now,
    updated_at: now,
  },
  {
    id: "c1000000-0000-0000-0000-000000000005",
    canonical_name: "Height",
    aliases: [],
    parent_company: null,
    official_domain: "height.app",
    help_center_domain: null,
    video_channels: [],
    app_store_pages: [],
    acquired_from: null,
    valid_from: null,
    valid_to: null,
    status: "pending",
    competitor_type: "direct",
    created_at: now,
    updated_at: now,
  },
];

export const mockLexicon: LexiconEntry[] = [
  { id: "l1", term: "邀请协作者", term_type: "task", language: "zh", level: "category", valid_for_competitors: [], source: null, created_at: now, updated_at: now },
  { id: "l2", term: "invite collaborators", term_type: "task", language: "en", level: "category", valid_for_competitors: [], source: null, created_at: now, updated_at: now },
  { id: "l3", term: "权限矩阵", term_type: "ui_state", language: "zh", level: "category", valid_for_competitors: [], source: null, created_at: now, updated_at: now },
  { id: "l4", term: "role / permission matrix", term_type: "ui_state", language: "en", level: "category", valid_for_competitors: [], source: null, created_at: now, updated_at: now },
  { id: "l5", term: "seat", term_type: "product_alias", language: "en", level: "project", valid_for_competitors: ["Linear"], source: "help docs", created_at: now, updated_at: now },
  { id: "l6", term: "管理员", term_type: "role", language: "zh", level: "category", valid_for_competitors: [], source: null, created_at: now, updated_at: now },
];

export const mockCells: GridCell[] = [
  { id: "g1", cell_key: "invite-collaborators.first-setup.invite-modal", jtbd: "邀请协作者+权限分级", journey_stage: "首次配置", page_state: "邀请弹窗", value_score: 0.7, version: 1, status: "active", requires_review: false, created_at: now, updated_at: now },
  { id: "g2", cell_key: "invite-collaborators.first-setup.role-select", jtbd: "邀请协作者+权限分级", journey_stage: "首次配置", page_state: "角色选择", value_score: 0.9, version: 1, status: "active", requires_review: false, created_at: now, updated_at: now },
  { id: "g3", cell_key: "invite-collaborators.advanced.perm-editor", jtbd: "邀请协作者+权限分级", journey_stage: "进阶配置", page_state: "权限编辑页", value_score: 0.85, version: 1, status: "active", requires_review: false, created_at: now, updated_at: now },
  { id: "g4", cell_key: "invite-collaborators.error.perm-conflict", jtbd: "邀请协作者+权限分级", journey_stage: "异常处理", page_state: "权限冲突提示", value_score: 0.6, version: 1, status: "active", requires_review: false, created_at: now, updated_at: now },
  { id: "g5", cell_key: "invite-collaborators.scale.bulk-perm", jtbd: "邀请协作者+权限分级", journey_stage: "规模化管理", page_state: "批量改权限", value_score: 0.5, version: 1, status: "active", requires_review: false, created_at: now, updated_at: now },
];

export const mockCoverage: CoverageRow[] = [
  // g1 — 邀请弹窗
  { cell_id: "g1", competitor_id: "c1000000-0000-0000-0000-000000000001", status: "SHORTLIST_READY", independent_source_count: 3, latest_captured_at: "2026-07-20T15:30:00Z", coverage_confidence: 0.82, evidence_type_breakdown: { screenshot: 2, video: 1 }, tier: "tier-1" },
  { cell_id: "g1", competitor_id: "c1000000-0000-0000-0000-000000000002", status: "UNPROBED", independent_source_count: 0, latest_captured_at: null, coverage_confidence: 0, evidence_type_breakdown: {}, tier: "tier-1" },
  { cell_id: "g1", competitor_id: "c1000000-0000-0000-0000-000000000003", status: "SHORTLIST_READY", independent_source_count: 2, latest_captured_at: "2026-07-19T10:00:00Z", coverage_confidence: 0.68, evidence_type_breakdown: { screenshot: 1, doc: 1 }, tier: "tier-1" },
  { cell_id: "g1", competitor_id: "c1000000-0000-0000-0000-000000000004", status: "PARTIAL", independent_source_count: 1, latest_captured_at: "2026-07-18T08:00:00Z", coverage_confidence: 0.35, evidence_type_breakdown: { screenshot: 1 }, tier: "tier-2" },

  // g2 — 角色选择
  { cell_id: "g2", competitor_id: "c1000000-0000-0000-0000-000000000001", status: "PARTIAL", independent_source_count: 1, latest_captured_at: "2026-07-19T14:00:00Z", coverage_confidence: 0.45, evidence_type_breakdown: { doc: 1 }, tier: "tier-1" },
  { cell_id: "g2", competitor_id: "c1000000-0000-0000-0000-000000000002", status: "SHORTLIST_READY", independent_source_count: 4, latest_captured_at: "2026-07-21T09:00:00Z", coverage_confidence: 0.9, evidence_type_breakdown: { screenshot: 2, video: 1, doc: 1 }, tier: "tier-1" },
  { cell_id: "g2", competitor_id: "c1000000-0000-0000-0000-000000000003", status: "UNPROBED", independent_source_count: 0, latest_captured_at: null, coverage_confidence: 0, evidence_type_breakdown: {}, tier: "tier-1" },
  { cell_id: "g2", competitor_id: "c1000000-0000-0000-0000-000000000004", status: "QUEUED", independent_source_count: 0, latest_captured_at: null, coverage_confidence: 0.1, evidence_type_breakdown: {}, tier: "tier-2" },

  // g3 — 权限编辑页
  { cell_id: "g3", competitor_id: "c1000000-0000-0000-0000-000000000001", status: "UNPROBED", independent_source_count: 0, latest_captured_at: null, coverage_confidence: 0, evidence_type_breakdown: {}, tier: "tier-1" },
  { cell_id: "g3", competitor_id: "c1000000-0000-0000-0000-000000000002", status: "STALE", independent_source_count: 1, latest_captured_at: "2025-12-01T10:00:00Z", coverage_confidence: 0.2, evidence_type_breakdown: { screenshot: 1 }, tier: "tier-1" },
  { cell_id: "g3", competitor_id: "c1000000-0000-0000-0000-000000000003", status: "REJECTED_EMPTY", independent_source_count: 0, latest_captured_at: "2026-07-15T12:00:00Z", coverage_confidence: 0, evidence_type_breakdown: {}, tier: "tier-1" },

  // g4 — 权限冲突提示
  { cell_id: "g4", competitor_id: "c1000000-0000-0000-0000-000000000001", status: "SHORTLIST_READY", independent_source_count: 2, latest_captured_at: "2026-07-20T11:00:00Z", coverage_confidence: 0.75, evidence_type_breakdown: { screenshot: 1, doc: 1 }, tier: "tier-1" },
  { cell_id: "g4", competitor_id: "c1000000-0000-0000-0000-000000000002", status: "UNPROBED", independent_source_count: 0, latest_captured_at: null, coverage_confidence: 0, evidence_type_breakdown: {}, tier: "tier-1" },
  { cell_id: "g4", competitor_id: "c1000000-0000-0000-0000-000000000003", status: "UNPROBED", independent_source_count: 0, latest_captured_at: null, coverage_confidence: 0, evidence_type_breakdown: {}, tier: "tier-1" },

  // g5 — 批量改权限
  { cell_id: "g5", competitor_id: "c1000000-0000-0000-0000-000000000001", status: "PROBING", independent_source_count: 0, latest_captured_at: null, coverage_confidence: 0.15, evidence_type_breakdown: {}, tier: "tier-1" },
  { cell_id: "g5", competitor_id: "c1000000-0000-0000-0000-000000000002", status: "UNPROBED", independent_source_count: 0, latest_captured_at: null, coverage_confidence: 0, evidence_type_breakdown: {}, tier: "tier-1" },
];

export const mockShortlist: Record<string, ShortlistItem[]> = {
  "g1|c1000000-0000-0000-0000-000000000001": [
    {
      id: "a0001", cell_id: "g1", competitor_id: "c1000000-0000-0000-0000-000000000001",
      source_url: "https://help.linear.app/docs/invite-members",
      source_type: "help_docs", title: "Invite members to your workspace — Linear Help",
      snippet: "前往「设置 › 成员 › 邀请成员」，输入邮箱地址并选择角色（成员、管理员或访客）。发送前可预览每个角色的权限详情。",
      evidence_type: "observed", ai_score: 0.87,
      ai_score_breakdown: { state_match: 0.92, product_match: 1.0, version_recency: 0.85, evidence_directness: 0.9, fidelity: 0.7, reasoning: "逐步操作文档展示了邀请弹窗、角色选择器及权限预览，精确描述了目标 UI 流程。因文档内容可复现，判定为已观测。", scored_by: "gpt:gpt-5.6-luna" },
      rights_status: "third_party_official", media_disposition: "thumbnail_only",
      captured_at: "2026-07-20T15:30:00Z", image_path_available: false,
    },
    {
      id: "a0002", cell_id: "g1", competitor_id: "c1000000-0000-0000-0000-000000000001",
      source_url: "https://app.storylane.io/demo/linear-invite-flow",
      source_type: "interactive_demo", title: "Linear product tour — Invite & Permissions",
      snippet: "产品导览第 2/7 步：邀请弹窗已打开，角色下拉菜单展开，右侧可见实时权限预览面板。",
      evidence_type: "observed", ai_score: 0.93,
      ai_score_breakdown: { state_match: 0.95, product_match: 1.0, version_recency: 0.92, evidence_directness: 1.0, fidelity: 0.8, reasoning: "交互式 Demo 截图直接展示了邀请弹窗，角色下拉已展开并附实时权限预览面板，目标状态清晰可见。", scored_by: "gpt:gpt-5.6-luna" },
      rights_status: "embedded_third_party", media_disposition: "thumbnail_only",
      captured_at: "2026-07-20T16:00:00Z", image_path_available: true,
    },
  ],
  "g1|c1000000-0000-0000-0000-000000000003": [
    {
      id: "a0003", cell_id: "g1", competitor_id: "c1000000-0000-0000-0000-000000000003",
      source_url: "https://www.notion.so/help/add-members-to-your-workspace",
      source_type: "help_docs", title: "Add members to your workspace — Notion Help",
      snippet: "点击左侧边栏「设置 & 成员」，选择「成员」后点击「邀请成员」。输入邮箱，选择角色（工作区所有者、成员或访客）。",
      evidence_type: "observed", ai_score: 0.74,
      ai_score_breakdown: { state_match: 0.78, product_match: 1.0, version_recency: 0.7, evidence_directness: 0.8, fidelity: 0.6, reasoning: "正确描述了邀请流程，但未展示权限预览——角色列表缺少权限上下文说明，state_match 低于 Linear。", scored_by: "gpt:gpt-5.6-luna" },
      rights_status: "third_party_official", media_disposition: "thumbnail_only",
      captured_at: "2026-07-19T10:00:00Z", image_path_available: false,
    },
  ],
  "g2|c1000000-0000-0000-0000-000000000002": [
    {
      id: "a0004", cell_id: "g2", competitor_id: "c1000000-0000-0000-0000-000000000002",
      source_url: "https://help.asana.com/hc/en-us/articles/roles",
      source_type: "help_docs", title: "Roles and permissions in Asana",
      snippet: "Asana 提供三种角色：访客、成员和管理员。访客仅能访问受邀项目，成员可创建和编辑项目，管理员负责管理账单和成员。",
      evidence_type: "claimed", ai_score: 0.41,
      ai_score_breakdown: { state_match: 0.3, product_match: 1.0, version_recency: 0.6, evidence_directness: 0.5, fidelity: 0.4, reasoning: "文字描述了角色定义，但未展示任何 UI 界面，角色选择界面本身不可见。因该文章无角色选择器截图，判定为仅声称。", scored_by: "gpt:gpt-5.6-luna" },
      rights_status: "third_party_official", media_disposition: "thumbnail_only",
      captured_at: "2026-07-21T09:00:00Z", image_path_available: false,
    },
    {
      id: "a0005", cell_id: "g2", competitor_id: "c1000000-0000-0000-0000-000000000002",
      source_url: "https://app.arcade.software/share/asana-permissions",
      source_type: "interactive_demo", title: "Asana demo — Roles & Access",
      snippet: "产品导览第 4 步：已选中「成员」角色，权限范围显示为「可编辑该团队所有项目」。",
      evidence_type: "observed", ai_score: 0.88,
      ai_score_breakdown: { state_match: 0.9, product_match: 1.0, version_recency: 0.9, evidence_directness: 1.0, fidelity: 0.75, reasoning: "交互式 Demo 截图清晰展示了角色选择状态及权限范围文字，目标 UI 直接可见，state_match 得分较高。", scored_by: "gpt:gpt-5.6-luna" },
      rights_status: "embedded_third_party", media_disposition: "thumbnail_only",
      captured_at: "2026-07-21T09:30:00Z", image_path_available: true,
    },
  ],
  "g4|c1000000-0000-0000-0000-000000000001": [
    {
      id: "a0006", cell_id: "g4", competitor_id: "c1000000-0000-0000-0000-000000000001",
      source_url: "https://help.linear.app/docs/permission-conflict",
      source_type: "help_docs", title: "Handling permission conflicts — Linear",
      snippet: "当成员角色与项目级别的权限覆盖冲突时，Linear 会显示黄色警告横幅：「该成员的工作区角色（访客）与其项目权限（编辑者）冲突」。点击「解决」可选择哪一方优先生效。",
      evidence_type: "observed", ai_score: 0.81,
      ai_score_breakdown: { state_match: 0.85, product_match: 1.0, version_recency: 0.8, evidence_directness: 0.85, fidelity: 0.65, reasoning: "以具体 UI 文案详细描述了权限冲突警告状态，因冲突解决 UI 描述精确且可复现，state_match 较高。", scored_by: "gpt:gpt-5.6-luna" },
      rights_status: "third_party_official", media_disposition: "thumbnail_only",
      captured_at: "2026-07-20T11:00:00Z", image_path_available: false,
    },
  ],
};

// M2 · Mapping cards — pre-filled for cells with SHORTLIST_READY coverage
export const mockMappingCards: Record<string, MappingCard> = {
  g2: {
    id: "mc-g2",
    cell_id: "g2",
    intent_definition: "首次为新成员分配角色时，了解每个角色能做什么、不能做什么",
    inclusion_criteria: "角色选择界面、权限清单、邀请弹窗中的角色预览",
    exclusion_criteria: "定价页、营销文案",
    anchor_screenshot_asset_id: null,
    version: 1,
    is_complete: true,
    created_by: null,
    reviewed_by: null,
    created_at: now,
    updated_at: now,
  },
  g4: {
    id: "mc-g4",
    cell_id: "g4",
    intent_definition: "遇到权限冲突时，理解冲突原因并找到解决路径",
    inclusion_criteria: "权限冲突警告界面、解决操作步骤",
    exclusion_criteria: "一般性帮助文档",
    anchor_screenshot_asset_id: null,
    version: 1,
    is_complete: true,
    created_by: null,
    reviewed_by: null,
    created_at: now,
    updated_at: now,
  },
};

// L3 · Insights (mutable store — persists across mock API calls) ---------------

export const mockInsights: Insight[] = [
  {
    id: "ins-0001-0000-0000-0000-000000000001",
    cell_id: "g2",
    competitor_id: "c1000000-0000-0000-0000-000000000001",
    claim: "在为新成员分配访问权限的场景中，Linear 将角色选择与权限明细实时展开绑定在同一视图内，使分配者在不离开决策上下文的情况下完成「角色→具体能力」核对，跳转次数为 0。",
    analysis: "认知成本降低：角色名是抽象标签，把每项权限以离散开关逐条呈现，等于将抽象标签即时翻译成可观测的能力清单。操作成本降低：选择与核对发生在同一容器内，消除往返路径。决策成本降低：开关的开/关状态提供二值化可扫描的边界信号。",
    recommendation: "在角色/权限分配的选择控件旁，绑定一个随选中项实时刷新的权限明细区，用离散开/关状态逐条列出关键能力（读/写/删/管理）。",
    design_principle: "决策触发点与决策依据信息同屏共置（Inline Consequence Preview）：凡用户在做选择前需查阅该选项后果/属性，就应将该信息直接内联展示在选择控件旁，目标为跳转次数 0。",
    limits: "权限项超过 20 条时逐条展开可能增加扫描负担；角色权限完全不可修改时须用只读样式避免歧义。",
    source_observation_ids: [],
    confidence: "medium",
    generated_by: "mock",
    is_draft: false,
    created_at: now,
    updated_at: now,
  },
  {
    id: "ins-0002-0000-0000-0000-000000000002",
    cell_id: "g2",
    competitor_id: "c1000000-0000-0000-0000-000000000002",
    claim: "Notion 在邀请人数超出席位限制时，在阻断提示内同时呈现「当前已用/总量」和「升级入口」，使用户在同一步骤内完成「感知边界→决策升级」闭环，避免死胡同体验。",
    analysis: "资源限制阻断的核心矛盾：用户被迫中断流程但无法在当前页面解决问题。Notion 的方案把「感知边界」和「解决出口」共置，将死胡同变成可继续的分支。",
    recommendation: "当触发资源限制阻断时，提示框内包含：当前消耗量/总配额 + 主要升级CTA + 次要的「移除现有成员」选项。",
    design_principle: "资源限制阻断应同时告知边界+提供解决路径（No Dead-end Error States）：任何阻断页面必须至少包含一个可操作的解决出口，避免用户无路可走。",
    limits: "仅适用于席位/配额类限制；纯权限不足的情况（用户无法升级）应改为联系管理员的引导，否则升级CTA会造成误导。",
    source_observation_ids: [],
    confidence: "medium",
    generated_by: "mock",
    is_draft: false,
    created_at: now,
    updated_at: now,
  },
  {
    id: "ins-0003-0000-0000-0000-000000000003",
    cell_id: "g1",
    competitor_id: "c1000000-0000-0000-0000-000000000001",
    claim: "Linear 的邀请弹窗在用户输入邮箱后立即显示「工作区已有该成员」的内联提示，阻止重复邀请，减少管理员处理重复席位占用的后续成本。",
    analysis: "表单验证的时机选择影响修复成本：提交后提示比输入时提示需要更多步骤来修正错误。Linear 使用实时校验将错误修复时机前移，符合尼尔森「帮助用户识别和从错误中恢复」原则。",
    recommendation: "邀请表单在用户输入邮箱的 onBlur 事件时，调用轻量 API 检查邮箱是否已存在，存在则立即显示内联提示而非等待提交。",
    design_principle: "错误感知时机越靠前，修复成本越低。表单字段的状态校验应尽可能在用户完成输入时（而非提交时）给出反馈。",
    limits: "实时 API 校验会增加后端请求量，需对邮箱输入做 debounce（建议 500ms）；离线或 API 响应慢时需有降级策略（不阻断提交）。",
    source_observation_ids: [],
    confidence: "low",
    generated_by: "mock",
    is_draft: true,
    created_at: now,
    updated_at: now,
  },
];

// L5 · Reports -----------------------------------------------------------------

export const mockReportBody = `# 权限管理场景 · 竞品设计标杆报告

## 核心洞察

共分析 **2** 条高置信洞察，均来自「首次配置 × 权限分配」场景。

---

### 洞察 1 · 角色选择与权限预览同屏联动（Linear）

**结论**
在为新成员分配访问权限的场景中，将角色选择与该角色权限明细的实时展开绑定在同一视图内，使分配者在不离开当前决策上下文的情况下完成「角色→具体能力」的核对，页面跳转次数为 0。

**设计原则**
决策触发点与决策依据信息同屏共置（Inline Consequence Preview）：凡用户在做选择前需查阅该选项后果/属性，就应将该信息直接内联展示在选择控件旁，目标为跳转次数 0。

**建议**
在角色/权限分配的选择控件旁，绑定一个随选中项实时刷新的权限明细区，用离散开关逐条列出关键能力（读/写/删/管理），支持在预览区直接调整。

**适用限制**
权限项超过 20 条时逐条展开可能增加扫描负担；角色权限完全不可修改时须用只读样式避免歧义。

---

### 洞察 2 · 席位用尽时的阻断态设计（Notion）

**结论**
邀请人数超出席位限制时，若在阻断提示内同时呈现「当前已用/总量」和「升级入口」，用户感知到的受阻感显著低于仅显示错误消息的方案，因为用户在同一步骤内可完成「感知边界→决策升级」的闭环。

**设计原则**
资源限制阻断应同时告知边界+提供解决路径，避免死胡同，减少用户离开当前流程的次数。

**建议**
当触发资源限制阻断时，提示框内包含三个元素：当前消耗量/总配额、主要升级CTA、以及次要的「移除现有成员」选项。

---

## 可复用设计原则汇总

1. **Inline Consequence Preview** — 在选择控件旁同步渲染该选项展开后的离散能力清单
2. **No Dead-end Error States** — 阻断提示内永远包含至少一个可操作的解决出口

---

*本报告由 UX 设计标杆工具自动生成，基于已采集的真实证据。置信度仅反映观察充分程度，不代表绝对结论。*
`;

export const mockReports: Report[] = [
  {
    id: "rpt-0001-0000-0000-0000-000000000001",
    title: "权限管理场景 · 设计评审 · 设计师",
    audience: "designer",
    format_type: "review_15min",
    source_insight_ids: ["ins-0001-0000-0000-0000-000000000001"],
    body_markdown: mockReportBody,
    generated_by: "mock",
    created_at: now,
    updated_at: now,
  },
];
