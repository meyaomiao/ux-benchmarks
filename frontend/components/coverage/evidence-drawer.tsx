"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import type { ShortlistItem, RubricBreakdown } from "@/lib/types";

const RUBRIC_LABELS: Record<keyof Omit<RubricBreakdown, "reasoning" | "scored_by">, string> = {
  state_match: "状态命中",
  product_match: "产品命中",
  version_recency: "版本时效",
  evidence_directness: "证据直接性",
  fidelity: "保真度",
};

const EVIDENCE_LABEL: Record<string, { label: string; cls: string }> = {
  observed: { label: "已观测", cls: "bg-green-50 text-green-700" },
  claimed: { label: "仅声称", cls: "bg-gray-100 text-gray-500" },
  inferred: { label: "推断", cls: "bg-amber-50 text-amber-700" },
};

const SOURCE_LABEL: Record<string, string> = {
  help_docs: "帮助文档",
  interactive_demo: "交互式 Demo",
  video: "视频",
  community: "社区",
  generic: "通用",
};

function scoreColor(score: number): string {
  if (score >= 0.75) return "bg-green-500";
  if (score >= 0.55) return "bg-amber-500";
  return "bg-gray-300";
}

export function EvidenceDrawer({
  cellId,
  competitorId,
  cellLabel,
  competitorLabel,
  onClose,
}: {
  cellId: string;
  competitorId: string;
  cellLabel: string;
  competitorLabel: string;
  onClose: () => void;
}) {
  const [items, setItems] = useState<ShortlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [acted, setActed] = useState<Record<string, "accepted" | "rejected">>({});
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    api.getShortlist(cellId, competitorId)
      .then((res) => setItems(res.items))
      .finally(() => setLoading(false));
  }, [cellId, competitorId]);

  async function handleAccept(id: string) {
    setBusy(id);
    try {
      await api.acceptAsset(id);
      setActed((a) => ({ ...a, [id]: "accepted" }));
    } finally {
      setBusy(null);
    }
  }

  async function handleReject(id: string) {
    setBusy(id);
    try {
      await api.rejectAsset(id);
      setActed((a) => ({ ...a, [id]: "rejected" }));
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/30 z-40 animate-[fadeIn_0.15s_ease]"
        onClick={onClose}
      />
      {/* Drawer */}
      <aside className="fixed top-0 right-0 h-full w-[520px] max-w-[92vw] bg-white z-50 shadow-2xl overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-white border-b border-gray-100 px-6 py-4 flex items-start justify-between">
          <div>
            <div className="text-xs text-gray-400 mb-0.5">证据 · 待审核</div>
            <div className="font-semibold text-gray-800">{cellLabel}</div>
            <div className="text-sm text-indigo-600 mt-0.5">{competitorLabel}</div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-700 text-xl leading-none px-2"
            aria-label="关闭"
          >
            ×
          </button>
        </div>

        <div className="px-6 py-4">
          {loading ? (
            <div className="py-12 text-center text-gray-400 text-sm">加载证据中…</div>
          ) : items.length === 0 ? (
            <div className="py-12 text-center text-gray-400 text-sm">
              该格子暂无采集到的证据。
            </div>
          ) : (
            <div className="space-y-4">
              <div className="text-xs text-gray-500">
                共 {items.length} 条候选，按 AI 相关性评分排序。审核后进入证据库。
              </div>
              {items
                .slice()
                .sort((a, b) => (b.ai_score ?? 0) - (a.ai_score ?? 0))
                .map((item) => {
                  const ev = EVIDENCE_LABEL[item.evidence_type] ?? EVIDENCE_LABEL.inferred;
                  const status = acted[item.id];
                  return (
                    <div
                      key={item.id}
                      className={[
                        "border rounded-xl p-4 transition-opacity",
                        status === "rejected" ? "opacity-40 border-gray-200" : "border-gray-200",
                      ].join(" ")}
                    >
                      {/* Score + source header */}
                      <div className="flex items-center gap-2 mb-2 flex-wrap">
                        {item.ai_score != null && (
                          <span className="inline-flex items-center gap-1.5 font-bold text-lg text-gray-800">
                            {item.ai_score.toFixed(2)}
                            <span className="text-[10px] font-normal text-gray-400">AI 评分</span>
                          </span>
                        )}
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${ev.cls}`}>
                          {ev.label}
                        </span>
                        <Badge variant="default">
                          {SOURCE_LABEL[item.source_type ?? ""] ?? item.source_type ?? "未知来源"}
                        </Badge>
                        {item.image_path_available && (
                          <Badge variant="direct">含截图</Badge>
                        )}
                        {status && (
                          <span className={`ml-auto text-[11px] font-medium ${status === "accepted" ? "text-green-600" : "text-gray-400"}`}>
                            {status === "accepted" ? "✓ 已接受" : "✕ 已拒绝"}
                          </span>
                        )}
                      </div>

                      {/* Title + snippet */}
                      {item.title && (
                        <div className="font-medium text-sm text-gray-800 mb-1">{item.title}</div>
                      )}
                      {item.snippet && (
                        <p className="text-xs text-gray-600 leading-relaxed mb-3">{item.snippet}</p>
                      )}

                      {/* Rubric breakdown */}
                      {item.ai_score_breakdown && (
                        <div className="bg-gray-50 rounded-lg p-3 mb-3 space-y-1.5">
                          {(Object.keys(RUBRIC_LABELS) as (keyof typeof RUBRIC_LABELS)[]).map((k) => {
                            const v = item.ai_score_breakdown![k];
                            return (
                              <div key={k} className="flex items-center gap-2">
                                <span className="text-[10px] text-gray-500 w-16 flex-none">{RUBRIC_LABELS[k]}</span>
                                <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                                  <div className={`h-full ${scoreColor(v)}`} style={{ width: `${v * 100}%` }} />
                                </div>
                                <span className="text-[10px] text-gray-400 w-7 text-right">{v.toFixed(2)}</span>
                              </div>
                            );
                          })}
                          {item.ai_score_breakdown.reasoning && (
                            <p className="text-[11px] text-gray-500 italic pt-1.5 leading-relaxed border-t border-gray-200 mt-2">
                              {item.ai_score_breakdown.reasoning}
                              {item.ai_score_breakdown.scored_by && (
                                <span className="not-italic text-gray-300"> · {item.ai_score_breakdown.scored_by}</span>
                              )}
                            </p>
                          )}
                        </div>
                      )}

                      {/* Source link + actions */}
                      <div className="flex items-center justify-between gap-2">
                        <a
                          href={item.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[11px] text-indigo-500 hover:underline truncate max-w-[240px]"
                        >
                          {item.source_url}
                        </a>
                        {!status && (
                          <div className="flex gap-2 flex-none">
                            <button
                              disabled={busy === item.id}
                              onClick={() => handleReject(item.id)}
                              className="text-xs px-3 py-1 rounded-md border border-gray-200 text-gray-500 hover:bg-gray-50 disabled:opacity-50"
                            >
                              拒绝
                            </button>
                            <button
                              disabled={busy === item.id}
                              onClick={() => handleAccept(item.id)}
                              className="text-xs px-3 py-1 rounded-md bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
                            >
                              {busy === item.id ? "…" : "接受"}
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
