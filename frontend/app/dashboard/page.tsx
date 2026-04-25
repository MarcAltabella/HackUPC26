"use client";

import { useEffect, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { MOCK_STATE, MOCK_HISTORY, type MachineState, type HistoryRow } from "@/lib/mock-data";

// ── Constants ─────────────────────────────────────────────────────────────────

const API_BASE = "http://localhost:8000";
const SCENARIO  = "baseline_nominal";
const TICK_MS   = 333;

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
  if (h > 0.7) return "#22c55e";
  if (h > 0.4) return "#eab308";
  if (h > 0.2) return "#f97316";
  return "#ef4444";
}

function segColor(h: number): string {
  if (h > 0.85) return "#166534";
  if (h > 0.70) return "#15803d";
  if (h > 0.50) return "#854d0e";
  if (h > 0.25) return "#9a3412";
  if (h > 0.10) return "#991b1b";
  return "#7f1d1d";
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

// ── KPI Card ──────────────────────────────────────────────────────────────────

function KpiCard({ title, value, sub, accent }: {
  title: string; value: string | number; sub?: string; accent?: string;
}) {
  return (
    <Card>
      <CardContent className="pt-4 pb-3 px-4">
        <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">{title}</p>
        <p className="text-2xl font-mono font-semibold leading-none" style={{ color: accent }}>{value}</p>
        {sub && <p className="text-[10px] text-muted-foreground mt-1">{sub}</p>}
      </CardContent>
    </Card>
  );
}

// ── Line Chart ────────────────────────────────────────────────────────────────
// data: visible slice (grows each tick); totalTicks: full series length (fixed axis)

function LineChart({ data, totalTicks, color, label, unit, yMin, yMax }: {
  data: number[]; totalTicks: number; color: string;
  label: string; unit: string; yMin: number; yMax: number;
}) {
  const W = 900, H = 72, padL = 34, padR = 8, padT = 6, padB = 18;
  const cW = W - padL - padR;
  const cH = H - padT - padB;
  const n = data.length;
  const total = Math.max(totalTicks, 2);

  const px = (i: number) => padL + (i / (total - 1)) * cW;
  const py = (v: number) => padT + (1 - (v - yMin) / (yMax - yMin)) * cH;

  const pts = n > 1 ? data.map((v, i) => `${px(i).toFixed(1)},${py(v).toFixed(1)}`).join(" ") : "";
  const areaPath = n > 1 ? [
    `M${px(0).toFixed(1)},${(padT + cH).toFixed(1)}`,
    ...data.map((v, i) => `L${px(i).toFixed(1)},${py(v).toFixed(1)}`),
    `L${px(n - 1).toFixed(1)},${(padT + cH).toFixed(1)}Z`,
  ].join("") : "";

  const yMid = (yMin + yMax) / 2;
  const xTicks = [0, 0.2, 0.4, 0.6, 0.8, 1].map(p => Math.round(p * (total - 1)));
  const gradId = `lg-${label.replace(/\W/g, "")}`;

  return (
    <div className="space-y-0.5">
      <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
        {label} <span className="font-normal opacity-60 normal-case">{unit}</span>
      </p>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: "72px" }} preserveAspectRatio="none">
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.28" />
            <stop offset="100%" stopColor={color} stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {/* Y gridlines */}
        {[yMin, yMid, yMax].map((v, i) => {
          const y = py(v);
          return (
            <g key={i}>
              <line x1={padL} y1={y} x2={W - padR} y2={y} stroke="rgba(255,255,255,0.06)" strokeWidth="0.7" />
              <text x={padL - 3} y={y + 3.5} textAnchor="end" fill="#666" fontSize="8" fontFamily="ui-monospace,monospace">
                {v.toFixed(0)}
              </text>
            </g>
          );
        })}
        {/* X tick labels (fixed, based on totalTicks) */}
        {xTicks.map(t => (
          <text key={t} x={px(t)} y={H - 2} textAnchor="middle" fill="#666" fontSize="8" fontFamily="ui-monospace,monospace">
            {t}
          </text>
        ))}
        {/* Area fill */}
        {areaPath && <path d={areaPath} fill={`url(#${gradId})`} />}
        {/* Line */}
        {n > 1 && (
          <polyline points={pts} fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />
        )}
        {/* "Now" cursor */}
        {n > 0 && (
          <>
            <line
              x1={px(n - 1)} y1={padT} x2={px(n - 1)} y2={padT + cH}
              stroke={color} strokeWidth="0.8" strokeDasharray="3 2" opacity="0.45"
            />
            <circle cx={px(n - 1)} cy={py(data[n - 1])} r="3" fill={color} />
          </>
        )}
      </svg>
    </div>
  );
}

