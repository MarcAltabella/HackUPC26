"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { TimelineControls } from "@/components/timeline-controls";
import { MOCK_STATE, MOCK_HISTORY, type MachineState, type HistoryRow } from "@/lib/mock-data";

// ── Constants ─────────────────────────────────────────────────────────────────

const API_BASE = "http://localhost:8000";
const SCENARIO  = "baseline_nominal";
const BASE_SPEED = 3; // ticks per second at 1x

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

function getKpisFromRow(row: HistoryRow) {
  const healths = [
    clamp(row.health_recoating + 0.04),
    clamp(row.health_recoating + 0.18),
    clamp(row.health_recoating - 0.06),
    clamp(row.health_printhead - 0.04),
    clamp(row.health_printhead + 0.12),
    clamp(row.health_printhead + 0.02),
    clamp(row.health_thermal + 0.06),
    clamp(row.health_thermal + 0.02),
    clamp(row.health_thermal - 0.03),
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
      sub:   scenarioId,
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
  const cursorX = last ? Math.round(px(last.x)) + 0.5 : null;
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
              x1={cursorX!} y1={padT} x2={cursorX!} y2={padT + cH}
              stroke={color} strokeWidth="0.9" strokeDasharray="3 2" opacity="0.5"
              shapeRendering="crispEdges"
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
  const floor = Math.floor(animTick);
  const frac  = animTick - floor;

  return (
    <div className="flex items-center gap-2 text-[10px]">
      <span className="text-muted-foreground font-mono w-[72px] shrink-0 text-right tracking-wide">{label}</span>
      <div className="flex-1 flex gap-[1.5px] h-[14px] overflow-hidden" style={{ minWidth: 0 }}>
        {fullData.map((h, i) => (
          <div
            key={i}
            className="flex-1 h-full"
            style={{
              background: i <= floor ? segColor(h) : "rgba(228,234,246,0.08)",
              opacity:    i === floor ? frac : 1,
              minWidth:   0,
            }}
          />
        ))}
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
  const [state,    setState]    = useState<MachineState>(MOCK_STATE);
  const [history,  setHistory]  = useState<HistoryRow[]>(MOCK_HISTORY);
  const [isDemo,   setIsDemo]   = useState(true);
  const [animTick, setAnimTick] = useState(0); // float
  const [playbackSpeed, setPlaybackSpeed] = useState(1);

  // Mutable refs for the RAF loop — avoids closure-stale issues
  const animTimeRef  = useRef(0);
  const speedRef     = useRef(1);
  const pausedRef    = useRef(false);
  const lastTimeRef  = useRef<number | null>(null);
  const rafRef       = useRef<number | null>(null);
  const pauseTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Live state polling
  useEffect(() => {
    let alive = true;
    async function fetchState() {
      try {
        const res = await fetch(`${API_BASE}/api/runs/${SCENARIO}/state/latest`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const d: MachineState = await res.json();
        if (alive) { setState(d); setIsDemo(false); }
      } catch {
        if (alive) { setState(MOCK_STATE); setIsDemo(true); }
      }
    }
    fetchState();
    const id = setInterval(fetchState, 5_000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  useEffect(() => {
    speedRef.current = playbackSpeed;
  }, [playbackSpeed]);

  // History fetch
  useEffect(() => {
    fetch(`${API_BASE}/api/runs/${SCENARIO}/history?start_t=0&end_t=999`)
      .then(r => r.ok ? r.json() : Promise.reject())
      .then((rows: HistoryRow[]) => { setHistory(rows); setIsDemo(false); })
      .catch(() => setHistory(MOCK_HISTORY));
  }, []);

  // RAF animation loop — smooth fractional tick
  useEffect(() => {
    if (history.length === 0) return;
    const total = history.length;

    animTimeRef.current = 0;
    pausedRef.current   = false;
    lastTimeRef.current = null;
    setAnimTick(0);

    function frame(now: number) {
      const dt = lastTimeRef.current === null ? 0 : (now - lastTimeRef.current) / 1000;
      lastTimeRef.current = now;

      if (!pausedRef.current) {
        animTimeRef.current = Math.min(animTimeRef.current + dt * BASE_SPEED * speedRef.current, total - 1);

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

  const totalTicks = history.length || 1;

  const floor = Math.min(Math.floor(animTick), history.length - 1);
  const frac  = animTick - Math.floor(animTick);
  const rowA  = history[floor]                          ?? history[0];
  const rowB  = history[Math.min(floor + 1, history.length - 1)] ?? rowA;

  const currentRow = lerpRows(rowA, rowB, frac);
  const { critical, warning, avgHealth } = getKpisFromRow(currentRow);

  // Pre-computed full series for charts (stable references — recomputed only when history changes)
  const tempFull  = useMemo(() => history.map(r => r.temperature),   [history]);
  const humidFull = useMemo(() => history.map(r => r.humidity * 100), [history]);

  const allTemps = useMemo(() => MOCK_HISTORY.map(r => r.temperature), []);
  const tempMin  = Math.floor(Math.min(...allTemps) - 1);
  const tempMax  = Math.ceil(Math.max(...allTemps)  + 1);

  const groups = useMemo(() => [
    {
      label: "Recoating",
      rows: [
        { name: "Blade",   full: history.map(r => clamp(r.health_recoating + 0.04)) },
        { name: "Motor",   full: history.map(r => clamp(r.health_recoating + 0.18)) },
        { name: "Rail",    full: history.map(r => clamp(r.health_recoating - 0.06)) },
      ],
    },
    {
      label: "Printhead",
      rows: [
        { name: "Nozzle",    full: history.map(r => clamp(r.health_printhead - 0.04)) },
        { name: "Resistors", full: history.map(r => clamp(r.health_printhead + 0.12)) },
        { name: "Cleaning",  full: history.map(r => clamp(r.health_printhead + 0.02)) },
      ],
    },
    {
      label: "Thermal",
      rows: [
        { name: "Heater",     full: history.map(r => clamp(r.health_thermal + 0.06)) },
        { name: "Sensor",     full: history.map(r => clamp(r.health_thermal + 0.02)) },
        { name: "Insulation", full: history.map(r => clamp(r.health_thermal - 0.03)) },
      ],
    },
  ], [history]);

  // Current health per component (interpolated)
  const curR = currentRow.health_recoating;
  const curP = currentRow.health_printhead;
  const curT = currentRow.health_thermal;
  const compCur: Record<string, Record<string, number>> = {
    Recoating: { Blade: clamp(curR + 0.04), Motor: clamp(curR + 0.18), Rail: clamp(curR - 0.06) },
    Printhead: { Nozzle: clamp(curP - 0.04), Resistors: clamp(curP + 0.12), Cleaning: clamp(curP + 0.02) },
    Thermal:   { Heater: clamp(curT + 0.06), Sensor: clamp(curT + 0.02), Insulation: clamp(curT - 0.03) },
  };

  function handleScrub(nextTick: number) {
    const bounded = Math.max(0, Math.min(nextTick, Math.max(history.length - 1, 0)));
    animTimeRef.current = bounded;
    pausedRef.current = false;
    lastTimeRef.current = null;
    if (pauseTimeout.current) {
      clearTimeout(pauseTimeout.current);
      pauseTimeout.current = null;
    }
    setAnimTick(bounded);
  }

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

            <TimelineControls
              totalTicks={totalTicks}
              animTick={animTick}
              onScrub={handleScrub}
              speed={playbackSpeed}
              onSpeedChange={setPlaybackSpeed}
            />
          </div>
        </BpPanel>

      </div>
    </ScrollArea>
  );
}
