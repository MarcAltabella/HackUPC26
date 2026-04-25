"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { MOCK_HISTORY } from "@/lib/mock-data";

// ── Types ─────────────────────────────────────────────────────────────────────

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

// Per-component health offsets from subsystem base
const COMP_OFFSETS = {
  blade:      { sub: "health_recoating" as const, d: +0.04 },
  motor:      { sub: "health_recoating" as const, d: +0.18 },
  rail:       { sub: "health_recoating" as const, d: -0.06 },
  nozzle:     { sub: "health_printhead" as const, d: -0.04 },
  resistors:  { sub: "health_printhead" as const, d: +0.12 },
  cleaning:   { sub: "health_printhead" as const, d: +0.02 },
  heater:     { sub: "health_thermal"   as const, d: +0.06 },
  sensor:     { sub: "health_thermal"   as const, d: +0.02 },
  insulation: { sub: "health_thermal"   as const, d: -0.03 },
} as const;

type CompKey = keyof typeof COMP_OFFSETS;

function compHealth(row: HistoryRow, comp: CompKey): number {
  const { sub, d } = COMP_OFFSETS[comp];
  return Math.max(0, Math.min(1, row[sub] + d));
}

function allCompHealths(row: HistoryRow): number[] {
  return (Object.keys(COMP_OFFSETS) as CompKey[]).map(k => compHealth(row, k));
}

// ── Constants ─────────────────────────────────────────────────────────────────

const API_BASE  = "http://localhost:8000";
const SCENARIO  = "baseline_nominal";
const PAGE_SIZE = 50;

const SCENARIOS = [
  "baseline_nominal",
  "humid_factory",
  "chaos_run",
  "no_maintenance",
  "fixed_schedule",
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function healthColor(h: number): string {
  if (h > 0.7) return "#22c55e";
  if (h > 0.4) return "#eab308";
  if (h > 0.2) return "#f97316";
  return "#ef4444";
}

function HealthCell({ value }: { value: number }) {
  return (
    <td className="px-2 py-1.5 font-mono tabular-nums text-right" style={{ color: healthColor(value) }}>
      {(value * 100).toFixed(1)}%
    </td>
  );
}

// ── Filter bar ────────────────────────────────────────────────────────────────

interface Filters {
  scenario: string;
  runNumber: number;
  startT: number;
  endT: number;
  statusFilter: string;
}

function FilterGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] text-muted-foreground font-mono uppercase tracking-[0.18em]">{label}</span>
      {children}
    </div>
  );
}

const inputCls =
  "bg-card border border-border rounded px-2 py-1 text-xs font-mono text-foreground focus:outline-none focus:border-primary/60 transition-colors";

// ── Page ──────────────────────────────────────────────────────────────────────

