"use client";

import { useEffect, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { MachineExperience, type CompStatus, type ComponentStatuses } from "./machine-experience";
import { getTimeline } from "@/lib/api";
import type { DiagnosticAlert, MachineState as ApiMachineState } from "@/lib/api-types";

// ── Agent activity state ───────────────────────────────────────────────────────

interface AgentStatus {
  subsystem: string;
  phase: "scanning" | "applying" | "fixed";
}

// ── Constants ─────────────────────────────────────────────────────────────────

const TICK_INTERVAL = 333;
const LOOP_PAUSE    = 1500;

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

  // Auto-expand and scroll into view when this alert is activated by a dot click
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

  const activeBorder = isActive
    ? alert.severity === "CRITICAL"
      ? "ring-1 ring-red-500/60 shadow-[0_0_12px_rgba(239,68,68,0.25)]"
      : "ring-1 ring-yellow-500/60 shadow-[0_0_12px_rgba(234,179,8,0.25)]"
    : "";

  return (
    <div
      ref={cardRef}
      className={`rounded-md border border-border border-l-2 text-xs overflow-hidden transition-shadow duration-300 ${severityColor(alert.severity)} ${activeBorder}`}
    >
      <button
        className="w-full text-left px-2.5 pt-2.5 pb-2 flex items-start gap-2 hover:bg-muted/20 transition-colors"
        onClick={() => { setOpen(o => !o); if (isActive) onDismiss(); }}
      >
        <div className="flex-1 min-w-0 space-y-0.5">
          <div className="flex items-center gap-1.5">
            <Badge variant={badgeVariant(alert.severity)} className="text-[9px] h-3.5 px-1 shrink-0">
              {alert.severity}
            </Badge>
            <span className="font-medium truncate">{alert.component}</span>
            {isActive && (
              <span className="ml-auto shrink-0 h-1.5 w-1.5 rounded-full bg-blue-400 animate-pulse" />
            )}
          </div>
          <p className="text-[11px] text-muted-foreground">{alert.subsystem} · {alert.metric}</p>
          <p className="text-[11px] leading-snug">{alert.summary}</p>
        </div>
        <span className="text-muted-foreground shrink-0 mt-0.5 text-[10px]">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="border-t border-border/50 px-2.5 py-2 space-y-2.5 bg-muted/10">
          <div>
            <p className="text-[9px] font-semibold text-muted-foreground uppercase tracking-widest mb-1">Reasoning</p>
            <ul className="space-y-0.5">
              {alert.reasoning.map((r, i) => (
                <li key={i} className="flex gap-1 text-[11px] text-muted-foreground leading-snug">
                  <span className="shrink-0 opacity-40">•</span>
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-[9px] font-semibold text-muted-foreground uppercase tracking-widest mb-1">Actions</p>
            <div className="flex flex-wrap gap-1">
              {alert.actions.map((a, i) => (
                <span key={i} className="rounded-full border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground bg-muted/20">
                  {a}
                </span>
              ))}
            </div>
          </div>
          <button
            onClick={askCopilot}
            className="text-[10px] text-blue-400 hover:text-blue-300 underline underline-offset-2 transition-colors"
          >
            Ask co-pilot ↗
          </button>
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
  const [agentStatus,   setAgentStatus]   = useState<AgentStatus | null>(null);
  const [blueprintView, setBlueprintView] = useState(false);
  const [activeAlertComp, setActiveAlertComp] = useState<string | null>(null);
  const triggeredRef  = useRef<Set<string>>(new Set());
  const agentTimers   = useRef<ReturnType<typeof setTimeout>[]>([]);

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
    const id = setTimeout(() => setAnimTick(t => t + 1), TICK_INTERVAL);
    return () => clearTimeout(id);
  }, [animTick, timeline.length]);

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

  return (
    <div className="flex h-full">

      {/* Center: 3D machine */}
      <div className="flex-1 relative overflow-hidden border-r border-border">
        <MachineExperience
          statuses={statuses}
          blueprintMode={blueprintView}
          onDotClick={handleDotClick}
        />

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

        {/* Dot-click hint */}
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 text-xs font-mono text-muted-foreground bg-background/70 rounded px-2 py-1 pointer-events-none">
          {animState.scenario_id} · t = {animTick}
          {isDemo && <span className="ml-2 text-yellow-400">· demo</span>}
          <span className="ml-2 opacity-50">· click dots to inspect</span>
        </div>
      </div>

      {/* Right rail */}
      <aside className="w-[440px] h-full flex flex-col gap-3 p-3 bg-background overflow-hidden shrink-0">

        {/* Active Diagnostics */}
        <Card className="flex-1 flex flex-col min-h-0">
          <CardHeader className="py-3 px-4 shrink-0">
            <CardTitle className="text-xs font-semibold flex items-center justify-between">
              <span>Active Diagnostics</span>
              <div className="flex items-center gap-1.5">
                {alerts.some(a => a.severity === "CRITICAL") && (
                  <Badge variant="destructive" className="text-[9px] h-4 px-1.5">
                    {alerts.filter(a => a.severity === "CRITICAL").length} critical
                  </Badge>
                )}
                {alerts.some(a => a.severity === "WARNING") && (
                  <Badge variant="outline" className="text-[9px] h-4 px-1.5 border-yellow-500 text-yellow-400">
                    {alerts.filter(a => a.severity === "WARNING").length} warn
                  </Badge>
                )}
                {activeAlertComp && (
                  <button
                    onClick={() => setActiveAlertComp(null)}
                    className="text-[9px] font-mono text-blue-400/70 hover:text-blue-300 transition-colors"
                  >
                    ✕ deselect
                  </button>
                )}
              </div>
            </CardTitle>
          </CardHeader>
          <Separator />

          {"maintenance_recommendation" in animState && (
            <div className="shrink-0 flex items-center gap-2.5 px-4 py-2 border-b bg-blue-950/20 border-blue-500/20">
              <span className="h-1.5 w-1.5 rounded-full shrink-0 bg-blue-400" />
              <div className="flex-1 min-w-0">
                <span className="text-[10px] font-semibold uppercase tracking-widest mr-2 text-muted-foreground">
                  DQN Policy
                </span>
                <span className="text-[11px] text-foreground">
                  {animState.maintenance_recommendation.action_label.replaceAll("_", " ")}
                  {" "}· reward {animState.maintenance_recommendation.reward.toFixed(2)}
                </span>
              </div>
            </div>
          )}

          {/* Agent activity — inline banner */}
          {agentStatus && (
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
            </ScrollArea>
          </CardContent>
        </Card>

        {/* Subsystem Health */}
        <Card className="shrink-0">
          <CardHeader className="py-3 px-4">
            <CardTitle className="text-xs font-semibold flex items-center justify-between">
              <span>Subsystem Health</span>
              <span className="text-muted-foreground font-normal text-[10px]">t = {animTick}</span>
            </CardTitle>
          </CardHeader>
          <Separator />
          <CardContent className="p-3 flex flex-col gap-3">
            {subsystems.map(({ label, health }) => (
              <div key={label} className="flex flex-col gap-1">
                <div className="flex justify-between text-xs">
                  <span className="font-medium">{label}</span>
                  <span className="font-mono text-muted-foreground">{(health * 100).toFixed(1)}%</span>
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
