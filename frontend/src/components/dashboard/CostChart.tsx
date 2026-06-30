"use client";

import { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

interface TraceRow {
  id: string;
  created_at: string;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  agent_type: string;
}

interface DayPoint {
  date: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export default function CostChart({ days }: { days: number }) {
  const [data, setData] = useState<DayPoint[]>([]);
  const [totals, setTotals] = useState({ input: 0, output: 0, cost: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${BACKEND}/api/traces?limit=500`)
      .then((r) => r.json())
      .then((traces: TraceRow[]) => {
        const cutoff = new Date();
        cutoff.setDate(cutoff.getDate() - days);

        const map: Record<string, DayPoint> = {};
        for (const t of traces) {
          if (!t.created_at) continue;
          const d = new Date(t.created_at);
          if (d < cutoff) continue;
          const key = t.created_at.slice(0, 10);
          if (!map[key]) map[key] = { date: key, input_tokens: 0, output_tokens: 0, cost_usd: 0 };
          map[key].input_tokens += t.input_tokens ?? 0;
          map[key].output_tokens += t.output_tokens ?? 0;
          map[key].cost_usd += t.cost_usd ?? 0;
        }
        const sorted = Object.values(map).sort((a, b) => a.date.localeCompare(b.date));
        setData(sorted);
        setTotals({
          input: sorted.reduce((s, r) => s + r.input_tokens, 0),
          output: sorted.reduce((s, r) => s + r.output_tokens, 0),
          cost: sorted.reduce((s, r) => s + r.cost_usd, 0),
        });
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [days]);

  if (loading) return <div className="h-60 bg-surface-tertiary rounded-lg animate-pulse" />;
  if (!data.length)
    return (
      <div className="h-60 flex items-center justify-center text-slate-500 text-sm">
        Henüz maliyet verisi yok.
      </div>
    );

  return (
    <div className="space-y-6">
      {/* Summary */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Toplam Input Token", value: totals.input.toLocaleString(), color: "text-indigo-400" },
          { label: "Toplam Output Token", value: totals.output.toLocaleString(), color: "text-emerald-400" },
          { label: "Toplam Maliyet", value: `$${totals.cost.toFixed(5)}`, color: "text-amber-400" },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-surface-tertiary rounded-xl p-4 border border-surface-border">
            <p className="text-slate-400 text-xs">{label}</p>
            <p className={`${color} text-xl font-bold mt-1`}>{value}</p>
          </div>
        ))}
      </div>

      {/* Token kullanımı */}
      <div>
        <p className="text-slate-400 text-sm mb-3">Günlük Token Kullanımı</p>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2e3347" />
            <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 11 }} />
            <YAxis tick={{ fill: "#64748b", fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: "#1a1d27", border: "1px solid #2e3347", borderRadius: 8 }}
              labelStyle={{ color: "#e2e8f0" }}
            />
            <Legend wrapperStyle={{ color: "#94a3b8", fontSize: 12 }} />
            <Bar dataKey="input_tokens" name="Input" fill="#6366f1" radius={[2, 2, 0, 0]} />
            <Bar dataKey="output_tokens" name="Output" fill="#10b981" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Maliyet */}
      <div>
        <p className="text-slate-400 text-sm mb-3">Günlük Maliyet (USD)</p>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2e3347" />
            <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 11 }} />
            <YAxis tick={{ fill: "#64748b", fontSize: 11 }} tickFormatter={(v) => `$${v.toFixed(4)}`} />
            <Tooltip
              contentStyle={{ background: "#1a1d27", border: "1px solid #2e3347", borderRadius: 8 }}
              formatter={(v) => [`$${Number(v).toFixed(5)}`, "Maliyet"]}
            />
            <Bar dataKey="cost_usd" name="Maliyet ($)" fill="#f59e0b" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
