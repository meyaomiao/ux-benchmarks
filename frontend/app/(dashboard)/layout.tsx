"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/registry", label: "产品实体注册", module: "M0" },
  { href: "/grid",     label: "场景网格",     module: "M1" },
  { href: "/collect",  label: "采集监控",     module: "M3" },
  { href: "/review",   label: "素材审核",     module: "M4" },
  { href: "/coverage", label: "覆盖看板",     module: "M5" },
  { href: "/insights", label: "洞察库",       module: "L3" },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  return (
    <div className="grid grid-cols-[220px_1fr] min-h-screen">
      <aside className="bg-[#12151c] text-[#c7ccd6] p-5 flex flex-col gap-1">
        <div className="text-white font-bold text-base mb-1">
          Benchmarks
          <span className="block text-[#8b93a1] font-normal text-[11px] mt-1">
            UX 设计标杆工具 · 采集阶段
          </span>
        </div>
        <div className="text-[#5f6774] text-[10px] tracking-wider uppercase mt-4 mb-1">
          模块
        </div>
        {NAV.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2 px-2.5 py-2 rounded-md text-[13px] transition-colors",
                active
                  ? "bg-[#4f46e5] text-white"
                  : "text-[#c7ccd6] hover:bg-[#1c202a] hover:text-white"
              )}
            >
              <span
                className={cn(
                  "w-5 h-5 rounded grid place-items-center text-[10px] flex-none",
                  active ? "bg-white/20 text-white" : "bg-[#2a2f3a] text-[#c7ccd6]"
                )}
              >
                {item.module}
              </span>
              {item.label}
            </Link>
          );
        })}
        <div className="mt-auto text-[#5f6774] text-[10px] pt-4 border-t border-[#232833]">
          Mock 模式 · 数据为示例
        </div>
      </aside>
      <main className="p-8 overflow-auto">{children}</main>
    </div>
  );
}
