"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";

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

interface CopilotBarProps {
  scenarioId?: string;
}

function severityVariant(s: "INFO" | "WARNING" | "CRITICAL") {
  if (s === "CRITICAL") return "destructive" as const;
  if (s === "WARNING") return "outline" as const;
  return "secondary" as const;
}

export function CopilotBar({ scenarioId = "baseline_nominal" }: CopilotBarProps) {
  const [value, setValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [reply, setReply] = useState<ChatResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  async function handleSubmit() {
    const q = value.trim();
    if (!q || loading) return;

    setLoading(true);
    setReply(null);
    setError(null);

    try {
      const res = await fetch("http://localhost:8000/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: q, scenario_id: scenarioId, run_number: 0 }),
      });

      if (res.ok) {
        const data: ChatResponse = await res.json();
        setReply(data);
      } else {
        const text = await res.text();
        setError(`API error ${res.status}: ${text}`);
      }
    } catch {
      setError("Could not reach the backend — start the FastAPI server on :8000.");
    } finally {
      setLoading(false);
      setValue("");
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div className="border-t border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      {(reply || error) && (
        <ScrollArea className="max-h-72 border-b border-border">
          <div className="px-4 py-3 space-y-3">

            {error && (
              <p className="text-xs text-destructive font-mono">{error}</p>
            )}

            {reply && (
              <>
                {/* Severity + summary */}
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge
                    variant={severityVariant(reply.severity)}
                    className="text-[10px] h-4 px-1.5 shrink-0"
                  >
                    {reply.severity}
                  </Badge>
                  <p className="text-xs font-medium">{reply.summary}</p>
                </div>

                {/* Answer */}
                <p className="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed">
                  {reply.answer}
                </p>

                {/* Reasoning */}
                {reply.reasoning_summary.length > 0 && (
                  <div>
                    <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">
                      Reasoning
                    </p>
                    <ul className="space-y-0.5">
                      {reply.reasoning_summary.map((r, i) => (
                        <li key={i} className="text-xs text-muted-foreground flex gap-1.5">
                          <span className="shrink-0 opacity-40">•</span>
                          <span>{r}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Citations */}
                {reply.citations.length > 0 && (
                  <div>
                    <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">
                      Evidence
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {reply.citations.map((c, i) => (
                        <div
                          key={i}
                          className="rounded border border-border px-2 py-1 text-[10px] font-mono bg-muted/50 flex items-center gap-0.5"
                        >
                          <span className="text-muted-foreground">{c.run_id}</span>
                          <span className="opacity-30 mx-0.5">·</span>
                          <span>t={c.t}</span>
                          <span className="opacity-30 mx-0.5">·</span>
                          <span className="text-blue-400">{c.field}</span>
                          {c.value !== null && c.value !== undefined && (
                            <>
                              <span className="opacity-30 mx-0.5">=</span>
                              <span>
                                {typeof c.value === "number"
                                  ? c.value.toFixed(3)
                                  : c.value}
                              </span>
                            </>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Recommended actions */}
                {reply.recommended_actions.length > 0 && (
                  <div>
                    <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">
                      Actions
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {reply.recommended_actions.map((a, i) => (
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
              </>
            )}
          </div>
        </ScrollArea>
      )}

      <div className="flex items-end gap-2 px-4 py-3 max-w-5xl mx-auto">
        <Textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            loading
              ? "Co-pilot is thinking…"
              : "Ask the co-pilot about the machine… (Enter to send)"
          }
          className="min-h-[40px] max-h-[120px] resize-none text-sm"
          rows={1}
          disabled={loading}
        />
        <Button
          onClick={handleSubmit}
          disabled={!value.trim() || loading}
          size="sm"
          className="shrink-0"
        >
          {loading ? "…" : "Send"}
        </Button>
      </div>
    </div>
  );
}
