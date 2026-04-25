"use client";

import { useEffect, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
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

function statusVariant(s: string): "destructive" | "outline" | "secondary" {
  if (s === "FAILED" || s === "CRITICAL") return "destructive";
  if (s === "WARNING" || s === "DEGRADED") return "outline";
  return "secondary";
}

function StatusCell({ status }: { status: string }) {
  const isNominal = status === "FUNCTIONAL" || status === "NOMINAL" || status === "OK";
  if (isNominal) {
    return <span className="text-muted-foreground/50 font-mono text-[10px]">{status}</span>;
  }
  return (
    <Badge variant={statusVariant(status)} className="text-[10px] h-4 px-1.5">
      {status}
    </Badge>
  );
}

// ── Filter row ────────────────────────────────────────────────────────────────

interface Filters {
  scenario: string;
  runNumber: number;
  startT: number;
  endT: number;
  statusFilter: string; // "all" | "warnings" | "critical"
}

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

  // Draft values for the filter inputs (applied on "Apply")
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

  // Client-side status filter
  const filtered = rows.filter(row => {
    if (filters.statusFilter === "all") return true;
    const statuses = [row.status_blade, row.status_nozzle, row.status_heater];
    if (filters.statusFilter === "critical")
      return statuses.some(s => s === "FAILED" || s === "CRITICAL");
    if (filters.statusFilter === "warnings")
      return statuses.some(s => s === "WARNING" || s === "DEGRADED" || s === "FAILED" || s === "CRITICAL");
    return true;
  });

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const pageRows   = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div className="h-full flex flex-col gap-0 overflow-hidden">

      {/* Filter bar */}
      <div className="px-4 py-2.5 border-b border-border bg-background shrink-0 flex flex-wrap items-end gap-3">

        <FilterGroup label="Scenario">
          <select
            value={draft.scenario}
            onChange={e => setDraft(d => ({ ...d, scenario: e.target.value }))}
            className="bg-muted border border-border rounded-md px-2 py-1 text-xs text-foreground focus:outline-none"
          >
            {SCENARIOS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </FilterGroup>

        <FilterGroup label="Run #">
          <input
            type="number"
            min={0}
            max={19}
            value={draft.runNumber}
            onChange={e => setDraft(d => ({ ...d, runNumber: Number(e.target.value) }))}
            className="w-14 bg-muted border border-border rounded-md px-2 py-1 text-xs text-foreground focus:outline-none"
          />
        </FilterGroup>

        <FilterGroup label="Tick range">
          <div className="flex items-center gap-1">
            <input
              type="number"
              min={0}
              value={draft.startT}
              onChange={e => setDraft(d => ({ ...d, startT: Number(e.target.value) }))}
              className="w-16 bg-muted border border-border rounded-md px-2 py-1 text-xs text-foreground focus:outline-none"
              placeholder="0"
            />
            <span className="text-muted-foreground text-xs">–</span>
            <input
              type="number"
              min={0}
              value={draft.endT}
              onChange={e => setDraft(d => ({ ...d, endT: Number(e.target.value) }))}
              className="w-16 bg-muted border border-border rounded-md px-2 py-1 text-xs text-foreground focus:outline-none"
              placeholder="999"
            />
          </div>
        </FilterGroup>

        <FilterGroup label="Status">
          <select
            value={draft.statusFilter}
            onChange={e => setDraft(d => ({ ...d, statusFilter: e.target.value }))}
            className="bg-muted border border-border rounded-md px-2 py-1 text-xs text-foreground focus:outline-none"
          >
            <option value="all">All rows</option>
            <option value="warnings">Warnings &amp; above</option>
            <option value="critical">Critical only</option>
          </select>
        </FilterGroup>

        <Button size="sm" onClick={applyFilters} className="text-xs h-7 px-3">
          Apply
        </Button>

        <span className="text-[10px] text-muted-foreground ml-auto self-center">
          {loading ? "Loading…" : `${filtered.length} rows`}
        </span>
      </div>

      {/* Demo / error banner */}
      {isDemo && !error && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground bg-muted/40 border-b border-border px-4 py-2 shrink-0">
          <span className="h-1.5 w-1.5 rounded-full bg-yellow-400 shrink-0" />
          <span>
            <span className="font-semibold text-foreground">Demo mode</span> — showing synthetic data.
            Start the backend (<code className="font-mono">uvicorn api:app --reload --port 8000</code>) to switch to live data.
          </span>
        </div>
      )}
      {error && (
        <p className="text-xs text-destructive px-4 py-2 bg-destructive/10 shrink-0">{error}</p>
      )}

      {/* Table */}
      <Card className="flex-1 min-h-0 rounded-none border-x-0 border-b-0">
        <ScrollArea className="h-full">
          <table className="w-full text-xs min-w-[700px]">
            <thead className="sticky top-0 bg-background z-10">
              <tr className="border-b border-border">
                {["t", "Temp °C", "Humidity", "Recoating", "Printhead", "Thermal", "Blade status", "Nozzle status", "Heater status"].map(h => (
                  <th
                    key={h}
                    className="text-left px-3 py-2 text-[10px] font-semibold text-muted-foreground uppercase tracking-wide whitespace-nowrap"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {!loading && pageRows.length === 0 && (
                <tr>
                  <td colSpan={9} className="text-center text-muted-foreground py-8">
                    No rows match the current filters.
                  </td>
                </tr>
              )}
              {pageRows.map(row => (
                <tr
                  key={row.t}
                  className="border-b border-border/40 hover:bg-muted/20 transition-colors"
                >
                  <td className="px-3 py-1.5 font-mono font-semibold">{row.t}</td>
                  <td className="px-3 py-1.5 font-mono text-muted-foreground">{row.temperature.toFixed(1)}</td>
                  <td className="px-3 py-1.5 font-mono text-muted-foreground">{(row.humidity * 100).toFixed(0)}%</td>
                  <td className="px-3 py-1.5 font-mono" style={{ color: healthColor(row.health_recoating) }}>
                    {(row.health_recoating * 100).toFixed(1)}%
                  </td>
                  <td className="px-3 py-1.5 font-mono" style={{ color: healthColor(row.health_printhead) }}>
                    {(row.health_printhead * 100).toFixed(1)}%
                  </td>
                  <td className="px-3 py-1.5 font-mono" style={{ color: healthColor(row.health_thermal) }}>
                    {(row.health_thermal * 100).toFixed(1)}%
                  </td>
                  <td className="px-3 py-1.5"><StatusCell status={row.status_blade} /></td>
                  <td className="px-3 py-1.5"><StatusCell status={row.status_nozzle} /></td>
                  <td className="px-3 py-1.5"><StatusCell status={row.status_heater} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollArea>
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="shrink-0 flex items-center justify-between px-4 py-2 border-t border-border text-xs text-muted-foreground bg-background">
          <span>
            Page {page + 1} of {totalPages} · {filtered.length} rows
          </span>
          <div className="flex gap-1">
            <Button
              size="sm"
              variant="outline"
              className="h-6 px-2 text-xs"
              disabled={page === 0}
              onClick={() => setPage(p => p - 1)}
            >
              ← Prev
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-6 px-2 text-xs"
              disabled={page >= totalPages - 1}
              onClick={() => setPage(p => p + 1)}
            >
              Next →
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Small helper component ────────────────────────────────────────────────────

function FilterGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] text-muted-foreground font-medium uppercase tracking-wide">{label}</span>
      {children}
    </div>
  );
}
