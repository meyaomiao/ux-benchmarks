import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "UX Benchmarks",
  description: "场景级 UX 设计标杆工具 · 采集阶段",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
