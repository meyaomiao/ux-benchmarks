"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useJob } from "@/lib/useJob";
import type { Insight, Report, ReportAudience, ReportFormat } from "@/lib/types";

// ---- helpers ---------------------------------------------------------------

const AUDIENCE_LABELS: Record<ReportAudience, string> = {
  management: "管理层",
  designer: "设计师",
  pm: "产品经理",
};

const FORMAT_LABELS: Record<ReportFormat, { label: string; desc: string }> = {
  summary_5min:  { label: "5分钟摘要",  desc: "3~5个核心发现 + 每条一句话建议" },
  review_15min:  { label: "15分钟评审", desc: "分章节展开洞察，有机制/建议/限制" },
  onepager:      { label: "单页总览",   desc: "标题 + 洞察列表 + 原则汇总" },
  full:          { label: "完整报告",   desc: "全字段全展开，可作工作留底" },
};

// ---- Markdown renderer (lightweight, no deps) ------------------------------

function renderMd(md: string): string {
  return md
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold text-gray-800 mt-6 mb-2">$1</h3>')
    .replace(/^## (.+)$/gm,  '<h2 class="text-lg font-bold text-gray-900 mt-8 mb-3">$1</h2>')
    .replace(/^# (.+)$/gm,   '<h1 class="text-xl font-bold text-gray-900 mt-2 mb-4">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^---$/gm, '<hr class="border-gray-200 my-4">')
    .replace(/^\d+\. (.+)$/gm, '<li class="ml-4 list-decimal text-sm text-gray-700">$1</li>')
    .replace(/^[-*] (.+)$/gm,  '<li class="ml-4 list-disc   text-sm text-gray-700">$1</li>')
    .replace(/^(?!<[h1-6li]|<hr)(.+)$/gm, '<p class="text-sm text-gray-700 leading-relaxed mb-2">$1</p>')
    .replace(/^\s*\n/gm, "");
}

// ---- ReportCard ------------------------------------------------------------

function ReportCard({ report, onClick }: { report: Report; onClick: () => void }) {
  const fmt = FORMAT_LABELS[report.format_type as ReportFormat];
  return (
    <button
      onClick={onClick}
      className="w-full text-left bg-white border border-gray-200 rounded-xl p-4 hover:border-indigo-300 hover:shadow-sm transition-all"
    >
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-lg bg-indigo-50 flex items-center justify-center flex-none mt-0.5">
          <span className="text-indigo-600 text-xs font-bold">L5</span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-gray-800 truncate">{report.title}</div>
          <div className="text-xs text-gray-400 mt-0.5">
            {AUDIENCE_LABELS[report.audience as ReportAudience]}
            &nbsp;·&nbsp;{fmt?.label}
            &nbsp;·&nbsp;{report.source_insight_ids.length} 条洞察
          </div>
        </div>
        <span className="text-xs text-gray-300 flex-none">
          {new Date(report.created_at).toLocaleDateString("zh-CN", { month: "short", day: "numeric" })}
        </span>
      </div>
    </button>
  );
}

// ---- ReportViewer ----------------------------------------------------------

function ReportViewer({ report, onClose, onDelete }: {
  report: Report;
  onClose: () => void;
  onDelete: (id: string) => void;
}) {
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    if (!confirm("确认删除这份报告？")) return;
    setDeleting(true);
    try {
      await api.deleteReport(report.id);
      onDelete(report.id);
      onClose();
    } finally { setDeleting(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* backdrop */}
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      {/* panel */}
      <div className="relative ml-auto w-full max-w-3xl bg-white shadow-2xl overflow-auto flex flex-col">
        {/* toolbar */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 flex-none">
          <div>
            <div className="text-xs text-gray-400 mb-0.5">
              {AUDIENCE_LABELS[report.audience as ReportAudience]}
              &nbsp;·&nbsp;
              {FORMAT_LABELS[report.format_type as ReportFormat]?.label}
              &nbsp;·&nbsp;
              {report.generated_by === "mock" ? "示例" : "AI 生成"}
            </div>
            <div className="text-sm font-semibold text-gray-800">{report.title}</div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="text-xs text-red-400 hover:text-red-600 px-2 py-1 rounded hover:bg-red-50 transition-colors disabled:opacity-50"
            >
              删除
            </button>
            <button
              onClick={onClose}
              className="text-xs text-gray-400 hover:text-gray-700 px-2 py-1 rounded hover:bg-gray-100"
            >
              关闭
            </button>
          </div>
        </div>
        {/* body */}
        <div
          className="flex-1 px-8 py-6 prose prose-sm max-w-none"
          dangerouslySetInnerHTML={{ __html: renderMd(report.body_markdown) }}
        />
      </div>
    </div>
  );
}

// ---- Page ------------------------------------------------------------------

export default function ReportsPage() {
  const [insights, setInsights] = useState<Insight[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);

  // Composer state
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [audience, setAudience] = useState<ReportAudience>("designer");
  const [format, setFormat] = useState<ReportFormat>("review_15min");
  const [composeError, setComposeError] = useState<string | null>(null);

  // Viewer state
  const [viewing, setViewing] = useState<Report | null>(null);

  // #53 Async report compose — runs server-side, survives navigation.
  const reportJob = useJob("report_compose", async (result) => {
    const rpts = await api.listReports();
    setReports(rpts);
    setSelected(new Set());
    const newId = result?.report_id;
    const fresh = rpts.find((r) => r.id === newId);
    if (fresh) setViewing(fresh);
  });
  const composing = reportJob.running;

  useEffect(() => {
    Promise.all([api.listInsights(), api.listReports()])
      .then(([ins, rpts]) => {
        setInsights(ins);
        setReports(rpts);
        // Auto-select all insights on load — no reason to make users click
        setSelected(new Set(ins.map((i) => i.id)));
      })
      .finally(() => setLoading(false));
  }, []);

  function toggleInsight(id: string) {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (selected.size === insights.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(insights.map(i => i.id)));
    }
  }

  async function handleCompose(insightIds?: string[]) {
    const ids = insightIds ?? Array.from(selected);
    if (ids.length === 0) return;
    setComposeError(null);
    try {
      await reportJob.start({ insight_ids: ids, audience, format_type: format });
    } catch (e) {
      setComposeError(e instanceof Error ? e.message : "生成失败");
    }
  }

  const handleDelete = useCallback((id: string) => {
    setReports(prev => prev.filter(r => r.id !== id));
  }, []);

  return (
    <div>
      {viewing && (
        <ReportViewer
          report={viewing}
          onClose={() => setViewing(null)}
          onDelete={handleDelete}
        />
      )}

      <div className="text-gray-500 text-xs mb-1">L5 · 报告重组</div>
      <h1 className="text-xl font-bold mb-1">报告重组</h1>
      <p className="text-gray-500 text-sm mb-8 max-w-2xl">
        选择一批洞察，按受众与格式重组为可直接使用的报告——重组而非重生，证据只写一次。
      </p>

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_340px] gap-8 max-w-5xl">
        {/* Left: insight selector + compose controls */}
        <div className="space-y-6">
          {/* Compose settings card */}
          <div className="bg-white border border-gray-200 rounded-xl p-5">
            <div className="text-sm font-semibold text-gray-700 mb-4">重组设置</div>
            <div className="grid grid-cols-2 gap-4 mb-4">
              <label>
                <span className="block text-xs text-gray-500 mb-1">目标受众</span>
                <select
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  value={audience}
                  onChange={e => setAudience(e.target.value as ReportAudience)}
                  disabled={composing}
                >
                  {(Object.entries(AUDIENCE_LABELS) as [ReportAudience, string][]).map(([v, label]) => (
                    <option key={v} value={v}>{label}</option>
                  ))}
                </select>
              </label>
              <label>
                <span className="block text-xs text-gray-500 mb-1">报告格式</span>
                <select
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  value={format}
                  onChange={e => setFormat(e.target.value as ReportFormat)}
                  disabled={composing}
                >
                  {(Object.entries(FORMAT_LABELS) as [ReportFormat, { label: string; desc: string }][]).map(([v, { label, desc }]) => (
                    <option key={v} value={v}>{label} — {desc}</option>
                  ))}
                </select>
              </label>
            </div>
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <span className="text-xs text-gray-400">
                已选 {selected.size} / {insights.length} 条洞察
              </span>
              <button
                onClick={() => handleCompose()}
                disabled={selected.size === 0 || composing}
                className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
              >
                {composing ? "AI 重组中…" : "生成报告"}
              </button>
            </div>
            {insights.length === 0 && (
              <p className="mt-2 text-xs text-amber-600">
                还没有洞察。请先到「洞察库」基于已审核证据生成洞察，再回来重组报告。
              </p>
            )}
            {composeError && <p className="mt-2 text-xs text-red-500">{composeError}</p>}
          </div>

          {/* Insight multi-select list */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                洞察列表
              </div>
              {insights.length > 0 && (
                <button
                  onClick={toggleAll}
                  className="text-xs text-indigo-500 hover:text-indigo-700"
                >
                  {selected.size === insights.length ? "取消全选" : "全选"}
                </button>
              )}
            </div>
            {loading ? (
              <div className="py-8 text-center text-gray-400 text-sm">加载中…</div>
            ) : insights.length === 0 ? (
              <div className="bg-white border border-gray-200 rounded-xl p-8 text-center">
                <div className="text-gray-400 text-sm">暂无洞察。请先前往洞察库生成洞察，再来此处重组。</div>
              </div>
            ) : (
              <div className="space-y-2">
                {insights.map(ins => {
                  const checked = selected.has(ins.id);
                  return (
                    <label
                      key={ins.id}
                      className={`flex items-start gap-3 p-4 rounded-xl border cursor-pointer transition-colors ${
                        checked
                          ? "bg-indigo-50 border-indigo-300"
                          : "bg-white border-gray-200 hover:border-indigo-200"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleInsight(ins.id)}
                        className="mt-0.5 rounded accent-indigo-600 flex-none"
                      />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-gray-800 leading-snug line-clamp-2">{ins.claim}</p>
                        {ins.design_principle && (
                          <p className="text-xs text-indigo-600 mt-1 line-clamp-1">{ins.design_principle}</p>
                        )}
                        <div className="flex items-center gap-2 mt-1.5">
                          <span className={`inline-flex text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                            ins.confidence === "high" ? "bg-green-50 text-green-700" :
                            ins.confidence === "medium" ? "bg-indigo-50 text-indigo-700" :
                            "bg-gray-100 text-gray-500"
                          }`}>
                            {ins.confidence === "high" ? "高置信" : ins.confidence === "medium" ? "中置信" : ins.confidence === "low" ? "低置信" : "假设"}
                          </span>
                          {ins.is_draft && (
                            <span className="text-[10px] text-gray-400">草稿</span>
                          )}
                        </div>
                      </div>
                    </label>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Right: reports history */}
        <div>
          <div className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">
            已生成报告
          </div>
          {loading ? (
            <div className="py-8 text-center text-gray-400 text-sm">加载中…</div>
          ) : reports.length === 0 ? (
            <div className="bg-white border border-gray-200 rounded-xl p-6 text-center">
              <div className="text-gray-400 text-xs">还没有报告，从左侧选择洞察并生成。</div>
            </div>
          ) : (
            <div className="space-y-2">
              {reports.map(r => (
                <ReportCard key={r.id} report={r} onClick={() => setViewing(r)} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
