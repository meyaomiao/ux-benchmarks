"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import type { GridCell, Competitor, CoverageRow, CoverageStatus } from "@/lib/types";

// Status display config
const STATUS_CONFIG: Record<
  CoverageStatus,
  { label: string; cellBg: string; cellBorder: string; textColor: string; barColor: string; dashed?: boolean; pulse?: boolean; strikethrough?: boolean }
> = {
  SATURATED:      { label: "已饱和",  cellBg: "bg-green-50",    cellBorder: "border-green-200",  textColor: "text-green-700",  barColor: "bg-green-400" },
  SHORTLIST_READY:{ label: "待审核",  cellBg: "bg-amber-50",    cellBorder: "border-amber-200",  textColor: "text-amber-700",  barColor: "bg-amber-400" },
  PARTIAL:        { label: "部分",    cellBg: "bg-amber-50/40", cellBorder: "border-amber-100",  textColor: "text-amber-600",  barColor: "bg-amber-300" },
  UNPROBED:       { label: "未探测",  cellBg: "bg-gray-50",     cellBorder: "border-gray-200",   textColor: "text-gray-400",   barColor: "bg-gray-200",  dashed: true },
  REJECTED_EMPTY: { label: "已拒绝",  cellBg: "bg-red-50",      cellBorder: "border-red-200",    textColor: "text-red-400",    barColor: "bg-red-200",   strikethrough: true },
  QUEUED:         { label: "排队中",  cellBg: "bg-blue-50",     cellBorder: "border-blue-200",   textColor: "text-blue-600",   barColor: "bg-blue-300",  pulse: true },
  PROBING:        { label: "探测中",  cellBg: "bg-blue-50",     cellBorder: "border-blue-200",   textColor: "text-blue-600",   barColor: "bg-blue-300",  pulse: true },
  STALE:          { label: "已陈旧",  cellBg: "bg-gray-100",    cellBorder: "border-gray-200",   textColor: "text-gray-400",   barColor: "bg-gray-300" },
};

const EMPTY_CFG = STATUS_CONFIG.UNPROBED;