// ── Degradation Row ───────────────────────────────────────────────────────────
// fullData: pre-computed health for every tick in history
// filledCount: how many ticks are "revealed" so far

function DegradationRow({ label, fullData, filledCount, currentHealth }: {
  label: string; fullData: number[]; filledCount: number; currentHealth: number;
}) {
  return (
    <div className="flex items-center gap-2 text-[10px]">
      <span className="text-muted-foreground w-[72px] shrink-0 text-right">{label}</span>
      <div className="flex-1 flex gap-[1.5px] h-[16px] overflow-hidden rounded-[3px]" style={{ minWidth: 0 }}>
        {fullData.map((h, i) => (
          <div
            key={i}
            className="flex-1 h-full"
            style={{
              background: i < filledCount ? segColor(h) : "rgba(255,255,255,0.04)",
              minWidth: 0,
              transition: "background-color 0.2s ease",
            }}
          />
        ))}
      </div>
      <span className="w-9 shrink-0 font-mono text-right text-[9px]" style={{ color: healthColor(currentHealth) }}>
        {(currentHealth * 100).toFixed(0)}%
      </span>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const [state,    setState]    = useState<MachineState>(MOCK_STATE);
  const [history,  setHistory]  = useState<HistoryRow[]>(MOCK_HISTORY);
  const [loading,  setLoading]  = useState(true);
  const [isDemo,   setIsDemo]   = useState(true);
  const [animTick, setAnimTick] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

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
      } finally {
        if (alive) setLoading(false);
      }
    }
    fetchState();
    const id = setInterval(fetchState, 5_000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  // History fetch
  useEffect(() => {
    fetch(`${API_BASE}/api/runs/${SCENARIO}/history?start_t=0&end_t=999`)
      .then(r => r.ok ? r.json() : Promise.reject())
      .then((rows: HistoryRow[]) => { setHistory(rows); setIsDemo(false); })
      .catch(() => setHistory(MOCK_HISTORY));
  }, []);

  // Animation loop: tick 0 → N-1, then pause 1.5 s and restart
  useEffect(() => {
    if (history.length === 0) return;
    const total = history.length;
    let tick = 0;
    let paused = false;

    setAnimTick(0);
    if (intervalRef.current) clearInterval(intervalRef.current);

    intervalRef.current = setInterval(() => {
      if (paused) return;
      tick += 1;
      if (tick >= total) {
        setAnimTick(total - 1);
        paused = true;
        setTimeout(() => { tick = 0; setAnimTick(0); paused = false; }, 1500);
      } else {
        setAnimTick(tick);
      }
    }, TICK_MS);

    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [history]);

  // ── Derived values ──────────────────────────────────────────────────────────

  const totalTicks  = history.length || 1;
  const filledCount = animTick + 1;
  const currentRow  = history[animTick] ?? history[0];

  const { critical, warning, avgHealth } = currentRow
    ? getKpisFromRow(currentRow)
    : { critical: 0, warning: 0, avgHealth: 1 };

  // Visible slice for line charts
  const visibleHistory = history.slice(0, filledCount);
  const tempData  = visibleHistory.map(r => r.temperature);
  const humidData = visibleHistory.map(r => r.humidity * 100);

  // Y range fixed from full dataset so the axis doesn't jump
  const allTemps = MOCK_HISTORY.map(r => r.temperature);
  const tempMin  = Math.floor(Math.min(...allTemps) - 1);
  const tempMax  = Math.ceil(Math.max(...allTemps) + 1);

  // Full health arrays pre-computed from the complete history (for degradation rows)
  const groups = [
    {
      label: "Recoating",
      rows: [
        { name: "Blade",   full: history.map(r => clamp(r.health_recoating + 0.04)), cur: clamp((currentRow?.health_recoating ?? 1) + 0.04) },
        { name: "Motor",   full: history.map(r => clamp(r.health_recoating + 0.18)), cur: clamp((currentRow?.health_recoating ?? 1) + 0.18) },
        { name: "Rail",    full: history.map(r => clamp(r.health_recoating - 0.06)), cur: clamp((currentRow?.health_recoating ?? 1) - 0.06) },
      ],
    },
    {
      label: "Printhead",
      rows: [
        { name: "Nozzle",    full: history.map(r => clamp(r.health_printhead - 0.04)), cur: clamp((currentRow?.health_printhead ?? 1) - 0.04) },
        { name: "Resistors", full: history.map(r => clamp(r.health_printhead + 0.12)), cur: clamp((currentRow?.health_printhead ?? 1) + 0.12) },
        { name: "Cleaning",  full: history.map(r => clamp(r.health_printhead + 0.02)), cur: clamp((currentRow?.health_printhead ?? 1) + 0.02) },
      ],
    },
    {
      label: "Thermal",
      rows: [
        { name: "Heater",     full: history.map(r => clamp(r.health_thermal + 0.06)), cur: clamp((currentRow?.health_thermal ?? 1) + 0.06) },
        { name: "Sensor",     full: history.map(r => clamp(r.health_thermal + 0.02)), cur: clamp((currentRow?.health_thermal ?? 1) + 0.02) },
        { name: "Insulation", full: history.map(r => clamp(r.health_thermal - 0.03)), cur: clamp((currentRow?.health_thermal ?? 1) - 0.03) },
      ],
    },
  ];

  return (
    <ScrollArea className="h-full">
      <div className="p-4 space-y-4 max-w-6xl mx-auto">

        {/* Demo banner */}
        {isDemo && !loading && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground bg-muted/40 border border-border rounded-md px-3 py-2">
            <span className="h-1.5 w-1.5 rounded-full bg-yellow-400 shrink-0" />
            <span>
              <span className="font-semibold text-foreground">Demo mode</span> — showing synthetic data.
              Start the backend (<code className="font-mono">uvicorn api:app --reload --port 8000</code>) to switch to live data.
            </span>
          </div>
        )}

        {/* KPI row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <KpiCard
            title="Active Alerts"
            value={critical + warning}
            sub={`${critical} critical · ${warning} warning`}
            accent={critical > 0 ? "#ef4444" : warning > 0 ? "#eab308" : "#22c55e"}
          />
          <KpiCard
            title="Critical Components"
            value={critical}
            accent={critical > 0 ? "#ef4444" : undefined}
          />
          <KpiCard
            title="Avg Subsystem Health"
            value={`${(avgHealth * 100).toFixed(1)}%`}
            accent={healthColor(avgHealth)}
          />
          <KpiCard
            title="Simulation Tick"
            value={animTick}
            sub={`${state.scenario_id} · run ${state.run_number}`}
          />
        </div>

        {/* Input Drivers */}
        <Card>
          <CardHeader className="py-3 px-4">
            <CardTitle className="text-xs font-semibold">Input Drivers</CardTitle>
          </CardHeader>
          <Separator />
          <CardContent className="pt-3 pb-4 px-4 space-y-5">
            <LineChart
              data={tempData}
              totalTicks={totalTicks}
              color="#f97316"
              label="Temperature"
              unit="°C"
              yMin={tempMin}
              yMax={tempMax}
            />
            <LineChart
              data={humidData}
              totalTicks={totalTicks}
              color="#38bdf8"
              label="Humidity"
              unit="%"
              yMin={0}
              yMax={100}
            />
          </CardContent>
        </Card>

        {/* Component Degradation Timeline */}
        <Card>
          <CardHeader className="py-3 px-4">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <CardTitle className="text-xs font-semibold">Component Degradation</CardTitle>
              <div className="flex items-center gap-3 text-[9px] text-muted-foreground">
                {[
                  { color: "#166534", label: "Functional" },
                  { color: "#854d0e", label: "Warning" },
                  { color: "#9a3412", label: "Degraded" },
                  { color: "#991b1b", label: "Critical" },
                ].map(({ color, label }) => (
                  <span key={label} className="flex items-center gap-1">
                    <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: color }} />
                    {label}
                  </span>
                ))}
              </div>
            </div>
          </CardHeader>
          <Separator />
          <CardContent className="pt-3 pb-4 px-4 space-y-4">

            {/* Tick ruler */}
            <div className="flex text-[9px] text-muted-foreground font-mono" style={{ paddingLeft: "80px", paddingRight: "44px" }}>
              {[0, 0.2, 0.4, 0.6, 0.8, 1].map(p => (
                <span key={p} className="flex-1 text-center first:text-left last:text-right">
                  {Math.round(p * (totalTicks - 1))}
                </span>
              ))}
            </div>

            {groups.map(({ label, rows }) => (
              <div key={label} className="space-y-1.5">
                <p className="text-[9px] font-semibold text-muted-foreground/60 uppercase tracking-widest">{label}</p>
                {rows.map(({ name, full, cur }) => (
                  <DegradationRow
                    key={name}
                    label={name}
                    fullData={full}
                    filledCount={filledCount}
                    currentHealth={cur}
                  />
                ))}
              </div>
            ))}

            {/* Footer */}
            <div
              className="flex text-[9px] text-muted-foreground font-mono border-t border-border/40 pt-2"
              style={{ paddingLeft: "80px", paddingRight: "44px" }}
            >
              <span>t = 0</span>
              <span className="flex-1 text-center opacity-50">← simulation tick →</span>
              <span>t = {totalTicks - 1}</span>
            </div>
          </CardContent>
        </Card>

      </div>
    </ScrollArea>
  );
}
