"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import type { Competitor, LexiconEntry, CompetitorType } from "@/lib/types";

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

export default function RegistryPage() {
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [lexicon, setLexicon] = useState<LexiconEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState<string>("all");

  useEffect(() => {
    Promise.all([api.listCompetitors(), api.listLexicon()])
      .then(([c, l]) => {
        setCompetitors(c.items);
        setLexicon(l.items);
      })
      .finally(() => setLoading(false));
  }, []);

  const filtered =
    typeFilter === "all"
      ? competitors
      : competitors.filter((c) => c.competitor_type === typeFilter);

  return (
    <div>
      <div className="text-gray-500 text-xs mb-1">M0 · 产品实体注册</div>
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
                <tr
                  key={c.id}
                  className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50"
                >
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
                  <td className="px-4 py-3 text-gray-500 text-xs">
                    {c.official_domain || "—"}
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">
                    {c.help_center_domain || "—"}
                  </td>
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
                <td className="px-4 py-3 text-gray-500 text-xs">
                  {TERM_TYPE_LABEL[l.term_type]}
                </td>
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