export default function LogsPage() {
  const [rows,    setRows]    = useState<HistoryRow[]>(MOCK_HISTORY);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);
  const [page,    setPage]    = useState(0);
  const [isDemo,  setIsDemo]  = useState(true);

  const [filters, setFilters] = useState<Filters>({
    scenario:     SCENARIO,
    runNumber:    0,
    startT:       0,
    endT:         999,
    statusFilter: "all",
  });

  const [draft, setDraft] = useState(filters);
  const abortRef = useRef<AbortController | null>(null);

  function applyFilters() {
    setFilters(draft);
    setPage(0);
  }

  useEffect(() => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);

    fetch(
      `${API_BASE}/api/runs/${filters.scenario}/history` +
      `?run_number=${filters.runNumber}&start_t=${filters.startT}&end_t=${filters.endT}`,
      { signal: ctrl.signal }
    )
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: HistoryRow[]) => {
        if (!ctrl.signal.aborted) { setRows(data); setIsDemo(false); setError(null); }
      })
      .catch(e => {
        if (e.name !== "AbortError") { setRows(MOCK_HISTORY); setIsDemo(true); }
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
  }, [filters]);

  const filtered = rows.filter(row => {
    if (filters.statusFilter === "all") return true;
    const healths = allCompHealths(row);
    if (filters.statusFilter === "critical")
      return healths.some(h => h <= 0.25);
    if (filters.statusFilter === "warnings")
      return healths.some(h => h <= 0.50);
    return true;
  });

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const pageRows   = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div className="h-full flex flex-col gap-0 overflow-hidden bg-background">

      {/* ── Filter bar ── */}
      <div className="px-4 py-2.5 border-b border-border bg-card shrink-0 flex flex-wrap items-end gap-3">

        <FilterGroup label="Scenario">
          <select
            value={draft.scenario}
            onChange={e => setDraft(d => ({ ...d, scenario: e.target.value }))}
            className={inputCls}
          >
            {SCENARIOS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </FilterGroup>

        <FilterGroup label="Run #">
          <input
            type="number" min={0} max={19}
            value={draft.runNumber}
            onChange={e => setDraft(d => ({ ...d, runNumber: Number(e.target.value) }))}
            className={`w-14 ${inputCls}`}
          />
        </FilterGroup>

        <FilterGroup label="Tick range">
          <div className="flex items-center gap-1">
            <input
              type="number" min={0}
              value={draft.startT}
              onChange={e => setDraft(d => ({ ...d, startT: Number(e.target.value) }))}
              className={`w-16 ${inputCls}`} placeholder="0"
            />
            <span className="text-muted-foreground text-xs font-mono">–</span>
            <input
              type="number" min={0}
              value={draft.endT}
              onChange={e => setDraft(d => ({ ...d, endT: Number(e.target.value) }))}
              className={`w-16 ${inputCls}`} placeholder="999"
            />
          </div>
        </FilterGroup>

        <FilterGroup label="Status">
          <select
            value={draft.statusFilter}
            onChange={e => setDraft(d => ({ ...d, statusFilter: e.target.value }))}
            className={inputCls}
          >
            <option value="all">All rows</option>
            <option value="warnings">Warnings &amp; above</option>
            <option value="critical">Critical only</option>
          </select>
        </FilterGroup>

        <Button size="sm" onClick={applyFilters} className="text-xs h-7 px-3 font-mono tracking-wider">
          APPLY
        </Button>

        <span className="text-[10px] font-mono text-muted-foreground ml-auto self-center">
          {loading ? "LOADING…" : `${filtered.length} ROWS`}
        </span>
      </div>

      {/* ── Demo / error banner ── */}
      {isDemo && !error && (
        <div className="flex items-center gap-2 text-xs font-mono text-yellow-400/80 bg-yellow-400/5 border-b border-yellow-400/20 px-4 py-1.5 shrink-0">
          <span className="h-1.5 w-1.5 rounded-full bg-yellow-400 shrink-0" />
          <span>
            ⚠ DEMO_MODE — synthetic data · start backend
            (<code className="text-yellow-300/70">uvicorn api:app --reload --port 8000</code>) to load live telemetry
          </span>
        </div>
      )}
      {error && (
        <p className="text-xs font-mono text-destructive px-4 py-1.5 bg-destructive/10 border-b border-destructive/20 shrink-0">{error}</p>
      )}

      {/* ── Table ── */}
      <div className="flex-1 min-h-0 overflow-hidden">
        <ScrollArea className="h-full">
          <table className="w-full text-xs" style={{ minWidth: 1040 }}>
            <thead className="sticky top-0 z-10 bg-background">
              {/* Row 1 — subsystem group headers */}
              <tr className="border-b border-border/60">
                <th className="px-3 py-1.5 text-left font-mono text-[10px] text-muted-foreground tracking-[0.22em] uppercase" rowSpan={2}>T</th>
                <th className="px-3 py-1.5 text-left font-mono text-[10px] text-muted-foreground tracking-[0.22em] uppercase" rowSpan={2}>TEMP °C</th>
                <th className="px-3 py-1.5 text-left font-mono text-[10px] text-muted-foreground tracking-[0.22em] uppercase" rowSpan={2}>HUMID</th>
                <th
                  colSpan={3}
                  className="px-3 py-1 text-center font-mono text-[10px] tracking-[0.22em] uppercase border-l border-border/60"
                  style={{ color: "oklch(0.72 0.19 210)" }}
                >
                  ▸ RECOATING
                </th>
                <th
                  colSpan={3}
                  className="px-3 py-1 text-center font-mono text-[10px] tracking-[0.22em] uppercase border-l border-border/60"
                  style={{ color: "oklch(0.72 0.19 210)" }}
                >
                  ▸ PRINTHEAD
                </th>
                <th
                  colSpan={3}
                  className="px-3 py-1 text-center font-mono text-[10px] tracking-[0.22em] uppercase border-l border-border/60"
                  style={{ color: "oklch(0.72 0.19 210)" }}
                >
                  ▸ THERMAL
                </th>
              </tr>
              {/* Row 2 — component sub-headers */}
              <tr className="border-b border-border">
                {/* Recoating */}
                <th className="px-2 py-1 text-right font-mono text-[9px] text-muted-foreground/70 tracking-wider uppercase border-l border-border/60">BLADE</th>
                <th className="px-2 py-1 text-right font-mono text-[9px] text-muted-foreground/70 tracking-wider uppercase">MOTOR</th>
                <th className="px-2 py-1 text-right font-mono text-[9px] text-muted-foreground/70 tracking-wider uppercase">RAIL</th>
                {/* Printhead */}
                <th className="px-2 py-1 text-right font-mono text-[9px] text-muted-foreground/70 tracking-wider uppercase border-l border-border/60">NOZZLE</th>
                <th className="px-2 py-1 text-right font-mono text-[9px] text-muted-foreground/70 tracking-wider uppercase">RESIST</th>
                <th className="px-2 py-1 text-right font-mono text-[9px] text-muted-foreground/70 tracking-wider uppercase">CLEAN</th>
                {/* Thermal */}
                <th className="px-2 py-1 text-right font-mono text-[9px] text-muted-foreground/70 tracking-wider uppercase border-l border-border/60">HEATER</th>
                <th className="px-2 py-1 text-right font-mono text-[9px] text-muted-foreground/70 tracking-wider uppercase">SENSOR</th>
                <th className="px-2 py-1 text-right font-mono text-[9px] text-muted-foreground/70 tracking-wider uppercase">INSUL</th>
              </tr>
            </thead>
            <tbody>
              {!loading && pageRows.length === 0 && (
                <tr>
                  <td colSpan={12} className="text-center text-muted-foreground font-mono text-xs py-10">
                    NO ROWS MATCH CURRENT FILTERS
                  </td>
                </tr>
              )}
              {pageRows.map(row => {
                const bl  = compHealth(row, "blade");
                const mo  = compHealth(row, "motor");
                const ra  = compHealth(row, "rail");
                const no  = compHealth(row, "nozzle");
                const re  = compHealth(row, "resistors");
                const cl  = compHealth(row, "cleaning");
                const he  = compHealth(row, "heater");
                const se  = compHealth(row, "sensor");
                const ins = compHealth(row, "insulation");

                const rowMin = Math.min(bl, mo, ra, no, re, cl, he, se, ins);
                const rowWarn = rowMin <= 0.50;
                const rowCrit = rowMin <= 0.25;

                return (
                  <tr
                    key={row.t}
                    className={[
                      "border-b border-border/30 transition-colors",
                      rowCrit  ? "bg-red-500/5 hover:bg-red-500/10" :
                      rowWarn  ? "bg-yellow-400/5 hover:bg-yellow-400/10" :
                                 "hover:bg-muted/20",
                    ].join(" ")}
                  >
                    <td className="px-3 py-1.5 font-mono font-bold tabular-nums text-primary">{row.t}</td>
                    <td className="px-3 py-1.5 font-mono tabular-nums text-muted-foreground">{row.temperature.toFixed(1)}</td>
                    <td className="px-3 py-1.5 font-mono tabular-nums text-muted-foreground">{(row.humidity * 100).toFixed(0)}%</td>

                    {/* Recoating group */}
                    <HealthCell value={bl} />
                    <HealthCell value={mo} />
                    <HealthCell value={ra} />

                    {/* Printhead group */}
                    <HealthCell value={no} />
                    <HealthCell value={re} />
                    <HealthCell value={cl} />

                    {/* Thermal group */}
                    <HealthCell value={he} />
                    <HealthCell value={se} />
                    <HealthCell value={ins} />
                  </tr>
                );
              })}
            </tbody>
          </table>
        </ScrollArea>
      </div>

      {/* ── Pagination ── */}
      {totalPages > 1 && (
        <div className="shrink-0 flex items-center justify-between px-4 py-2 border-t border-border text-[10px] font-mono text-muted-foreground bg-card">
          <span className="tracking-wider">
            PAGE {page + 1} / {totalPages} · {filtered.length} ROWS
          </span>
          <div className="flex gap-1">
            <Button
              size="sm" variant="outline"
              className="h-6 px-2 text-xs font-mono"
              disabled={page === 0}
              onClick={() => setPage(p => p - 1)}
            >
              ← PREV
            </Button>
            <Button
              size="sm" variant="outline"
              className="h-6 px-2 text-xs font-mono"
              disabled={page >= totalPages - 1}
              onClick={() => setPage(p => p + 1)}
            >
              NEXT →
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
