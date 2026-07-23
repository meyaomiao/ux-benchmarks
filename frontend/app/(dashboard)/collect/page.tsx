"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { GridCell, Competitor, CoverageRow } from "@/lib/types";

// Coverage status → chip label + style.
const STATUS_META: Record<string, { label: string; cls: string }> = {
  SATURATED:       { label: "已审核", cls: "bg-green-100 text-green-700" },
  SHORTLIST_READY: { label: "已采到", cls: "bg-green-50 text-green-600 border border-green-200" },
  PARTIAL:         { label: "部分",   cls: "bg-amber-50 text-amber-700" },
  PROBING:         { label: "采集中", cls: "bg-blue-50 text-blue-600" },
  QUEUED:          { label: "待采",   cls: "bg-amber-50 text-amber-600" },
  REJECTED_EMPTY:  { label: "空",     cls: "bg-gray-100 text-gray-400" },
  UNPROBED:        { label: "未采",   cls: "bg-gray-50 text-gray-400" },
};
function statusMeta(s?: string) {
  return STATUS_META[s ?? ""] ?? { label: "未采", cls: "bg-gray-50 text-gray-400 border border-gray-200" };
}

export default function CollectPage() {
  const router = useRouter();
  const [cells, setCells] = useState<GridCell[]>([]);
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [coverage, setCoverage] = useState<CoverageRow[]>([]);
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);

  // One-click / per-scene collection.
  const [collecting, setCollecting] = useState(false);
  const [collectMsg, setCollectMsg] = useState("");
  const [sceneBusy, setSceneBusy] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [stopping, setStopping] = useState(false);

  // Advanced: fold single-pair pin (kept for补采 edge cases).
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [pinCell, setPinCell] = useState("");
  const [pinComp, setPinComp] = useState("");
  const [pinStatus, setPinStatus] = useState<"idle" | "loading" | "ok" | "err">("idle");
  const [pinErr, setPinErr] = useState("");

  // Manual screenshot.
  const [ssUrl, setSsUrl] = useState("");
  const [ssCell, setSsCell] = useState("");
  const [ssComp, setSsComp] = useState("");
  const [ssStatus, setSsStatus] = useState<"idle" | "loading" | "ok" | "err">("idle");
  const [ssErr, setSsErr] = useState("");
  const [ssResult, setSsResult] = useState<{ source_url: string; ai_score: number | null } | null>(null);

  const cov = (metrics as any)?.coverage?.by_status ?? {};
  const nQueued = Number(cov.QUEUED ?? 0);
  const nProbing = Number(cov.PROBING ?? 0);
  const nActive = nQueued + nProbing;

  const refreshLive = () =>
    Promise.all([api.getCoverage(), api.getCoverageMetrics()])
      .then(([cv, m]) => { setCoverage(cv); setMetrics(m); });

  useEffect(() => {
    Promise.all([api.listCells(), api.listCompetitors(), api.getCoverage(), api.getCoverageMetrics()])
      .then(([g, c, cv, m]) => {
        setCells(g.items);
        const confirmed = c.items.filter((x) => x.status === "confirmed");
        setCompetitors(confirmed);
        setCoverage(cv);
        setMetrics(m);
        if (g.items[0]) { setPinCell(g.items[0].id); setSsCell(g.items[0].id); }
        if (confirmed[0]) { setPinComp(confirmed[0].id); setSsComp(confirmed[0].id); }
      })
      .finally(() => setLoading(false));
  }, []);

  // Auto-poll while server-side collection is in flight (DB-backed, survives nav).
  useEffect(() => {
    if (nActive <= 0) return;
    const t = setInterval(() => { refreshLive(); }, 5000);
    return () => clearInterval(t);
  }, [nActive]);

  // 一键采集全部：入队全部 active格子×confirmed竞品 → 派发后台。
  async function handleCollectAll() {
    setCollecting(true);
    setCollectMsg("");
    try {
      await api.enqueueAll();
      const r = await api.dispatchQueued();
      setCollectMsg(
        r.dispatched > 0
          ? `已派发 ${r.dispatched} 个采集任务到后台，进度自动刷新（可离开本页）`
          : "没有新任务可派发（可能都已采过）"
      );
      await refreshLive();
    } catch (e) {
      setCollectMsg(e instanceof Error ? e.message : "采集失败");
    } finally {
      setCollecting(false);
    }
  }

  // 按场景采集：把该场景下所有竞品入队 → 派发。
  async function handleCollectScene(cellId: string) {
    setSceneBusy(cellId);
    try {
      for (const comp of competitors) {
        await api.manualPin(cellId, comp.id);
      }
      await api.dispatchQueued();
      await refreshLive();
    } catch {
      // best-effort
    } finally {
      setSceneBusy(null);
    }
  }

  // 停止：取消所有待采（QUEUED→UNPROBED）。已在跑的 ≤4 个自然跑完。
  async function handleStop() {
    setStopping(true);
    try {
      const r = await api.stopCollection();
      setCollectMsg(`已停止 ${r.stopped} 个待采任务（正在跑的少量会自然结束）`);
      await refreshLive();
    } catch (e) {
      setCollectMsg(e instanceof Error ? e.message : "停止失败");
    } finally {
      setStopping(false);
    }
  }

  async function handlePin() {
    if (!pinCell || !pinComp) return;
    setPinStatus("loading"); setPinErr("");
    try {
      await api.manualPin(pinCell, pinComp);
      await api.dispatchQueued();
      setPinStatus("ok");
      await refreshLive();
    } catch (e) {
      setPinErr(e instanceof Error ? e.message : "操作失败");
      setPinStatus("err");
    }
  }

  async function handleScreenshot() {
    if (!ssUrl.trim() || !ssCell || !ssComp) return;
    setSsStatus("loading"); setSsErr(""); setSsResult(null);
    try {
      const result = await api.manualScreenshot({ url: ssUrl.trim(), cell_id: ssCell, competitor_id: ssComp });
      setSsResult({ source_url: result.source_url, ai_score: result.ai_score });
      setSsStatus("ok");
      setSsUrl("");
    } catch (e) {
      setSsErr(e instanceof Error ? e.message : "截图失败");
      setSsStatus("err");
    }
  }

  function toggleExpand(cellId: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(cellId) ? next.delete(cellId) : next.add(cellId);
      return next;
    });
  }

  // Aggregate coverage by cell: status per competitor.
  const covMap = new Map<string, string>();  // `${cell}|${comp}` -> status
  for (const r of coverage) covMap.set(`${r.cell_id}|${r.competitor_id}`, r.status);
  const sortedCells = [...cells].sort((a, b) => (b.value_score ?? 0) - (a.value_score ?? 0));

  const readyCount = Number((metrics as any)?.coverage?.shortlist_ready ?? 0);
  const p = (metrics as any)?.pipeline ?? {};
  const adoptionPct = p.adoption_rate != null ? Math.round(p.adoption_rate * 100) : null;

  return (
    <div>
      <div className="text-gray-500 text-xs mb-1">M3 · 采集监控</div>
      <h1 className="text-xl font-bold mb-1">采集监控</h1>
      <p className="text-gray-500 text-sm mb-5 max-w-2xl">
        以场景为主轴，横向拉齐各竞品的采集情况。选定竞品后一键采集全部，或按单个场景采集。
      </p>

      {/* 待审核提醒 */}
      {!loading && readyCount > 0 && (
        <div className="mb-5 flex items-center justify-between gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
          <span className="text-sm text-amber-800">
            有 <span className="font-semibold">{readyCount}</span> 个场景采集到证据，等待人工审核
          </span>
          <button onClick={() => router.push("/review")}
            className="flex-none text-sm px-4 py-2 rounded-lg bg-amber-600 text-white hover:bg-amber-700 transition-colors font-medium">
            下一步：审核证据 →
          </button>
        </div>
      )}

      {/* 一键采集 + 进度 */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 mb-6">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <h2 className="text-sm font-semibold text-gray-700">采集全部竞品</h2>
            <p className="text-xs text-gray-500 mt-1">
              {cells.length} 个场景 × {competitors.length} 个竞品，一键在后台采集所有组合。
            </p>
          </div>
          <button
            onClick={handleCollectAll}
            disabled={collecting || loading || competitors.length === 0}
            className="text-sm px-4 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors font-medium whitespace-nowrap"
          >
            {collecting ? "派发中…" : "▶ 一键采集全部"}
          </button>
        </div>
        {collectMsg && <div className="text-xs text-gray-500 mt-3">{collectMsg}</div>}
        {nActive > 0 && (
          <div className="mt-3">
            <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
              <span>
                后台采集中
                <span className="ml-2 text-blue-600">采集中 {nProbing}</span>
                <span className="ml-2 text-amber-600">待采 {nQueued}</span>
              </span>
              <div className="flex items-center gap-3">
                <span className="text-gray-400">每 5 秒自动刷新 · 可离开本页</span>
                <button
                  onClick={handleStop}
                  disabled={stopping}
                  className="px-2.5 py-1 rounded-md bg-red-50 text-red-600 border border-red-200 hover:bg-red-100 disabled:opacity-50 transition-colors font-medium"
                >
                  {stopping ? "停止中…" : "⏹ 停止采集"}
                </button>
              </div>
            </div>
            <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
              <div className="h-full bg-indigo-500 animate-pulse" style={{ width: "100%" }} />
            </div>
          </div>
        )}
      </div>

      {/* 场景 × 竞品 聚合矩阵 */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden mb-6">
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-700">场景采集情况</h2>
          <button onClick={() => { setLoading(true); refreshLive().finally(() => setLoading(false)); }}
            className="text-xs text-indigo-500 hover:text-indigo-700">刷新</button>
        </div>
        {loading ? (
          <div className="p-8 text-center text-gray-400 text-sm">加载中…</div>
        ) : sortedCells.length === 0 ? (
          <div className="p-10 text-center text-gray-400 text-sm">
            还没有场景。请先到「场景网格」生成网格。
          </div>
        ) : (
          <div className="divide-y divide-gray-50">
            {sortedCells.map((cell) => {
              const isOpen = expanded.has(cell.id);
              const statuses = competitors.map((c) => covMap.get(`${cell.id}|${c.id}`));
              const doneN = statuses.filter((s) => s === "SHORTLIST_READY" || s === "SATURATED").length;
              const emptyN = statuses.filter((s) => s === "REJECTED_EMPTY").length;
              return (
                <div key={cell.id}>
                  <div className="flex items-center gap-3 px-5 py-3 hover:bg-gray-50/50">
                    <button onClick={() => toggleExpand(cell.id)} className="flex-1 min-w-0 text-left">
                      <div className="flex items-center gap-2">
                        <span className="text-gray-400 text-xs">{isOpen ? "▼" : "▶"}</span>
                        <span className="font-medium text-gray-800 text-sm truncate">{cell.page_state}</span>
                        <span className="text-xs text-gray-400">{cell.journey_stage}</span>
                      </div>
                      <div className="text-xs text-gray-400 mt-1 ml-5">
                        {competitors.length} 竞品 · <span className="text-green-600">采到 {doneN}</span> · <span className="text-gray-400">空 {emptyN}</span>
                      </div>
                    </button>
                    <button
                      onClick={() => handleCollectScene(cell.id)}
                      disabled={sceneBusy === cell.id || competitors.length === 0}
                      className="flex-none text-xs px-3 py-1.5 rounded-md border border-indigo-200 text-indigo-600 hover:bg-indigo-50 disabled:opacity-50 transition-colors"
                    >
                      {sceneBusy === cell.id ? "派发中…" : "采集本场景"}
                    </button>
                  </div>
                  {isOpen && (
                    <div className="px-5 pb-3 ml-5 flex flex-wrap gap-2">
                      {competitors.map((c) => {
                        const m = statusMeta(covMap.get(`${cell.id}|${c.id}`));
                        return (
                          <span key={c.id} className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md ${m.cls}`}>
                            <span className="font-medium">{c.canonical_name}</span>
                            <span className="opacity-70">{m.label}</span>
                          </span>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 手动截图 */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 mb-6">
        <div className="flex items-center gap-2 mb-3">
          <h2 className="text-sm font-semibold text-gray-700">手动截图</h2>
          <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">Playwright</span>
        </div>
        <p className="text-xs text-gray-500 mb-4">
          自动采集够不到的深层页面，可粘贴 URL 手动截图入库（如登录后才能看到的界面）。
        </p>
        {!loading && (
          <div className="space-y-3">
            <input
              type="url" value={ssUrl}
              onChange={(e) => setSsUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleScreenshot()}
              placeholder="https://help.linear.app/docs/…"
              disabled={ssStatus === "loading"}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-300 disabled:opacity-50"
            />
            <div className="flex flex-wrap gap-3 items-end">
              <select value={ssCell} onChange={(e) => setSsCell(e.target.value)} disabled={ssStatus === "loading"}
                className="border border-gray-200 rounded-lg px-3 py-2 text-sm min-w-[200px] disabled:opacity-50">
                {cells.map((c) => <option key={c.id} value={c.id}>{c.page_state} · {c.journey_stage}</option>)}
              </select>
              <select value={ssComp} onChange={(e) => setSsComp(e.target.value)} disabled={ssStatus === "loading"}
                className="border border-gray-200 rounded-lg px-3 py-2 text-sm min-w-[140px] disabled:opacity-50">
                {competitors.map((c) => <option key={c.id} value={c.id}>{c.canonical_name}</option>)}
              </select>
              <button onClick={handleScreenshot}
                disabled={!ssUrl.trim() || !ssCell || !ssComp || ssStatus === "loading"}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors">
                {ssStatus === "loading" ? "截图中…" : "📸 截图并加入审核"}
              </button>
            </div>
            {ssStatus === "ok" && ssResult && (
              <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
                <span>✓ 截图完成</span>
                <span className="text-xs text-green-600 truncate max-w-[300px]">{ssResult.source_url}</span>
                <a href="/review" className="text-xs text-indigo-600 hover:underline ml-auto whitespace-nowrap">→ 去审核</a>
              </div>
            )}
            {ssStatus === "err" && <p className="text-xs text-red-500">{ssErr}</p>}
          </div>
        )}
      </div>

      {/* 高级：单对补采（折叠） */}
      <div className="bg-white border border-gray-200 rounded-xl p-5">
        <button onClick={() => setShowAdvanced((v) => !v)}
          className="text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1">
          <span>{showAdvanced ? "▼" : "▶"}</span> 高级：单个「场景×竞品」补采
        </button>
        {showAdvanced && !loading && (
          <div className="mt-4 flex flex-wrap gap-3 items-end">
            <select value={pinCell} onChange={(e) => setPinCell(e.target.value)}
              className="border border-gray-200 rounded-lg px-3 py-2 text-sm min-w-[200px]">
              {cells.map((c) => <option key={c.id} value={c.id}>{c.page_state} · {c.journey_stage}</option>)}
            </select>
            <select value={pinComp} onChange={(e) => setPinComp(e.target.value)}
              className="border border-gray-200 rounded-lg px-3 py-2 text-sm min-w-[140px]">
              {competitors.map((c) => <option key={c.id} value={c.id}>{c.canonical_name}</option>)}
            </select>
            <button onClick={handlePin} disabled={!pinCell || !pinComp || pinStatus === "loading"}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-800 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors">
              {pinStatus === "loading" ? "采集中…" : "补采这一对"}
            </button>
            {pinStatus === "ok" && <span className="text-sm text-green-600">✓ 已派发</span>}
            {pinStatus === "err" && <span className="text-sm text-red-500">{pinErr}</span>}
          </div>
        )}
      </div>
    </div>
  );
}
