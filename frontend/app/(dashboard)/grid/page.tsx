"use client";

import { useEffect, useState, useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import type { GridCell, Competitor } from "@/lib/types";
import { MappingCardEditor } from "@/components/grid/mapping-card-editor";
import CellWizard from "@/components/grid/cell-wizard";

export default function GridPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [cells, setCells] = useState<GridCell[]>([]);
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [loading, setLoading] = useState(true);
  const [editorCell, setEditorCell] = useState<GridCell | null>(null);
  const [showWizard, setShowWizard] = useState(false);
  const [wizardCategory, setWizardCategory] = useState("");
  const [quickAdd, setQuickAdd] = useState({ jtbd: "", journey_stage: "", page_state: "" });
  const [quickAddLoading, setQuickAddLoading] = useState(false);
  // Real per-cell mapping-card readiness (cell_ids that have a card), from DB.
  const [cardCellIds, setCardCellIds] = useState<Set<string>>(new Set());
  const [batchGen, setBatchGen] = useState<{ running: boolean; done: number; total: number } | null>(null);

  const loadCards = useCallback(() => {
    return api.listMappingCards().then((cards) => {
      setCardCellIds(new Set(cards.map((c) => c.cell_id)));
    });
  }, []);

  useEffect(() => {
    Promise.all([api.listCells(), api.listCompetitors(), api.listMappingCards()])
      .then(([g, c, cards]) => {
        setCells(g.items);
        setCompetitors(c.items.filter((x) => x.status === "confirmed"));
        setCardCellIds(new Set(cards.map((mc) => mc.cell_id)));
      })
      .finally(() => setLoading(false));
  }, []);

  // Carry the category from the registry discover step: /grid?category=…
  // auto-opens the wizard with the category prefilled.
  useEffect(() => {
    const cat = searchParams.get("category");
    if (cat) {
      setWizardCategory(cat);
      setShowWizard(true);
    }
  }, [searchParams]);

  const stages = Array.from(new Set(cells.map((c) => c.journey_stage)));

  async function handleQuickAdd(e: React.FormEvent) {
    e.preventDefault();
    const { jtbd, journey_stage, page_state } = quickAdd;
    if (!jtbd.trim() || !journey_stage.trim() || !page_state.trim()) return;
    setQuickAddLoading(true);
    try {
      const newCell = await api.createCell({ jtbd: jtbd.trim(), journey_stage: journey_stage.trim(), page_state: page_state.trim() });
      setCells((prev) => [...prev, newCell]);
      setQuickAdd({ jtbd: "", journey_stage: "", page_state: "" });
    } finally {
      setQuickAddLoading(false);
    }
  }

  // #2 Batch AI-generate mapping cards for every cell that doesn't have one yet.
  // Runs sequentially (each call hits the relay) with a live progress counter.
  async function handleBatchGenerateCards() {
    const targets = cells.filter((c) => !cardCellIds.has(c.id));
    if (targets.length === 0) return;
    setBatchGen({ running: true, done: 0, total: targets.length });
    for (let i = 0; i < targets.length; i++) {
      const cell = targets[i];
      try {
        const draft = await api.generateMappingCard(cell.id);
        await api.saveMappingCard(cell.id, {
          intent_definition: draft.intent_definition,
          inclusion_criteria: draft.inclusion_criteria || null,
          exclusion_criteria: draft.exclusion_criteria || null,
        });
        setCardCellIds((prev) => new Set([...prev, cell.id]));
      } catch {
        // one failure shouldn't abort the batch; leave that cell as 待填写
      }
      setBatchGen({ running: true, done: i + 1, total: targets.length });
    }
    await loadCards();
    setBatchGen(null);
  }

  return (
    <div>
      <div className="text-gray-500 text-xs mb-1">M1 · 场景网格</div>
      <div className="flex items-start justify-between mb-1">
        <h1 className="text-xl font-bold">场景网格：任务 × 旅程阶段 × 页面/状态</h1>
        <button
          onClick={() => setShowWizard(true)}
          className="shrink-0 ml-4 px-3 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
        >
          初始化网格
        </button>
      </div>
      <p className="text-gray-500 text-sm mb-6 max-w-2xl">
        网格是采集的靶子。每个格子是一个可寻址的场景单元，产品向坐标看齐（而非反过来）。
        下方矩阵的列是竞品，格子的证据充分度由 M5 覆盖看板填充。
      </p>

      {!loading && cells.length > 0 && (
        <div className="mb-6 flex items-center justify-between gap-3 bg-indigo-50 border border-indigo-200 rounded-xl px-4 py-3">
          <span className="text-sm text-indigo-800">
            网格已有 <span className="font-semibold">{cells.length}</span> 个场景格子，
            {competitors.length > 0 ? `${competitors.length} 个竞品待采集` : "去注册竞品后即可采集"}
          </span>
          <button
            onClick={() => router.push("/collect")}
            className="flex-none text-sm px-4 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors font-medium"
          >
            下一步：采集证据 →
          </button>
        </div>
      )}

      {loading ? (
        <div className="p-8 text-center text-gray-400 text-sm">加载中…</div>
      ) : (
        <>
          {/* Mapping-card batch toolbar */}
          {cells.length > 0 && (() => {
            const missing = cells.filter((c) => !cardCellIds.has(c.id)).length;
            const ready = cells.length - missing;
            return (
              <div className="mb-3 flex items-center justify-between gap-3 flex-wrap">
                <span className="text-xs text-gray-500">
                  映射卡：<span className="text-green-600 font-medium">{ready} 已就绪</span>
                  {missing > 0 && <span className="text-amber-600 font-medium"> · {missing} 待填写</span>}
                </span>
                {missing > 0 && (
                  <button
                    onClick={handleBatchGenerateCards}
                    disabled={!!batchGen?.running}
                    className="text-xs px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors font-medium"
                  >
                    {batchGen?.running
                      ? `AI 生成中… ${batchGen.done}/${batchGen.total}`
                      : `✨ 批量生成 ${missing} 张映射卡`}
                  </button>
                )}
              </div>
            );
          })()}

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
                  <th className="text-left px-4 py-3 font-medium">映射卡</th>
                </tr>
              </thead>
              <tbody>
                {cells.map((c) => {
                  const hasCard = cardCellIds.has(c.id);
                  return (
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
                    <td className="px-4 py-3">
                      <button
                        onClick={() => setEditorCell(c)}
                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium transition-colors cursor-pointer border ${
                          hasCard
                            ? "bg-green-50 text-green-700 border-green-200 hover:bg-green-100"
                            : "bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100"
                        }`}
                      >
                        {hasCard ? "已就绪" : "待填写"}
                      </button>
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Quick-add single cell */}
          <form onSubmit={handleQuickAdd} className="bg-white border border-gray-200 rounded-xl p-4 mb-8 flex flex-wrap gap-3 items-end">
            <div className="flex flex-col gap-1 flex-1 min-w-[140px]">
              <label className="text-xs text-gray-500">JTBD 任务</label>
              <input
                type="text"
                value={quickAdd.jtbd}
                onChange={(e) => setQuickAdd((prev) => ({ ...prev, jtbd: e.target.value }))}
                placeholder="邀请协作者+权限分级"
                className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div className="flex flex-col gap-1 flex-1 min-w-[120px]">
              <label className="text-xs text-gray-500">旅程阶段</label>
              <input
                type="text"
                value={quickAdd.journey_stage}
                onChange={(e) => setQuickAdd((prev) => ({ ...prev, journey_stage: e.target.value }))}
                placeholder="首次配置"
                className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div className="flex flex-col gap-1 flex-1 min-w-[120px]">
              <label className="text-xs text-gray-500">页面 / 状态</label>
              <input
                type="text"
                value={quickAdd.page_state}
                onChange={(e) => setQuickAdd((prev) => ({ ...prev, page_state: e.target.value }))}
                placeholder="邀请弹窗"
                className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <button
              type="submit"
              disabled={quickAddLoading || !quickAdd.jtbd.trim() || !quickAdd.journey_stage.trim() || !quickAdd.page_state.trim()}
              className="px-4 py-1.5 text-sm bg-gray-800 text-white rounded-lg hover:bg-gray-900 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {quickAddLoading ? "添加中…" : "+ 添加格子"}
            </button>
          </form>
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

      {/* Mapping card editor modal */}
      {editorCell && (
        <MappingCardEditor
          cellId={editorCell.id}
          cellLabel={`${editorCell.journey_stage} · ${editorCell.page_state}`}
          onClose={() => { setEditorCell(null); loadCards(); }}
        />
      )}

      {/* Grid initialization wizard */}
      {showWizard && (
        <CellWizard
          initialCategory={wizardCategory}
          initialCompetitors={competitors.map((c) => c.canonical_name)}
          onDone={(newCells: GridCell[]) => {
            setCells((prev) => [...prev, ...newCells]);
            setShowWizard(false);
          }}
          onClose={() => setShowWizard(false)}
        />
      )}
    </div>
  );
}
