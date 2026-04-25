"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

interface SubsystemState {
  subsystem_health: number;
}

interface MachineState {
  scenario_id: string;
  run_number: number;
  t: number;
  recoating: SubsystemState & {
    blade: { health: number; status: string; thickness_mm: number };
    motor: { health: number; status: string; vibration_mm_s: number };
    rail:  { health: number; status: string; deviation_um: number };
  };
  printhead: SubsystemState & {
    nozzle:    { health: number; status: string; clog_probability: number };
    resistor:  { health: number; status: string; drift_pct: number };
    cleaning:  { health: number; status: string; efficiency: number };
  };
  thermal: SubsystemState & {
    heater:     { health: number; status: string; resistance_ohm: number };
    sensor:     { health: number; status: string; measurement_error_c: number };
    insulation: { health: number; status: string; thermal_resistance: number };
  };
}

interface Alert {
  id: number;
  severity: "CRITICAL" | "WARNING" | "INFO";
  subsystem: string;
  component: string;
  message: string;
}

const API_BASE = "http://localhost:8000";
const SCENARIO  = "baseline_nominal";

function barColor(h: number) {
  if (h > 0.7) return "bg-green-500";
  if (h > 0.4) return "bg-yellow-500";
  if (h > 0.2) return "bg-orange-500";
  return "bg-red-600";
}

function badgeVariant(s: "CRITICAL" | "WARNING" | "INFO") {
  if (s === "CRITICAL") return "destructive" as const;
  if (s === "WARNING")  return "outline" as const;
  return "secondary" as const;
}

function deriveAlerts(state: MachineState): Alert[] {
  const alerts: Alert[] = [];
  let id = 1;

  function check(
    health: number,
    status: string,
    subsystem: string,
    component: string,
    hint: string
  ) {
    if (status === "FAILED" || status === "CRITICAL") {
      alerts.push({
        id: id++,
        severity: status === "FAILED" ? "CRITICAL" : "WARNING",
        subsystem,
        component,
        message: `${status} — ${hint}`,
      });
    }
  }

  check(state.recoating.blade.health,     state.recoating.blade.status,     "Recoating", "Blade",           `${state.recoating.blade.thickness_mm.toFixed(2)} mm`);
  check(state.recoating.motor.health,     state.recoating.motor.status,     "Recoating", "Motor",           `${state.recoating.motor.vibration_mm_s.toFixed(1)} mm/s vib.`);
  check(state.recoating.rail.health,      state.recoating.rail.status,      "Recoating", "Rail",            `${state.recoating.rail.deviation_um.toFixed(0)} µm dev.`);
  check(state.printhead.nozzle.health,    state.printhead.nozzle.status,    "Printhead", "Nozzle",          `${(state.printhead.nozzle.clog_probability * 100).toFixed(0)}% clog`);
  check(state.printhead.resistor.health,  state.printhead.resistor.status,  "Printhead", "Resistors",       `${state.printhead.resistor.drift_pct.toFixed(1)}% drift`);
  check(state.printhead.cleaning.health,  state.printhead.cleaning.status,  "Printhead", "Cleaning I/F",    `${(state.printhead.cleaning.efficiency * 100).toFixed(0)}% eff.`);
  check(state.thermal.heater.health,      state.thermal.heater.status,      "Thermal",   "Heater",          `${state.thermal.heater.resistance_ohm.toFixed(1)} Ω`);
  check(state.thermal.sensor.health,      state.thermal.sensor.status,      "Thermal",   "Temp. Sensor",    `±${state.thermal.sensor.measurement_error_c.toFixed(1)} °C err.`);
  check(state.thermal.insulation.health,  state.thermal.insulation.status,  "Thermal",   "Insulation",      `R=${state.thermal.insulation.thermal_resistance.toFixed(2)}`);

  return alerts;
}

