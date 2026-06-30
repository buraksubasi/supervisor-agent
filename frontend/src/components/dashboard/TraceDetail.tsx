"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

interface ToolCall {
  id: string;
  tool_name: string;
  tool_args: string;
  tool_result: string;
  latency_ms: number | null;
  step_order: number;
}

interface Evaluation {
  faithfulness_score: number | null;
  relevance_score: number | null;
  hallucination_score: number | null;
  overall_score: number | null;
  faithfulness_reason: string | null;
  relevance_reason: string | null;
  hallucination_reason: string | null;
  evaluated_at: string | null;
}

interface TraceDetail {
  id: string;
  question: string;
  answer: string | null;
  agent_type: string;
  latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  status: string;
  created_at: string | null;
  tool_calls: ToolCall[];
  evaluation: Evaluation | null;
}

function ScoreBar({ label, value, invert = false }: { label: string; value: number | null; invert?: boolean }) {
  if (value == null) return null;
  const display = invert ? 1 - value : value;
  const pct = Math.round(display * 100);
  const color = pct >= 80 ? "bg-emerald-500" : pct >= 50 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-slate-400">{label}</span>
        <span className="text-white font-medium">{pct}%</span>
      </div>
      <div className="h-1.5 bg-surface-tertiary rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function TraceDetail({
  traceId,
  onClose,
}: {
  traceId: string;
  onClose: () => void;
}) {
  const [trace, setTrace] = useState<TraceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);

  const load = () => {
    setLoading(true);
    fetch(`${BACKEND}/api/traces/${traceId}`)
      .then((r) => r.json())
      .then(setTrace)
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [traceId]); // eslint-disable-line react-hooks/exhaustive-deps

  const runEval = async () => {
    setEvaluating(true);
    await fetch(`${BACKEND}/api/evaluate/${traceId}`, { method: "POST" });
    load();
    setEvaluating(false);
  };

  return (
    <div className="bg-surface-secondary rounded-xl border border-surface-border flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-surface-border shrink-0">
        <h3 className="text-white font-medium text-sm">Trace Detayı</h3>
        <button onClick={onClose} className="text-slate-400 hover:text-white text-lg leading-none">✕</button>
      </div>

      {loading ? (
        <div className="p-6 space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-8 bg-surface-tertiary rounded animate-pulse" />
          ))}
        </div>
      ) : !trace ? (
        <div className="p-6 text-slate-500 text-sm">Trace bulunamadı.</div>
      ) : (
        <div className="overflow-y-auto flex-1 p-4 space-y-4">
          {/* Meta */}
          <div className="grid grid-cols-2 gap-2 text-xs">
            {[
              ["Agent", trace.agent_type.replace("query_", "").replace("_", " ")],
              ["Latency", trace.latency_ms != null ? `${trace.latency_ms} ms` : "—"],
              ["Input Token", trace.input_tokens?.toLocaleString() ?? "—"],
              ["Output Token", trace.output_tokens?.toLocaleString() ?? "—"],
              ["Maliyet", trace.cost_usd != null ? `$${trace.cost_usd.toFixed(5)}` : "—"],
              ["Tarih", trace.created_at ? new Date(trace.created_at).toLocaleString("tr-TR") : "—"],
            ].map(([k, v]) => (
              <div key={k} className="bg-surface-tertiary rounded-lg p-2">
                <p className="text-slate-500">{k}</p>
                <p className="text-white font-medium mt-0.5 truncate">{v}</p>
              </div>
            ))}
          </div>

          {/* Soru */}
          <div>
            <p className="text-slate-400 text-xs font-medium mb-1.5">Soru</p>
            <div className="bg-surface-tertiary rounded-lg px-3 py-2 text-sm text-slate-200">
              {trace.question}
            </div>
          </div>

          {/* Cevap */}
          {trace.answer && (
            <div>
              <p className="text-slate-400 text-xs font-medium mb-1.5">Cevap</p>
              <div className="bg-surface-tertiary rounded-lg px-3 py-2 text-sm prose prose-sm prose-invert max-w-none max-h-48 overflow-y-auto">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{trace.answer}</ReactMarkdown>
              </div>
            </div>
          )}

          {/* Tool calls */}
          {trace.tool_calls.length > 0 && (
            <div>
              <p className="text-slate-400 text-xs font-medium mb-1.5">Tool Çağrıları ({trace.tool_calls.length})</p>
              <div className="space-y-2">
                {trace.tool_calls
                  .sort((a, b) => a.step_order - b.step_order)
                  .map((tc) => (
                    <details key={tc.id} className="bg-surface-tertiary rounded-lg">
                      <summary className="flex items-center gap-2 px-3 py-2 cursor-pointer text-xs text-slate-300 list-none">
                        <span className="w-4 h-4 rounded bg-indigo-500/30 text-indigo-300 flex items-center justify-center text-[10px] shrink-0">
                          {tc.step_order + 1}
                        </span>
                        <span className="font-medium">{tc.tool_name}</span>
                        {tc.latency_ms && (
                          <span className="ml-auto text-slate-500">{tc.latency_ms} ms</span>
                        )}
                      </summary>
                      <div className="px-3 pb-3 space-y-2 text-xs">
                        <div>
                          <p className="text-slate-500 mb-1">Args</p>
                          <pre className="text-slate-300 bg-surface rounded p-2 overflow-x-auto">
                            {tc.tool_args}
                          </pre>
                        </div>
                        <div>
                          <p className="text-slate-500 mb-1">Sonuç (ilk 400 kar.)</p>
                          <p className="text-slate-300 bg-surface rounded p-2 line-clamp-4">
                            {tc.tool_result?.slice(0, 400)}
                          </p>
                        </div>
                      </div>
                    </details>
                  ))}
              </div>
            </div>
          )}

          {/* Evaluation */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-slate-400 text-xs font-medium">LLM-as-Judge Değerlendirmesi</p>
              {!trace.evaluation && (
                <button
                  onClick={runEval}
                  disabled={evaluating}
                  className="text-xs px-2.5 py-1 rounded-lg bg-accent/20 text-accent border border-accent/30 hover:bg-accent/30 disabled:opacity-50 transition-colors"
                >
                  {evaluating ? "Değerlendiriliyor…" : "▶ Değerlendir"}
                </button>
              )}
            </div>

            {trace.evaluation ? (
              <div className="bg-surface-tertiary rounded-lg p-3 space-y-3">
                <ScoreBar label="Faithfulness" value={trace.evaluation.faithfulness_score} />
                <ScoreBar label="Relevance" value={trace.evaluation.relevance_score} />
                <ScoreBar label="Hallucination (düşük = iyi)" value={trace.evaluation.hallucination_score} invert />
                <div className="pt-1 border-t border-surface-border">
                  <ScoreBar label="Overall" value={trace.evaluation.overall_score} />
                </div>

                {/* Gerekçeler */}
                {[
                  ["Faithfulness", trace.evaluation.faithfulness_reason],
                  ["Relevance", trace.evaluation.relevance_reason],
                  ["Hallucination", trace.evaluation.hallucination_reason],
                ]
                  .filter(([, r]) => r)
                  .map(([label, reason]) => (
                    <div key={label} className="text-xs text-slate-400 border-t border-surface-border pt-2">
                      <span className="text-slate-500 mr-1">{label}:</span>
                      {reason}
                    </div>
                  ))}
              </div>
            ) : (
              <div className="bg-surface-tertiary rounded-lg p-3 text-xs text-slate-500 text-center">
                Henüz değerlendirilmemiş.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
