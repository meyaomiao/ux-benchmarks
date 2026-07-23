"use client";

import { useState, useCallback, type KeyboardEvent } from "react";
import type { GridCell } from "@/lib/types";
import { api } from "@/lib/api";
import type { GeneratedCell, GridGenerationResult } from "@/lib/api";

type Phase = "input" | "review";

interface Props {
  onDone: (newCells: GridCell[]) => void;
  onClose: () => void;
  initialCategory?: string;
  initialCompetitors?: string[];
}

export default function CellWizard({ onDone, onClose, initialCategory = "", initialCompetitors = [] }: Props) {
  /* ── Phase A state ─────────────────────────────────────────── */
  const [phase, setPhase] = useState<Phase>("input");
  const [category, setCategory] = useState(initialCategory);
  const [competitorInput, setCompetitorInput] = useState("");
  // Prefill with already-registered competitors — the user just discovered them,
  // and grounding on real products dramatically improves JTBD relevance (#1).
  const [knownProducts, setKnownProducts] = useState<string[]>(initialCompetitors);
  const [generating, setGenerating] = useState(false);
  const [generationError, setGenerationError] = useState<string | null>(null);

  /* ── Phase B state ─────────────────────────────────────────── */
  const [result, setResult] = useState<GridGenerationResult | null>(null);
  const [cells, setCells] = useState<GeneratedCell[]>([]);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  /* ── Phase A handlers ──────────────────────────────────────── */
  const addCompetitor = useCallback(() => {
    const t = competitorInput.trim();
    if (t && !knownProducts.includes(t)) {
      setKnownProducts((prev) => [...prev, t]);
      setCompetitorInput("");
    }
  }, [competitorInput, knownProducts]);

  const handleCompetitorKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") { e.preventDefault(); addCompetitor(); }
  };

  const handleGenerate = async () => {
    const cat = category.trim();
    if (!cat) return;
    setGenerating(true);
    setGenerationError(null);
    try {
      const res = await api.generateGrid(cat, knownProducts);
      setResult(res);
      setCells(res.cells);
      setPhase("review");
    } catch (err) {
      setGenerationError(err instanceof Error ? err.message : "生成失败，请重试");
    } finally {
      setGenerating(false);
    }
  };

  const handleRegenerate = () => {
    setPhase("input");
    setResult(null);
    setCells([]);
    setCreateError(null);
  };

  const removeCell = (index: number) => {
    setCells((prev) => prev.filter((_, i) => i !== index));
  };

  /* ── Phase B handlers ──────────────────────────────────────── */
  const handleCreate = async () => {
    if (cells.length === 0) return;
    setCreating(true);
    setCreateError(null);
    try {
      const created: GridCell[] = [];
      for (const cell of cells) {
        const newCell = await api.createCell(cell);
        created.push(newCell);
      }
      onDone(created);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "创建失败，请重试");
    } finally {
      setCreating(false);
    }
  };

  /* ── Shared overlay ────────────────────────────────────────── */
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="relative w-full max-w-2xl mx-4 bg-white rounded-xl shadow-lg flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center gap-2 px-6 py-4 border-b border-gray-100">
          <h2 className="text-base font-semibold text-gray-900 flex-1 truncate">
            {phase === "input"
              ? "AI 分析生成场景网格"
              : `AI 生成了 ${cells.length} 个场景格子`}
          </h2>
          {phase === "review" && result && (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-700 shrink-0">
              {result.generated_by}
            </span>
          )}
          <button
            onClick={onClose}
            className="shrink-0 text-gray-400 hover:text-gray-600 transition-colors text-xl leading-none ml-2"
            aria-label="关闭"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {phase === "input" ? (
            <PhaseInput
              category={category}
              setCategory={setCategory}
              competitorInput={competitorInput}
              setCompetitorInput={setCompetitorInput}
              knownProducts={knownProducts}
              setKnownProducts={setKnownProducts}
              addCompetitor={addCompetitor}
              handleCompetitorKey={handleCompetitorKey}
              generating={generating}
              generationError={generationError}
              onGenerate={handleGenerate}
            />
          ) : (
            <PhaseReview
              result={result!}
              cells={cells}
              onRemoveCell={removeCell}
              onRegenerate={handleRegenerate}
              creating={creating}
              createError={createError}
              onConfirm={handleCreate}
            />
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Phase A: category input ───────────────────────────────────────────── */

interface PhaseInputProps {
  category: string;
  setCategory: (v: string) => void;
  competitorInput: string;
  setCompetitorInput: (v: string) => void;
  knownProducts: string[];
  setKnownProducts: (v: string[]) => void;
  addCompetitor: () => void;
  handleCompetitorKey: (e: KeyboardEvent<HTMLInputElement>) => void;
  generating: boolean;
  generationError: string | null;
  onGenerate: () => void;
}

function PhaseInput({
  category, setCategory, competitorInput, setCompetitorInput,
  knownProducts, setKnownProducts, addCompetitor, handleCompetitorKey,
  generating, generationError, onGenerate,
}: PhaseInputProps) {
  return (
    <div className="space-y-5">
      <p className="text-sm text-gray-500">
        输入产品品类，AI 自动分析生成研究场景框架（JTBD 任务 × 旅程阶段 × 关键页面/状态），人工按需调整后批量创建。
      </p>

      {/* Category input */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          产品品类或产品名称 <span className="text-red-500">*</span>
        </label>
        <input
          type="text"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") onGenerate(); }}
          placeholder="如：项目管理工具、Linear、企业预算软件..."
          className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
          disabled={generating}
        />
      </div>

      {/* Known products chips */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          已知竞品
          <span className="text-gray-400 font-normal ml-1">（强烈建议填写，AI 会据此提炼更准的 JTBD，按 Enter 添加）</span>
        </label>
        {knownProducts.length > 0 && (
          <p className="text-[11px] text-indigo-500 mb-1.5">已自动带入注册过的竞品，可增删</p>
        )}
        <div className="flex gap-2 flex-wrap mb-2">
          {knownProducts.map((p) => (
            <span key={p} className="inline-flex items-center gap-1 px-2.5 py-1 bg-indigo-50 text-indigo-700 rounded-full text-xs font-medium">
              {p}
              <button onClick={() => setKnownProducts(knownProducts.filter((x) => x !== p))}
                className="text-indigo-400 hover:text-indigo-700 leading-none">×</button>
            </span>
          ))}
        </div>
        <input
          type="text"
          value={competitorInput}
          onChange={(e) => setCompetitorInput(e.target.value)}
          onKeyDown={handleCompetitorKey}
          placeholder="如：Linear、Asana、Notion"
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
          disabled={generating}
        />
      </div>

      {generationError && (
        <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{generationError}</p>
      )}

      <button
        onClick={onGenerate}
        disabled={!category.trim() || generating}
        className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-colors flex items-center justify-center gap-2"
      >
        {generating ? (
          <>
            <span className="animate-spin text-lg">⟳</span>
            正在分析 {category.trim()}…
          </>
        ) : (
          "AI 生成场景网格 →"
        )}
      </button>
    </div>
  );
}

/* ── Phase B: review & create ─────────────────────────────────────────── */

interface PhaseReviewProps {
  result: GridGenerationResult;
  cells: GeneratedCell[];
  onRemoveCell: (i: number) => void;
  onRegenerate: () => void;
  creating: boolean;
  createError: string | null;
  onConfirm: () => void;
}

function PhaseReview({
  result, cells, onRemoveCell, onRegenerate, creating, createError, onConfirm,
}: PhaseReviewProps) {
  return (
    <div className="space-y-4">
      {/* Meta row */}
      <div className="flex items-center justify-between">
        <div className="flex gap-4 text-sm text-gray-500">
          <span>JTBD 任务 <strong className="text-gray-700">{result.jtbd_tasks.length}</strong></span>
          <span>旅程阶段 <strong className="text-gray-700">{result.journey_stages.length}</strong></span>
        </div>
        <button onClick={onRegenerate}
          className="text-xs text-indigo-600 hover:text-indigo-800 font-medium">
          ← 重新生成
        </button>
      </div>

      {/* Cell table */}
      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200 text-gray-500">
              <th className="text-left px-3 py-2 font-medium">JTBD 任务</th>
              <th className="text-left px-3 py-2 font-medium">旅程阶段</th>
              <th className="text-left px-3 py-2 font-medium">页面/状态</th>
              <th className="text-center px-3 py-2 font-medium w-12">价值</th>
              <th className="w-8" />
            </tr>
          </thead>
          <tbody>
            {cells.map((cell, i) => (
              <tr key={i} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/60">
                <td className="px-3 py-2 text-gray-700 max-w-[140px] truncate" title={cell.jtbd}>{cell.jtbd}</td>
                <td className="px-3 py-2 text-gray-500">{cell.journey_stage}</td>
                <td className="px-3 py-2 text-gray-700">{cell.page_state}</td>
                <td className="px-3 py-2 text-center">
                  <span className={`font-medium ${cell.value_score >= 0.8 ? "text-green-600" : cell.value_score >= 0.6 ? "text-amber-600" : "text-gray-400"}`}>
                    {cell.value_score.toFixed(1)}
                  </span>
                </td>
                <td className="px-2 py-2 text-center">
                  <button onClick={() => onRemoveCell(i)}
                    className="text-gray-300 hover:text-red-400 transition-colors text-base leading-none"
                    title="移除此格子">×</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-gray-400">共 {cells.length} 个格子（可点 × 移除不需要的）</p>

      {createError && (
        <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{createError}</p>
      )}

      <button
        onClick={onConfirm}
        disabled={cells.length === 0 || creating}
        className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-colors flex items-center justify-center gap-2"
      >
        {creating ? (
          <><span className="animate-spin text-lg">⟳</span> 正在创建…</>
        ) : (
          `确认创建 ${cells.length} 个格子`
        )}
      </button>
    </div>
  );
}
