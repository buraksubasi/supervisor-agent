"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type SseEventType = "thinking" | "tool_call" | "tool_result" | "answer" | "done" | "error";

interface SseEvent {
  type: SseEventType;
  // thinking
  message?: string;
  // tool_call / tool_result
  step?: number;
  tool?: string;
  args?: Record<string, unknown>;
  preview?: string;
  // answer
  content?: string;
  // done
  trace?: TraceItem[];
  // error
  // (message is reused)
}

interface TraceItem {
  tool: string;
  args: Record<string, unknown>;
  result: string;
}

// A single "step" card shown while the agent is working
interface StepCard {
  id: number;
  tool: string;
  args: Record<string, unknown>;
  preview?: string;
  done: boolean;
}

type MessageRole = "user" | "assistant";

interface Message {
  id: string;
  role: MessageRole;
  text?: string;        // final answer (assistant) or user question
  steps: StepCard[];    // tool call cards (assistant only)
  thinking?: string;    // last "thinking" message
  streaming: boolean;
  error?: string;
}

// ---------------------------------------------------------------------------
// Tool display helpers
// ---------------------------------------------------------------------------
const TOOL_META: Record<string, { label: string; icon: string; color: string }> = {
  query_youtube_rag: { label: "YouTube RAG", icon: "▶", color: "indigo" },
  query_sql_agent: { label: "SQL Agent", icon: "🗄", color: "emerald" },
  query_browser_agent: { label: "Browser Agent", icon: "🌐", color: "amber" },
};

function toolMeta(name: string) {
  return TOOL_META[name] ?? { label: name, icon: "⚙", color: "slate" };
}

