"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { MappingCard } from "@/lib/types";

interface Props {
  cellId: string;
  cellLabel: string;
  onClose: () => void;
}

type SaveState = "idle" | "saving" | "saved";

const MAX_INTENT = 150;

export function MappingCardEditor({ cellId, cellLabel, onClose }: Props) {
  const [card, setCard] = useState<MappingCard | null>(null);
  const [loading, setLoading] = useState(true);

  const [intent, setIntent] = useState("");
  const [inclusion, setInclusion] = useState("");
  const [exclusion, setExclusion] = useState("");

  const [saveState, setSaveState] = useState<SaveState>("idle");
  const savedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    api.getMappingCard(cellId).then((existing) => {
      setCard(existing);
      if (existing) {
        setIntent(existing.intent_definition);
        setInclusion(existing.inclusion_criteria ?? "");
        setExclusion(existing.exclusion_criteria ?? "");
      }
      setLoading(false);
    });
    return () => {
      if (savedTimerRef.current) clearTimeout(savedTimerRef.current);
    };
  }, [cellId]);

  const isComplete =
    intent.trim().length > 0 &&
    (inclusion.trim().length > 0 || exclusion.trim().length > 0);

  async function handleSave() {
    if (!intent.trim()) return;
    setSaveState("saving");
    try {
      const updated = await api.saveMappingCard(cellId, {
        intent_definition: intent.trim(),
        inclusion_criteria: inclusion.trim() || null,
        exclusion_criteria: exclusion.trim() || null,
      });
      setCard(updated);
      setSaveState("saved");
      savedTimerRef.current = setTimeout(() => {
        onClose();
      }, 900);
    } catch {
      setSaveState("idle");
    }
  }

  // Backdrop click closes
  function handleBackdropClick(e: React.MouseEvent<HTMLDivElement>) {
    if (e.target === e.currentTarget) onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
      onClick={handleBackdropClick}
    >
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div>
            <div className="text-xs text-gray-400 mb-0.5">M2 · 映射卡编辑器</div>
            <h2 className="text-sm font-semibold text-gray-800">{cellLabel}</h2>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors text-lg leading-none"
            aria-label="关闭"
          >
            ×
          </button>
        </div>

        {/* Body */}
        {loading ? (
          <div className="p-6 space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="space-y-1.5">
                <div className="h-3 w-24 bg-gray-100 rounded animate-pulse" />
                <div className="h-14 bg-gray-100 rounded animate-pulse" />
              </div>
            ))}
          </div>
        ) : (
          <div className="p-5 space-y-4">
            {/* Intent */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs font-medium text-gray-700">
                  意图定义 <span className="text-red-500">*</span>
                </label>
                <span
                  className={`text-xs ${
                    intent.length > MAX_INTENT ? "text-red-500" : "text-gray-400"
                  }`}
                >
                  {intent.length} / {MAX_INTENT}
                </span>
              </div>
              <textarea
                rows={2}
                value={intent}
                onChange={(e) => setIntent(e.target.value.slice(0, MAX_INTENT))}
                placeholder="用一句话描述用户在这个场景里想完成的事"
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 placeholder:text-gray-300"
              />
            </div>

            {/* Inclusion */}
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                纳入标准 <span className="text-gray-400 font-normal">（选填）</span>
              </label>
              <textarea
                rows={2}
                value={inclusion}
                onChange={(e) => setInclusion(e.target.value)}
                placeholder="哪些截图/文档算命中？"
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 placeholder:text-gray-300"
              />
            </div>

            {/* Exclusion */}
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                排除标准 <span className="text-gray-400 font-normal">（选填）</span>
              </label>
              <textarea
                rows={2}
                value={exclusion}
                onChange={(e) => setExclusion(e.target.value)}
                placeholder="哪些不算？（如营销文案、定价页）"
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 placeholder:text-gray-300"
              />
            </div>

            {/* Anchor screenshot stub */}
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">
                锚点截图 <span className="font-normal">（选填）</span>
              </label>
              <div className="flex items-center gap-2 border border-dashed border-gray-200 rounded-lg px-3 py-2 bg-gray-50 cursor-not-allowed">
                <svg className="w-4 h-4 text-gray-300 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                </svg>
                <span className="text-xs text-gray-400">锚点截图（上传功能即将上线）</span>
              </div>
            </div>

            {/* Completeness indicator */}
            <div className="text-xs font-medium">
              {isComplete ? (
                <span className="text-green-600">✓ 已就绪</span>
              ) : (
                <span className="text-amber-500">⚠ 缺少意图定义</span>
              )}
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-gray-100 bg-gray-50/50">
          <button
            onClick={onClose}
            className="text-sm text-gray-500 hover:text-gray-700 transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleSave}
            disabled={loading || saveState === "saving" || saveState === "saved" || !intent.trim()}
            className="text-sm px-4 py-1.5 rounded-lg bg-indigo-600 text-white font-medium
              hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors
              min-w-[96px] text-center"
          >
            {saveState === "saving"
              ? "保存中…"
              : saveState === "saved"
              ? "已保存 ✓"
              : "保存映射卡"}
          </button>
        </div>
      </div>
    </div>
  );
}
