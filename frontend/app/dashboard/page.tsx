"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { getHistory, getLatestState } from "@/lib/api";
import type { HistoryRow, MachineState } from "@/lib/api-types";

// ── Constants ─────────────────────────────────────────────────────────────────

const SCENARIO  = "baseline_nominal";
const SPEED     = 3; // ticks per second

// ── Helpers ───────────────────────────────────────────────────────────────────

function toStatus(h: number): string {
  if (h > 0.85) return "FUNCTIONAL";
  if (h > 0.70) return "NOMINAL";
  if (h > 0.50) return "WARNING";
  if (h > 0.25) return "DEGRADED";
  if (h > 0.10) return "CRITICAL";
  return "FAILED";
}

function healthColor(h: number): string {
  if (h > 0.7)  return "#4ade80";
  if (h > 0.4)  return "#fde047";
  if (h > 0.2)  return "#fb923c";
  return "#f87171";
}

function segColor(h: number): string {
  if (h > 0.85) return "#4ade80";
  if (h > 0.70) return "#86efac";
  if (h > 0.50) return "#fde047";
  if (h > 0.25) return "#fb923c";
  if (h > 0.10) return "#f87171";
  return "#ef4444";
}

const clamp = (v: number) => Math.max(0, Math.min(1, v));

function componentHealth(row: HistoryRow, component: string): number {
  const direct = row[`health_${component}` as keyof HistoryRow];
  if (typeof direct === "number") return clamp(direct);
  if (component === "blade") return clamp(row.health_recoating + 0.04);
  if (component === "motor") return clamp(row.health_recoating + 0.18);
  if (component === "rail") return clamp(row.health_recoating - 0.06);
  if (component === "nozzle") return clamp(row.health_printhead - 0.04);
  if (component === "resistor") return clamp(row.health_printhead + 0.12);
  if (component === "cleaning") return clamp(row.health_printhead + 0.02);
  if (component === "heater") return clamp(row.health_thermal + 0.06);
  if (component === "sensor") return clamp(row.health_thermal + 0.02);
  return clamp(row.health_thermal - 0.03);
}

function getKpisFromRow(row: HistoryRow) {
  const healths = [
    componentHealth(row, "blade"),
    componentHealth(row, "motor"),
    componentHealth(row, "rail"),
    componentHealth(row, "nozzle"),
    componentHealth(row, "resistor"),
    componentHealth(row, "cleaning"),
    componentHealth(row, "heater"),
    componentHealth(row, "sensor"),
    componentHealth(row, "insulation"),
  ];
  const statuses = healths.map(toStatus);
  return {
    critical:  statuses.filter(s => s === "FAILED" || s === "CRITICAL").length,
    warning:   statuses.filter(s => s === "WARNING" || s === "DEGRADED").length,
    avgHealth: (row.health_recoating + row.health_printhead + row.health_thermal) / 3,
  };
}

// Linear interpolation between two rows
function lerpRows(a: HistoryRow, b: HistoryRow, t: number): HistoryRow {
  const lerp = (x: number, y: number) => x + (y - x) * t;
  return {
    ...a,
    health_recoating: lerp(a.health_recoating, b.health_recoating),
    health_printhead: lerp(a.health_printhead, b.health_printhead),
    health_thermal:   lerp(a.health_thermal,   b.health_thermal),
    temperature:      lerp(a.temperature,      b.temperature),
    humidity:         lerp(a.humidity,         b.humidity),
  };
}

// ── Blueprint panel ───────────────────────────────────────────────────────────

function BpPanel({
  title,
  right,
  children,
  className = "",
}: {
  title: string;
  right?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`border border-border bg-card relative ${className}`}>
      <span className="absolute top-0 left-0   w-2.5 h-2.5 border-t-[1.5px] border-l-[1.5px] border-primary/50 pointer-events-none" />
      <span className="absolute top-0 right-0  w-2.5 h-2.5 border-t-[1.5px] border-r-[1.5px] border-primary/50 pointer-events-none" />
      <span className="absolute bottom-0 left-0  w-2.5 h-2.5 border-b-[1.5px] border-l-[1.5px] border-primary/50 pointer-events-none" />
      <span className="absolute bottom-0 right-0 w-2.5 h-2.5 border-b-[1.5px] border-r-[1.5px] border-primary/50 pointer-events-none" />
      <div className="flex items-center gap-3 px-4 py-2 border-b border-border">
        <span className="text-[10px] font-mono font-semibold text-foreground tracking-wide shrink-0">
          {title}
        </span>
        <div className="flex-1 border-t border-white/20" />
        {right}
      </div>
      {children}
    </div>
  );
}

