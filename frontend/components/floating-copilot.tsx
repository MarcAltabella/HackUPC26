"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { askCopilot } from "@/lib/api";
import { cleanChatText, displayChatAnswer } from "@/lib/chat-format";
import { logHref } from "@/lib/log-links";
import type { ChatResponse, Severity } from "@/lib/api-types";

// ── Helpers ───────────────────────────────────────────────────────────────────

function cardBorder(s: Severity) {
  if (s === "CRITICAL") return "border-red-500/30";
  if (s === "WARNING")  return "border-yellow-500/25";
  return "border-blue-500/25";
}
function cardBg(s: Severity) {
  if (s === "CRITICAL") return "bg-red-950/10";
  if (s === "WARNING")  return "bg-yellow-950/5";
  return "bg-blue-950/5";
}
function severityPill(s: Severity) {
  if (s === "CRITICAL") return "text-red-400 bg-red-500/15";
  if (s === "WARNING")  return "text-yellow-400 bg-yellow-500/15";
  return "text-blue-400 bg-blue-500/15";
}

// ── Message card ──────────────────────────────────────────────────────────────

interface Message { question: string; response: ChatResponse; }

function FloatingMessage({ msg }: { msg: Message }) {
  const r = msg.response;
  const summary = cleanChatText(r.summary);
  const answer = displayChatAnswer(r.answer, summary);
  return (
    <div className="space-y-2">
      {/* User bubble */}
      <div className="flex justify-end">
        <div className="bg-blue-600/20 border border-blue-500/30 text-[12px] px-3.5 py-2 rounded-2xl rounded-br-md text-foreground max-w-[88%] leading-relaxed">
          {msg.question}
        </div>
      </div>

      {/* AI label */}
      <div className="flex items-center gap-2">
        <div className="h-5 w-5 rounded-full bg-blue-600/25 border border-blue-500/40 flex items-center justify-center shrink-0">
          <span className="text-[8px] text-blue-300 font-bold leading-none">AI</span>
        </div>
        <span className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wide">Co-Pilot</span>
        <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-bold ${severityPill(r.severity)}`}>{r.severity}</span>
      </div>

      {/* Response card */}
      <div className={`rounded-xl border ${cardBorder(r.severity)} ${cardBg(r.severity)} overflow-hidden`}>
        <div className="px-3.5 pt-3 pb-2.5">
          <p className="text-[12px] font-semibold text-foreground leading-snug">{summary}</p>
          {answer && (
            <p className="text-[11.5px] text-foreground/80 mt-1.5 leading-relaxed whitespace-pre-wrap">{answer}</p>
          )}
        </div>

        {r.reasoning_summary.length > 0 && (
          <div className="border-t border-border/30 px-3.5 py-2.5">
            <p className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest mb-2">Reasoning</p>
            <ol className="space-y-1.5">
              {r.reasoning_summary.map((step, i) => (
                <li key={i} className="flex gap-2 text-[11px] text-muted-foreground leading-relaxed">
                  <span className="shrink-0 font-mono text-[10px] text-muted-foreground/40 mt-px">{i + 1}.</span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          </div>
        )}

        {r.recommended_actions.length > 0 && (
          <div className="border-t border-border/30 px-3.5 py-2.5">
            <p className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest mb-2">Actions</p>
            <div className="flex flex-col gap-1.5">
              {r.recommended_actions.map((a, i) => (
                <div key={i} className="flex items-start gap-2 text-[11px] text-foreground/80 leading-relaxed">
                  <span className="h-1.5 w-1.5 rounded-full bg-blue-400/60 shrink-0 mt-1.5" />
                  <span>{a}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {r.citations.length > 0 && (
          <div className="border-t border-border/30 px-3.5 py-2.5">
            <p className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest mb-2">Evidence</p>
            <div className="flex flex-wrap gap-1.5">
              {r.citations.map((c, i) => (
                <Link key={i} href={logHref(c)} className="rounded-md border border-border/50 px-2 py-0.5 text-[10px] font-mono bg-muted/40 flex items-center gap-1 text-muted-foreground hover:border-blue-400/60 hover:text-foreground transition-colors">
                  <span className="text-blue-400">{c.field}</span>
                  {c.value != null && <span>= {typeof c.value === "number" ? (c.value as number).toFixed(3) : String(c.value)}</span>}
                  <span className="opacity-40">@t={c.t}</span>
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── FloatingCopilot ───────────────────────────────────────────────────────────

export function FloatingCopilot({
  scenarioId = "baseline_nominal",
  runNumber  = 0,
  t,
}: {
  scenarioId?: string;
  runNumber?:  number;
  t?: number;
}) {
  const [open,     setOpen]     = useState(false);
  const [input,    setInput]    = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);
  const bottomRef   = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Focus input when panel opens
  useEffect(() => {
    if (open) setTimeout(() => textareaRef.current?.focus(), 50);
  }, [open]);

  async function submit() {
    const q = input.trim();
    if (!q || loading) return;
    setInput("");
    setLoading(true);
    setError(null);
    try {
      const data = await askCopilot({ message: q, scenarioId, runNumber, t });
      setMessages(prev => [...prev, { question: q, response: data }]);
    } catch {
      setError("Could not reach the backend — make sure the FastAPI server is running on :8000.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed bottom-4 right-6 z-40">

      {/* ── Chat panel — replaces the lobster button when open ── */}
      {open ? (
        <div
          className="flex flex-col rounded-xl border border-border bg-background shadow-2xl overflow-hidden w-[370px]"
          style={{ maxHeight: 520 }}
        >
          {/* Header */}
          <div className="shrink-0 flex items-center justify-between px-4 py-2.5 border-b border-border bg-muted/20">
            <div className="flex items-center gap-2">
              <img src="/lobster.png" alt="" className="h-5 w-5 object-contain" />
              <span className="text-[11px] font-semibold text-foreground">Co-Pilot</span>
              {messages.length > 0 && (
                <span className="text-[9px] text-muted-foreground font-mono">
                  {messages.length} {messages.length === 1 ? "reply" : "replies"}
                </span>
              )}
            </div>
            <div className="flex items-center gap-3">
              {messages.length > 0 && (
                <button
                  onClick={() => { setMessages([]); setError(null); }}
                  className="text-[10px] text-muted-foreground hover:text-foreground transition-colors"
                >
                  Clear
                </button>
              )}
              <button
                onClick={() => setOpen(false)}
                className="text-muted-foreground hover:text-foreground transition-colors text-lg leading-none w-5 h-5 flex items-center justify-center"
                aria-label="Close"
              >
                ×
              </button>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto min-h-0 p-3 space-y-4">
            {messages.length === 0 && !loading && !error && (
              <div className="flex flex-col items-center text-center py-8 gap-3">
                <div className="h-10 w-10 rounded-full bg-blue-600/20 border border-blue-500/30 flex items-center justify-center">
                  <svg className="w-5 h-5 text-blue-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
                    fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                  </svg>
                </div>
                <div>
                  <p className="text-sm font-semibold text-foreground/90">Ask the Co-Pilot</p>
                  <p className="text-[11px] text-muted-foreground mt-1 leading-relaxed">
                    Questions about the{" "}
                    <span className="font-mono text-foreground/70">{scenarioId}</span> scenario.
                  </p>
                </div>
              </div>
            )}

            {error && (
              <p className="text-[11px] text-destructive bg-destructive/10 px-3 py-2 rounded-lg border border-destructive/30">
                {error}
              </p>
            )}

            {messages.map((msg, i) => <FloatingMessage key={i} msg={msg} />)}

            {loading && (
              <div className="space-y-2">
                <div className="flex justify-end">
                  <div className="bg-blue-600/20 border border-blue-500/30 text-[12px] px-3.5 py-2 rounded-2xl rounded-br-md text-foreground/50 animate-pulse">
                    …
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <div className="h-5 w-5 rounded-full bg-blue-600/25 border border-blue-500/40 flex items-center justify-center shrink-0">
                    <span className="text-[8px] text-blue-300 font-bold leading-none">AI</span>
                  </div>
                  <span className="text-[11px] text-muted-foreground animate-pulse">Co-Pilot is thinking…</span>
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* Input inside panel */}
          <div className="shrink-0 border-t border-border p-2">
            <div className="flex items-center gap-2">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    submit();
                  }
                }}
                placeholder="Ask the co-pilot… (Enter to send)"
                rows={1}
                className="min-h-[44px] max-h-[100px] flex-1 resize-none text-[12px] bg-muted/20 border border-border/60 rounded-xl px-3 py-2.5 focus:outline-none focus:ring-1 focus:ring-blue-500/40 placeholder:text-muted-foreground/50 text-foreground"
              />
              <button
                onClick={submit}
                disabled={!input.trim() || loading}
                className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-blue-600 hover:bg-blue-500 active:scale-95 disabled:bg-muted/50 disabled:cursor-not-allowed transition-all shadow-sm"
                aria-label="Send"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  className="block h-4 w-4 text-white"
                  aria-hidden="true"
                >
                  <path d="M3.4 20.4l17.45-7.48a1 1 0 0 0 0-1.84L3.4 3.6a1 1 0 0 0-1.36 1.18L4.5 11l8 1-8 1-2.46 6.22a1 1 0 0 0 1.36 1.18z" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      ) : (
        /* ── Lobster trigger button (hidden while panel is open) ── */
        <button
          onClick={() => setOpen(true)}
          className="h-14 w-14 rounded-xl border border-border bg-background hover:bg-muted/30 hover:border-border/80 flex items-center justify-center transition-all duration-200 shadow-xl"
          aria-label="Open Co-Pilot"
        >
          <img src="/lobster.png" alt="Co-Pilot" className="h-8 w-8 object-contain" />
        </button>
      )}
    </div>
  );
}
