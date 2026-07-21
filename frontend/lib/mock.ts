// Mock data — used when NEXT_PUBLIC_USE_MOCK !== "false" (default: on).
// Lets the UI render fully without a running backend.

import type { Competitor, LexiconEntry, GridCell, CoverageRow } from "./types";

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
