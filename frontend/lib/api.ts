// API client. Falls back to mock data when NEXT_PUBLIC_USE_MOCK !== "false".
// Backend endpoints mirror docs/collection-phase-spec-v2.md (M0 / M1).

import type { Competitor, LexiconEntry, GridCell, ListResponse, CoverageRow, ShortlistResponse } from "./types";
import { mockCompetitors, mockLexicon, mockCells, mockCoverage, mockShortlist } from "./mock";

const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK !== "false";
const BASE = "/api/v1";

function paginate<T>(items: T[]): ListResponse<T> {
  return { items, total: items.length, limit: items.length, offset: 0, has_next: false };
}

async function get<T>(path: string, fallback: T): Promise<T> {
  if (USE_MOCK) {
    // Simulate a tiny latency so loading states are visible.
    await new Promise((r) => setTimeout(r, 150));
    return fallback;
  }
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export const api = {
  useMock: USE_MOCK,

  // M0 · Competitors
  listCompetitors: () =>
    get<ListResponse<Competitor>>("/m0/competitors", paginate(mockCompetitors)),

  // M0 · Lexicon
  listLexicon: () =>
    get<ListResponse<LexiconEntry>>("/m0/lexicon", paginate(mockLexicon)),

  // M1 · Grid cells
  listCells: () =>
    get<ListResponse<GridCell>>("/m1/cells", paginate(mockCells)),

  // M5 · Coverage
  getCoverage: () =>
    get<CoverageRow[]>("/m5/coverage", mockCoverage),

  // M4 · Shortlist (evidence awaiting review)
  getShortlist: (cellId: string, competitorId: string) =>
    get<ShortlistResponse>(
      `/m4/shortlist/${cellId}/${competitorId}`,
      { items: mockShortlist[`${cellId}|${competitorId}`] ?? [], total: (mockShortlist[`${cellId}|${competitorId}`] ?? []).length },
    ),

  // M4 · Review actions. In mock mode these are no-ops that resolve immediately
  // so the UI flow is exercisable without a backend.
  acceptAsset: async (assetId: string, observationFields: Record<string, unknown> = {}) => {
    if (USE_MOCK) { await new Promise((r) => setTimeout(r, 120)); return { ok: true, asset_id: assetId }; }
    const res = await fetch(`${BASE}/m4/shortlist/accept`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ asset_id: assetId, observation_fields: observationFields }),
    });
    if (!res.ok) throw new Error(`accept failed: ${res.status}`);
    return res.json();
  },
  rejectAsset: async (assetId: string, reason?: string) => {
    if (USE_MOCK) { await new Promise((r) => setTimeout(r, 120)); return { ok: true, asset_id: assetId }; }
    const res = await fetch(`${BASE}/m4/shortlist/reject`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ asset_id: assetId, reason }),
    });
    if (!res.ok) throw new Error(`reject failed: ${res.status}`);
    return res.json();
  },

  // M1 · Create a single grid cell
  createCell: async (input: GeneratedCell): Promise<GridCell> => {
    if (USE_MOCK) {
      await new Promise((r) => setTimeout(r, 120));
      const slug = (s: string) =>
        s.toLowerCase().replace(/\s+/g, "-").replace(/[^\w-]/g, "").slice(0, 40);
      const now = new Date().toISOString();
      return {
        id: `g-${Math.random().toString(36).slice(2, 10)}`,
        cell_key: `${slug(input.jtbd)}.${slug(input.journey_stage)}.${slug(input.page_state)}`,
        jtbd: input.jtbd,
        journey_stage: input.journey_stage,
        page_state: input.page_state,
        value_score: input.value_score,
        version: 1,
        status: "active",
        requires_review: false,
        created_at: now,
        updated_at: now,
      };
    }
    const res = await fetch(`${BASE}/m1/cells`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
    if (!res.ok) throw new Error(`createCell failed: ${res.status}`);
    return res.json() as Promise<GridCell>;
  },

  // M1 · AI grid generation
  generateGrid: async (category: string, knownProducts: string[] = []): Promise<GridGenerationResult> => {
    if (USE_MOCK) {
      await new Promise((r) => setTimeout(r, 1800));
      return {
        category,
        jtbd_tasks: ["邀请协作者+权限分级", "创建首个项目/工作区", "追踪任务进度", "设置通知与提醒"],
        journey_stages: ["首次配置", "日常使用", "异常处理"],
        cells: [
          { jtbd: "邀请协作者+权限分级", journey_stage: "首次配置", page_state: "角色选择页", value_score: 0.9 },
          { jtbd: "邀请协作者+权限分级", journey_stage: "首次配置", page_state: "权限冲突提示（异常态）", value_score: 0.85 },
          { jtbd: "邀请协作者+权限分级", journey_stage: "首次配置", page_state: "邀请弹窗（空状态）", value_score: 0.8 },
          { jtbd: "创建首个项目/工作区", journey_stage: "首次配置", page_state: "空状态引导页", value_score: 0.8 },
          { jtbd: "追踪任务进度", journey_stage: "日常使用", page_state: "看板视图", value_score: 0.6 },
          { jtbd: "追踪任务进度", journey_stage: "异常处理", page_state: "数据加载失败态", value_score: 0.75 },
          { jtbd: "设置通知与提醒", journey_stage: "首次配置", page_state: "通知权限请求", value_score: 0.7 },
        ],
        total: 7,
        generated_by: "mock",
      };
    }
    const res = await fetch("/api/v1/m1/cells/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category, known_products: knownProducts }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<GridGenerationResult>;
  },
};

// Types for AI grid generation (exported for use in components)
export interface GeneratedCell {
  jtbd: string;
  journey_stage: string;
  page_state: string;
  value_score: number;
}
export interface GridGenerationResult {
  category: string;
  jtbd_tasks: string[];
  journey_stages: string[];
  cells: GeneratedCell[];
  total: number;
  generated_by: string;
}
