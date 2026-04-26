"use client";

import { useEffect, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { TimelineControls } from "@/components/timeline-controls";
import { MachineExperience, type CompStatus, type ComponentStatuses } from "./machine-experience";
import { LobsterNotifications } from "./lobster-notifications";
import { getTimeline, askCopilot } from "@/lib/api";
import type { DiagnosticAlert, MachineState as ApiMachineState, ChatResponse } from "@/lib/api-types";

// ── Agent activity state ───────────────────────────────────────────────────────

interface AgentStatus {
  subsystem: string;
  phase: "scanning" | "applying" | "fixed";
}

// ── Constants ─────────────────────────────────────────────────────────────────

const TICK_INTERVAL = 333;
const LOOP_PAUSE    = 1500;
const BASE_SPEED    = 1;

// ── Types ─────────────────────────────────────────────────────────────────────

interface RichAlert {
  id: number | string;
  severity: "CRITICAL" | "WARNING";
  subsystem: string;
  component: string;
  metric: string;
  summary: string;
  reasoning: string[];
  actions: string[];
  query: string;
}

interface ChatMessage {
  question: string;
  response: ChatResponse;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function healthPct(h: number) { return (h * 100).toFixed(0); }

function barColor(h: number) {
  if (h > 0.7) return "bg-green-400";
  if (h > 0.4) return "bg-yellow-300";
  if (h > 0.2) return "bg-orange-400";
  return "bg-red-400";
}

function severityColor(s: "CRITICAL" | "WARNING") {
  return s === "CRITICAL" ? "border-l-red-500" : "border-l-yellow-500";
}

function badgeVariant(s: "CRITICAL" | "WARNING") {
  return s === "CRITICAL" ? "destructive" as const : "outline" as const;
}

function chatSeverityVariant(s: "INFO" | "WARNING" | "CRITICAL") {
  if (s === "CRITICAL") return "destructive" as const;
  if (s === "WARNING")  return "outline" as const;
  return "secondary" as const;
}

function chatSeverityBorder(s: "INFO" | "WARNING" | "CRITICAL") {
  if (s === "CRITICAL") return "border-l-red-500";
  if (s === "WARNING")  return "border-l-yellow-500";
  return "border-l-blue-400";
}

function toCompStatuses(s: ApiMachineState): ComponentStatuses {
  return {
    blade:      s.recoating.blade.status    as CompStatus,
    motor:      s.recoating.motor.status    as CompStatus,
    rail:       s.recoating.rail.status     as CompStatus,
    nozzle:     s.printhead.nozzle.status   as CompStatus,
    resistors:  s.printhead.resistor.status as CompStatus,
    cleaning:   s.printhead.cleaning.status as CompStatus,
    heater:     s.thermal.heater.status     as CompStatus,
    sensor:     s.thermal.sensor.status     as CompStatus,
    insulation: s.thermal.insulation.status as CompStatus,
  };
}

function deriveAlerts(state: ApiMachineState): RichAlert[] {
  const alerts: RichAlert[] = [];
  let id = 1;

  function add(
    status: string,
    subsystem: string,
    component: string,
    metric: string,
    summary: string,
    reasoning: string[],
    actions: string[],
    query: string,
  ) {
    const sev = status === "FAILED" || status === "CRITICAL" ? "CRITICAL" as const
              : status === "DEGRADED" || status === "WARNING" ? "WARNING"  as const
              : null;
    if (!sev) return;
    alerts.push({ id: id++, severity: sev, subsystem, component, metric, summary, reasoning, actions, query });
  }

  const s = state;

  add(
    s.recoating.blade.status, "Recoating", "Blade",
    `${s.recoating.blade.thickness_mm.toFixed(2)} mm`,
    `Blade at ${healthPct(s.recoating.blade.health)}% health — wear rate above baseline`,
    [
      `Health ${healthPct(s.recoating.blade.health)}%, degrading ~0.72%/tick`,
      `Humidity >60% accelerating abrasive edge wear`,
      `Est. critical crossing in ~${Math.max(0, Math.round((s.recoating.blade.health - 0.10) / 0.0072))} ticks`,
    ],
    ["Schedule blade replacement", "Reduce recoating speed 15%", "Log wear in maintenance record"],
    `Why is the recoating blade degrading and what should I do?`,
  );

  add(
    s.recoating.motor.status, "Recoating", "Motor",
    `${s.recoating.motor.vibration_mm_s.toFixed(1)} mm/s`,
    `Vibration at ${s.recoating.motor.vibration_mm_s.toFixed(1)} mm/s — bearing fatigue detected`,
    [
      `Vibration trend: 1.2 → ${s.recoating.motor.vibration_mm_s.toFixed(1)} mm/s over 30 ticks`,
      `Humidity ingress degrading bearing lubrication film`,
      `Safety limit 5.0 mm/s — ${((5.0 - s.recoating.motor.vibration_mm_s) / 0.08).toFixed(0)} tick headroom`,
    ],
    ["Inspect motor bearings for moisture", "Lubricate recoating shaft", "Check alignment"],
    `What's causing the recoating motor vibration to increase?`,
  );

  add(
    s.recoating.rail.status, "Recoating", "Rail",
    `${s.recoating.rail.deviation_um.toFixed(0)} μm`,
    `Rail deviation ${s.recoating.rail.deviation_um.toFixed(0)} μm — ${(s.recoating.rail.deviation_um / 50).toFixed(1)}× tolerance`,
    [
      `Deviation: 12 μm (t=0) → ${s.recoating.rail.deviation_um.toFixed(0)} μm (t=${s.t})`,
      `Root cause: humidity-driven frame thermal expansion`,
      `Layer inconsistency risk HIGH — tolerance limit is 50 μm`,
    ],
    ["Halt production, inspect rail", "Re-calibrate build bed", "Install humidity baffles"],
    `Diagnose the recoating rail deviation — what is causing it?`,
  );

  add(
    s.printhead.nozzle.status, "Printhead", "Nozzle",
    `${(s.printhead.nozzle.clog_probability * 100).toFixed(0)}% clog risk`,
    `Nozzle at ${healthPct(s.printhead.nozzle.health)}% — clog probability critical`,
    [
      `Clog probability: 0.18 → ${s.printhead.nozzle.clog_probability.toFixed(2)} since humidity spike at t=55`,
      `Contamination cascade: humid air → binder residue → nozzle blockage`,
      `Health threshold CRITICAL at ${healthPct(s.printhead.nozzle.health)}% — intervention required`,
    ],
    ["Clean nozzle array immediately", "Reduce ambient humidity <50%", "Schedule nozzle replacement"],
    `Why is the printhead nozzle failing and how urgent is it?`,
  );

  add(
    s.printhead.resistor.status, "Printhead", "Resistors",
    `${s.printhead.resistor.drift_pct.toFixed(1)}% drift`,
    `Resistor drift at ${s.printhead.resistor.drift_pct.toFixed(1)}% — inconsistent drop energy`,
    [
      `Drift: 0.8% → ${s.printhead.resistor.drift_pct.toFixed(1)}% correlated with humidity >60%`,
      `High humidity causing resistive layer oxidation`,
      `Print quality degraded — drop ejection energy inconsistent`,
    ],
    ["Recalibrate drive voltage", "Run printhead purge cycle", "Inspect for corrosion"],
    `What is causing the printhead resistor drift?`,
  );

  add(
    s.printhead.cleaning.status, "Printhead", "Cleaning",
    `${(s.printhead.cleaning.efficiency * 100).toFixed(0)}% efficiency`,
    `Cleaning system at ${(s.printhead.cleaning.efficiency * 100).toFixed(0)}% — contamination feedback loop`,
    [
      `Efficiency dropped step-change at t=55 (humidity spike)`,
      `Wiper condensation reducing effective stroke length by ~${(100 - s.printhead.cleaning.efficiency * 100).toFixed(0)}%`,
      `Positive feedback: poor cleaning → nozzle clog → more debris → worse cleaning`,
    ],
    ["Clean wiper assembly manually", "Purge with dry air", "Increase cleaning frequency"],
    `Explain the cleaning system degradation and its impact on the printhead.`,
  );

  add(
    s.thermal.heater.status, "Thermal", "Heater",
    `${s.thermal.heater.resistance_ohm.toFixed(1)} Ω`,
    `Heater resistance drifting to ${s.thermal.heater.resistance_ohm.toFixed(1)} Ω`,
    [
      `Resistance: 10.8 → ${s.thermal.heater.resistance_ohm.toFixed(1)} Ω at 0.032 Ω/tick`,
      `Within 20% tolerance — no immediate risk`,
      `Projected limit crossing at t≈140 if trend continues`,
    ],
    ["Log for trend tracking", "Schedule check at t+30", "No immediate action required"],
    `Is the thermal heater resistance drift a concern?`,
  );

  add(
    s.thermal.sensor.status, "Thermal", "Sensor",
    `±${s.thermal.sensor.measurement_error_c.toFixed(1)} °C`,
    `Sensor error ±${s.thermal.sensor.measurement_error_c.toFixed(1)} °C — within ±1.0 °C spec`,
    [
      `Error: 0.2 → ${s.thermal.sensor.measurement_error_c.toFixed(1)} °C, slow linear drift`,
      `Humidity correlation weak (R²=0.31) — likely normal aging`,
      `${(1.0 - s.thermal.sensor.measurement_error_c).toFixed(1)} °C headroom before spec limit`,
    ],
    ["Log for calibration record", "Schedule calibration at next window"],
    `How serious is the temperature sensor measurement error?`,
  );

  add(
    s.thermal.insulation.status, "Thermal", "Insulation",
    `R = ${s.thermal.insulation.thermal_resistance.toFixed(2)}`,
    `Insulation resistance at ${s.thermal.insulation.thermal_resistance.toFixed(2)} — minor degradation`,
    [
      `Thermal R: 2.0 → ${s.thermal.insulation.thermal_resistance.toFixed(2)} over run duration`,
      `Humidity contributing ~5% to degradation rate`,
      `No projected threshold crossings before run end`,
    ],
    ["No immediate action required", "Check integrity at next disassembly"],
    `Is the thermal insulation degradation significant?`,
  );

  return alerts.sort((a, b) => (a.severity === b.severity ? 0 : a.severity === "CRITICAL" ? -1 : 1));
}

function fromBackendAlert(alert: DiagnosticAlert): RichAlert {
  return {
    id: alert.id,
    severity: alert.severity,
    subsystem: alert.subsystem,
    component: alert.component === "Resistor" ? "Resistors" : alert.component,
    metric: alert.metric,
    summary: alert.summary,
    reasoning: alert.reasoning,
    actions: alert.actions,
    query: alert.query,
  };
}

// ── Chat Message Card ─────────────────────────────────────────────────────────

function MessageCard({ msg }: { msg: ChatMessage }) {
  const r = msg.response;
  const borderColor = r.severity === "CRITICAL" ? "border-red-500/30" : r.severity === "WARNING" ? "border-yellow-500/25" : "border-blue-500/25";
  const bgColor = r.severity === "CRITICAL" ? "bg-red-950/10" : r.severity === "WARNING" ? "bg-yellow-950/5" : "bg-blue-950/5";

  return (
    <div className="space-y-2.5">
      {/* User bubble */}
      <div className="flex justify-end">
        <div className="bg-blue-600/20 border border-blue-500/30 text-[12px] px-4 py-2.5 rounded-2xl rounded-br-md text-foreground max-w-[88%] leading-relaxed">
          {msg.question}
        </div>
      </div>

      {/* Co-pilot label */}
      <div className="flex items-center gap-2">
        <div className="h-5 w-5 rounded-full bg-blue-600/25 border border-blue-500/40 flex items-center justify-center shrink-0">
          <span className="text-[8px] text-blue-300 font-bold leading-none">AI</span>
        </div>
        <span className="text-[10px] text-muted-foreground font-semibold tracking-wide uppercase">Co-Pilot</span>
        <Badge variant={chatSeverityVariant(r.severity)} className="text-[9px] h-4 px-1.5">
          {r.severity}
        </Badge>
      </div>

      {/* AI response card */}
      <div className={`rounded-xl border ${borderColor} ${bgColor} overflow-hidden`}>
        {/* Summary */}
        <div className="px-4 pt-3.5 pb-3">
          <p className="text-[12.5px] font-semibold text-foreground leading-snug">{r.summary}</p>
          <p className="text-[12px] text-foreground/80 mt-2 leading-relaxed whitespace-pre-wrap">{r.answer}</p>
        </div>

        {/* Reasoning */}
        {r.reasoning_summary.length > 0 && (
          <div className="border-t border-border/30 px-4 py-3">
            <p className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest mb-2.5">Reasoning</p>
            <ol className="space-y-2">
              {r.reasoning_summary.map((step, i) => (
                <li key={i} className="flex gap-2.5 text-[11.5px] text-muted-foreground leading-relaxed">
                  <span className="shrink-0 text-muted-foreground/40 font-mono text-[10px] mt-px">{i + 1}.</span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          </div>
        )}

        {/* Recommended actions */}
        {r.recommended_actions.length > 0 && (
          <div className="border-t border-border/30 px-4 py-3">
            <p className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest mb-2.5">Recommended Actions</p>
            <div className="flex flex-col gap-1.5">
              {r.recommended_actions.map((a, i) => (
                <div key={i} className="flex items-start gap-2 text-[11.5px] text-foreground/80 leading-relaxed">
                  <span className="h-1.5 w-1.5 rounded-full bg-blue-400/60 shrink-0 mt-1.5" />
                  <span>{a}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Citations */}
        {r.citations.length > 0 && (
          <div className="border-t border-border/30 px-4 py-3">
            <p className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest mb-2">Evidence</p>
            <div className="flex flex-wrap gap-1.5">
              {r.citations.map((c, i) => (
                <div key={i} className="rounded-md border border-border/50 px-2 py-0.5 text-[10px] font-mono bg-muted/40 flex items-center gap-1 text-muted-foreground">
                  <span className="text-blue-400">{c.field}</span>
                  {c.value !== null && c.value !== undefined && (
                    <span>= {typeof c.value === "number" ? c.value.toFixed(3) : c.value}</span>
                  )}
                  <span className="opacity-40">@t={c.t}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Alert Card ────────────────────────────────────────────────────────────────

function AlertCard({
  alert,
  isActive,
  onDismiss,
}: {
  alert: RichAlert;
  isActive: boolean;
  onDismiss: () => void;
}) {
  const [open, setOpen] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isActive) return;
    requestAnimationFrame(() => {
      setOpen(true);
      cardRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  }, [isActive]);

  function askCopilot() {
    window.dispatchEvent(new CustomEvent("copilot-query", { detail: alert.query }));
  }

  const isCritical = alert.severity === "CRITICAL";
  const borderColor = isCritical ? "border-red-500/40" : "border-yellow-500/30";
  const glowClass = isActive
    ? isCritical
      ? "ring-1 ring-red-500/50 shadow-[0_0_14px_rgba(239,68,68,0.2)]"
      : "ring-1 ring-yellow-500/50 shadow-[0_0_14px_rgba(234,179,8,0.2)]"
    : "";
  const dotColor = isCritical ? "bg-red-500 shadow-[0_0_5px_rgba(239,68,68,0.7)]" : "bg-yellow-400 shadow-[0_0_5px_rgba(234,179,8,0.6)]";
  const severityText = isCritical ? "text-red-400" : "text-yellow-400";

  return (
    <div
      ref={cardRef}
      className={`rounded-xl border text-xs overflow-hidden ${borderColor} ${glowClass}`}
    >
      {/* Header */}
      <div className="px-4 pt-3 pb-2.5">
        {/* Top row: severity indicator + chevron toggle */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full shrink-0 ${dotColor}`} />
            <span className={`text-[10px] font-bold uppercase tracking-widest ${severityText}`}>
              {alert.severity}
            </span>
            {isActive && (
              <span className="h-1.5 w-1.5 rounded-full bg-blue-400 animate-pulse ml-0.5" />
            )}
          </div>
          <button
            className="p-1 rounded hover:bg-muted/30 transition-colors"
            onClick={() => { setOpen(o => !o); if (isActive) onDismiss(); }}
            aria-label={open ? "Collapse" : "Expand"}
          >
            <svg
              className={`w-3.5 h-3.5 text-muted-foreground transition-transform duration-200 ${open ? "rotate-180" : ""}`}
              xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
            >
              <path d="m6 9 6 6 6-6" />
            </svg>
          </button>
        </div>
        {/* Component name + subsystem */}
        <div className="flex items-baseline gap-2 mb-1.5">
          <span className="text-[13px] font-bold text-foreground">{alert.component}</span>
          <span className="text-[10px] text-muted-foreground">{alert.subsystem}</span>
          <span className="ml-auto font-mono text-[10px] text-muted-foreground">{alert.metric}</span>
        </div>
        {/* Summary */}
        <p className="text-[11.5px] leading-relaxed text-foreground/80">{alert.summary}</p>
      </div>

      {/* Expanded content */}
      {open && (
        <div className="border-t border-border/40 bg-muted/5">
          {/* Diagnosis */}
          <div className="px-4 py-3">
            <p className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest mb-2.5">Diagnosis</p>
            <ol className="space-y-2">
              {alert.reasoning.map((r, i) => (
                <li key={i} className="flex gap-2.5 text-[11.5px] text-muted-foreground leading-relaxed">
                  <span className="shrink-0 text-muted-foreground/40 font-mono text-[10px] mt-px">{i + 1}.</span>
                  <span>{r}</span>
                </li>
              ))}
            </ol>
          </div>

          {/* Actions */}
          <div className="border-t border-border/30 px-4 py-3">
            <p className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest mb-2.5">Recommended Actions</p>
            <div className="flex flex-col gap-1.5">
              {alert.actions.map((a, i) => (
                <div key={i} className="flex items-start gap-2 text-[11.5px] text-foreground/80 leading-relaxed">
                  <span className={`h-1.5 w-1.5 rounded-full shrink-0 mt-1.5 ${isCritical ? "bg-red-400/60" : "bg-yellow-400/60"}`} />
                  <span>{a}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Ask Co-Pilot CTA */}
          <div className="border-t border-border/30 px-4 py-3">
            <button
              onClick={askCopilot}
              className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg bg-blue-600/15 hover:bg-blue-600/25 border border-blue-500/30 hover:border-blue-500/50 text-[11.5px] font-semibold text-blue-300 hover:text-blue-200 transition-all duration-150 active:scale-[0.99]"
            >
              <svg className="w-3.5 h-3.5 shrink-0" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
                fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
              Ask Co-Pilot about this alert
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function MachinePage() {
  const [animTick,      setAnimTick]      = useState(0);
  const [timeline,      setTimeline]      = useState<ApiMachineState[]>([]);
  const [loading,       setLoading]       = useState(true);
  const [error,         setError]         = useState<string | null>(null);
  const isDemo = false;
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [agentStatus,   setAgentStatus]   = useState<AgentStatus | null>(null);
  const [blueprintView, setBlueprintView] = useState(false);
  const [activeAlertComp, setActiveAlertComp] = useState<string | null>(null);
  const [activeView,    setActiveView]    = useState<"alerts" | "chat">("alerts");
  const [chatMessages,  setChatMessages]  = useState<ChatMessage[]>([]);
  const [chatLoading,   setChatLoading]   = useState(false);
  const [chatError,     setChatError]     = useState<string | null>(null);
  const triggeredRef  = useRef<Set<string>>(new Set());
  const agentTimers   = useRef<ReturnType<typeof setTimeout>[]>([]);
  const chatBottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    getTimeline("humid_factory", 0, 0, 999, ctrl.signal)
      .then(rows => {
        if (rows.length === 0) throw new Error("API returned no timeline rows");
        setTimeline(rows);
        setError(null);
        setAnimTick(0);
      })
      .catch((err: Error) => {
        setTimeline([]);
        if (!ctrl.signal.aborted) setError(err.message);
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
  }, []);

  // Animation loop
  useEffect(() => {
    if (timeline.length === 0) return;
    const maxTick = timeline.length - 1;
    if (animTick >= maxTick) {
      const id = setTimeout(() => {
        triggeredRef.current.clear();
        setAnimTick(0);
      }, LOOP_PAUSE);
      return () => clearTimeout(id);
    }
    const msPerTick = TICK_INTERVAL / (BASE_SPEED * playbackSpeed);
    const id = setTimeout(() => setAnimTick(t => Math.min(t + 1, maxTick)), msPerTick);
    return () => clearTimeout(id);
  }, [animTick, timeline.length, playbackSpeed]);

  // Threshold crossing detection
  useEffect(() => {
    if (animTick === 0) return;
    const prevApi = timeline[animTick - 1];
    const currApi = timeline[animTick];
    if (!prevApi || !currApi) return;
    const prev = {
      health_recoating: prevApi.recoating.subsystem_health,
      health_printhead: prevApi.printhead.subsystem_health,
      health_thermal: prevApi.thermal.subsystem_health,
    };
    const curr = {
      health_recoating: currApi.recoating.subsystem_health,
      health_printhead: currApi.printhead.subsystem_health,
      health_thermal: currApi.thermal.subsystem_health,
    };

    function check(
      key:       string,
      field:     "health_recoating" | "health_printhead" | "health_thermal",
      threshold: number,
    ) {
      if ((prev[field] as number) > threshold &&
          (curr[field] as number) <= threshold &&
          !triggeredRef.current.has(key)) {
        triggeredRef.current.add(key);
        window.dispatchEvent(new CustomEvent("copilot-proactive", { detail: key }));
      }
    }

    check("recoating-WARNING",  "health_recoating", 0.50);
    check("printhead-WARNING",  "health_printhead", 0.50);
    check("recoating-CRITICAL", "health_recoating", 0.25);
  }, [animTick, timeline]);

  // Agent activity banner on proactive events
  useEffect(() => {
    function handleProactive(e: Event) {
      const key = (e as CustomEvent<string>).detail;
      const sub = key.startsWith("printhead") ? "Printhead" : "Recoating";
      const sev = key.endsWith("CRITICAL") ? " (CRITICAL)" : "";

      agentTimers.current.forEach(clearTimeout);
      agentTimers.current = [];

      setAgentStatus({ subsystem: sub + sev, phase: "scanning" });
      agentTimers.current.push(
        setTimeout(() => setAgentStatus({ subsystem: sub + sev, phase: "applying" }), 2500),
        setTimeout(() => setAgentStatus({ subsystem: sub + sev, phase: "fixed"    }), 4500),
        setTimeout(() => setAgentStatus(null),                                         7500),
      );
    }
    window.addEventListener("copilot-proactive", handleProactive);
    return () => {
      window.removeEventListener("copilot-proactive", handleProactive);
      agentTimers.current.forEach(clearTimeout);
    };
  }, []);

  // Dot click → look up component name and set as active alert
  function handleDotClick(key: keyof ComponentStatuses) {
    const compName = key.charAt(0).toUpperCase() + key.slice(1);
    setActiveAlertComp(prev => prev === compName ? null : compName); // toggle
  }

  // Listen for copilot-query events and switch to chat view
  useEffect(() => {
    async function handleCopilotQuery(e: Event) {
      const query = (e as CustomEvent<string>).detail;

      // Switch to chat view
      setActiveView("chat");

      // Submit the query
      setChatLoading(true);
      setChatError(null);

      try {
        const data = await askCopilot({ message: query, scenarioId: "humid_factory", runNumber: 0 });
        setChatMessages(prev => [...prev, { question: query, response: data }]);
      } catch {
        setChatError("Could not reach the backend — start the FastAPI server on :8000.");
      } finally {
        setChatLoading(false);
      }
    }
    window.addEventListener("copilot-query", handleCopilotQuery);
    return () => window.removeEventListener("copilot-query", handleCopilotQuery);
  }, []);

  // Scroll chat to bottom on new messages
  useEffect(() => {
    if (activeView === "chat") {
      chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [chatMessages, activeView]);

  if (loading || error || timeline.length === 0) {
    return (
      <div className="flex h-full items-center justify-center bg-background p-6">
        <Card className="max-w-md w-full">
          <CardHeader>
            <CardTitle className="text-sm">
              {loading ? "Loading live telemetry" : "Live telemetry unavailable"}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs text-muted-foreground">
            <p>
              {loading
                ? "Requesting /api/runs/humid_factory/timeline from the backend."
                : error ?? "The backend returned no rows for this run."}
            </p>
            {!loading && (
              <p className="font-mono text-[11px]">
                No synthetic fallback is rendered on this screen.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    );
  }

  const animState = timeline[animTick] ?? timeline[timeline.length - 1];
  const alerts    = animState.alerts.map(fromBackendAlert);
  const statuses  = toCompStatuses(animState);

  const subsystems = [
    { label: "Recoating", health: animState.recoating.subsystem_health },
    { label: "Printhead", health: animState.printhead.subsystem_health },
    { label: "Thermal",   health: animState.thermal.subsystem_health   },
  ];

  const maxTick = timeline.length - 1;

  function handleScrub(nextTick: number) {
    const bounded = Math.max(0, Math.min(Math.round(nextTick), maxTick));
    setAnimTick(bounded);
  }

  return (
    <div className="flex h-full">

      {/* Center: 3D machine */}
      <div className="flex-1 relative overflow-hidden border-r border-border">
        <MachineExperience
          statuses={statuses}
          blueprintMode={blueprintView}
          onDotClick={handleDotClick}
        />

        {/* Lobster notifications — top-right corner */}
        <LobsterNotifications />

        {/* Blueprint toggle */}
        <button
          onClick={() => setBlueprintView(v => !v)}
          className={[
            "absolute top-3 left-3 z-10 flex items-center gap-1.5 h-7 px-3 rounded text-[11px] font-mono font-medium",
            "border transition-all duration-200",
            blueprintView
              ? "bg-blue-900/80 border-blue-400/60 text-blue-200 shadow-[0_0_8px_rgba(56,152,255,0.4)]"
              : "bg-background/70 border-border text-muted-foreground hover:text-foreground hover:border-blue-500/50",
          ].join(" ")}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${blueprintView ? "bg-blue-400" : "bg-muted-foreground"}`} />
          Blueprint
        </button>

        {/* Timeline controls at bottom */}
        <div className="absolute inset-x-3 bottom-3 z-10 rounded border border-border bg-background/75 px-3 py-2 backdrop-blur-sm">
          <TimelineControls
            totalTicks={timeline.length}
            animTick={animTick}
            onScrub={handleScrub}
            speed={playbackSpeed}
            onSpeedChange={setPlaybackSpeed}
          />
        </div>
      </div>

      {/* Right rail */}
      <aside className="w-[440px] h-full flex flex-col gap-3 p-3 bg-background overflow-hidden shrink-0">

        {/* Active Diagnostics / Chat */}
        <Card className="flex-1 flex flex-col min-h-0 shadow-lg">
          <div className="shrink-0 flex border-b border-border">
            <button
              onClick={() => setActiveView("alerts")}
              className={`flex-1 flex items-center justify-center gap-2 py-2.5 text-[11px] font-semibold transition-colors border-b-2 -mb-px ${
                activeView === "alerts"
                  ? "border-blue-500 text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              Alerts
              {alerts.some(a => a.severity === "CRITICAL") && (
                <span className="text-[9px] px-1.5 py-0.5 rounded-full font-bold bg-red-500/20 text-red-400">
                  {alerts.filter(a => a.severity === "CRITICAL").length}
                </span>
              )}
              {alerts.some(a => a.severity === "WARNING") && (
                <span className="text-[9px] px-1.5 py-0.5 rounded-full font-bold bg-yellow-500/20 text-yellow-400">
                  {alerts.filter(a => a.severity === "WARNING").length}
                </span>
              )}
            </button>
            <button
              onClick={() => setActiveView("chat")}
              className={`flex-1 flex items-center justify-center gap-2 py-2.5 text-[11px] font-semibold transition-colors border-b-2 -mb-px ${
                activeView === "chat"
                  ? "border-blue-500 text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              Chat
              {activeView === "chat" && chatMessages.length > 0 && (
                <span
                  role="button"
                  onClick={e => { e.stopPropagation(); setChatMessages([]); setChatError(null); }}
                  className="text-[9px] text-muted-foreground hover:text-foreground transition-colors ml-0.5"
                >
                  ✕
                </span>
              )}
            </button>
          </div>

          {/* Agent activity — inline banner */}
          {agentStatus && activeView === "alerts" && (
            <div className={[
              "shrink-0 flex items-center gap-2.5 px-4 py-2 border-b",
              agentStatus.phase === "fixed"
                ? "bg-green-950/20 border-green-500/20"
                : "bg-blue-950/20 border-blue-500/20",
            ].join(" ")}>
              <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${
                agentStatus.phase === "fixed" ? "bg-green-400" : "bg-blue-400 animate-pulse"
              }`} />
              <div className="flex-1 min-w-0">
                <span className="text-[10px] font-semibold uppercase tracking-widest mr-2 text-muted-foreground">
                  {agentStatus.phase === "fixed" ? "Maintenance Applied" : "Agent Activity"}
                </span>
                <span className="text-[11px] text-foreground">
                  {agentStatus.phase === "scanning" && `Analyzing ${agentStatus.subsystem} subsystem…`}
                  {agentStatus.phase === "applying" && "Applying corrective maintenance…"}
                  {agentStatus.phase === "fixed"    && `${agentStatus.subsystem} recovering — monitoring`}
                </span>
              </div>
            </div>
          )}

          <CardContent className="flex-1 min-h-0 p-0">
            <ScrollArea className="h-full">
              {activeView === "alerts" ? (
                <div className="flex flex-col gap-2 p-3">
                  {alerts.length === 0 ? (
                    <p className="text-xs text-muted-foreground px-1">All components nominal.</p>
                  ) : (
                    alerts.map(a => (
                      <AlertCard
                        key={a.id}
                        alert={a}
                        isActive={a.component === activeAlertComp}
                        onDismiss={() => setActiveAlertComp(null)}
                      />
                    ))
                  )}
                </div>
              ) : (
                <div className="flex flex-col gap-3 p-3">
                  {chatError && (
                    <p className="text-xs text-destructive font-mono bg-destructive/10 px-3 py-2 rounded border border-destructive/30">
                      {chatError}
                    </p>
                  )}

                  {chatMessages.length === 0 && !chatLoading && (
                    <div className="flex flex-col items-center text-center py-10 gap-3 px-2">
                      <div className="h-10 w-10 rounded-full bg-blue-600/20 border border-blue-500/30 flex items-center justify-center">
                        <svg className="w-5 h-5 text-blue-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                        </svg>
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-foreground/90">Ask the Co-Pilot</p>
                        <p className="text-[11px] text-muted-foreground mt-1 leading-relaxed">
                          Type a question below, or click<br />&ldquo;Ask Co-Pilot&rdquo; on any alert.
                        </p>
                      </div>
                    </div>
                  )}

                  {chatMessages.map((msg, i) => (
                    <MessageCard key={i} msg={msg} />
                  ))}

                  {chatLoading && (
                    <div className="space-y-2.5">
                      <div className="flex justify-end">
                        <div className="bg-blue-600/20 border border-blue-500/30 text-[12px] px-4 py-2.5 rounded-2xl rounded-br-md text-foreground/60 animate-pulse">
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

                  <div ref={chatBottomRef} />
                </div>
              )}
            </ScrollArea>
          </CardContent>
        </Card>

        {/* Subsystem Health */}
        <Card className="shrink-0">
          <CardContent className="px-3 py-2 flex items-center gap-4">
            <span className="text-[9px] font-semibold text-muted-foreground uppercase tracking-wider shrink-0">Health</span>
            {subsystems.map(({ label, health }) => (
              <div key={label} className="flex-1 flex flex-col gap-1 min-w-0">
                <div className="flex justify-between text-[9px]">
                  <span className="font-medium text-foreground/80 truncate">{label}</span>
                  <span className="font-mono text-muted-foreground ml-1 shrink-0">{(health * 100).toFixed(0)}%</span>
                </div>
                <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${barColor(health)}`}
                    style={{ width: `${(health * 100).toFixed(1)}%` }}
                  />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

      </aside>
    </div>
  );
}
