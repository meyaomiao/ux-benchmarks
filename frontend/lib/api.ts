// API client. Falls back to mock data when NEXT_PUBLIC_USE_MOCK !== "false".
// Backend endpoints mirror docs/collection-phase-spec-v2.md (M0 / M1).

import type { Competitor, LexiconEntry, GridCell, ListResponse, CoverageRow, ShortlistResponse, MappingCard, QueueItem, Insight, Report, ReportAudience, ReportFormat } from "./types";
import { mockCompetitors, mockLexicon, mockCells, mockCoverage, mockShortlist, mockMappingCards, mockReports, mockReportBody, mockInsights } from "./mock";

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

  // M1 · Create a new grid cell
  createCell: async (data: { jtbd: string; journey_stage: string; page_state: string; value_score?: number; cell_key?: string }): Promise<GridCell> => {
    if (USE_MOCK) {
      await new Promise((r) => setTimeout(r, 200));
      return {
        ...data,
        id: crypto.randomUUID(),
        cell_key: data.cell_key || [data.jtbd, data.journey_stage, data.page_state].join('.').replace(/[^a-z0-9.]+/gi, '-').toLowerCase().slice(0, 80),
        version: 1,
        status: 'active',
        requires_review: false,
        value_score: data.value_score ?? 0.5,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      } as GridCell;
    }
    const res = await fetch('/api/v1/m1/cells', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<GridCell>;
  },

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

  // M3 · Collection queue
  getQueueStatus: () =>
    get<QueueItem[]>("/m3/queue", []),

  manualPin: async (cellId: string, competitorId: string): Promise<{ ok: boolean }> => {
    if (USE_MOCK) {
      await new Promise((r) => setTimeout(r, 200));
      return { ok: true };
    }
    const res = await fetch(`${BASE}/m3/queue/pin`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cell_id: cellId, competitor_id: competitorId }),
    });
    if (!res.ok) throw new Error(`manualPin failed: ${res.status}`);
    return res.json();
  },

  // M5 · Metrics + reports (#29 #30)
  getCoverageMetrics: () =>
    get<Record<string, unknown>>("/m5/metrics", {
      pipeline: { total_assets_in_shortlist: 0, total_accepted: 0, total_rejected: 0, adoption_rate: null, adoption_rate_healthy: false },
      coverage: { total_cell_competitor_pairs: 0, shortlist_ready: 0, saturated: 0, by_status: {}, avg_confidence: 0 },
    }),

  generateReport: async () => {
    if (USE_MOCK) { await new Promise(r => setTimeout(r, 300)); return { generated_at: new Date().toISOString(), note: "mock" }; }
    const res = await fetch(`${BASE}/m5/reports/generate`, { method: "POST" });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  downloadReport: async () => {
    if (USE_MOCK) return "# UX Coverage Report\n\nMock mode — no real data.";
    const res = await fetch(`${BASE}/m5/reports/export.md`);
    if (!res.ok) throw new Error(await res.text());
    return res.text();
  },

  // M2 · Mapping cards
  getMappingCard: async (cellId: string): Promise<MappingCard | null> => {
    if (USE_MOCK) {
      await new Promise((r) => setTimeout(r, 150));
      return mockMappingCards[cellId] ?? null;
    }
    const res = await fetch(`${BASE}/m2/mapping-cards/${cellId}`);
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`getMappingCard failed: ${res.status}`);
    return res.json();
  },

  // L3 · Insights
  listInsights: async (cellId?: string, competitorId?: string): Promise<Insight[]> => {
    if (USE_MOCK) {
      await new Promise(r => setTimeout(r, 150));
      let items = mockInsights;
      if (cellId) items = items.filter(i => i.cell_id === cellId);
      if (competitorId) items = items.filter(i => i.competitor_id === competitorId);
      return [...items];
    }
    const params = new URLSearchParams();
    if (cellId) params.set("cell_id", cellId);
    if (competitorId) params.set("competitor_id", competitorId);
    const res = await fetch(`/api/v1/m4/insights?${params}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  generateInsight: async (cellId: string, competitorId: string): Promise<Insight> => {
    if (USE_MOCK) {
      await new Promise(r => setTimeout(r, 1200));
      const comp = mockCompetitors.find(c => c.id === competitorId);
      const compName = comp?.canonical_name ?? "竞品";
      const existing = mockInsights.find(
        i => i.cell_id === cellId && i.competitor_id === competitorId
      );
      if (existing) return existing; // idempotent — don't duplicate
      const ins: Insight = {
        id: crypto.randomUUID(),
        cell_id: cellId,
        competitor_id: competitorId,
        claim: `在该场景下，${compName} 通过明确的状态可见性与即时反馈机制，使用户在执行关键操作前即可预知后果，从而降低误操作概率。`,
        analysis: "状态可见性（Nielsen 启发式 #1）：系统将当前状态和操作后果清晰呈现，减少用户的认知负担与决策不确定性。",
        recommendation: `参考 ${compName} 的交互模式，在对应场景中将操作后果信息内联展示在操作控件旁，减少用户跳转。`,
        design_principle: "让操作后果在执行前可见（Visible Consequences）：凡涉及不可逆或高影响操作，系统应在确认步骤前就呈现其后果。",
        limits: "当后果信息过于复杂时，内联展示可能造成视觉噪音；需根据信息量决定是内联展示还是展开面板。",
        source_observation_ids: [],
        confidence: "hypothesis",
        generated_by: "mock",
        is_draft: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      mockInsights.push(ins); // persist to shared mock store
      return ins;
    }
    const res = await fetch("/api/v1/m4/insights/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cell_id: cellId, competitor_id: competitorId }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  updateInsight: async (insightId: string, data: Partial<Insight>): Promise<Insight> => {
    if (USE_MOCK) {
      await new Promise(r => setTimeout(r, 150));
      return { id: insightId, ...data } as Insight;
    }
    const res = await fetch(`/api/v1/m4/insights/${insightId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // L5 · Reports
  listReports: async (): Promise<Report[]> => {
    if (USE_MOCK) {
      await new Promise(r => setTimeout(r, 150));
      return mockReports;
    }
    const res = await fetch(`${BASE}/reports`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  composeReport: async (payload: {
    insight_ids: string[];
    audience: ReportAudience;
    format_type: ReportFormat;
    title?: string;
  }): Promise<Report> => {
    if (USE_MOCK) {
      await new Promise(r => setTimeout(r, 2500));
      const now = new Date().toISOString();
      const labels: Record<string, string> = {
        management: "管理层", designer: "设计师", pm: "产品经理",
      };
      const fmts: Record<string, string> = {
        summary_5min: "5分钟摘要", review_15min: "设计评审",
        onepager: "单页总览", full: "完整报告",
      };
      const report: Report = {
        id: crypto.randomUUID(),
        title: payload.title || `竞品设计标杆 · ${fmts[payload.format_type]} · ${labels[payload.audience]}`,
        audience: payload.audience,
        format_type: payload.format_type,
        source_insight_ids: payload.insight_ids,
        body_markdown: mockReportBody,
        generated_by: "mock",
        created_at: now,
        updated_at: now,
      };
      mockReports.unshift(report);
      return report;
    }
    const res = await fetch(`${BASE}/reports`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  deleteReport: async (reportId: string): Promise<void> => {
    if (USE_MOCK) {
      const idx = mockReports.findIndex(r => r.id === reportId);
      if (idx >= 0) mockReports.splice(idx, 1);
      return;
    }
    const res = await fetch(`${BASE}/reports/${reportId}`, { method: "DELETE" });
    if (!res.ok) throw new Error(await res.text());
  },

  saveMappingCard: async (
    cellId: string,
    data: { intent_definition: string; inclusion_criteria?: string | null; exclusion_criteria?: string | null },
  ): Promise<MappingCard> => {
    if (USE_MOCK) {
      await new Promise((r) => setTimeout(r, 180));
      const existing = mockMappingCards[cellId];
      const now = new Date().toISOString();
      const card: MappingCard = {
        id: existing?.id ?? `mc-${cellId}`,
        cell_id: cellId,
        intent_definition: data.intent_definition,
        inclusion_criteria: data.inclusion_criteria ?? null,
        exclusion_criteria: data.exclusion_criteria ?? null,
        anchor_screenshot_asset_id: existing?.anchor_screenshot_asset_id ?? null,
        version: (existing?.version ?? 0) + 1,
        is_complete: data.intent_definition.trim().length > 0 &&
          (!!data.inclusion_criteria?.trim() || !!data.exclusion_criteria?.trim()),
        created_by: existing?.created_by ?? null,
        reviewed_by: existing?.reviewed_by ?? null,
        created_at: existing?.created_at ?? now,
        updated_at: now,
      };
      mockMappingCards[cellId] = card;
      return card;
    }
    const existing = await api.getMappingCard(cellId);
    if (!existing) {
      const res = await fetch(`${BASE}/m2/mapping-cards`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cell_id: cellId, ...data }),
      });
      if (!res.ok) throw new Error(`createMappingCard failed: ${res.status}`);
      return res.json();
    }
    const res = await fetch(`${BASE}/m2/mapping-cards/${cellId}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(`patchMappingCard failed: ${res.status}`);
    return res.json();
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
