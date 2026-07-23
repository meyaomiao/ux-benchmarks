"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { GridCell, Competitor, QueueItem } from "@/lib/types";

export default function CollectPage() {
  const router = useRouter();
  const [cells, setCells] = useState<GridCell[]>([]);
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [pinCell, setPinCell] = useState("");
  const [pinComp, setPinComp] = useState("");
  const [pinStatus, setPinStatus] = useState<"idle" | "loading" | "ok" | "err">("idle");
  const [pinErr, setPinErr] = useState("");

  // Manual screenshot state
  const [ssUrl, setSsUrl] = useState("");
  const [ssCell, setSsCell] = useState("");
  const [ssComp, setSsComp] = useState("");
  const [ssStatus, setSsStatus] = useState<"idle" | "loading" | "ok" | "err">("idle");
  const [ssErr, setSsErr] = useState("");
  const [ssResult, setSsResult] = useState<{ source_url: string; ai_score: number | null } | null>(null);

  // Batch enqueue (#4) + synchronous probe (#5) state
  const [enqueuing, setEnqueuing] = useState(false);
  const [enqueueMsg, setEnqueueMsg] = useState("");
  const [probing, setProbing] = useState<string | null>(null); // "cellId|compId" being probed
  const [probeResults, setProbeResults] = useState<Record<string, string>>({});
  // Async batch (#51): dispatch to Celery, progress read from DB via /m5/metrics.
  const [dispatching, setDispatching] = useState(false);
  const [dispatchMsg, setDispatchMsg] = useState("");

  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);

  const loadQueue = () =>
    api.getQueueStatus().then((items) => setQueue(items));

  // Live status counts from DB-backed metrics (survive navigation / tab close).
  const cov = (metrics as any)?.coverage?.by_status ?? {};
  const nQueued = Number(cov.QUEUED ?? 0);
  const nProbing = Number(cov.PROBING ?? 0);
  const nActive = nQueued + nProbing;   // work still in flight on the server

  const refreshLive = () =>
    Promise.all([api.getQueueStatus(), api.getCoverageMetrics()])
      .then(([q, m]) => { setQueue(q); setMetrics(m); });

  useEffect(() => {
    Promise.all([api.listCells(), api.listCompetitors(), api.getQueueStatus(), api.getCoverageMetrics()])
      .then(([g, c, q, m]) => {
        setCells(g.items);
        const confirmed = c.items.filter((x) => x.status === "confirmed");
        setCompetitors(confirmed);
        setQueue(q);
        setMetrics(m);
        if (g.items[0]) { setPinCell(g.items[0].id); setSsCell(g.items[0].id); }
        if (confirmed[0]) { setPinComp(confirmed[0].id); setSsComp(confirmed[0].id); }
      })
      .finally(() => setLoading(false));
  }, []);

  // Auto-poll while server-side collection is in flight. Because state lives in
  // the DB, this resumes correctly even after navigating away and back.
  useEffect(() => {
    if (nActive <= 0) return;
    const t = setInterval(() => { refreshLive(); }, 5000);
    return () => clearInterval(t);
  }, [nActive]);

  async function handlePin() {
    if (!pinCell || !pinComp) return;
    setPinStatus("loading");
    setPinErr("");
    try {
      await api.manualPin(pinCell, pinComp);
      setPinStatus("ok");
      loadQueue();
    } catch (e) {
      setPinErr(e instanceof Error ? e.message : "操作失败");
      setPinStatus("err");
    }
  }

  async function handleScreenshot() {
    if (!ssUrl.trim() || !ssCell || !ssComp) return;
    setSsStatus("loading");
    setSsErr("");
    setSsResult(null);
    try {
      const result = await api.manualScreenshot({
        url: ssUrl.trim(),
        cell_id: ssCell,
        competitor_id: ssComp,
      });
      setSsResult({ source_url: result.source_url, ai_score: result.ai_score });
      setSsStatus("ok");
      setSsUrl("");
    } catch (e) {
      setSsErr(e instanceof Error ? e.message : "截图失败");
      setSsStatus("err");
    }
  }

  // #4 Queue every (active cell × confirmed competitor) pair in one click.
  async function handleEnqueueAll() {
    setEnqueuing(true);
    setEnqueueMsg("");
    try {
      const r = await api.enqueueAll();
      setEnqueueMsg(`已入队 ${r.newly_queued} 对（共 ${r.pairs_total} 个格子×竞品组合）`);
      await loadQueue();
    } catch (e) {
      setEnqueueMsg(e instanceof Error ? e.message : "批量入队失败");
    } finally {
      setEnqueuing(false);
    }
  }

  // #5 Run one probe synchronously so the user sees collection progress now.
  async function handleProbeNow(cellId: string, compId: string) {
    const key = `${cellId}|${compId}`;
    setProbing(key);
    try {
      const r = await api.probeNow(cellId, compId);
      setProbeResults((prev) => ({
        ...prev,
        [key]: `找到 ${r.candidates_found} · 通过 ${r.passed} · ${r.state}`,
      }));
      await loadQueue();
    } catch (e) {
      setProbeResults((prev) => ({ ...prev, [key]: e instanceof Error ? e.message : "采集失败" }));
    } finally {
      setProbing(null);
    }
  }

  // #50 Batch: probe every queued pair one at a time with live progress.
  // Sequential (each probe is heavy: search + fetch + AI score). Stoppable.
  // #51 Async batch: dispatch all queued pairs to the Celery workers, then let
  // the DB-backed poller (above) show live counts. Returns instantly; the work
  // runs server-side, so navigating away / closing the tab doesn't lose it.
  async function handleDispatch() {
    setDispatching(true);
    setDispatchMsg("");
    try {
      const r = await api.dispatchQueued();
      setDispatchMsg(
        r.dispatched > 0
          ? `已派发 ${r.dispatched} 个采集任务到后台，进度会自动刷新（可离开本页）`
          : "队列为空，请先「加入采集队列」再派发"
      );
      await refreshLive();
    } catch (e) {
      setDispatchMsg(e instanceof Error ? e.message : "派发失败");
    } finally {
      setDispatching(false);
    }
  }

  const cellMap = Object.fromEntries(cells.map((c) => [c.id, c]));
  const compMap = Object.fromEntries(competitors.map((c) => [c.id, c]));

  return (
    <div>
      <div className="text-gray-500 text-xs mb-1">M3 · 采集监控</div>
      <h1 className="text-xl font-bold mb-1">采集监控</h1>
      <p className="text-gray-500 text-sm mb-5 max-w-2xl">
        管理证据采集队列，监控各格子的采集进度。
      </p>

      {/* Next-step banner — appears once there is evidence awaiting review */}
      {!loading && (() => {
        const readyCount = Number((metrics as any)?.coverage?.shortlist_ready ?? 0);
        if (readyCount <= 0) return null;
        return (
          <div className="mb-5 flex items-center justify-between gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
            <span className="text-sm text-amber-800">
              有 <span className="font-semibold">{readyCount}</span> 个格子采集到证据，等待人工审核
            </span>
            <button
              onClick={() => router.push("/review")}
              className="flex-none text-sm px-4 py-2 rounded-lg bg-amber-600 text-white hover:bg-amber-700 transition-colors font-medium"
            >
              下一步：审核证据 →
            </button>
          </div>
        );
      })()}

      {/* Metrics strip (#29) */}
      {metrics && !loading && (() => {
        const p = (metrics as any).pipeline ?? {};
        const cov = (metrics as any).coverage ?? {};
        const adoptionPct = p.adoption_rate != null ? Math.round(p.adoption_rate * 100) : null;
        const healthy = p.adoption_rate_healthy;
        return (
          <div className="grid grid-cols-3 gap-3 mb-5">
            <div className="bg-white border border-gray-200 rounded-xl p-4">
              <div className={`text-2xl font-bold ${adoptionPct != null ? (healthy ? "text-green-600" : "text-amber-600") : "text-gray-400"}`}>
                {adoptionPct != null ? `${adoptionPct}%` : "—"}
              </div>
              <div className="text-xs text-gray-500 mt-1">
                Shortlist 采纳率
                {adoptionPct != null && (
                  <span className={`ml-1 font-medium ${healthy ? "text-green-600" : "text-amber-600"}`}>
                    {healthy ? "✓ 健康" : "⚠ 偏低"}
                  </span>
                )}
              </div>
            </div>
            <div className="bg-white border border-gray-200 rounded-xl p-4">
              <div className="text-2xl font-bold text-indigo-600">{cov.shortlist_ready ?? 0}</div>
              <div className="text-xs text-gray-500 mt-1">待审核格子（SHORTLIST_READY）</div>
            </div>
            <div className="bg-white border border-gray-200 rounded-xl p-4">
              <div className="text-2xl font-bold text-green-600">{cov.saturated ?? 0}</div>
              <div className="text-xs text-gray-500 mt-1">已饱和格子（SATURATED）</div>
            </div>
          </div>
        );
      })()}

      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-6 text-sm text-blue-800 leading-relaxed">
        <div className="font-medium mb-1">采集怎么跑</div>
        点「立即采集 / 批量采集」会<strong>实时执行</strong>：搜索引擎找页面 → 抓取网页 →
        Claude AI 评分打分 → 通过的证据入库待审核。单个约需 1-3 分钟（含真实搜索+抓取+评分），
        批量时按进度条逐个执行。有证据的格子标为「待审核」，搜不到的标为「已拒绝(空)」。
      </div>

      <div className="bg-white border border-gray-200 rounded-xl p-5 mb-6">
        <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
          <h2 className="text-sm font-semibold text-gray-700">手动触发采集</h2>
          <div className="flex items-center gap-2">
            {enqueueMsg && <span className="text-xs text-gray-500">{enqueueMsg}</span>}
            <button
              onClick={handleEnqueueAll}
              disabled={enqueuing || loading}
              className="text-xs px-3 py-1.5 rounded-lg bg-gray-800 text-white hover:bg-gray-900 disabled:opacity-50 transition-colors font-medium"
            >
              {enqueuing ? "入队中…" : "⚡ 全部格子×竞品加入队列"}
            </button>
          </div>
        </div>
        {loading ? (
          <div className="text-sm text-gray-400">加载中…</div>
        ) : (
          <div className="flex flex-wrap gap-3 items-end">
            <div>
              <label className="block text-xs text-gray-500 mb-1">场景格子</label>
              <select
                value={pinCell}
                onChange={(e) => setPinCell(e.target.value)}
                className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 min-w-[200px]"
              >
                {cells.map((c) => (
                  <option key={c.id} value={c.id}>{c.page_state} · {c.journey_stage}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">竞品</label>
              <select
                value={pinComp}
                onChange={(e) => setPinComp(e.target.value)}
                className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 min-w-[140px]"
              >
                {competitors.map((c) => (
                  <option key={c.id} value={c.id}>{c.canonical_name}</option>
                ))}
              </select>
            </div>
            <button
              onClick={handlePin}
              disabled={!pinCell || !pinComp || pinStatus === "loading"}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
            >
              {pinStatus === "loading" ? "加入中…" : "加入采集队列"}
            </button>
            {pinStatus === "ok" && <span className="text-sm text-green-600">✓ 已加入队列</span>}
            {pinStatus === "err" && <span className="text-sm text-red-500">{pinErr}</span>}
          </div>
        )}
      </div>

      {/* Manual Screenshot Panel */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 mb-6">
        <div className="flex items-center gap-2 mb-3">
          <h2 className="text-sm font-semibold text-gray-700">手动截图</h2>
          <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">Playwright</span>
        </div>
        <p className="text-xs text-gray-500 mb-4">
          粘贴竞品页面 URL，系统自动截图并加入审核队列。支持任何公开网页：帮助文档、功能页、产品演示页等。
        </p>
        {loading ? (
          <div className="text-sm text-gray-400">加载中…</div>
        ) : (
          <div className="space-y-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">页面 URL</label>
              <input
                type="url"
                value={ssUrl}
                onChange={(e) => setSsUrl(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleScreenshot()}
                placeholder="https://help.linear.app/docs/…"
                disabled={ssStatus === "loading"}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-300 disabled:opacity-50"
              />
            </div>
            <div className="flex flex-wrap gap-3 items-end">
              <div>
                <label className="block text-xs text-gray-500 mb-1">关联场景格子</label>
                <select
                  value={ssCell}
                  onChange={(e) => setSsCell(e.target.value)}
                  disabled={ssStatus === "loading"}
                  className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 min-w-[200px] disabled:opacity-50"
                >
                  {cells.map((c) => (
                    <option key={c.id} value={c.id}>{c.page_state} · {c.journey_stage}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">竞品</label>
                <select
                  value={ssComp}
                  onChange={(e) => setSsComp(e.target.value)}
                  disabled={ssStatus === "loading"}
                  className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 min-w-[140px] disabled:opacity-50"
                >
                  {competitors.map((c) => (
                    <option key={c.id} value={c.id}>{c.canonical_name}</option>
                  ))}
                </select>
              </div>
              <button
                onClick={handleScreenshot}
                disabled={!ssUrl.trim() || !ssCell || !ssComp || ssStatus === "loading"}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
              >
                {ssStatus === "loading" ? "截图中…" : "📸 截图并加入审核"}
              </button>
            </div>
            {ssStatus === "ok" && ssResult && (
              <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
                <span>✓ 截图完成</span>
                <span className="text-xs text-green-600 truncate max-w-[300px]">{ssResult.source_url}</span>
                {ssResult.ai_score != null && (
                  <span className="ml-auto text-xs bg-green-100 text-green-800 px-2 py-0.5 rounded-full">
                    分数 {(ssResult.ai_score * 100).toFixed(0)}
                  </span>
                )}
                <a href="/review" className="text-xs text-indigo-600 hover:underline ml-1 whitespace-nowrap">→ 去审核</a>
              </div>
            )}
            {ssStatus === "err" && (
              <p className="text-xs text-red-500">{ssErr}</p>
            )}
          </div>
        )}
      </div>

      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-700">
            采集队列
            {queue.length > 0 && (
              <span className="ml-2 text-xs text-gray-400 font-normal">{queue.length} 条</span>
            )}
          </h2>
          <div className="flex items-center gap-3">
            {queue.length > 0 && (
              <button
                onClick={handleDispatch}
                disabled={dispatching}
                className="text-xs px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors font-medium"
              >
                {dispatching ? "派发中…" : `▶ 后台批量采集（${queue.length}）`}
              </button>
            )}
            <button
              onClick={() => { setLoading(true); refreshLive().finally(() => setLoading(false)); }}
              className="text-xs text-indigo-500 hover:text-indigo-700"
            >
              刷新
            </button>
          </div>
        </div>
        {(nActive > 0 || dispatchMsg) && (
          <div className="px-5 pt-3">
            {dispatchMsg && <div className="text-xs text-gray-500 mb-2">{dispatchMsg}</div>}
            {nActive > 0 && (
              <>
                <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
                  <span>
                    后台采集中
                    <span className="ml-1 text-indigo-600">采集中 {nProbing}</span>
                    <span className="ml-1 text-amber-600">待采 {nQueued}</span>
                  </span>
                  <span className="text-gray-400">每 5 秒自动刷新 · 可离开本页</span>
                </div>
                <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
                  <div className="h-full bg-indigo-500 animate-pulse" style={{ width: "100%" }} />
                </div>
              </>
            )}
          </div>
        )}
        {loading ? (
          <div className="p-8 text-center text-gray-400 text-sm">加载中…</div>
        ) : queue.length === 0 ? (
          <div className="p-10 text-center text-gray-400 text-sm">
            队列为空。使用上方表单手动触发，或等待系统自动将格子加入队列。
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 text-xs border-b border-gray-100">
                <th className="px-5 py-3 font-medium">格子</th>
                <th className="px-4 py-3 font-medium">竞品</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium">探测次数</th>
                <th className="px-4 py-3 font-medium">上次探测</th>
                <th className="px-4 py-3 font-medium text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {queue.map((item) => {
                const cell = cellMap[item.cell_id];
                const comp = compMap[item.competitor_id];
                const key = `${item.cell_id}|${item.competitor_id}`;
                const result = probeResults[key];
                const isProbing = probing === key;
                return (
                  <tr key={item.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50">
                    <td className="px-5 py-3 text-gray-700">
                      {cell ? `${cell.page_state} · ${cell.journey_stage}` : item.cell_id.slice(0, 8)}
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {comp?.canonical_name ?? item.competitor_id.slice(0, 8)}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${
                        item.status === "PROBING" ? "bg-blue-50 text-blue-600" :
                        item.status === "QUEUED"  ? "bg-amber-50 text-amber-700" :
                        "bg-gray-100 text-gray-500"
                      }`}>{item.status}</span>
                    </td>
                    <td className="px-4 py-3 text-gray-500">{item.probe_cycles}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs">
                      {item.last_probed_at
                        ? new Date(item.last_probed_at).toLocaleString("zh-CN")
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      {result ? (
                        <span className="text-[11px] text-green-600">{result}</span>
                      ) : (
                        <button
                          onClick={() => handleProbeNow(item.cell_id, item.competitor_id)}
                          disabled={isProbing}
                          className="text-xs px-2.5 py-1 rounded-md bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                        >
                          {isProbing ? "采集中…" : "立即采集"}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
