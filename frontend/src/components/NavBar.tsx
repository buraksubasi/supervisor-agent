"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/", label: "Chat", icon: "💬" },
  { href: "/dashboard", label: "Dashboard", icon: "📊" },
];

export default function NavBar() {
  const pathname = usePathname();

  return (
    <header className="flex items-center gap-3 px-6 py-3 border-b border-surface-border bg-surface-secondary shrink-0">
      {/* Logo */}
      <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
        <span className="text-white text-xs font-bold">S</span>
      </div>
      <span className="text-white font-semibold text-sm mr-4">Supervisor Agent</span>

      {/* Tabs */}
      <nav className="flex items-center gap-1">
        {TABS.map((tab) => {
          const active =
            tab.href === "/"
              ? pathname === "/"
              : pathname.startsWith(tab.href);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                active
                  ? "bg-accent text-white"
                  : "text-slate-400 hover:text-white hover:bg-surface-tertiary"
              }`}
            >
              <span className="text-base leading-none">{tab.icon}</span>
              {tab.label}
            </Link>
          );
        })}
      </nav>

      {/* Status */}
      <div className="ml-auto flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
        <span className="text-xs text-slate-400">localhost:8000</span>
      </div>
    </header>
  );
}
