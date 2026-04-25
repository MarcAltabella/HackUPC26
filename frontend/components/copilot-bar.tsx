"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Citation {
  run_id: string;
  t: number;
  field: string;
  value?: number | string | null;
}

interface ChatResponse {
  severity: "INFO" | "WARNING" | "CRITICAL";
  summary: string;
  answer: string;
  reasoning_summary: string[];
  citations: Citation[];
  recommended_actions: string[];
}

interface Message {
  question: string;
  response: ChatResponse;
}

interface CopilotBarProps {
  scenarioId?: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function severityVariant(s: "INFO" | "WARNING" | "CRITICAL") {
  if (s === "CRITICAL") return "destructive" as const;
  if (s === "WARNING")  return "outline" as const;
  return "secondary" as const;
}

function severityBorder(s: "INFO" | "WARNING" | "CRITICAL") {
  if (s === "CRITICAL") return "border-l-red-500";
  if (s === "WARNING")  return "border-l-yellow-500";
  return "border-l-blue-400";
}

// ── Message card ──────────────────────────────────────────────────────────────

function MessageCard({ msg }: { msg: Message }) {
  const r = msg.response;
  return (
    <div className="space-y-2">
      {/* User question */}
      <div className="flex justify-end">
        <span className="bg-muted/60 text-xs px-2.5 py-1 rounded-md text-muted-foreground max-w-[80%] text-right">
          {msg.question}
        </span>
      </div>

      {/* AI response */}
      <div className={`rounded-md border border-border border-l-2 ${severityBorder(r.severity)} bg-muted/10 px-3 py-2.5 space-y-2`}>
        {/* Severity + summary */}
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant={severityVariant(r.severity)} className="text-[10px] h-4 px-1.5 shrink-0">
            {r.severity}
          </Badge>
          <p className="text-xs font-medium">{r.summary}</p>
        </div>

        {/* Answer */}
        <p className="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed">
          {r.answer}
        </p>

        {/* Reasoning */}
        {r.reasoning_summary.length > 0 && (
          <div>
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">Reasoning</p>
            <ul className="space-y-0.5">
              {r.reasoning_summary.map((step, i) => (
                <li key={i} className="text-xs text-muted-foreground flex gap-1.5">
                  <span className="shrink-0 opacity-40">•</span>
                  <span>{step}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Citations */}
        {r.citations.length > 0 && (
          <div>
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">Evidence</p>
            <div className="flex flex-wrap gap-1.5">
              {r.citations.map((c, i) => (
                <div
                  key={i}
                  className="rounded border border-border px-2 py-0.5 text-[10px] font-mono bg-muted/50 flex items-center gap-0.5"
                >
                  <span className="text-muted-foreground">{c.run_id}</span>
                  <span className="opacity-30 mx-0.5">·</span>
                  <span>t={c.t}</span>
                  <span className="opacity-30 mx-0.5">·</span>
                  <span className="text-blue-400">{c.field}</span>
                  {c.value !== null && c.value !== undefined && (
                    <>
                      <span className="opacity-30 mx-0.5">=</span>
                      <span>{typeof c.value === "number" ? c.value.toFixed(3) : c.value}</span>
                    </>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recommended actions */}
        {r.recommended_actions.length > 0 && (
          <div>
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">Actions</p>
            <div className="flex flex-wrap gap-1.5">
              {r.recommended_actions.map((a, i) => (
                <span
                  key={i}
                  className="rounded-full border border-border px-2.5 py-0.5 text-[10px] text-muted-foreground bg-muted/30"
                >
                  {a}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── CopilotBar ────────────────────────────────────────────────────────────────

export function CopilotBar({ scenarioId = "baseline_nominal" }: CopilotBarProps) {
  const [value,    setValue]    = useState("");
  const [loading,  setLoading]  = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [error,    setError]    = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef   = useRef<HTMLDivElement>(null);

  // Listen for "Ask co-pilot" events fired by AlertCard buttons
  useEffect(() => {
    function handleQuery(e: Event) {
      const query = (e as CustomEvent<string>).detail;
      setValue(query);
      textareaRef.current?.focus();
    }
    window.addEventListener("copilot-query", handleQuery);
    return () => window.removeEventListener("copilot-query", handleQuery);
  }, []);

  // Scroll to bottom when new message arrives
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSubmit() {
    const q = value.trim();
    if (!q || loading) return;

    setLoading(true);
    setError(null);
    setValue("");

    try {
      const res = await fetch("http://localhost:8000/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: q, scenario_id: scenarioId, run_number: 0 }),
      });

      if (res.ok) {
        const data: ChatResponse = await res.json();
        setMessages(prev => [...prev, { question: q, response: data }]);
      } else {
        const text = await res.text();
        setError(`API error ${res.status}: ${text}`);
      }
    } catch {
      setError("Could not reach the backend — start the FastAPI server on :8000.");
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  const hasContent = messages.length > 0 || error;

  return (
    <div className="border-t border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">

      {/* Conversation history */}
      {hasContent && (
        <ScrollArea className="max-h-80 border-b border-border">
          <div className="px-4 py-3 space-y-4">

            {error && (
              <p className="text-xs text-destructive font-mono">{error}</p>
            )}

            {messages.map((msg, i) => (
              <MessageCard key={i} msg={msg} />
            ))}

            {/* Loading indicator */}
            {loading && (
              <div className="flex justify-end">
                <span className="bg-muted/60 text-xs px-2.5 py-1 rounded-md text-muted-foreground animate-pulse">
                  Co-pilot is thinking…
                </span>
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        </ScrollArea>
      )}

      {/* Input row */}
      <div className="flex items-end gap-2 px-4 py-3 max-w-5xl mx-auto">
        <Textarea
          ref={textareaRef}
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={loading ? "Co-pilot is thinking…" : "Ask the co-pilot about the machine… (Enter to send)"}
          className="min-h-[40px] max-h-[120px] resize-none text-sm"
          rows={1}
          disabled={loading}
        />
        <Button onClick={handleSubmit} disabled={!value.trim() || loading} size="sm" className="shrink-0">
          {loading ? "…" : "Send"}
        </Button>
        {messages.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="shrink-0 text-muted-foreground text-xs"
            onClick={() => { setMessages([]); setError(null); }}
          >
            Clear
          </Button>
        )}
      </div>
    </div>
  );
}
