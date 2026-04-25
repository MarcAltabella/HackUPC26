"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface CopilotBarProps {
  scenarioId?: string;
}

export function CopilotBar({ scenarioId = "baseline_nominal" }: CopilotBarProps) {
  const [value, setValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [reply, setReply] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  async function handleSubmit() {
    const q = value.trim();
    if (!q || loading) return;

    setLoading(true);
    setReply(null);

    try {
      const res = await fetch(
        `http://localhost:8000/api/runs/${scenarioId}/state/latest`
      );
      if (res.ok) {
        const state = await res.json();
        setReply(
          `[t=${state.t}] Recoating ${(state.recoating.subsystem_health * 100).toFixed(0)}% · ` +
            `Printhead ${(state.printhead.subsystem_health * 100).toFixed(0)}% · ` +
            `Thermal ${(state.thermal.subsystem_health * 100).toFixed(0)}%`
        );
      } else {
        setReply("API unreachable — start the FastAPI server on :8000.");
      }
    } catch {
      setReply("Could not reach the backend.");
    } finally {
      setLoading(false);
      setValue("");
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div className="border-t border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      {reply && (
        <div className="px-4 pt-2 pb-0">
          <p className="text-xs text-muted-foreground bg-muted rounded-md px-3 py-2 font-mono">
            {reply}
          </p>
        </div>
      )}

      <div className="flex items-end gap-2 px-4 py-3 max-w-5xl mx-auto">
        <Textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask the co-pilot about the machine… (Enter to send)"
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
