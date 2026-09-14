import type { Metadata } from "next";
import { AppShell } from "./app-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "BadmintonAnalysis 羽毛球分析平台",
  description: "外部分析结果的复核、指标计算与导出平台",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
