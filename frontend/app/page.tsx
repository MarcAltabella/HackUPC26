"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { MachineExperience } from "./machine-experience";
import { MOCK_STATE, type MachineState } from "@/lib/mock-data";

// ── Constants ─────────────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const SCENARIO  = "baseline_nominal";

// ── Types ─────────────────────────────────────────────────────────────────────

interface RichAlert {
  id: number;
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
  if (h > 0.7) return "bg-green-500";
  if (h > 0.4) return "bg-yellow-500";
  if (h > 0.2) return "bg-orange-500";
  return "bg-red-600";
}

function severityColor(s: "CRITICAL" | "WARNING") {
  return s === "CRITICAL" ? "border-l-red-500" : "border-l-yellow-500";
}

function badgeVariant(s: "CRITICAL" | "WARNING") {
  return s === "CRITICAL" ? "destructive" as const : "outline" as const;
}

function toSeverity(status: string): "CRITICAL" | "WARNING" | null {
  if (status === "FAILED" || status === "CRITICAL") return "CRITICAL";
  if (status === "DEGRADED" || status === "WARNING") return "WARNING";
  return null;
}

function deriveAlerts(state: MachineState): RichAlert[] {
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
    const severity = toSeverity(status);
    if (!severity) return;
    alerts.push({ id: id++, severity, subsystem, component, metric, summary, reasoning, actions, query });
  }

  const s = state;

  add(
    s.recoating.blade.status,
    "Recoating", "Blade",
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
    s.recoating.motor.status,
    "Recoating", "Motor",
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
    s.recoating.rail.status,
    "Recoating", "Rail",
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
    s.printhead.nozzle.status,
    "Printhead", "Nozzle",
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
    s.printhead.resistor.status,
    "Printhead", "Resistors",
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
    s.printhead.cleaning.status,
    "Printhead", "Cleaning",
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
    s.thermal.heater.status,
    "Thermal", "Heater",
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
    s.thermal.sensor.status,
    "Thermal", "Sensor",
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
    s.thermal.insulation.status,
    "Thermal", "Insulation",
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

  return alerts.sort((a, b) => {
    if (a.severity === b.severity) return 0;
    return a.severity === "CRITICAL" ? -1 : 1;
  });
}

// ── Alert Card ────────────────────────────────────────────────────────────────

function AlertCard({ alert }: { alert: RichAlert }) {
  const [open, setOpen] = useState(false);

  function askCopilot() {
    window.dispatchEvent(new CustomEvent("copilot-query", { detail: alert.query }));
  }

  return (
    <div className={`rounded-md border border-border border-l-2 text-xs overflow-hidden ${severityColor(alert.severity)}`}>
      {/* Header */}
      <button
        className="w-full text-left px-2.5 pt-2.5 pb-2 flex items-start gap-2 hover:bg-muted/20 transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        <div className="flex-1 min-w-0 space-y-0.5">
          <div className="flex items-center gap-1.5">
            <Badge variant={badgeVariant(alert.severity)} className="text-[9px] h-3.5 px-1 shrink-0">
              {alert.severity}
            </Badge>
            <span className="font-medium truncate">{alert.component}</span>
          </div>
          <p className="text-[11px] text-muted-foreground">{alert.subsystem} · {alert.metric}</p>
          <p className="text-[11px] leading-snug">{alert.summary}</p>
        </div>
        <span className="text-muted-foreground shrink-0 mt-0.5 text-[10px]">{open ? "▲" : "▼"}</span>
      </button>

      {/* Expanded diagnosis */}
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
  const [state,   setState]  = useState<MachineState>(MOCK_STATE);
  const [isDemo,  setIsDemo] = useState(true);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    async function poll() {
      try {
        const res = await fetch(`${API_BASE}/api/runs/${SCENARIO}/state/latest`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: MachineState = await res.json();
        if (alive) { setState(data); setIsDemo(false); }
      } catch {
        if (alive) { setState(MOCK_STATE); setIsDemo(true); }
      } finally {
        if (alive) setLoading(false);
      }
    }
    poll();
    const id = setInterval(poll, 5_000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const alerts = deriveAlerts(state);
  const subsystems = [
    { label: "Recoating", health: state.recoating.subsystem_health },
    { label: "Printhead", health: state.printhead.subsystem_health },
    { label: "Thermal",   health: state.thermal.subsystem_health   },
  ];

  return (
    <div className="flex h-full">

      {/* Center: 3D machine */}
      <div className="flex-1 relative overflow-hidden border-r border-border">
        <MachineExperience />
        {!loading && (
          <div className="absolute bottom-3 left-1/2 -translate-x-1/2 text-xs font-mono text-muted-foreground bg-background/70 rounded px-2 py-1 pointer-events-none">
            {state.scenario_id} · run {state.run_number} · t = {state.t}
            {isDemo && <span className="ml-2 text-yellow-400">· demo</span>}
          </div>
        )}
      </div>

      {/* Right rail */}
      <aside className="w-80 flex flex-col gap-3 p-3 bg-background overflow-hidden shrink-0">

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
              </div>
            </CardTitle>
          </CardHeader>
          <Separator />
          <CardContent className="flex-1 min-h-0 p-0">
            <ScrollArea className="h-full">
              <div className="flex flex-col gap-1.5 p-3">
                {alerts.length === 0 ? (
                  <p className="text-xs text-muted-foreground px-1">All components nominal.</p>
                ) : (
                  alerts.map(a => <AlertCard key={a.id} alert={a} />)
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
              <span className="text-muted-foreground font-normal text-[10px]">t = {state.t}</span>
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
