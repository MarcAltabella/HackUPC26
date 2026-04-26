"use client";

import { useEffect, useRef, useState } from "react";

const LOBSTER_SRC = "/lobster.png";
const LIFETIME_MS = 8000;

type Severity = "WARNING" | "CRITICAL";

interface Template {
  severity: Severity;
  subsystem: string;
  title:    string;
  summary:  string;
  reasoning: string[];
}

interface Notification extends Template {
  id: number;
  key: string;
}

const TEMPLATES: Record<string, Template> = {
  "recoating-WARNING": {
    severity: "WARNING",
    subsystem: "Recoating",
    title:    "Eased recoating",
    summary:  "Slowed the blade 15% and refreshed the humidity baffle.",
    reasoning: [
      "Blade health crossed the 50% mark — wear was accelerating with the humid air.",
      "Reducing recoating speed takes load off the bearings and rail simultaneously.",
      "Baffle refresh keeps moisture off the powder bed for the next ~30 layers.",
    ],
  },
  "recoating-CRITICAL": {
    severity: "CRITICAL",
    subsystem: "Recoating",
    title:    "Critical recoating fix",
    summary:  "Halted recoating, ran a moisture purge, queued a blade swap.",
    reasoning: [
      "Blade health dropped past 25% — the failure window was closing fast.",
      "Rail deviation already past 100 μm — layer quality at risk of going non-spec.",
      "Pause + purge + swap is the only path that doesn't scrap the build in progress.",
    ],
  },
  "printhead-WARNING": {
    severity: "WARNING",
    subsystem: "Printhead",
    title:    "Purged the printhead",
    summary:  "Ran a nozzle purge and trimmed drive voltage to compensate for drift.",
    reasoning: [
      "Nozzle clog probability passed 50% — humidity is feeding contamination.",
      "A quick purge clears binder residue before it cascades into the cleaning system.",
      "Drive-voltage trim compensates for resistor drift caused by oxidation.",
    ],
  },
};

export function LobsterNotifications() {
  const [items, setItems] = useState<Notification[]>([]);
  const idRef = useRef(0);

  useEffect(() => {
    function onProactive(e: Event) {
      const key = (e as CustomEvent<string>).detail;
      const tpl = TEMPLATES[key];
      if (!tpl) return;
      idRef.current += 1;
      const item: Notification = { id: idRef.current, key, ...tpl };
      setItems(curr => [item, ...curr]);
    }
    window.addEventListener("copilot-proactive", onProactive);
    return () => window.removeEventListener("copilot-proactive", onProactive);
  }, []);

  function dismiss(id: number) {
    setItems(curr => curr.filter(i => i.id !== id));
  }

  return (
    <div className="absolute top-3 right-3 z-20 flex flex-col gap-2 w-[320px] pointer-events-none">
      {items.map(item => (
        <NotificationCard key={item.id} n={item} onDismiss={() => dismiss(item.id)} />
      ))}
    </div>
  );
}

function NotificationCard({ n, onDismiss }: { n: Notification; onDismiss: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [hover,    setHover]    = useState(false);
  const [mounted,  setMounted]  = useState(false);

  // Latest onDismiss in a ref so the timer effect doesn't restart every time
  // the parent re-renders (the 3D scene ticks every ~333ms).
  const onDismissRef = useRef(onDismiss);
  useEffect(() => { onDismissRef.current = onDismiss; }, [onDismiss]);

  // Slide-in on mount
  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);

  // Auto-dismiss timer — paused while hovered or expanded
  useEffect(() => {
    if (hover || expanded) return;
    const t = setTimeout(() => onDismissRef.current(), LIFETIME_MS);
    return () => clearTimeout(t);
  }, [hover, expanded]);

  const accent = n.severity === "CRITICAL"
    ? "border-l-red-500"
    : "border-l-yellow-400";

  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      className={[
        "pointer-events-auto rounded-md border border-border border-l-2 bg-black/90 backdrop-blur-md shadow-2xl overflow-hidden",
        "transition-all duration-300 ease-out",
        accent,
        mounted ? "opacity-100 translate-x-0" : "opacity-0 translate-x-4",
      ].join(" ")}
    >
      {/* Header + summary — clickable to expand */}
      <div
        onClick={() => setExpanded(x => !x)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setExpanded(x => !x);
          }
        }}
        className="cursor-pointer select-none hover:bg-muted/15 transition-colors"
      >
        <div className="flex items-center gap-2 px-2.5 pt-2">
          <span className="relative h-8 w-8 flex items-center justify-center shrink-0">
            <img
              src={LOBSTER_SRC}
              alt=""
              width={32}
              height={32}
              className="relative h-full w-full object-contain"
            />
          </span>

          <div className="flex-1 min-w-0">
            <p className="text-[11px] font-semibold leading-tight truncate">{n.title}</p>
            <p className="text-[9.5px] text-muted-foreground font-mono mt-0.5 truncate">
              {n.subsystem} · {n.severity.toLowerCase()}
            </p>
          </div>

          <button
            onClick={(e) => { e.stopPropagation(); onDismiss(); }}
            className="text-muted-foreground hover:text-foreground text-base leading-none w-5 h-5 flex items-center justify-center shrink-0"
            aria-label="Dismiss"
          >
            ×
          </button>
        </div>

        <p className="px-2.5 pt-1.5 pb-2 text-[11px] text-foreground/90 leading-snug">
          {n.summary}
        </p>
      </div>

      {/* Expanded reasoning */}
      {expanded && (
        <div className="border-t border-border/50 px-2.5 py-2 bg-muted/10">
          <p className="text-[9px] font-semibold text-muted-foreground uppercase tracking-widest mb-1.5">
            Why
          </p>
          <ul className="space-y-1">
            {n.reasoning.map((r, i) => (
              <li key={i} className="flex gap-1.5 text-[11px] text-muted-foreground leading-snug">
                <span className="shrink-0 opacity-50">•</span>
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Countdown bar — visual cue of remaining lifetime */}
      {!hover && !expanded && (
        <div className="h-0.5 bg-muted/30 overflow-hidden">
          <div
            key={n.id}
            className="h-full bg-foreground/40 origin-right"
            style={{ animation: `lobster-shrink ${LIFETIME_MS}ms linear forwards` }}
          />
        </div>
      )}
    </div>
  );
}
