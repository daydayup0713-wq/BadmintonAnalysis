"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { navigationKeyForPath, type NavigationKey } from "./metrics";

const items: Array<{ key: NavigationKey; href: string; label: string }> = [
  { key: "analysis", href: "/analysis", label: "分析工作台" },
  { key: "tasks", href: "/tasks", label: "任务" },
  { key: "athletes", href: "/athletes", label: "运动员" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const active = navigationKeyForPath(pathname);
  return (
    <>
      <header className="topbar">
        <Link className="brand" href="/analysis">
          <span className="brandMark">BA</span>
          <span className="brandCopy">
            <strong>BadmintonAnalysis</strong>
            <small>外部结果分析平台</small>
          </span>
        </Link>
        <nav aria-label="主导航">
          {items.map((item) => (
            <Link
              aria-current={active === item.key ? "page" : undefined}
              className={active === item.key ? "navActive" : ""}
              href={item.href}
              key={item.key}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="systemState">
          <i />
          结果复核与导出
        </div>
      </header>
      {children}
    </>
  );
}