function colorClasses(color: string) {
  switch (color) {
    case "indigo": return { border: "border-indigo-500", bg: "bg-indigo-500/10", text: "text-indigo-400", badge: "bg-indigo-500/20 text-indigo-300" };
    case "emerald": return { border: "border-emerald-500", bg: "bg-emerald-500/10", text: "text-emerald-400", badge: "bg-emerald-500/20 text-emerald-300" };
    case "amber": return { border: "border-amber-500", bg: "bg-amber-500/10", text: "text-amber-400", badge: "bg-amber-500/20 text-amber-300" };
    default: return { border: "border-slate-500", bg: "bg-slate-500/10", text: "text-slate-400", badge: "bg-slate-500/20 text-slate-300" };
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------
function ToolCard({ step, isLast }: { step: StepCard; isLast: boolean }) {
  const meta = toolMeta(step.tool);
  const c = colorClasses(meta.color);

  return (
    <div
      className={`rounded-lg border ${c.border} ${c.bg} p-3 text-sm mb-2 transition-all ${
        !step.done && isLast ? "tool-active" : "opacity-80"
      }`}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className={`text-base leading-none ${c.text}`}>{meta.icon}</span>
        <span className={`font-medium ${c.text}`}>{meta.label}</span>
        {!step.done ? (
          <span className="ml-auto flex items-center gap-1 text-xs text-slate-400">
            <SpinnerIcon /> çalışıyor
          </span>
        ) : (
          <span className="ml-auto text-xs text-slate-500">✓ tamamlandı</span>
        )}
      </div>

      {/* Args */}
      <div className="mt-1 space-y-0.5">
        {Object.entries(step.args).map(([k, v]) => (
          <p key={k} className="text-slate-400 text-xs truncate">
            <span className="text-slate-500">{k}: </span>
            <span className="text-slate-300">{String(v)}</span>
          </p>
        ))}
      </div>

      {/* Preview */}
      {step.preview && (
        <p className="mt-2 text-xs text-slate-400 border-t border-white/5 pt-2 line-clamp-2">
          {step.preview}
        </p>
      )}
    </div>
  );
}

function ThinkingDots() {
  return (
    <span className="inline-flex items-center gap-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-bounce"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </span>
  );
}

function SpinnerIcon() {
  return (
    <svg className="animate-spin w-3 h-3" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  );
}

function AssistantMessage({ msg }: { msg: Message }) {
  return (
    <div className="flex gap-3 max-w-3xl">
      {/* Avatar */}
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white text-xs font-bold mt-1">
        AI
      </div>

      <div className="flex-1 min-w-0">
        {/* Tool cards */}
        {msg.steps.length > 0 && (
          <div className="mb-3 space-y-1">
            {msg.steps.map((s, i) => (
              <ToolCard key={s.id} step={s} isLast={i === msg.steps.length - 1} />
            ))}
          </div>
        )}

        {/* Thinking / loading */}
        {msg.streaming && !msg.text && (
          <div className="flex items-center gap-2 text-slate-400 text-sm py-1">
            {msg.thinking ? (
              <>
                <ThinkingDots />
                <span>{msg.thinking}</span>
              </>
            ) : (
              <ThinkingDots />
            )}
          </div>
        )}

        {/* Error */}
        {msg.error && (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-red-400 text-sm">
            ⚠ {msg.error}
          </div>
        )}

        {/* Final answer */}
        {msg.text && (
          <div
            className={`prose prose-sm prose-invert max-w-none rounded-xl bg-surface-secondary p-4 ${
              msg.streaming ? "typing-cursor" : ""
            }`}
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}

function UserMessage({ msg }: { msg: Message }) {
  return (
    <div className="flex gap-3 justify-end max-w-3xl ml-auto">
      <div className="bg-accent rounded-2xl rounded-tr-sm px-4 py-2.5 text-white text-sm max-w-xl break-words">
        {msg.text}
      </div>
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-slate-600 flex items-center justify-center text-white text-xs font-bold mt-1">
        U
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Auto-resize textarea
  const resizeTextarea = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  };

  const updateLastMessage = useCallback((updater: (msg: Message) => Message) => {
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (last && last.role === "assistant") {
        next[next.length - 1] = updater(last);
      }
      return next;
    });
  }, []);

  const sendMessage = useCallback(async () => {
    const question = input.trim();
    if (!question || loading) return;

    setInput("");
    setLoading(true);
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      role: "user",
      text: question,
      steps: [],
      streaming: false,
    };
    const assistantMsg: Message = {
      id: `a-${Date.now()}`,
      role: "assistant",
      steps: [],
      streaming: true,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);

    let revealStarted = false;

    try {
      const res = await fetch(`${BACKEND_URL}/ask/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });

      if (!res.ok || !res.body) {
        throw new Error(`HTTP ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          const raw = line.slice(5).trim();
          if (!raw) continue;

          let event: SseEvent;
          try {
            event = JSON.parse(raw);
          } catch {
            continue;
          }

          switch (event.type) {
            case "thinking":
              updateLastMessage((m) => ({ ...m, thinking: event.message }));
              break;

            case "tool_call":
              updateLastMessage((m) => ({
                ...m,
                thinking: undefined,
                steps: [
                  ...m.steps,
                  {
                    id: event.step!,
                    tool: event.tool!,
                    args: event.args ?? {},
                    done: false,
                  },
                ],
              }));
              break;

            case "tool_result":
              updateLastMessage((m) => ({
                ...m,
                steps: m.steps.map((s) =>
                  s.id === event.step && s.tool === event.tool
                    ? { ...s, preview: event.preview, done: true }
                    : s
                ),
              }));
              break;

            case "answer": {
              revealStarted = true;
              const fullText = event.content ?? "";
              // Thinking'i hemen temizle, cursor'ı aktif et
              updateLastMessage((m) => ({ ...m, thinking: undefined, text: "" }));
              // Simüle stream: 8 karakter / 16ms ≈ doğal yazım hissi
              let charIdx = 0;
              const CHUNK = 8;
              const DELAY = 16;
              const reveal = () => {
                charIdx = Math.min(charIdx + CHUNK, fullText.length);
                updateLastMessage((m) => ({ ...m, text: fullText.slice(0, charIdx) }));
                if (charIdx < fullText.length) {
                  setTimeout(reveal, DELAY);
                } else {
                  // Yazım tamamlandı — cursor kapat ve input'u aç
                  updateLastMessage((m) => ({ ...m, streaming: false }));
                  setLoading(false);
                }
              };
              reveal();
              break;
            }

            case "done":
              // Reveal animasyonu zaten streaming=false ve setLoading(false) yapıyor.
              // Sadece answer gelmeden done gelirse (hata/fallback durumu) temizle.
              if (!revealStarted) {
                updateLastMessage((m) => ({ ...m, streaming: false }));
                setLoading(false);
              }
              break;

            case "error":
              updateLastMessage((m) => ({
                ...m,
                streaming: false,
                error: event.message,
              }));
              setLoading(false);
              break;
          }
        }
      }
    } catch (err) {
      updateLastMessage((m) => ({
        ...m,
        streaming: false,
        error: err instanceof Error ? err.message : "Bilinmeyen hata",
      }));
      setLoading(false);
    }
  }, [input, loading, updateLastMessage]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex flex-col h-full bg-surface">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center gap-4 pb-20">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-3xl shadow-lg shadow-indigo-500/20">
              🤖
            </div>
            <div>
              <h2 className="text-white text-xl font-semibold mb-1">Supervisor Agent</h2>
              <p className="text-slate-400 text-sm max-w-sm">
                YouTube videolarını özetleyebilir, veritabanını sorgulayabilir ve web&apos;de
                gezinebilirim.
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-2 max-w-2xl w-full">
              {[
                { icon: "▶", text: "Bu videoyu özetle: youtube.com/...", color: "indigo" },
                { icon: "🗄", text: "Veritabanındaki ürünleri listele", color: "emerald" },
                { icon: "🌐", text: "Python 3.13 haberlerini ara", color: "amber" },
              ].map(({ icon, text, color }) => {
                const c = colorClasses(color);
                return (
                  <button
                    key={text}
                    onClick={() => { setInput(text); textareaRef.current?.focus(); }}
                    className={`text-left rounded-xl border ${c.border} ${c.bg} px-3 py-2.5 text-xs ${c.text} hover:opacity-80 transition-opacity`}
                  >
                    <span className="text-base mr-1">{icon}</span> {text}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {messages.map((msg) =>
          msg.role === "user" ? (
            <UserMessage key={msg.id} msg={msg} />
          ) : (
            <AssistantMessage key={msg.id} msg={msg} />
          )
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-4 py-4 border-t border-surface-border bg-surface-secondary">
        <div className="flex items-end gap-3 max-w-3xl mx-auto bg-surface-tertiary rounded-2xl border border-surface-border px-4 py-3">
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={(e) => { setInput(e.target.value); resizeTextarea(); }}
            onKeyDown={handleKeyDown}
            placeholder="Sorunuzu yazın... (Shift+Enter yeni satır)"
            className="flex-1 bg-transparent text-sm text-white placeholder-slate-500 resize-none outline-none leading-relaxed"
            disabled={loading}
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || loading}
            className="flex-shrink-0 w-8 h-8 rounded-xl bg-accent hover:bg-accent-hover disabled:opacity-30 disabled:cursor-not-allowed transition-colors flex items-center justify-center"
            aria-label="Gönder"
          >
            {loading ? (
              <SpinnerIcon />
            ) : (
              <svg className="w-4 h-4 text-white" viewBox="0 0 24 24" fill="currentColor">
                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
              </svg>
            )}
          </button>
        </div>
        <p className="text-center text-xs text-slate-600 mt-2">Enter gönderir · Shift+Enter yeni satır</p>
      </div>
    </div>
  );
}