// ── KPI Strip ─────────────────────────────────────────────────────────────────

function KpiStrip({ animTick, critical, warning, avgHealth, scenarioId, runNumber }: {
  animTick: number; critical: number; warning: number;
  avgHealth: number; scenarioId: string; runNumber: number;
}) {
  const total = critical + warning;
  const items = [
    {
      label: "Active Alerts",
      value: String(total),
      sub:   total === 0 ? "all nominal" : "require attention",
      color: critical > 0 ? "#ef4444" : warning > 0 ? "#eab308" : "#22c55e",
    },
    {
      label: "Critical",
      value: String(critical),
      sub:   warning > 0 ? `${warning} warning` : "none",
      color: critical > 0 ? "#ef4444" : "#86efac",
    },
    {
      label: "Avg Health",
      value: `${(avgHealth * 100).toFixed(1)}%`,
      sub:   toStatus(avgHealth),
      color: healthColor(avgHealth),
    },
    {
      label: "Simulation",
      value: String(Math.floor(animTick)).padStart(3, "0"),
      sub:   `${scenarioId} · run ${runNumber}`,
      color: "rgba(228,234,246,0.92)",
    },
  ];

  return (
    <div className="border border-border bg-card relative overflow-hidden">
      <span className="absolute top-0 left-0   w-2.5 h-2.5 border-t-[1.5px] border-l-[1.5px] border-primary/50 pointer-events-none" />
      <span className="absolute top-0 right-0  w-2.5 h-2.5 border-t-[1.5px] border-r-[1.5px] border-primary/50 pointer-events-none" />
      <span className="absolute bottom-0 left-0  w-2.5 h-2.5 border-b-[1.5px] border-l-[1.5px] border-primary/50 pointer-events-none" />
      <span className="absolute bottom-0 right-0 w-2.5 h-2.5 border-b-[1.5px] border-r-[1.5px] border-primary/50 pointer-events-none" />
      <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-border">
        {items.map(({ label, value, sub, color }) => (
          <div key={label} className="px-4 py-3">
            <p className="text-[10px] font-mono text-foreground/70 tracking-wide mb-1.5">{label}</p>
            <p className="text-3xl font-mono font-bold leading-none tabular-nums transition-all duration-150" style={{ color }}>{value}</p>
            <p className="text-[10px] font-mono text-muted-foreground mt-1.5 tracking-wide">{sub}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Line Chart ────────────────────────────────────────────────────────────────

function LineChart({ data, animTick, totalTicks, color, label, unit, yMin, yMax }: {
  data: number[];        // full history of this series
  animTick: number;      // float — current position in data
  totalTicks: number;
  color: string;
  label: string;
  unit: string;
  yMin: number;
  yMax: number;
}) {
  const W = 900, H = 80, padL = 36, padR = 8, padT = 6, padB = 18;
  const cW = W - padL - padR;
  const cH = H - padT - padB;
  const total = Math.max(totalTicks, 2);

  const px = (x: number) => padL + (x / (total - 1)) * cW;
  const py = (v: number) => padT + (1 - (v - yMin) / (yMax - yMin)) * cH;

  const floor = Math.min(Math.floor(animTick), data.length - 1);
  const frac  = animTick - Math.floor(animTick);

  // Visible data points: 0..floor (integer), plus a fractional interpolated tail
  const visPoints: { x: number; y: number }[] = [];
  for (let i = 0; i <= floor; i++) {
    visPoints.push({ x: i, y: data[i] });
  }
  if (floor + 1 < data.length && frac > 0.001) {
    const yInterp = data[floor] + (data[floor + 1] - data[floor]) * frac;
    visPoints.push({ x: animTick, y: yInterp });
  }

  const pts = visPoints.map(({ x, y }) => `${px(x).toFixed(1)},${py(y).toFixed(1)}`).join(" ");

  const areaPath = visPoints.length > 1 ? [
    `M${px(visPoints[0].x).toFixed(1)},${(padT + cH).toFixed(1)}`,
    ...visPoints.map(({ x, y }) => `L${px(x).toFixed(1)},${py(y).toFixed(1)}`),
    `L${px(visPoints[visPoints.length - 1].x).toFixed(1)},${(padT + cH).toFixed(1)}Z`,
  ].join("") : "";

  const last  = visPoints[visPoints.length - 1];
  const yMid  = (yMin + yMax) / 2;
  const xTicks = [0, 0.25, 0.5, 0.75, 1].map(p => Math.round(p * (total - 1)));
  const gradId = `lg-${label.replace(/\W/g, "")}`;

  return (
    <div className="space-y-1">
      <div className="flex items-baseline gap-2">
        <span className="text-[10px] font-mono font-semibold text-foreground/90 tracking-wide">{label}</span>
        <span className="text-[9px] font-mono text-muted-foreground">{unit}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: "80px" }} preserveAspectRatio="none">
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor={color} stopOpacity="0.22" />
            <stop offset="100%" stopColor={color} stopOpacity="0.01" />
          </linearGradient>
        </defs>
        {[yMin, yMid, yMax].map((v, i) => {
          const y = py(v);
          return (
            <g key={i}>
              <line x1={padL} y1={y} x2={W - padR} y2={y}
                stroke="rgba(228,234,246,0.24)" strokeWidth="0.8"
                strokeDasharray={i === 1 ? "4 3" : "none"}
              />
              <text x={padL - 4} y={y + 3.5}
                textAnchor="end" fill="rgba(228,234,246,0.65)" fontSize="8"
                fontFamily="ui-monospace,monospace">
                {v.toFixed(0)}
              </text>
            </g>
          );
        })}
        {xTicks.map(t => (
          <text key={t} x={px(t)} y={H - 2}
            textAnchor="middle" fill="rgba(228,234,246,0.65)" fontSize="8"
            fontFamily="ui-monospace,monospace">
            {t}
          </text>
        ))}
        {areaPath && <path d={areaPath} fill={`url(#${gradId})`} />}
        {visPoints.length > 1 && (
          <polyline points={pts} fill="none" stroke={color}
            strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />
        )}
        {last && (
          <>
            <line
              x1={px(last.x)} y1={padT} x2={px(last.x)} y2={padT + cH}
              stroke={color} strokeWidth="0.9" strokeDasharray="3 2" opacity="0.5"
            />
            <circle cx={px(last.x)} cy={py(last.y)} r="3" fill={color} />
          </>
        )}
      </svg>
    </div>
  );
}

// ── Degradation Row ───────────────────────────────────────────────────────────

function DegradationRow({ label, fullData, animTick, currentHealth }: {
  label: string;
  fullData: number[];
  animTick: number;   // float
  currentHealth: number;
}) {
  const maxSegments = 140;
  const bucketSize = Math.max(1, Math.ceil(fullData.length / maxSegments));
  const segments = [];

  for (let start = 0; start < fullData.length; start += bucketSize) {
    const values = fullData.slice(start, start + bucketSize);
    segments.push({
      start,
      end: Math.min(start + bucketSize - 1, fullData.length - 1),
      health: Math.min(...values),
    });
  }

  return (
    <div className="flex items-center gap-2 text-[10px]">
      <span className="text-muted-foreground font-mono w-[72px] shrink-0 text-right tracking-wide">{label}</span>
      <div className="flex-1 grid h-[14px] overflow-hidden gap-px" style={{ minWidth: 0, gridTemplateColumns: `repeat(${segments.length}, minmax(2px, 1fr))` }}>
        {segments.map(({ start, end, health }) => {
          const visible = start <= animTick;
          const active = start <= animTick && animTick <= end;
          const progress = active ? Math.max(0.35, (animTick - start + 1) / Math.max(1, end - start + 1)) : 1;
          return (
          <div
            key={start}
            className="h-full"
            style={{
              background: visible ? segColor(health) : "rgba(228,234,246,0.08)",
              opacity: visible ? progress : 1,
            }}
          />
        )})}
      </div>
      <span
        className="w-10 shrink-0 font-mono text-right text-[10px] tabular-nums"
        style={{ color: healthColor(currentHealth) }}
      >
        {(currentHealth * 100).toFixed(0)}%
      </span>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const [state,    setState]    = useState<MachineState | null>(null);
  const [history,  setHistory]  = useState<HistoryRow[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState<string | null>(null);
  const isDemo = false;
  const [animTick, setAnimTick] = useState(0); // float

  // Mutable refs for the RAF loop — avoids closure-stale issues
  const animTimeRef  = useRef(0);
  const pausedRef    = useRef(false);
  const lastTimeRef  = useRef<number | null>(null);
  const rafRef       = useRef<number | null>(null);
  const pauseTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Live state polling
  useEffect(() => {
    let alive = true;
    async function fetchState() {
      try {
        const d = await getLatestState(SCENARIO);
        if (alive) setState(d);
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : "Failed to load latest state");
      }
    }
    fetchState();
    const id = setInterval(fetchState, 5_000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  // History fetch
  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    getHistory(SCENARIO, 0, 0, 999, ctrl.signal)
      .then((rows) => {
        if (rows.length === 0) throw new Error("API returned no history rows");
        setHistory(rows);
        setError(null);
      })
      .catch((err: Error) => {
        if (!ctrl.signal.aborted) {
          setHistory([]);
          setError(err.message);
        }
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
  }, []);

  // RAF animation loop — smooth fractional tick
  useEffect(() => {
    if (history.length === 0) return;
    const total = history.length;

    animTimeRef.current = 0;
    pausedRef.current   = false;
    lastTimeRef.current = null;
    requestAnimationFrame(() => setAnimTick(0));

    function frame(now: number) {
      const dt = lastTimeRef.current === null ? 0 : (now - lastTimeRef.current) / 1000;
      lastTimeRef.current = now;

      if (!pausedRef.current) {
        animTimeRef.current = Math.min(animTimeRef.current + dt * SPEED, total - 1);

        if (animTimeRef.current >= total - 1) {
          animTimeRef.current = total - 1;
          pausedRef.current   = true;
          pauseTimeout.current = setTimeout(() => {
            animTimeRef.current = 0;
            pausedRef.current   = false;
            lastTimeRef.current = null;
          }, 1500);
        }

        setAnimTick(animTimeRef.current);
      }

      rafRef.current = requestAnimationFrame(frame);
    }

    rafRef.current = requestAnimationFrame(frame);
    return () => {
      if (rafRef.current)       cancelAnimationFrame(rafRef.current);
      if (pauseTimeout.current) clearTimeout(pauseTimeout.current);
    };
  }, [history]);

  // ── Derived values ──────────────────────────────────────────────────────────

  const tempFull  = useMemo(() => history.map(r => r.temperature),   [history]);
  const humidFull = useMemo(() => history.map(r => r.humidity * 100), [history]);

  const groups = useMemo(() => [
    {
      label: "Recoating",
      rows: [
        { name: "Blade",   full: history.map(r => componentHealth(r, "blade")) },
        { name: "Motor",   full: history.map(r => componentHealth(r, "motor")) },
        { name: "Rail",    full: history.map(r => componentHealth(r, "rail")) },
      ],
    },
    {
      label: "Printhead",
      rows: [
        { name: "Nozzle",    full: history.map(r => componentHealth(r, "nozzle")) },
        { name: "Resistors", full: history.map(r => componentHealth(r, "resistor")) },
        { name: "Cleaning",  full: history.map(r => componentHealth(r, "cleaning")) },
      ],
    },
    {
      label: "Thermal",
      rows: [
        { name: "Heater",     full: history.map(r => componentHealth(r, "heater")) },
        { name: "Sensor",     full: history.map(r => componentHealth(r, "sensor")) },
        { name: "Insulation", full: history.map(r => componentHealth(r, "insulation")) },
      ],
    },
  ], [history]);

  if (loading || error || history.length === 0 || state === null) {
    return (
      <ScrollArea className="h-full">
        <div className="p-4 max-w-6xl mx-auto">
          <div className="border border-border bg-card px-4 py-3 font-mono text-xs text-muted-foreground">
            {loading ? "LOADING LIVE TELEMETRY" : error ?? "NO LIVE HISTORY ROWS RETURNED"}
          </div>
        </div>
      </ScrollArea>
    );
  }

  const totalTicks = history.length;

  const floor = Math.min(Math.floor(animTick), history.length - 1);
  const frac  = animTick - Math.floor(animTick);
  const rowA  = history[floor]                          ?? history[0];
  const rowB  = history[Math.min(floor + 1, history.length - 1)] ?? rowA;

  const currentRow = lerpRows(rowA, rowB, frac);
  const { critical, warning, avgHealth } = getKpisFromRow(currentRow);

  // Pre-computed full series for charts (stable references — recomputed only when history changes)
  const tempMin  = Math.floor(Math.min(...tempFull) - 1);
  const tempMax  = Math.ceil(Math.max(...tempFull)  + 1);

  // Current health per component (interpolated)
  const compCur: Record<string, Record<string, number>> = {
    Recoating: { Blade: componentHealth(currentRow, "blade"), Motor: componentHealth(currentRow, "motor"), Rail: componentHealth(currentRow, "rail") },
    Printhead: { Nozzle: componentHealth(currentRow, "nozzle"), Resistors: componentHealth(currentRow, "resistor"), Cleaning: componentHealth(currentRow, "cleaning") },
    Thermal:   { Heater: componentHealth(currentRow, "heater"), Sensor: componentHealth(currentRow, "sensor"), Insulation: componentHealth(currentRow, "insulation") },
  };

  return (
    <ScrollArea className="h-full">
      <div className="p-4 space-y-4 max-w-6xl mx-auto">

        {/* Demo banner */}
        {isDemo && (
          <div className="flex items-center gap-3 border border-yellow-500/30 bg-yellow-950/20 px-4 py-2 font-mono">
            <span className="text-yellow-400 text-[10px] tracking-widest shrink-0">⚠ DEMO_MODE</span>
            <span className="text-[10px] text-yellow-400/60">
              synthetic data · start backend (
              <code className="text-yellow-300">uvicorn api:app --reload --port 8000</code>
              ) to connect live historian
            </span>
          </div>
        )}

        {/* KPI readout strip */}
        <KpiStrip
          animTick={animTick}
          critical={critical}
          warning={warning}
          avgHealth={avgHealth}
          scenarioId={state.scenario_id}
          runNumber={state.run_number}
        />

        {/* Input Drivers */}
        <BpPanel
          title="Input Drivers"
          right={
            <span className="text-[9px] font-mono text-muted-foreground tracking-wide">
              t = {String(Math.floor(animTick)).padStart(3, "0")} / {totalTicks - 1}
            </span>
          }
        >
          <div className="px-4 py-3 space-y-5">
            <LineChart
              data={tempFull}
              animTick={animTick}
              totalTicks={totalTicks}
              color="#fbbf24"
              label="Temperature"
              unit="°C"
              yMin={tempMin}
              yMax={tempMax}
            />
            <LineChart
              data={humidFull}
              animTick={animTick}
              totalTicks={totalTicks}
              color="#a5f3fc"
              label="Humidity"
              unit="%"
              yMin={0}
              yMax={100}
            />
          </div>
        </BpPanel>

        {/* Component Degradation Timeline */}
        <BpPanel
          title="Component Degradation"
          right={
            <div className="flex items-center gap-3 text-[9px] font-mono text-muted-foreground">
              {[
                { color: "#4ade80", label: "Nominal" },
                { color: "#fde047", label: "Warning" },
                { color: "#fb923c", label: "Degraded" },
                { color: "#f87171", label: "Critical" },
              ].map(({ color, label }) => (
                <span key={label} className="flex items-center gap-1">
                  <span className="inline-block w-2 h-2" style={{ background: color }} />
                  {label}
                </span>
              ))}
            </div>
          }
        >
          <div className="px-4 py-3 space-y-4">

            {/* Tick ruler */}
            <div className="flex text-[9px] font-mono text-muted-foreground" style={{ paddingLeft: "80px", paddingRight: "48px" }}>
              {[0, 0.25, 0.5, 0.75, 1].map(p => (
                <span key={p} className="flex-1 text-center first:text-left last:text-right">
                  {Math.round(p * (totalTicks - 1))}
                </span>
              ))}
            </div>

            {groups.map(({ label, rows }) => (
              <div key={label} className="space-y-1.5">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-foreground/70 text-[9px] font-mono font-bold shrink-0">▸</span>
                  <span className="text-[10px] font-mono font-semibold tracking-wide text-foreground/80">{label}</span>
                  <div className="flex-1 border-t border-white/15" />
                </div>
                {rows.map(({ name, full }) => (
                  <DegradationRow
                    key={name}
                    label={name}
                    fullData={full}
                    animTick={animTick}
                    currentHealth={compCur[label][name] ?? 1}
                  />
                ))}
              </div>
            ))}

            {/* Axis footer */}
            <div
              className="flex text-[9px] font-mono text-muted-foreground border-t border-border/40 pt-2"
              style={{ paddingLeft: "80px", paddingRight: "48px" }}
            >
              <span>t=0</span>
              <span className="flex-1 text-center opacity-40">◄── simulation tick ──►</span>
              <span>t={totalTicks - 1}</span>
            </div>
          </div>
        </BpPanel>

      </div>
    </ScrollArea>
  );
}
