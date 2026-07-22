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
};
