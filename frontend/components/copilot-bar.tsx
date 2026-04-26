"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import { Textarea } from "@/components/ui/textarea";

interface CopilotBarProps {
  scenarioId?: string;
  runNumber?: number;
}

// ── CopilotBar ────────────────────────────────────────────────────────────────

export function CopilotBar({ scenarioId = "humid_factory", runNumber = 0 }: CopilotBarProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function handleSubmit() {
    const q = value.trim();
    if (!q) return;

    setValue("");

    // Fire event to trigger chat in the main page
    window.dispatchEvent(new CustomEvent("copilot-query", { detail: q }));
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div className="border-t border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 shadow-[0_-1px_8px_rgba(0,0,0,0.15)]">
      <div className="px-4 py-2.5 max-w-5xl mx-auto">
        <div className="flex items-center gap-2">
          <Textarea
            ref={textareaRef}
            value={value}
            onChange={e => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask the co-pilot about the machine… (Enter to send, Shift+Enter for new line)"
            className="min-h-[44px] max-h-[120px] flex-1 resize-none text-sm px-3 py-3 rounded-xl border-border/60 bg-muted/20 focus:bg-background/80 transition-colors"
            rows={1}
          />
          <button
            onClick={handleSubmit}
            disabled={!value.trim()}
            className="h-10 w-10 shrink-0 rounded-lg bg-blue-600 hover:bg-blue-500 active:scale-95 disabled:bg-muted/50 disabled:cursor-not-allowed transition-all duration-150 flex items-center justify-center shadow-sm"
            aria-label="Send message"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="w-4 h-4 text-white disabled:text-muted-foreground"
            >
              <path d="M5 12h14" />
              <path d="m12 5 7 7-7 7" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
