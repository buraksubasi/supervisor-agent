"use client";

import { useEffect, useState } from "react";
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

interface EvalRow {
  date: string;
  faithfulness: number;
  relevance: number;
  hallucination: number;
  overall: number;
}

export default function EvalChart({ days, mini }: { days: number; mini?: boolean }) {
  const [data, setData] = useState<EvalRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${BACKEND}/api/eval-chart?days=${days}`)
      .then((r) => r.json())
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [days]);

  if (loading) return <div className="h-40 bg-surface-tertiary rounded-lg animate-pulse" />;
  if (!data.length)
    return (
      <div className="h-40 flex items-center justify-center text-slate-500 text-sm">
        Henüz eval verisi yok. Bir trace değerlendirmek için{" "}
        <code className="mx-1 text-indigo-400">POST /api/evaluate/{"<id>"}</code> çağır.
      </div>
    );

  const height = mini ? 180 : 320;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2e3347" />
        <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 11 }} />
        <YAxis
          domain={[0, 1]}
          tick={{ fill: "#64748b", fontSize: 11 }}
          tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <Tooltip
          contentStyle={{ background: "#1a1d27", border: "1px solid #2e3347", borderRadius: 8 }}
          labelStyle={{ color: "#e2e8f0" }}
          formatter={(v, name) => [
            `${(Number(v) * 100).toFixed(1)}%`,
            name === "hallucination" ? "🔴 Hallucination" : String(name),
          ]}
        />
        {!mini && <Legend wrapperStyle={{ color: "#94a3b8", fontSize: 12 }} />}

        <Bar dataKey="faithfulness" name="Faithfulness" fill="#6366f1" opacity={0.7} radius={[2, 2, 0, 0]} />
        <Bar dataKey="relevance" name="Relevance" fill="#10b981" opacity={0.7} radius={[2, 2, 0, 0]} />
        <Bar dataKey="hallucination" name="Hallucination" fill="#ef4444" opacity={0.7} radius={[2, 2, 0, 0]} />
        <Line
          type="monotone"
          dataKey="overall"
          name="Overall"
          stroke="#f59e0b"
          strokeWidth={2}
          dot={false}
          strokeDasharray="4 2"
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
