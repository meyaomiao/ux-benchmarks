"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import type { GridCell, Competitor } from "@/lib/types";

// Coverage state is M5's job; here we just show a placeholder legend so the
// matrix structure (cell × competitor) is visible. Real state comes later.
const PLACEHOLDER = "c-empty";

export default function GridPage() {
  const [cells, setCells] = useState<GridCell[]>([]);
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.listCells(), api.listCompetitors()])
      .then(([g, c]) => {
        setCells(g.items);
        setCompetitors(c.items.filter((x) => x.status === "confirmed"));
      })
      .finally(() => setLoading(false));
  }, []);

  const stages = Array.from(new Set(cells.map((c) => c.journey_stage)));

  return (
    <div>
      <div className="text-gray-500 text-xs mb-1">M1 · 场景网格</div>
      <h1 className="text-xl font-bold mb-1">场景网格：任务 × 旅程阶段 × 页面/状态</h1>
      <p className="text-gray-500 text-sm mb-6 max-w-2xl">
        网格是采集的靶子。每个格子是一个可寻址的场景单元，产品向坐标看齐（而非反过来）。
        下方矩阵的列是竞品，格子的证据充分度由 M5 覆盖看板填充。
      </p>

      {loading ? (
        <div className="p-8 text-center text-gray-400 text-sm">加载中…</div>
      ) : (
        <>
          {/* Coordinate list */}
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden mb-8">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-gray-500 text-xs">
                  <th className="text-left px-4 py-3 font-medium">用户任务 (JTBD)</th>
                  <th className="text-left px-4 py-3 font-medium">旅程阶段</th>
                  <th className="text-left px-4 py-3 font-medium">页面 / 状态</th>
                  <th className="text-left px-4 py-3 font-medium">价值分</th>
                  <th className="text-left px-4 py-3 font-medium">cell_key</th>
                  <th className="text-left px-4 py-3 font-medium">版本</th>
                </tr>
              </thead>
              <tbody>
                {cells.map((c) => (
                  <tr key={c.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50">
                    <td className="px-4 py-3">{c.jtbd}</td>
                    <td className="px-4 py-3 text-gray-600">{c.journey_stage}</td>
                    <td className="px-4 py-3 font-medium">{c.page_state}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-indigo-500"
                            style={{ width: `${c.value_score * 100}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-500">
                          {c.value_score.toFixed(2)}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-400 text-xs font-mono">{c.cell_key}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs">v{c.version}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Matrix preview */}
          <div className="text-gray-500 text-xs mb-1">覆盖矩阵预览</div>
          <h2 className="text-base font-semibold mb-1">场景 × 竞品</h2>
          <p className="text-gray-400 text-xs mb-3">
            格子颜色 = 证据充分度，由 M5 覆盖看板填充（当前为占位）
          </p>
          <div className="bg-white border border-gray-200 rounded-xl p-4 overflow-x-auto">
            <table className="border-separate border-spacing-0 text-xs min-w-[560px]">
              <thead>
                <tr>
                  <th className="text-left px-2 py-2 text-gray-500 font-medium">场景</th>
                  {competitors.map((c) => (
                    <th key={c.id} className="px-2 py-2 text-gray-500 font-medium text-center whitespace-nowrap">
                      {c.canonical_name}
                      {c.competitor_type === "cross_industry" && (
                        <span className="block text-[9px] text-amber-600">跨行业</span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {cells.map((cell) => (
                  <tr key={cell.id}>
                    <td className="px-2 py-1.5 whitespace-nowrap">
                      <span className="font-medium">{cell.page_state}</span>
                      <span className="block text-gray-400 text-[10px]">{cell.journey_stage}</span>
                    </td>
                    {competitors.map((comp) => (
                      <td key={comp.id} className="px-1 py-1">
                        <div className="h-8 rounded border border-dashed border-gray-200 bg-gray-50/50 grid place-items-center text-gray-300 text-[10px]">
                          未探测
                        </div>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex gap-4 mt-4 text-[11px] text-gray-400">
              <span className="flex items-center gap-1.5">
                <i className="w-3 h-3 rounded bg-green-100 inline-block" />
                已充分
              </span>
              <span className="flex items-center gap-1.5">
                <i className="w-3 h-3 rounded bg-amber-100 inline-block" />
                薄弱
              </span>
              <span className="flex items-center gap-1.5">
                <i className="w-3 h-3 rounded bg-red-100 inline-block" />
                缺失
              </span>
              <span className="flex items-center gap-1.5">
                <i className="w-3 h-3 rounded bg-gray-100 border border-dashed border-gray-300 inline-block" />
                未探测 / 墙后
              </span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
