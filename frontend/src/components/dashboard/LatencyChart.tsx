"use client";

import { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

const AGENT_COLORS: Record<string, string> = {
  query_youtube_rag: "#6366f1",
  query_sql_agent: "#10b981",
  query_browser_agent: "#f59e0b",
  supervisor: "#a855f7",
};

interface Row {
  date: string;
  agent_type: string;
  avg_latency_ms: number;
}

interface ChartPoint {
  date: string;
  [agent: string]: number | string;
}

export default function LatencyChart({ days, mini }: { days: number; mini?: boolean }) {
  const [data, setData] = useState<ChartPoint[]>([]);
  const [agents, setAgents] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${BACKEND}/api/latency-chart?days=${days}`)
      .then((r) => r.json())
      .then((rows: Row[]) => {
        // pivot: date → { date, agent1: ms, agent2: ms }
        const map: Record<string, ChartPoint> = {};
        const agentSet = new Set<string>();
        for (const row of rows) {
          if (!map[row.date]) map[row.date] = { date: row.date };
          map[row.date][row.agent_type] = row.avg_latency_ms;
          agentSet.add(row.agent_type);
        }
        setData(Object.values(map).sort((a, b) => a.date.localeCompare(b.date)));
        setAgents(Array.from(agentSet));
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [days]);

  if (loading) return <Skeleton />;
  if (!data.length) return <Empty text="Henüz latency verisi yok." />;

  const height = mini ? 180 : 320;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2e3347" />
        <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 11 }} />
        <YAxis
          tick={{ fill: "#64748b", fontSize: 11 }}
          tickFormatter={(v) => `${v}ms`}
        />
        <Tooltip
          contentStyle={{ background: "#1a1d27", border: "1px solid #2e3347", borderRadius: 8 }}
          labelStyle={{ color: "#e2e8f0" }}
          formatter={(v) => [`${Number(v)} ms`, ""]}
        />
        {!mini && <Legend wrapperStyle={{ color: "#94a3b8", fontSize: 12 }} />}
        {agents.map((a) => (
          <Line
            key={a}
            type="monotone"
            dataKey={a}
            name={a.replace("query_", "").replace("_", " ")}
            stroke={AGENT_COLORS[a] ?? "#94a3b8"}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

function Skeleton() {
  return <div className="h-40 bg-surface-tertiary rounded-lg animate-pulse" />;
}
function Empty({ text }: { text: string }) {
  return (
    <div className="h-40 flex items-center justify-center text-slate-500 text-sm">{text}</div>
  );
}
