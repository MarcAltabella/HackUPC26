"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

// ── Types ─────────────────────────────────────────────────────────────────────

interface SubsystemState {
  subsystem_health: number;
}

interface ComponentState {
  health: number;
  status: string;
}

interface MachineState {
  scenario_id: string;
  run_number: number;
  t: number;
  recoating: SubsystemState & {
    blade: ComponentState & { thickness_mm: number };
    motor: ComponentState & { vibration_mm_s: number };
    rail:  ComponentState & { deviation_um: number };
  };
  printhead: SubsystemState & {
    nozzle:   ComponentState & { clog_probability: number };
    resistor: ComponentState & { drift_pct: number };
    cleaning: ComponentState & { efficiency: number };
  };
  thermal: SubsystemState & {
    heater:     ComponentState & { resistance_ohm: number };
    sensor:     ComponentState & { measurement_error_c: number };
    insulation: ComponentState & { thermal_resistance: number };
  };
}

interface HistoryRow {
  t: number;
  temperature: number;
  humidity: number;
  health_recoating: number;
  health_printhead: number;
  health_thermal: number;
  status_blade: string;
  status_nozzle: string;
  status_heater: string;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const API_BASE = "http://localhost:8000";
const SCENARIO  = "baseline_nominal";

// ── Helpers ───────────────────────────────────────────────────────────────────

function countCritical(state: MachineState): number {
  const components = [
    state.recoating.blade, state.recoating.motor, state.recoating.rail,
    state.printhead.nozzle, state.printhead.resistor, state.printhead.cleaning,
    state.thermal.heater, state.thermal.sensor, state.thermal.insulation,
  ];
  return components.filter(c => c.status === "FAILED" || c.status === "CRITICAL").length;
}

function countWarning(state: MachineState): number {
  const components = [
    state.recoating.blade, state.recoating.motor, state.recoating.rail,
    state.printhead.nozzle, state.printhead.resistor, state.printhead.cleaning,
    state.thermal.heater, state.thermal.sensor, state.thermal.insulation,
  ];
  return components.filter(c => c.status === "WARNING" || c.status === "DEGRADED").length;
}

function healthColor(h: number): string {
  if (h > 0.7) return "#22c55e";
  if (h > 0.4) return "#eab308";
  if (h > 0.2) return "#f97316";
  return "#ef4444";
}

function statusBadge(s: string) {
  if (s === "FAILED" || s === "CRITICAL")
    return <Badge variant="destructive" className="text-[10px] h-4 px-1.5">{s}</Badge>;
  if (s === "WARNING" || s === "DEGRADED")
    return <Badge variant="outline" className="text-[10px] h-4 px-1.5 border-yellow-500 text-yellow-400">{s}</Badge>;
  return <Badge variant="secondary" className="text-[10px] h-4 px-1.5 opacity-50">{s}</Badge>;
}

// ── Sparkline ─────────────────────────────────────────────────────────────────

function Sparkline({ data, color }: { data: number[]; color: string }) {
  if (data.length < 2) {
    return <div className="h-9 rounded bg-muted/30" />;
  }
  const W = 300, H = 36, pad = 2;
  const pts = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (W - 2 * pad);
    const y = (H - pad) - Math.max(0, Math.min(1, v)) * (H - 2 * pad);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const last = pts[pts.length - 1];
  const first = pts[0];
  const [, lastY] = last.split(",");
  const area = `${first.split(",")[0]},${H - pad} ${pts.join(" ")} ${last.split(",")[0]},${H - pad}`;
  void lastY;
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full overflow-visible"
      preserveAspectRatio="none"
      style={{ height: H }}
    >
      <polygon points={area} fill={color} fillOpacity={0.1} />
      <polyline
        points={pts.join(" ")}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

// ── KPI card ──────────────────────────────────────────────────────────────────

function KpiCard({
  title,
  value,
  sub,
  accent,
}: {
  title: string;
  value: string | number;
  sub?: string;
  accent?: string;
}) {
  return (
    <Card>
      <CardContent className="pt-4 pb-3 px-4">
        <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">
          {title}
        </p>
        <p className="text-2xl font-mono font-semibold leading-none" style={{ color: accent }}>
          {value}
        </p>
        {sub && <p className="text-[10px] text-muted-foreground mt-1">{sub}</p>}
      </CardContent>
    </Card>
  );
}

// ── Component row inside subsystem card ───────────────────────────────────────

function ComponentRow({ name, health, status }: { name: string; health: number; status: string }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-muted-foreground w-20 shrink-0">{name}</span>
      <div className="flex-1 mx-2 h-1 bg-muted rounded-full overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{ width: `${(health * 100).toFixed(0)}%`, background: healthColor(health) }}
        />
      </div>
      {statusBadge(status)}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const [state,   setState]   = useState<MachineState | null>(null);
  const [history, setHistory] = useState<HistoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  // Poll state every 5 s
  useEffect(() => {
    let alive = true;
    async function fetchState() {
      try {
        const res = await fetch(`${API_BASE}/api/runs/${SCENARIO}/state/latest`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const d: MachineState = await res.json();
        if (alive) { setState(d); setError(null); }
      } catch {
        if (alive) setError("Backend unreachable");
      } finally {
        if (alive) setLoading(false);
      }
    }
    fetchState();
    const id = setInterval(fetchState, 5_000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  // Fetch history once for sparklines
  useEffect(() => {
    fetch(`${API_BASE}/api/runs/${SCENARIO}/history?start_t=0&end_t=999`)
      .then(r => r.ok ? r.json() : [])
      .then((rows: HistoryRow[]) => setHistory(rows))
      .catch(() => {});
  }, []);

  // Derived KPIs
  const critical = state ? countCritical(state) : 0;
  const warning  = state ? countWarning(state) : 0;
  const avgHealth = state
    ? (state.recoating.subsystem_health + state.printhead.subsystem_health + state.thermal.subsystem_health) / 3
    : 0;

  const recHistory = history.slice(-20);

  const subsystems = state
    ? [
        {
          label: "Recoating",
          health: state.recoating.subsystem_health,
          histKey: "health_recoating" as keyof HistoryRow,
          components: [
            { name: "Blade",  health: state.recoating.blade.health,  status: state.recoating.blade.status },
            { name: "Motor",  health: state.recoating.motor.health,  status: state.recoating.motor.status },
            { name: "Rail",   health: state.recoating.rail.health,   status: state.recoating.rail.status  },
          ],
        },
        {
          label: "Printhead",
          health: state.printhead.subsystem_health,
          histKey: "health_printhead" as keyof HistoryRow,
          components: [
            { name: "Nozzle",   health: state.printhead.nozzle.health,   status: state.printhead.nozzle.status   },
            { name: "Resistors",health: state.printhead.resistor.health, status: state.printhead.resistor.status },
            { name: "Cleaning", health: state.printhead.cleaning.health, status: state.printhead.cleaning.status },
          ],
        },
        {
          label: "Thermal",
          health: state.thermal.subsystem_health,
          histKey: "health_thermal" as keyof HistoryRow,
          components: [
            { name: "Heater",     health: state.thermal.heater.health,     status: state.thermal.heater.status     },
            { name: "Sensor",     health: state.thermal.sensor.health,     status: state.thermal.sensor.status     },
            { name: "Insulation", health: state.thermal.insulation.health, status: state.thermal.insulation.status },
          ],
        },
      ]
    : [];

  return (
    <ScrollArea className="h-full">
      <div className="p-4 space-y-4 max-w-6xl mx-auto">

        {error && (
          <p className="text-xs text-destructive bg-destructive/10 rounded-md px-3 py-2">
            {error} — run: <code>uvicorn api:app --reload --port 8000</code>
          </p>
        )}

        {/* KPI row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <KpiCard
            title="Active Alerts"
            value={loading ? "—" : critical + warning}
            sub={`${critical} critical · ${warning} warning`}
            accent={critical > 0 ? "#ef4444" : warning > 0 ? "#eab308" : "#22c55e"}
          />
          <KpiCard
            title="Critical Components"
            value={loading ? "—" : critical}
            accent={critical > 0 ? "#ef4444" : undefined}
          />
          <KpiCard
            title="Avg Subsystem Health"
            value={loading ? "—" : `${(avgHealth * 100).toFixed(1)}%`}
            accent={healthColor(avgHealth)}
          />
          <KpiCard
            title="Simulation Tick"
            value={loading ? "—" : state?.t ?? "—"}
            sub={state ? `${state.scenario_id} · run ${state.run_number}` : undefined}
          />
        </div>

        {/* Subsystem health cards with sparklines */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {loading
            ? [1, 2, 3].map(i => (
                <Card key={i}>
                  <CardContent className="pt-4 h-36 flex items-center justify-center">
                    <p className="text-xs text-muted-foreground">Awaiting data…</p>
                  </CardContent>
                </Card>
              ))
            : subsystems.map(({ label, health, histKey, components }) => (
                <Card key={label}>
                  <CardHeader className="py-3 px-4">
                    <CardTitle className="text-xs font-semibold flex items-center justify-between">
                      <span>{label}</span>
                      <span
                        className="text-lg font-mono font-bold"
                        style={{ color: healthColor(health) }}
                      >
                        {(health * 100).toFixed(0)}%
                      </span>
                    </CardTitle>
                  </CardHeader>
                  <Separator />
                  <CardContent className="pt-3 px-4 pb-4 space-y-3">
                    <Sparkline
                      data={history.map(r => r[histKey] as number)}
                      color={healthColor(health)}
                    />
                    <div className="space-y-1.5">
                      {components.map(c => (
                        <ComponentRow key={c.name} {...c} />
                      ))}
                    </div>
                  </CardContent>
                </Card>
              ))}
        </div>

        {/* Recent historian events */}
        <Card>
          <CardHeader className="py-3 px-4">
            <CardTitle className="text-xs font-semibold flex items-center justify-between">
              <span>Recent Historian Events</span>
              <span className="text-[10px] font-normal text-muted-foreground">last 20 ticks</span>
            </CardTitle>
          </CardHeader>
          <Separator />
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border">
                    {["t", "Temp °C", "Humidity", "Recoating", "Printhead", "Thermal", "Blade", "Nozzle", "Heater"].map(h => (
                      <th key={h} className="text-left px-3 py-2 text-[10px] font-semibold text-muted-foreground uppercase tracking-wide whitespace-nowrap">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {recHistory.length === 0 && (
                    <tr>
                      <td colSpan={9} className="px-3 py-4 text-muted-foreground text-center">
                        {loading ? "Loading…" : "No history available."}
                      </td>
                    </tr>
                  )}
                  {[...recHistory].reverse().map(row => (
                    <tr key={row.t} className="border-b border-border/50 hover:bg-muted/20 transition-colors">
                      <td className="px-3 py-1.5 font-mono">{row.t}</td>
                      <td className="px-3 py-1.5 font-mono">{row.temperature.toFixed(1)}</td>
                      <td className="px-3 py-1.5 font-mono">{(row.humidity * 100).toFixed(0)}%</td>
                      <td className="px-3 py-1.5 font-mono" style={{ color: healthColor(row.health_recoating) }}>
                        {(row.health_recoating * 100).toFixed(1)}%
                      </td>
                      <td className="px-3 py-1.5 font-mono" style={{ color: healthColor(row.health_printhead) }}>
                        {(row.health_printhead * 100).toFixed(1)}%
                      </td>
                      <td className="px-3 py-1.5 font-mono" style={{ color: healthColor(row.health_thermal) }}>
                        {(row.health_thermal * 100).toFixed(1)}%
                      </td>
                      <td className="px-3 py-1.5">{statusBadge(row.status_blade)}</td>
                      <td className="px-3 py-1.5">{statusBadge(row.status_nozzle)}</td>
                      <td className="px-3 py-1.5">{statusBadge(row.status_heater)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

      </div>
    </ScrollArea>
  );
}
