"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import type { Competitor, LexiconEntry, CompetitorType, DiscoverySuggestion } from "@/lib/types";

const TYPE_LABEL: Record<CompetitorType, string> = {
  direct: "直接竞品",
  indirect: "间接竞品",
  cross_industry: "跨行业标杆",
};

const STATUS_LABEL: Record<string, string> = {
  confirmed: "已确认",
  pending: "待核验",
  excluded: "已排除",
};

const TERM_TYPE_LABEL: Record<string, string> = {
  task: "任务",
  role: "角色",
  ui_state: "页面状态",
  product_alias: "产品别名",
};

const TIER_COLORS: Record<string, string> = {
  direct:          "bg-indigo-50 text-indigo-700 border border-indigo-100",
  indirect:        "bg-amber-50  text-amber-700  border border-amber-100",
  cross_industry:  "bg-green-50  text-green-700  border border-green-100",
};

// ---- Discovery Panel -------------------------------------------------------

function DiscoveryPanel({
  knownProducts,
  onAdd,
  onClose,
  onGoToGrid,
  onCategoryChange,
}: {
  knownProducts: string[];
  onAdd: (s: DiscoverySuggestion) => Promise<void>;
  onClose: () => void;
  onGoToGrid: () => void;
  onCategoryChange: (category: string) => void;
}) {
  const [category, setCategory] = useState("项目管理工具");
  const [discovering, setDiscovering] = useState(false);
  const [suggestions, setSuggestions] = useState<DiscoverySuggestion[]>([]);
  const [added, setAdded] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  async function handleDiscover() {
    if (!category.trim()) return;
    setDiscovering(true);
    setError(null);
    setSuggestions([]);
    try {
      const results = await api.discoverCompetitors(category.trim(), knownProducts);
      setSuggestions(results);
      onCategoryChange(category.trim());  // carry the category to the next step
    } catch (e) {
      setError(e instanceof Error ? e.message : "发现失败");
    } finally {
      setDiscovering(false);
    }
  }

  const [adding, setAdding] = useState<Set<string>>(new Set());

  async function handleAdd(s: DiscoverySuggestion) {
    if (added.has(s.name) || adding.has(s.name)) return;
    setAdding(prev => new Set([...prev, s.name]));
    try {
      await onAdd(s);  // actually persists to the backend
      setAdded(prev => new Set([...prev, s.name]));
    } catch (e) {
      setError(e instanceof Error ? `添加「${s.name}」失败：${e.message}` : "添加失败");
    } finally {
      setAdding(prev => {
        const next = new Set(prev);
        next.delete(s.name);
        return next;
      });
    }
  }

  const tierOrder = ["direct", "indirect", "cross_industry"] as const;
  const grouped = tierOrder.reduce<Record<string, DiscoverySuggestion[]>>((acc, t) => {
    acc[t] = suggestions.filter(s => s.tier === t);
    return acc;
  }, {} as Record<string, DiscoverySuggestion[]>);

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="relative ml-auto w-full max-w-xl bg-white shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 flex-none">
          <div>
            <div className="text-xs text-gray-400 mb-0.5">M0 · AI 发现竞品</div>
            <div className="text-sm font-semibold text-gray-800">输入品类，自动推荐三层标杆</div>
          </div>
          <button onClick={onClose} className="text-xs text-gray-400 hover:text-gray-700 px-2 py-1 rounded hover:bg-gray-100">关闭</button>
        </div>

        {/* Search */}
        <div className="px-6 py-4 border-b border-gray-100 flex-none">
          <div className="flex gap-2">
            <input
              className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-300"
              value={category}
              onChange={e => setCategory(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleDiscover()}
              placeholder="品类名称，如：项目管理工具、CRM、在线教育"
              disabled={discovering}
            />
            <button
              onClick={handleDiscover}
              disabled={!category.trim() || discovering}
              className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors whitespace-nowrap"
            >
              {discovering ? "发现中…" : "AI 发现"}
            </button>
          </div>
          {error && <p className="mt-2 text-xs text-red-500">{error}</p>}
        </div>

        {/* Results */}
        <div className="flex-1 overflow-auto px-6 py-4">
          {suggestions.length === 0 && !discovering && (
            <div className="py-12 text-center text-gray-400 text-sm">
              输入品类名称，点击「AI 发现」获取推荐
            </div>
          )}
          {discovering && (
            <div className="py-12 text-center text-gray-400 text-sm">AI 正在分析中…</div>
          )}
          {tierOrder.map(tier => {
            const items = grouped[tier];
            if (!items?.length) return null;
            const tierMeta = { direct: "直接竞品", indirect: "间接竞品", cross_industry: "跨行业标杆" };
            return (
              <div key={tier} className="mb-6">
                <div className={`inline-flex text-xs px-2 py-0.5 rounded-full font-medium mb-3 ${TIER_COLORS[tier]}`}>
                  {tierMeta[tier]}
                </div>
                <div className="space-y-3">
                  {items.map(s => (
                    <div key={s.name} className="bg-gray-50 border border-gray-200 rounded-xl p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-semibold text-gray-800">{s.name}</div>
                          {s.official_domain && (
                            <div className="text-xs text-gray-400 mt-0.5">{s.official_domain}</div>
                          )}
                          <p className="text-xs text-gray-600 mt-2 leading-relaxed">{s.rationale}</p>
                        </div>
                        <button
                          onClick={() => handleAdd(s)}
                          disabled={added.has(s.name) || adding.has(s.name)}
                          className="flex-none text-xs px-3 py-1.5 rounded-lg border border-indigo-200 text-indigo-600 hover:bg-indigo-50 disabled:opacity-50 disabled:cursor-default transition-colors whitespace-nowrap"
                        >
                          {added.has(s.name) ? "✓ 已添加" : adding.has(s.name) ? "添加中…" : "加入注册"}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        {/* Footer — next step */}
        {added.size > 0 && (
          <div className="flex-none border-t border-gray-200 px-6 py-4 flex items-center justify-between bg-gray-50">
            <span className="text-xs text-gray-500">
              已添加 <span className="font-semibold text-indigo-600">{added.size}</span> 个竞品到注册库
            </span>
            <button
              onClick={onGoToGrid}
              className="text-sm px-4 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors font-medium"
            >
              下一步：生成场景网格 →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ---- Page ------------------------------------------------------------------

export default function RegistryPage() {
  const router = useRouter();
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [lexicon, setLexicon] = useState<LexiconEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [showDiscover, setShowDiscover] = useState(false);
  const [discoverCategory, setDiscoverCategory] = useState("");

  useEffect(() => {
    Promise.all([api.listCompetitors(), api.listLexicon()])
      .then(([c, l]) => {
        setCompetitors(c.items);
        setLexicon(l.items);
      })
      .finally(() => setLoading(false));
  }, []);

  async function handleAddSuggestion(s: DiscoverySuggestion) {
    // Actually persist to the backend, then reflect the real row in local state.
    const created = await api.createCompetitor({
      canonical_name: s.name,
      competitor_type: s.tier,
      official_domain: s.official_domain,
      help_center_domain: s.help_center_domain,
      status: "confirmed",
    });
    setCompetitors(prev => [created, ...prev]);
  }

  const filtered =
    typeFilter === "all"
      ? competitors
      : competitors.filter((c) => c.competitor_type === typeFilter);

  const knownNames = competitors.map(c => c.canonical_name);

  return (
    <div>
      {showDiscover && (
        <DiscoveryPanel
          knownProducts={knownNames}
          onAdd={handleAddSuggestion}
          onClose={() => setShowDiscover(false)}
          onCategoryChange={setDiscoverCategory}
          onGoToGrid={() => {
            const q = discoverCategory.trim();
            router.push(q ? `/grid?category=${encodeURIComponent(q)}` : "/grid");
          }}
        />
      )}

      <div className="flex items-start justify-between mb-1">
        <div className="text-gray-500 text-xs">M0 · 产品实体注册</div>
        <button
          onClick={() => setShowDiscover(true)}
          className="text-xs px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors font-medium"
        >
          🔍 AI 发现竞品
        </button>
      </div>
      <h1 className="text-xl font-bold mb-1">竞品实体与领域词表</h1>
      <p className="text-gray-500 text-sm mb-6 max-w-2xl">
        统一产品实体（含别名、旧名称、域名树），解决 B 端产品改名、收购、模块拆分导致的重复和漏收。词表驱动 M3 的查询扩展。
      </p>

      {/* Filter */}
      <div className="flex gap-2 mb-4">
        {["all", "direct", "indirect", "cross_industry"].map((t) => (
          <button
            key={t}
            onClick={() => setTypeFilter(t)}
            className={`text-xs px-3 py-1.5 rounded-md border transition-colors ${
              typeFilter === t
                ? "border-indigo-500 bg-indigo-50 text-indigo-700 font-medium"
                : "border-gray-200 text-gray-500 hover:border-gray-300 bg-white"
            }`}
          >
            {t === "all" ? "全部" : TYPE_LABEL[t as CompetitorType]}
          </button>
        ))}
      </div>

      {/* Competitor table */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden mb-8">
        {loading ? (
          <div className="p-8 text-center text-gray-400 text-sm">加载中…</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 text-gray-500 text-xs">
                <th className="text-left px-4 py-3 font-medium">产品</th>
                <th className="text-left px-4 py-3 font-medium">类型</th>
                <th className="text-left px-4 py-3 font-medium">别名 / 旧名称</th>
                <th className="text-left px-4 py-3 font-medium">主域名</th>
                <th className="text-left px-4 py-3 font-medium">帮助中心</th>
                <th className="text-left px-4 py-3 font-medium">状态</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c) => (
                <tr key={c.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50">
                  <td className="px-4 py-3">
                    <div className="font-medium">{c.canonical_name}</div>
                    {c.parent_company && (
                      <div className="text-gray-400 text-xs">{c.parent_company}</div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {c.competitor_type && (
                      <Badge variant={c.competitor_type}>
                        {TYPE_LABEL[c.competitor_type]}
                      </Badge>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">
                    {c.aliases.length ? c.aliases.join(", ") : "—"}
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{c.official_domain || "—"}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{c.help_center_domain || "—"}</td>
                  <td className="px-4 py-3">
                    <Badge variant={c.status}>{STATUS_LABEL[c.status]}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Lexicon */}
      <div className="text-gray-500 text-xs mb-1">领域词表</div>
      <h2 className="text-base font-semibold mb-3">DomainLexicon（M3 查询扩展输入）</h2>
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 text-gray-500 text-xs">
              <th className="text-left px-4 py-3 font-medium">词条</th>
              <th className="text-left px-4 py-3 font-medium">类型</th>
              <th className="text-left px-4 py-3 font-medium">语言</th>
              <th className="text-left px-4 py-3 font-medium">级别</th>
              <th className="text-left px-4 py-3 font-medium">来源</th>
            </tr>
          </thead>
          <tbody>
            {lexicon.map((l) => (
              <tr key={l.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50">
                <td className="px-4 py-3 font-medium">{l.term}</td>
                <td className="px-4 py-3 text-gray-500 text-xs">{TERM_TYPE_LABEL[l.term_type]}</td>
                <td className="px-4 py-3 text-gray-500 text-xs uppercase">{l.language}</td>
                <td className="px-4 py-3">
                  <Badge variant={l.level === "category" ? "direct" : "default"}>
                    {l.level === "category" ? "品类级" : "项目级"}
                  </Badge>
                </td>
                <td className="px-4 py-3 text-gray-400 text-xs">{l.source || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