export default function CoveragePage() {
  const [cells, setCells] = useState<GridCell[]>([]);
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [coverage, setCoverage] = useState<CoverageRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.listCells(), api.listCompetitors(), api.getCoverage()])
      .then(([g, c, cov]) => {
        setCells(g.items);
        setCompetitors(c.items.filter((x) => x.status === "confirmed"));
        setCoverage(cov);
      })
      .finally(() => setLoading(false));
  }, []);

  // Build lookup: coverageMap[cell_id][competitor_id]
  const coverageMap = coverage.reduce<Record<string, Record<string, CoverageRow>>>(
    (acc, row) => {
      if (!acc[row.cell_id]) acc[row.cell_id] = {};
      acc[row.cell_id][row.competitor_id] = row;
      return acc;
    },
    {}
  );

  // Summary stats
  const total = coverage.length;
  const shortlistCount = coverage.filter((r) => r.status === "SHORTLIST_READY").length;
  const evidenceCount = coverage.filter((r) => r.status !== "UNPROBED").length;
  const pctShortlist = total > 0 ? Math.round((shortlistCount / total) * 100) : 0;
  const pctEvidence = total > 0 ? Math.round((evidenceCount / total) * 100) : 0;

  return (
    <div>
      <div className="text-gray-500 text-xs mb-1">M5 · 覆盖看板</div>
      <h1 className="text-xl font-bold mb-1">覆盖矩阵</h1>
      <p className="text-gray-500 text-sm mb-6 max-w-2xl">
        每格展示当前采集状态与置信度。SHORTLIST_READY 意味着已找到证据，等待人工审核；SATURATED 意味着已通过人工接受。
      </p>

      {loading ? (
        <div className="p-8 text-center text-gray-400 text-sm">加载中…</div>
      ) : (
        <>
          {/* Summary bar */}
          <div className="grid grid-cols-3 gap-4 mb-8">
            <div className="bg-white border border-gray-200 rounded-xl p-4">
              <div className="text-2xl font-bold text-gray-800">{total}</div>
              <div className="text-xs text-gray-500 mt-1">已追踪的格子（cell × 竞品）</div>
            </div>
            <div className="bg-white border border-gray-200 rounded-xl p-4">
              <div className="text-2xl font-bold text-amber-600">{pctShortlist}%</div>
              <div className="text-xs text-gray-500 mt-1">SHORTLIST_READY（待审核）</div>
              <div className="w-full h-1.5 bg-gray-100 rounded-full mt-2 overflow-hidden">
                <div className="h-full bg-amber-400 transition-all" style={{ width: `${pctShortlist}%` }} />
              </div>
            </div>
            <div className="bg-white border border-gray-200 rounded-xl p-4">
              <div className="text-2xl font-bold text-indigo-600">{pctEvidence}%</div>
              <div className="text-xs text-gray-500 mt-1">有任意证据的格子</div>
              <div className="w-full h-1.5 bg-gray-100 rounded-full mt-2 overflow-hidden">
                <div className="h-full bg-indigo-400 transition-all" style={{ width: `${pctEvidence}%` }} />
              </div>
            </div>
          </div>

          {/* Coverage matrix */}
          <div className="text-gray-500 text-xs mb-1">覆盖矩阵</div>
          <h2 className="text-base font-semibold mb-3">场景 × 竞品 覆盖状态</h2>
          <div className="bg-white border border-gray-200 rounded-xl p-4 overflow-x-auto">
            <table className="border-separate border-spacing-1 text-xs min-w-[600px]">
              <thead>
                <tr>
                  <th className="text-left px-3 py-2 text-gray-500 font-medium min-w-[200px]">场景</th>
                  {competitors.map((comp) => (
                    <th key={comp.id} className="px-2 py-2 text-gray-500 font-medium text-center whitespace-nowrap min-w-[110px]">
                      {comp.canonical_name}
                      {comp.competitor_type === "cross_industry" && (
                        <span className="block text-[9px] text-amber-600">跨行业</span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {cells.map((cell) => (
                  <tr key={cell.id}>
                    <td className="px-3 py-2 align-top">
                      <div className="font-medium text-gray-700">{cell.page_state}</div>
                      <div className="text-gray-400 text-[10px]">{cell.journey_stage}</div>
                      <div className="text-gray-300 text-[9px] font-mono mt-0.5 truncate max-w-[190px]">{cell.cell_key}</div>
                    </td>
                    {competitors.map((comp) => {
                      const row = coverageMap[cell.id]?.[comp.id];
                      const cfg = row ? (STATUS_CONFIG[row.status] ?? EMPTY_CFG) : EMPTY_CFG;
                      const confidencePct = row ? Math.round(row.coverage_confidence * 100) : 0;
                      return (
                        <td key={comp.id} className="px-0.5 py-0.5 align-top">
                          <div className={[
                            "rounded border p-2",
                            cfg.cellBg, cfg.cellBorder,
                            cfg.dashed ? "border-dashed" : "",
                            cfg.pulse ? "animate-pulse" : "",
                          ].join(" ")}>
                            {row ? (
                              <>
                                <div className="flex justify-center">
                                  <span className={[
                                    "inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-medium",
                                    cfg.textColor,
                                    cfg.strikethrough ? "line-through" : "",
                                  ].join(" ")}>
                                    {cfg.label}
                                  </span>
                                </div>
                                {confidencePct > 0 && (
                                  <>
                                    <div className="w-full h-1 bg-white/60 rounded-full mt-1.5 overflow-hidden">
                                      <div className={`h-full ${cfg.barColor}`} style={{ width: `${confidencePct}%` }} />
                                    </div>
                                    <div className={`text-center text-[9px] mt-0.5 ${cfg.textColor}`}>{confidencePct}%</div>
                                  </>
                                )}
                              </>
                            ) : (
                              <div className="text-center text-gray-300 text-[10px] py-1">—</div>
                            )}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Legend */}
            <div className="flex flex-wrap gap-x-5 gap-y-2 mt-5 text-[11px] text-gray-500 border-t border-gray-100 pt-4">
              {(Object.entries(STATUS_CONFIG) as [CoverageStatus, typeof EMPTY_CFG][]).map(([status, cfg]) => (
                <span key={status} className="flex items-center gap-1.5">
                  <span className={["w-3 h-3 rounded inline-block border", cfg.cellBg, cfg.cellBorder, cfg.dashed ? "border-dashed" : ""].join(" ")} />
                  <span className={cfg.strikethrough ? "line-through" : ""}>{status}</span>
                </span>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
