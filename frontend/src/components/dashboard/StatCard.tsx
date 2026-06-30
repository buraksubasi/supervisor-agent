interface StatCardProps {
  label: string;
  value: string;
  sub: string;
  icon: string;
  color: "indigo" | "amber" | "emerald" | "purple";
}

const colorMap = {
  indigo: "from-indigo-500/20 to-indigo-500/5 border-indigo-500/30 text-indigo-400",
  amber: "from-amber-500/20 to-amber-500/5 border-amber-500/30 text-amber-400",
  emerald: "from-emerald-500/20 to-emerald-500/5 border-emerald-500/30 text-emerald-400",
  purple: "from-purple-500/20 to-purple-500/5 border-purple-500/30 text-purple-400",
};

export default function StatCard({ label, value, sub, icon, color }: StatCardProps) {
  return (
    <div
      className={`rounded-xl border bg-gradient-to-br p-5 ${colorMap[color]}`}
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="text-slate-400 text-xs font-medium uppercase tracking-wide">{label}</p>
          <p className="text-white text-2xl font-bold mt-1">{value}</p>
          <p className="text-slate-500 text-xs mt-1">{sub}</p>
        </div>
        <span className="text-2xl">{icon}</span>
      </div>
    </div>
  );
}
