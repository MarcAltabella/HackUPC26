import type { ChatResponse, HistoryRow, MachineState } from "@/lib/api-types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { signal });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export function getTimeline(
  scenarioId: string,
  runNumber = 0,
  startT = 0,
  endT = 999,
  signal?: AbortSignal,
) {
  return getJson<MachineState[]>(
    `/api/runs/${scenarioId}/timeline?run_number=${runNumber}&start_t=${startT}&end_t=${endT}`,
    signal,
  );
}

export function getHistory(
  scenarioId: string,
  runNumber = 0,
  startT = 0,
  endT = 999,
  signal?: AbortSignal,
) {
  return getJson<HistoryRow[]>(
    `/api/runs/${scenarioId}/history?run_number=${runNumber}&start_t=${startT}&end_t=${endT}`,
    signal,
  );
}

export function getLatestState(scenarioId: string, runNumber = 0, signal?: AbortSignal) {
  return getJson<MachineState>(
    `/api/runs/${scenarioId}/state/latest?run_number=${runNumber}`,
    signal,
  );
}

export function getStateAt(scenarioId: string, runNumber: number, t: number, signal?: AbortSignal) {
  return getJson<MachineState>(
    `/api/runs/${scenarioId}/state/at/${t}?run_number=${runNumber}`,
    signal,
  );
}

export async function askCopilot(params: {
  message: string;
  scenarioId: string;
  runNumber?: number;
  t?: number;
}) {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: params.message,
      scenario_id: params.scenarioId,
      run_number: params.runNumber ?? 0,
      t: params.t,
    }),
  });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<ChatResponse>;
}
