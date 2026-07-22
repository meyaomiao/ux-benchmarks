// Mock data — used when NEXT_PUBLIC_USE_MOCK !== "false" (default: on).
// Lets the UI render fully without a running backend.

import type { Competitor, LexiconEntry, GridCell, CoverageRow, MappingCard, ShortlistItem } from "./types";

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
      snippet: "Navigate to Settings › Members › Invite people. Enter email addresses and select a role — Member, Admin, or Guest. You can preview each role's permissions before sending.",
      evidence_type: "observed", ai_score: 0.87,
      ai_score_breakdown: { state_match: 0.92, product_match: 1.0, version_recency: 0.85, evidence_directness: 0.9, fidelity: 0.7, reasoning: "Step-by-step doc shows the invite modal, role selector, and permission preview. Precisely describes the target UI flow. Marked observed because doc content is reproducible.", scored_by: "claude-vision" },
      rights_status: "third_party_official", media_disposition: "thumbnail_only",
      captured_at: "2026-07-20T15:30:00Z", image_path_available: false,
    },
    {
      id: "a0002", cell_id: "g1", competitor_id: "c1000000-0000-0000-0000-000000000001",
      source_url: "https://app.storylane.io/demo/linear-invite-flow",
      source_type: "interactive_demo", title: "Linear product tour — Invite & Permissions",
      snippet: "Guided product tour step 2 of 7: the invite modal with role dropdown expanded. Permissions panel visible on the right.",
      evidence_type: "observed", ai_score: 0.93,
      ai_score_breakdown: { state_match: 0.95, product_match: 1.0, version_recency: 0.92, evidence_directness: 1.0, fidelity: 0.8, reasoning: "Screenshot from interactive demo shows the exact invite modal with expanded role dropdown and real-time permission preview panel. Target state is directly visible.", scored_by: "claude-vision" },
      rights_status: "embedded_third_party", media_disposition: "thumbnail_only",
      captured_at: "2026-07-20T16:00:00Z", image_path_available: true,
    },
  ],
  "g1|c1000000-0000-0000-0000-000000000003": [
    {
      id: "a0003", cell_id: "g1", competitor_id: "c1000000-0000-0000-0000-000000000003",
      source_url: "https://www.notion.so/help/add-members-to-your-workspace",
      source_type: "help_docs", title: "Add members to your workspace — Notion Help",
      snippet: "Click Settings & members in the left sidebar. Select Members, then Invite members. Type in email address, choose a role (Workspace owner, Member, or Guest).",
      evidence_type: "observed", ai_score: 0.74,
      ai_score_breakdown: { state_match: 0.78, product_match: 1.0, version_recency: 0.7, evidence_directness: 0.8, fidelity: 0.6, reasoning: "Describes the invite flow correctly but does not show permission preview — role list with no contextual permission display. Lower state_match than Linear.", scored_by: "claude-vision" },
      rights_status: "third_party_official", media_disposition: "thumbnail_only",
      captured_at: "2026-07-19T10:00:00Z", image_path_available: false,
    },
  ],
  "g2|c1000000-0000-0000-0000-000000000002": [
    {
      id: "a0004", cell_id: "g2", competitor_id: "c1000000-0000-0000-0000-000000000002",
      source_url: "https://help.asana.com/hc/en-us/articles/roles",
      source_type: "help_docs", title: "Roles and permissions in Asana",
      snippet: "Asana offers three roles: Guest, Member, and Admin. Guests can only access projects they're invited to. Members can create and edit projects. Admins manage billing and members.",
      evidence_type: "claimed", ai_score: 0.41,
      ai_score_breakdown: { state_match: 0.3, product_match: 1.0, version_recency: 0.6, evidence_directness: 0.5, fidelity: 0.4, reasoning: "Text describes roles but shows no UI. The role-selection interface itself is not visible. Classified as claimed because no screenshot of the role picker exists in this article.", scored_by: "claude-vision" },
      rights_status: "third_party_official", media_disposition: "thumbnail_only",
      captured_at: "2026-07-21T09:00:00Z", image_path_available: false,
    },
    {
      id: "a0005", cell_id: "g2", competitor_id: "c1000000-0000-0000-0000-000000000002",
      source_url: "https://app.arcade.software/share/asana-permissions",
      source_type: "interactive_demo", title: "Asana demo — Roles & Access",
      snippet: "Product tour step 4: Member role selected. Permission scope shown as 'Can edit all projects in this team'.",
      evidence_type: "observed", ai_score: 0.88,
      ai_score_breakdown: { state_match: 0.9, product_match: 1.0, version_recency: 0.9, evidence_directness: 1.0, fidelity: 0.75, reasoning: "Screenshot from interactive demo clearly shows the role selection state with permission scope text visible. Strong state_match — the target UI is directly shown.", scored_by: "claude-vision" },
      rights_status: "embedded_third_party", media_disposition: "thumbnail_only",
      captured_at: "2026-07-21T09:30:00Z", image_path_available: true,
    },
  ],
  "g4|c1000000-0000-0000-0000-000000000001": [
    {
      id: "a0006", cell_id: "g4", competitor_id: "c1000000-0000-0000-0000-000000000001",
      source_url: "https://help.linear.app/docs/permission-conflict",
      source_type: "help_docs", title: "Handling permission conflicts — Linear",
      snippet: "If a member's role conflicts with a project-level override, Linear displays a yellow warning banner: 'This member's workspace role (Guest) conflicts with their project permission (Editor)'. Click Resolve to choose which takes precedence.",
      evidence_type: "observed", ai_score: 0.81,
      ai_score_breakdown: { state_match: 0.85, product_match: 1.0, version_recency: 0.8, evidence_directness: 0.85, fidelity: 0.65, reasoning: "Describes the permission conflict warning state in detail with specific UI copy. High state_match because the conflict-resolution UI is described precisely and reproducibly.", scored_by: "claude-vision" },
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
