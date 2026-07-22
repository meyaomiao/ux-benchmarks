"use client";

import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type { GridCell, Competitor, Insight } from "@/lib/types";

//---- helpers ---------------------------------------------------------------

const CONFIDENCE_META: Record<
  Insight["confidence"],
  { label: string; cls: string }
> = {
  hypothesis: { label: "假设", cls: "bg-gray-100 text-gray-500" },
  low: { label: "低置信", cls: "bg-amber-50 text-amber-700 border border-amber-200" },
  medium: { label: "中置信", cls: "bg-indigo-50 text-indigo-700 border border-indigo-200" },
  high: { label: "高置信", cls: "bg-green-50 text-green-700 border border-green-200" },
};

// ---- InsightCard -----------------------------------------------------------

interface InsightCardProps {
  insight: Insight;
  competitorLabel: string;
  cellLabel: string;
  onSave: (updated: Insight) => void;
}

function InsightCard({ insight, competitorLabel, cellLabel, onSave }: InsightCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Partial<Insight>>({});
  const [saving, setSaving] = useState(false);

  function startEdit() {
    setDraft({
      claim: insight.claim,
      analysis: insight.analysis,
      recommendation: insight.recommendation,
      design_principle: insight.design_principle,
      limits: insight.limits,
      confidence: insight.confidence,
      is_draft: insight.is_draft,
    });
    setEditing(true);
  }

  async function handleSave() {
    setSaving(true);
    try {
      const updated = await api.updateInsight(insight.id, { ...draft, is_draft: false });
      onSave(updated);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  const conf = CONFIDENCE_META[insight.confidence];

  if (editing) {
    return (
      <div className="bg-white border border-indigo-200 rounded-xl p-5 space-y-3">
        <div className="flex items-center gap-2 mb-1">
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700 border border-indigo-100">
            {competitorLabel}
          </span>
          <span className="text-xs text-gray-400">{cellLabel}</span>
        </div>
        <label className="block">
          <span className="text-xs text-gray-500 mb-1 block">结论</span>
          <textarea
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-300"
            rows={3}
            value={draft.claim ?? ""}
            onChange={(e) => setDraft((d) => ({ ...d, claim: e.target.value }))}
          />
        </label>
        <label className="block">
          <span className="text-xs text-gray-500 mb-1 block">设计原则</span>
          <textarea
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-300"
            rows={2}
            value={draft.design_principle ?? ""}
            onChange={(e) => setDraft((d) => ({ ...d, design_principle: e.target.value }))}
          />
        </label>
        <label className="block">
          <span className="text-xs text-gray-500 mb-1 block">建议</span>
          <textarea
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-300"
            rows={2}
            value={draft.recommendation ?? ""}
            onChange={(e) => setDraft((d) => ({ ...d, recommendation: e.target.value }))}
          />
        </label>
        <label className="block">
          <span className="text-xs text-gray-500 mb-1 block">分析</span>
          <textarea
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-300"
            rows={2}
            value={draft.analysis ?? ""}
            onChange={(e) => setDraft((d) => ({ ...d, analysis: e.target.value }))}
          />
        </label>
        <label className="block">
          <span className="text-xs text-gray-500 mb-1 block">限制</span>
          <textarea
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-300"
            rows={1}
            value={draft.limits ?? ""}
            onChange={(e) => setDraft((d) => ({ ...d, limits: e.target.value }))}
          />
        </label>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500 flex-none">置信度</span>
          <select
            className="border border-gray-200 rounded-md px-2 py-1 text-xs text-gray-700 focus:outline-none"
            value={draft.confidence ?? insight.confidence}
            onChange={(e) =>
              setDraft((d) => ({ ...d, confidence: e.target.value as Insight["confidence"] }))
            }
          >
            <option value="hypothesis">假设</option>
            <option value="low">低</option>
            <option value="medium">中</option>
            <option value="high">高</option>
          </select>
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <button
            onClick={() => setEditing(false)}
            className="text-xs px-3 py-1.5 rounded-md border border-gray-200 text-gray-500 hover:bg-gray-50"
          >
            取消
          </button>
          <button
            disabled={saving}
            onClick={handleSave}
            className="text-xs px-3 py-1.5 rounded-md bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </div>
    );
  }
  // View mode
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5">
      {/* Header row */}
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700 border border-indigo-100">
          {competitorLabel}
        </span>
        <span className="text-xs text-gray-400 truncate flex-1">{cellLabel}</span>
        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-medium ${conf.cls}`}>
          {conf.label}
        </span>
        {insight.is_draft && (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-gray-100 text-gray-400 border border-gray-200">
            草稿
          </span>
        )}
        <button
          onClick={startEdit}
          className="ml-auto text-xs text-gray-400 hover:text-indigo-600 px-2 py-0.5 rounded hover:bg-indigo-50 transition-colors"
        >
          编辑
        </button>
      </div>

      {/* Claim — prominent */}
      <div className="mb-3">
        <div className="text-[10px] text-gray-400 mb-1 uppercase tracking-wider">结论</div>
        <p className="text-sm font-medium text-gray-800 leading-relaxed">{insight.claim}</p>
      </div>

      {/* Design principle — indigo-tinted box */}
      {insight.design_principle && (
        <div className="bg-indigo-50 border border-indigo-100 rounded-lg px-4 py-3 mb-3">
          <div className="text-[10px] text-indigo-400 mb-1 uppercase tracking-wider">设计原则</div>
          <p className="text-sm text-indigo-800 leading-relaxed">{insight.design_principle}</p>
        </div>
      )}

      {/* Recommendation */}
      {insight.recommendation && (
        <div className="mb-3">
          <div className="text-[10px] text-gray-400 mb-1 uppercase tracking-wider">建议</div>
          <p className="text-sm text-gray-700 leading-relaxed">{insight.recommendation}</p>
        </div>
      )}

      {/* Collapsible: analysis + limits */}
      {(insight.analysis || insight.limits) && (
        <div className="border-t border-gray-100 pt-3">
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1"
          >
            <span>{expanded ? "▲" : "▼"}</span>
            {expanded ? "收起" : "展开分析与限制"}
          </button>
          {expanded && (
            <div className="mt-3 space-y-3">
              {insight.analysis && (
                <div>
                  <div className="text-[10px] text-gray-400 mb-1 uppercase tracking-wider">分析</div>
                  <p className="text-xs text-gray-600 leading-relaxed">{insight.analysis}</p>
                </div>
              )}
              {insight.limits && (
                <div>
                  <div className="text-[10px] text-gray-400 mb-1 uppercase tracking-wider">限制</div>
                  <p className="text-xs text-gray-600 leading-relaxed">{insight.limits}</p>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
// ---- Page ------------------------------------------------------------------

export default function InsightsPage() {
  const searchParams = useSearchParams();
  const [cells, setCells] = useState<GridCell[]>([]);
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [insights, setInsights] = useState<Insight[]>([]);
  const [loading, setLoading] = useState(true);

  // Generate form state
  const [genCellId, setGenCellId] = useState<string>("");
  const [genCompetitorId, setGenCompetitorId] = useState<string>("");
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);

  useEffect(() => {
    // Carry cell+competitor from the review step: /insights?cell_id=…&competitor_id=…
    // preselects the generate form so the user can generate immediately.
    const paramCell = searchParams.get("cell_id");
    const paramComp = searchParams.get("competitor_id");
    Promise.all([api.listCells(), api.listCompetitors(), api.listInsights()])
      .then(([g, c, ins]) => {
        setCells(g.items);
        const confirmed = c.items.filter((x) => x.status === "confirmed");
        setCompetitors(confirmed);
        setInsights(ins);
        const cellExists = g.items.some((x) => x.id === paramCell);
        const compExists = confirmed.some((x) => x.id === paramComp);
        if (paramCell && cellExists) setGenCellId(paramCell);
        else if (g.items.length > 0) setGenCellId(g.items[0].id);
        if (paramComp && compExists) setGenCompetitorId(paramComp);
        else if (confirmed.length > 0) setGenCompetitorId(confirmed[0].id);
      })
      .finally(() => setLoading(false));
  }, [searchParams]);

  const cellMap = cells.reduce<Record<string, GridCell>>(
    (acc, c) => { acc[c.id] = c; return acc; },
    {}
  );
  const competitorMap = competitors.reduce<Record<string, Competitor>>(
    (acc, c) => { acc[c.id] = c; return acc; },
    {}
  );

  function getCellLabel(cellId: string): string {
    const cell = cellMap[cellId];
    if (!cell) return cellId.slice(0, 8) + "…";
    return `${cell.page_state} · ${cell.journey_stage}`;
  }

  function getCompetitorLabel(competitorId: string): string {
    return competitorMap[competitorId]?.canonical_name ?? competitorId.slice(0, 8) + "…";
  }

  async function handleGenerate() {
    if (!genCellId || !genCompetitorId) return;
    setGenerating(true);
    setGenError(null);
    try {
      const insight = await api.generateInsight(genCellId, genCompetitorId);
      setInsights((prev) => [insight, ...prev]);
    } catch (e) {
      setGenError(e instanceof Error ? e.message : "生成失败");
    } finally {
      setGenerating(false);
    }
  }

  const handleSave = useCallback((updated: Insight) => {
    setInsights((prev) => prev.map((i) => (i.id === updated.id ? updated : i)));
  }, []);

  // Group insights by cell_id, preserving insertion order
  const groupedCellIds: string[] = [];
  const grouped: Record<string, Insight[]> = {};
  for (const ins of insights) {
    if (!grouped[ins.cell_id]) {
      groupedCellIds.push(ins.cell_id);
      grouped[ins.cell_id] = [];
    }
    grouped[ins.cell_id].push(ins);
  }
  return (
    <div>
      <div className="flex items-start justify-between mb-1">
        <div className="text-gray-500 text-xs">L3 · 洞察库</div>
        {insights.length > 0 && (
          <a
            href="/reports"
            className="text-xs px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors font-medium"
          >
            下一步：重组报告 →
          </a>
        )}
      </div>
      <h1 className="text-xl font-bold mb-1">洞察库</h1>
      <p className="text-gray-500 text-sm mb-8 max-w-2xl">
        从证据中提炼的设计洞察，可迁移到内部产品
      </p>

      {/* Generate section */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 mb-8 max-w-2xl">
        <div className="text-sm font-semibold text-gray-700 mb-4">生成新洞察</div>
        <div className="flex items-end gap-3 flex-wrap">
          <label className="flex-1 min-w-[160px]">
            <span className="block text-xs text-gray-500 mb-1">场景格子</span>
            <select
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-300"
              value={genCellId}
              onChange={(e) => setGenCellId(e.target.value)}
              disabled={loading || generating}
            >
              {cells.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.page_state} · {c.journey_stage}
                </option>
              ))}
            </select>
          </label>
          <label className="flex-1 min-w-[140px]">
            <span className="block text-xs text-gray-500 mb-1">竞品</span>
            <select
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-300"
              value={genCompetitorId}
              onChange={(e) => setGenCompetitorId(e.target.value)}
              disabled={loading || generating}
            >
              {competitors.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.canonical_name}
                </option>
              ))}
            </select>
          </label>
          <button
            onClick={handleGenerate}
            disabled={!genCellId || !genCompetitorId || generating}
            className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors flex-none"
          >
            {generating ? "AI 生成中…" : "AI 生成洞察"}
          </button>
        </div>
        {genError && (
          <p className="mt-2 text-xs text-red-500">{genError}</p>
        )}
      </div>

      {/* Insights list */}
      {loading ? (
        <div className="py-12 text-center text-gray-400 text-sm">加载中…</div>
      ) : insights.length === 0 ? (
        <div className="bg-white border border-gray-200 rounded-xl p-12 text-center max-w-2xl">
          <div className="text-gray-400 text-sm">暂无洞察，从上方选择格子和竞品生成第一条洞察。</div>
        </div>
      ) : (
        <div className="space-y-8 max-w-2xl">
          {groupedCellIds.map((cellId) => (
            <div key={cellId}>
              {/* Cell group header */}
              <div className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 flex-none" />
                {getCellLabel(cellId)}
                <span className="text-gray-300">{grouped[cellId].length} 条洞察</span>
              </div>
              <div className="space-y-4">
                {grouped[cellId].map((insight) => (
                  <InsightCard
                    key={insight.id}
                    insight={insight}
                    competitorLabel={getCompetitorLabel(insight.competitor_id)}
                    cellLabel={getCellLabel(insight.cell_id)}
                    onSave={handleSave}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