export default function DashboardPage() {
  const [state, setState]     = useState<MachineState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);

  useEffect(() => {
    let alive = true;

    async function poll() {
      try {
        const res = await fetch(`${API_BASE}/api/runs/${SCENARIO}/state/latest`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: MachineState = await res.json();
        if (alive) { setState(data); setError(null); }
      } catch {
        if (alive) setError("Backend unreachable — run: uvicorn api:app --reload --port 8000");
      } finally {
        if (alive) setLoading(false);
      }
    }

    poll();
    const id = setInterval(poll, 5_000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const subsystems = state
    ? [
        { label: "Recoating", health: state.recoating.subsystem_health },
        { label: "Printhead", health: state.printhead.subsystem_health },
        { label: "Thermal",   health: state.thermal.subsystem_health   },
      ]
    : [];

  const alerts = state ? deriveAlerts(state) : [];

  return (
    <div className="flex h-full">

      {/* Center: 3D canvas placeholder (Milestone 6) */}
      <div className="flex-1 flex flex-col items-center justify-center bg-muted/10 border-r border-border select-none">
        <div className="text-center space-y-3 text-muted-foreground">
          <div className="text-7xl opacity-20">⬡</div>
          <p className="text-base font-medium">3D Machine View</p>
          <p className="text-xs">
            Milestone 6 — react-three-fiber canvas mounts here
          </p>
          {state && (
            <p className="text-xs font-mono mt-4">
              {state.scenario_id} · run {state.run_number} · t = {state.t}
            </p>
          )}
        </div>
      </div>

      {/* Right sidebar */}
      <aside className="w-80 flex flex-col gap-3 p-3 bg-background overflow-hidden shrink-0">

        {/* Active Alerts */}
        <Card className="flex-1 flex flex-col min-h-0">
          <CardHeader className="py-3 px-4">
            <CardTitle className="text-xs font-semibold flex items-center justify-between">
              <span>Active Alerts</span>
              {alerts.length > 0 && (
                <Badge variant="destructive" className="text-[10px] h-4 px-1.5">
                  {alerts.length}
                </Badge>
              )}
            </CardTitle>
          </CardHeader>

          <Separator />

          <CardContent className="flex-1 min-h-0 p-0">
            <ScrollArea className="h-full">
              <div className="flex flex-col gap-1.5 p-3">
                {loading && (
                  <p className="text-xs text-muted-foreground px-1">Connecting…</p>
                )}

                {error && (
                  <p className="text-xs text-destructive px-1">{error}</p>
                )}

                {!loading && !error && alerts.length === 0 && (
                  <p className="text-xs text-muted-foreground px-1">
                    All components nominal.
                  </p>
                )}

                {alerts.map((a) => (
                  <div
                    key={a.id}
                    className="rounded-md border border-border p-2.5 text-xs flex flex-col gap-1"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium truncate">{a.component}</span>
                      <Badge variant={badgeVariant(a.severity)} className="text-[10px] h-4 px-1.5 shrink-0">
                        {a.severity}
                      </Badge>
                    </div>
                    <span className="text-muted-foreground">{a.subsystem}</span>
                    <span className="font-mono text-[11px]">{a.message}</span>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>

        {/* Subsystem Health */}
        <Card className="shrink-0">
          <CardHeader className="py-3 px-4">
            <CardTitle className="text-xs font-semibold flex items-center justify-between">
              <span>Subsystem Health</span>
              {state && (
                <span className="text-muted-foreground font-normal text-[10px]">
                  t = {state.t}
                </span>
              )}
            </CardTitle>
          </CardHeader>

          <Separator />

          <CardContent className="p-3 flex flex-col gap-3">
            {(loading && !state) ? (
              <p className="text-xs text-muted-foreground">Awaiting data…</p>
            ) : (
              subsystems.map(({ label, health }) => (
                <div key={label} className="flex flex-col gap-1">
                  <div className="flex justify-between text-xs">
                    <span className="font-medium">{label}</span>
                    <span className="font-mono text-muted-foreground">
                      {(health * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${barColor(health)}`}
                      style={{ width: `${(health * 100).toFixed(1)}%` }}
                    />
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

      </aside>
    </div>
  );
}
