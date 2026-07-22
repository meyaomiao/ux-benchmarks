"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { GridCell } from "@/lib/types";

const DEFAULT_STAGES = ["首次配置", "日常使用", "异常处理", "规模化管理"];

type WizardStep = 1 | 2 | 3;

interface CellPreviewRow {
  jtbd: string;
  journey_stage: string;
  page_state: string;
  cell_key: string;
}

interface Props {
  onDone: (newCells: GridCell[]) => void;
  onClose: () => void;
}

function makeCellKey(jtbd: string, stage: string, ps: string): string {
  return [jtbd, stage, ps]
    .join(".")
    .replace(/[^a-z0-9.]+/gi, "-")
    .toLowerCase()
    .slice(0, 80);
}

export function CellWizard({ onDone, onClose }: Props) {
  const [step, setStep] = useState<WizardStep>(1);
  const [jtbdRaw, setJtbdRaw] = useState("");
  const [selectedStages, setSelectedStages] = useState<string[]>([...DEFAULT_STAGES]);
  const [pageStatesMap, setPageStatesMap] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const jtbds = jtbdRaw
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 15);

  const previewRows: CellPreviewRow[] = [];
  for (const jtbd of jtbds) {
    const raw = pageStatesMap[jtbd] ?? "";
    const pageStates = raw.split(",").map((s) => s.trim()).filter(Boolean);
    if (pageStates.length === 0) pageStates.push("default");
    for (const stage of selectedStages) {
      for (const ps of pageStates) {
        previewRows.push({
          jtbd,
          journey_stage: stage,
          page_state: ps,
          cell_key: makeCellKey(jtbd, stage, ps),
        });
      }
    }
  }

  function toggleStage(stage: string) {
    setSelectedStages((prev) =>
      prev.includes(stage) ? prev.filter((s) => s !== stage) : [...prev, stage]
    );
  }

  function canNext(): boolean {
    if (step === 1) return jtbds.length > 0;
    if (step === 2) return selectedStages.length > 0;
    return false;
  }

  async function handleConfirm() {
    setIsSubmitting(true);
    setError(null);
    try {
      const results = await Promise.all(
        previewRows.map((row) =>
          api.createCell({
            jtbd: row.jtbd,
            journey_stage: row.journey_stage,
            page_state: row.page_state,
            cell_key: row.cell_key,
          })
        )
      );
      onDone(results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建失败，请重试");
      setIsSubmitting(false);
    }
  }

  const stepTitles: Record<WizardStep, string> = {
    1: "Step 1 · JTBD 任务定义",
    2: "Step 2 · 旅程阶段 + 页面/状态",
    3: "Step 3 · 预览 + 确认",
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div>
            <div className="flex gap-2 mb-1.5">
              {([1, 2, 3] as WizardStep[]).map((s) => (
                <div
                  key={s}
                  className={`w-2 h-2 rounded-full transition-colors ${
                    s === step ? "bg-indigo-500" : s < step ? "bg-indigo-300" : "bg-gray-200"
                  }`}
                />
              ))}
            </div>
            <h2 className="text-base font-semibold text-gray-800">{stepTitles[step]}</h2>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors text-xl leading-none"
            aria-label="关闭"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {step === 1 && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                每行一个 JTBD 任务（用意图语言，如&ldquo;邀请协作者+权限分级&rdquo;）
              </label>
              <textarea
                value={jtbdRaw}
                onChange={(e) => setJtbdRaw(e.target.value)}
                rows={8}
                placeholder={"邀请协作者+权限分级\n批量导入成员\n移除协作者"}
                className="w-full border border-gray-200 rounded-lg p-3 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-300 resize-none"
              />
              {jtbds.length > 0 && (
                <p className="text-xs text-gray-400 mt-1.5">
                  已识别{" "}
                  <span className="font-medium text-indigo-600">{jtbds.length}</span>{" "}
                  个任务{jtbds.length >= 15 && "（已达上限 15）"}
                </p>
              )}
            </div>
          )}

          {step === 2 && (
            <div>
              <div className="mb-5">
                <p className="text-sm font-medium text-gray-700 mb-2">选择适用的旅程阶段</p>
                <div className="flex flex-wrap gap-2">
                  {DEFAULT_STAGES.map((stage) => (
                    <button
                      key={stage}
                      type="button"
                      onClick={() => toggleStage(stage)}
                      className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                        selectedStages.includes(stage)
                          ? "bg-indigo-100 text-indigo-700 border-indigo-300"
                          : "bg-white text-gray-500 border-gray-200 hover:border-gray-300"
                      }`}
                    >
                      {stage}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-700 mb-2">
                  每个任务的页面 / 状态{" "}
                  <span className="font-normal text-gray-400">（逗号分隔，如&ldquo;邀请弹窗, 权限选择页&rdquo;）</span>
                </p>
                <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                  {jtbds.map((jtbd) => (
                    <div key={jtbd} className="flex items-center gap-3">
                      <span
                        className="text-xs text-gray-600 w-36 shrink-0 truncate"
                        title={jtbd}
                      >
                        {jtbd}
                      </span>
                      <input
                        type="text"
                        value={pageStatesMap[jtbd] ?? ""}
                        onChange={(e) =>
                          setPageStatesMap((prev) => ({ ...prev, [jtbd]: e.target.value }))
                        }
                        placeholder="邀请弹窗, 权限选择页"
                        className="flex-1 border border-gray-200 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-300"
                      />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {step === 3 && (
            <div>
              <p className="text-sm text-gray-600 mb-3">
                将创建{" "}
                <span className="font-semibold text-indigo-700">{previewRows.length}</span>{" "}
                个格子
              </p>
              <div className="border border-gray-200 rounded-lg overflow-hidden">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-100 text-gray-500">
                      <th className="text-left px-3 py-2 font-medium">JTBD</th>
                      <th className="text-left px-3 py-2 font-medium">旅程阶段</th>
                      <th className="text-left px-3 py-2 font-medium">页面/状态</th>
                      <th className="text-left px-3 py-2 font-medium font-mono text-gray-400">cell_key</th>
                    </tr>
                  </thead>
                  <tbody>
                    {previewRows.map((row, i) => (
                      <tr key={i} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50">
                        <td className="px-3 py-2 max-w-[140px] truncate" title={row.jtbd}>{row.jtbd}</td>
                        <td className="px-3 py-2 text-gray-600">{row.journey_stage}</td>
                        <td className="px-3 py-2 font-medium">{row.page_state}</td>
                        <td className="px-3 py-2 font-mono text-gray-400 text-[10px] max-w-[160px] truncate">{row.cell_key}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {error && (
                <p className="text-xs text-red-500 mt-2">{error}</p>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-100 bg-gray-50/50 rounded-b-xl">
          <button
            type="button"
            onClick={step === 1 ? onClose : () => setStep((s) => (s - 1) as WizardStep)}
            className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 transition-colors"
          >
            {step === 1 ? "取消" : "上一步"}
          </button>
          {step < 3 ? (
            <button
              type="button"
              disabled={!canNext()}
              onClick={() => setStep((s) => (s + 1) as WizardStep)}
              className="px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              下一步
            </button>
          ) : (
            <button
              type="button"
              disabled={isSubmitting || previewRows.length === 0}
              onClick={handleConfirm}
              className="px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {isSubmitting ? "创建中…" : "确认创建"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
