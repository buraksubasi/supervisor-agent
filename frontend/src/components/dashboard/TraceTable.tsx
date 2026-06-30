"use client";

import { useEffect, useState } from "react";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

interface TraceRow {
  id: string;
  question: string;
  agent_type: string;
  tools_used: string[];
  latency_ms: number | null;
  cost_usd: number | null;
  status: string;
  created_at: string | null;
}

const AGENT_BADGE: Record<string, string> = {
  query_youtube_rag: "bg-indigo-500/20 text-indigo-300",
  query_sql_agent: "bg-emerald-500/20 text-emerald-300",
  query_browser_agent: "bg-amber-500/20 text-amber-300",
  supervisor: "bg-purple-500/20 text-purple-300",
};

export default function TraceTable({
  onSelect,
  selectedId,
}: {
  onSelect: (id: string) => void;
  selectedId: string | null;
}) {
  const [traces, setTraces] = useState<TraceRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [agentFilter, setAgentFilter] = useState("");

  const load = () => {
    const url = agentFilter
      ? `${BACKEND}/api/traces?limit=100&agent_type=${agentFilter}`
      : `${BACKEND}/api/traces?limit=100`;
    fetch(url)
      .then((r) => r.json())
      .then(setTraces)
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    setLoading(true);
    load();
  }, [agentFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="bg-surface-secondary rounded-xl border border-surface-border flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-surface-border">
        <h3 className="text-white font-medium text-sm">Trace Listesi</h3>
        <div className="flex items-center gap-2">
          <select
            value={agentFilter}
            onChange={(e) => setAgentFilter(e.target.value)}
            className="bg-surface-tertiary border border-surface-border text-slate-300 text-xs rounded-lg px-2 py-1"
          >
            <option value="">Tüm agent'lar</option>
            <option value="query_youtube_rag">YouTube RAG</option>
            <option value="query_sql_agent">SQL Agent</option>
            <option value="query_browser_agent">Browser Agent</option>
            <option value="supervisor">Supervisor</option>
          </select>
          <button
            onClick={() => { setLoading(true); load(); }}
            className="text-slate-400 hover:text-white text-xs px-2 py-1 rounded-lg bg-surface-tertiary border border-surface-border"
          >
            ↻ Yenile
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-y-auto flex-1">
        {loading ? (
          <div className="p-6 space-y-2">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-10 bg-surface-tertiary rounded animate-pulse" />
            ))}
          </div>
        ) : !traces.length ? (
          <div className="p-10 text-center text-slate-500 text-sm">Henüz trace kaydı yok.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-surface-secondary">
              <tr className="border-b border-surface-border text-slate-400 text-xs">
                <th className="text-left px-4 py-2 font-medium">Soru</th>
                <th className="text-left px-4 py-2 font-medium">Agent</th>
                <th className="text-right px-4 py-2 font-medium">Latency</th>
                <th className="text-right px-4 py-2 font-medium">Maliyet</th>
                <th className="text-right px-4 py-2 font-medium">Zaman</th>
              </tr>
            </thead>
            <tbody>
              {traces.map((t) => (
                <tr
                  key={t.id}
                  onClick={() => onSelect(t.id)}
                  className={`border-b border-surface-border/50 cursor-pointer transition-colors ${
                    selectedId === t.id
                      ? "bg-accent/10 border-l-2 border-l-accent"
                      : "hover:bg-surface-tertiary"
                  }`}
                >
                  <td className="px-4 py-2.5 text-slate-200 max-w-xs">
                    <p className="truncate">{t.question}</p>
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex flex-wrap gap-1">
                      {(t.tools_used?.length ? t.tools_used : [t.agent_type]).map((tool) => (
                        <span
                          key={tool}
                          className={`px-2 py-0.5 rounded text-xs ${
                            AGENT_BADGE[tool] ?? "bg-slate-500/20 text-slate-300"
                          }`}
                        >
                          {tool.replace("query_", "").replace(/_/g, " ")}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-right text-slate-300">
                    {t.latency_ms != null ? `${t.latency_ms} ms` : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-right text-slate-300">
                    {t.cost_usd != null ? `$${t.cost_usd.toFixed(5)}` : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-right text-slate-500 text-xs">
                    {t.created_at ? new Date(t.created_at).toLocaleString("tr-TR") : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
