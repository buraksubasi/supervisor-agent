"use client";

import { useEffect, useState } from "react";
import StatCard from "@/components/dashboard/StatCard";
import LatencyChart from "@/components/dashboard/LatencyChart";
import EvalChart from "@/components/dashboard/EvalChart";
import CostChart from "@/components/dashboard/CostChart";
import TraceTable from "@/components/dashboard/TraceTable";
import TraceDetail from "@/components/dashboard/TraceDetail";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "latency", label: "Latency" },
  { id: "eval", label: "Eval Skorları" },
  { id: "traces", label: "Trace Explorer" },
  { id: "cost", label: "Maliyet" },
] as const;
type TabId = (typeof TABS)[number]["id"];

export interface Stats {
  total_requests: number;
  avg_latency_ms: number;
  total_cost_usd: number;
  avg_eval_score: number;
  agent_distribution: Record<string, number>;
  period_days: number;
}

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [days, setDays] = useState(7);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    fetch(`${BACKEND}/api/stats?days=${days}`)
      .then((r) => r.json())
      .then((d) => setStats(d))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [days]);

  return (
    <div className="h-full flex flex-col bg-surface overflow-hidden">
      {/* Dashboard header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-surface-border bg-surface-secondary shrink-0">
        <div>
          <h1 className="text-white font-semibold">Observability Dashboard</h1>
          <p className="text-slate-400 text-xs mt-0.5">Gerçek zamanlı performans ve kalite metrikleri</p>
        </div>
        {/* Period selector */}
        <div className="flex items-center gap-1 bg-surface-tertiary rounded-lg p-1">
          {[7, 14, 30].map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                days === d
                  ? "bg-accent text-white"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              {d}g
            </button>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-0 border-b border-surface-border bg-surface-secondary shrink-0 px-6">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? "border-accent text-accent"
                : "border-transparent text-slate-400 hover:text-white"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* ── Overview ── */}
        {activeTab === "overview" && (
          <div className="space-y-6">
            {/* Stat cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <StatCard
                label="Toplam İstek"
                value={loading ? "—" : String(stats?.total_requests ?? 0)}
                sub={`Son ${days} gün`}
                icon="📨"
                color="indigo"
              />
              <StatCard
                label="Ort. Latency"
                value={loading ? "—" : `${stats?.avg_latency_ms ?? 0} ms`}
                sub="Tüm agent'lar"
                icon="⚡"
                color="amber"
              />
              <StatCard
                label="Toplam Maliyet"
                value={loading ? "—" : `$${(stats?.total_cost_usd ?? 0).toFixed(4)}`}
                sub="Gemini API"
                icon="💵"
                color="emerald"
              />
              <StatCard
                label="Ort. Eval Skoru"
                value={
                  loading
                    ? "—"
                    : stats?.avg_eval_score
                    ? `${(stats.avg_eval_score * 100).toFixed(1)}%`
                    : "N/A"
                }
                sub="LLM-as-judge"
                icon="🎯"
                color="purple"
              />
            </div>

            {/* Agent dağılımı */}
            {stats?.agent_distribution && (
              <div className="bg-surface-secondary rounded-xl border border-surface-border p-5">
                <h3 className="text-white font-medium mb-4">Agent Dağılımı</h3>
                <div className="flex flex-wrap gap-3">
                  {Object.entries(stats.agent_distribution).map(([agent, count]) => {
                    const total = Object.values(stats.agent_distribution).reduce(
                      (a, b) => a + b,
                      0
                    );
                    const pct = total ? Math.round((count / total) * 100) : 0;
                    const colors: Record<string, string> = {
                      query_youtube_rag: "bg-indigo-500/20 text-indigo-300 border-indigo-500/30",
                      query_sql_agent: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
                      query_browser_agent: "bg-amber-500/20 text-amber-300 border-amber-500/30",
                      supervisor: "bg-purple-500/20 text-purple-300 border-purple-500/30",
                    };
                    return (
                      <div
                        key={agent}
                        className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm ${
                          colors[agent] ?? "bg-slate-500/20 text-slate-300 border-slate-500/30"
                        }`}
                      >
                        <span className="font-medium">{agent.replace("query_", "").replace("_", " ")}</span>
                        <span className="opacity-70">{count} istek ({pct}%)</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Mini preview charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="bg-surface-secondary rounded-xl border border-surface-border p-5">
                <h3 className="text-white font-medium mb-4">Latency Trendi</h3>
                <LatencyChart days={days} mini />
              </div>
              <div className="bg-surface-secondary rounded-xl border border-surface-border p-5">
                <h3 className="text-white font-medium mb-4">Eval Skor Trendi</h3>
                <EvalChart days={days} mini />
              </div>
            </div>
          </div>
        )}

        {/* ── Latency ── */}
        {activeTab === "latency" && (
          <div className="bg-surface-secondary rounded-xl border border-surface-border p-6">
            <h3 className="text-white font-medium mb-6">Latency — Zaman Serisi</h3>
            <LatencyChart days={days} />
          </div>
        )}

        {/* ── Eval ── */}
        {activeTab === "eval" && (
          <div className="space-y-4">
            <div className="bg-surface-secondary rounded-xl border border-surface-border p-6">
              <h3 className="text-white font-medium mb-6">Eval Skor Trendi</h3>
              <EvalChart days={days} />
            </div>
          </div>
        )}

        {/* ── Trace Explorer ── */}
        {activeTab === "traces" && (
          <div className="flex gap-4 h-full">
            <div className={`${selectedTraceId ? "w-1/2" : "w-full"} transition-all`}>
              <TraceTable onSelect={setSelectedTraceId} selectedId={selectedTraceId} />
            </div>
            {selectedTraceId && (
              <div className="w-1/2">
                <TraceDetail traceId={selectedTraceId} onClose={() => setSelectedTraceId(null)} />
              </div>
            )}
          </div>
        )}

        {/* ── Cost ── */}
        {activeTab === "cost" && (
          <div className="bg-surface-secondary rounded-xl border border-surface-border p-6">
            <h3 className="text-white font-medium mb-6">Token Kullanımı ve Maliyet</h3>
            <CostChart days={days} />
          </div>
        )}
      </div>
    </div>
  );
}
