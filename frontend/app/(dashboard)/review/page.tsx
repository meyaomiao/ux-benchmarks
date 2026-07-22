"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { EvidenceDrawer } from "@/components/coverage/evidence-drawer";
import type { GridCell, Competitor, CoverageRow } from "@/lib/types";

interface SelectedCell {
  cellId: string;
  competitorId: string;
  cellLabel: string;
  competitorLabel: string;
}

export default function ReviewPage() {
  const router = useRouter();
  const [cells, setCells] = useState<GridCell[]>([]);
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [coverage, setCoverage] = useState<CoverageRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<SelectedCell | null>(null);

  useEffect(() => {
    Promise.all([api.listCells(), api.listCompetitors(), api.getCoverage()])
      .then(([g, c, cov]) => {
        setCells(g.items);
        setCompetitors(c.items.filter((x) => x.status === "confirmed"));
        setCoverage(cov);
      })
      .finally(() => setLoading(false));
  }, []);

  // Lookup maps built from loaded data
  const cellMap = cells.reduce<Record<string, GridCell>>(
    (acc, c) => { acc[c.id] = c; return acc; },
    {}
  );
  const competitorMap = competitors.reduce<Record<string, Competitor>>(
    (acc, c) => { acc[c.id] = c; return acc; },
    {}
  );

  // Filtered rows
  const shortlistRows = coverage
    .filter((r) => r.status === "SHORTLIST_READY")
    .slice()
    .sort((a, b) => b.coverage_confidence - a.coverage_confidence);
  const partialCount = coverage.filter((r) => r.status === "PARTIAL").length;
  // Cells whose evidence has been accepted (SATURATED) are ready for insight generation.
  const saturatedRows = coverage.filter((r) => r.status === "SATURATED");

  function getCellLabel(cellId: string): string {
    const cell = cellMap[cellId];
    if (!cell) return cellId.slice(0, 8) + "…";
    return `${cell.page_state} · ${cell.journey_stage}`;
  }

  function getCompetitorLabel(competitorId: string): string {
    return competitorMap[competitorId]?.canonical_name ?? competitorId.slice(0, 8) + "…";
  }

  return (
    <div>
      <div className="text-gray-500 text-xs mb-1">M5 · 审核队列</div>
      <h1 className="text-xl font-bold mb-1">素材审核</h1>
      <p className="text-gray-500 text-sm mb-6 max-w-2xl">
        待人工确认的采集证据，审核通过后进入证据库
      </p>

      {loading ? (
        <div className="p-8 text-center text-gray-400 text-sm">加载中…</div>
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 gap-4 mb-8 max-w-md">
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
              <div className="text-2xl font-bold text-amber-700">{shortlistRows.length}</div>
              <div className="text-xs text-amber-600 mt-1">待审核格子数</div>
            </div>
            <div className="bg-white border border-gray-200 rounded-xl p-4">
              <div className="text-2xl font-bold text-gray-700">{partialCount}</div>
              <div className="text-xs text-gray-500 mt-1">已有部分证据</div>
            </div>
          </div>

          {/* Next-step banner — appears once some evidence is accepted */}
          {saturatedRows.length > 0 && (
            <div className="mb-6 flex items-center justify-between gap-3 bg-green-50 border border-green-200 rounded-xl px-4 py-3">
              <span className="text-sm text-green-800">
                已有 <span className="font-semibold">{saturatedRows.length}</span> 个格子通过审核，可以生成洞察了
              </span>
              <button
                onClick={() => {
                  const r = saturatedRows[0];
                  router.push(`/insights?cell_id=${r.cell_id}&competitor_id=${r.competitor_id}`);
                }}
                className="flex-none text-sm px-4 py-2 rounded-lg bg-green-600 text-white hover:bg-green-700 transition-colors font-medium"
              >
                下一步：生成洞察 →
              </button>
            </div>
          )}

          {/* Review list */}
          {shortlistRows.length === 0 ? (
            <div className="bg-white border border-gray-200 rounded-xl p-12 text-center text-gray-400 text-sm">
              暂无待审核的格子
            </div>
          ) : (
            <div className="space-y-3">
              {shortlistRows.map((row) => {
                const cell = cellMap[row.cell_id];
                const cellLabel = getCellLabel(row.cell_id);
                const competitorLabel = getCompetitorLabel(row.competitor_id);
                const confidencePct = Math.round(row.coverage_confidence * 100);
                return (
                  <div
                    key={`${row.cell_id}|${row.competitor_id}`}
                    className="bg-white border border-amber-200 rounded-xl p-4 flex items-center gap-4"
                  >
                    {/* Cell info */}
                    <div className="flex-1 min-w-0">
                      {cell ? (
                        <>
                          <div className="font-medium text-gray-800 text-sm truncate">{cell.page_state}</div>
                          <div className="text-xs text-gray-500 mt-0.5">{cell.journey_stage}</div>
                          <div className="text-[10px] text-gray-300 font-mono mt-0.5 truncate">{cell.jtbd}</div>
                        </>
                      ) : (
                        <div className="font-mono text-xs text-gray-400 truncate">{row.cell_id}</div>
                      )}
                    </div>

                    {/* Competitor badge */}
                    <div className="flex-none">
                      <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700 border border-indigo-100">
                        {competitorLabel}
                      </span>
                    </div>

                    {/* Status badge */}
                    <div className="flex-none">
                      <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-700">
                        待审核
                      </span>
                    </div>

                    {/* Confidence bar */}
                    <div className="flex-none w-24">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[10px] text-gray-400">置信度</span>
                        <span className="text-[10px] text-amber-600 font-medium">{confidencePct}%</span>
                      </div>
                      <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div className="h-full bg-amber-400 transition-all" style={{ width: `${confidencePct}%` }} />
                      </div>
                    </div>

                    {/* Action */}
                    <div className="flex-none">
                      <button
                        onClick={() =>
                          setSelected({ cellId: row.cell_id, competitorId: row.competitor_id, cellLabel, competitorLabel })
                        }
                        className="text-xs px-3 py-1.5 rounded-md bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
                      >
                        查看证据
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* Evidence drawer */}
      {selected && (
        <EvidenceDrawer
          cellId={selected.cellId}
          competitorId={selected.competitorId}
          cellLabel={selected.cellLabel}
          competitorLabel={selected.competitorLabel}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
