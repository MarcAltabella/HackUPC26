/**
 * Deterministic demo data used when the FastAPI backend is unreachable.
 * All values are pre-computed — no Math.random() — so the UI is stable.
 */

// ── Shared types (mirrors api.py Pydantic schemas) ────────────────────────────

export interface ComponentState {
  health: number;
  status: string;
}

export interface MachineState {
  scenario_id: string;
  run_number: number;
  t: number;
  recoating: {
    subsystem_health: number;
    blade: ComponentState & { thickness_mm: number };
    motor: ComponentState & { vibration_mm_s: number };
    rail:  ComponentState & { deviation_um: number };
  };
  printhead: {
    subsystem_health: number;
    nozzle:   ComponentState & { clog_probability: number };
    resistor: ComponentState & { drift_pct: number };
    cleaning: ComponentState & { efficiency: number };
  };
  thermal: {
    subsystem_health: number;
    heater:     ComponentState & { resistance_ohm: number };
    sensor:     ComponentState & { measurement_error_c: number };
    insulation: ComponentState & { thermal_resistance: number };
  };
}

export interface HistoryRow {
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

// ── Status helper ─────────────────────────────────────────────────────────────

function toStatus(h: number): string {
  if (h > 0.85) return "FUNCTIONAL";
  if (h > 0.70) return "NOMINAL";
  if (h > 0.50) return "WARNING";
  if (h > 0.25) return "DEGRADED";
  if (h > 0.10) return "CRITICAL";
  return "FAILED";
}

// Tiny sine-based deterministic noise (no Math.random)
function wave(t: number, freq: number, amp: number): number {
  return Math.sin(t * freq) * amp;
}

// ── History (100 ticks of a degrading humid_factory-style run) ────────────────

function generateHistory(): HistoryRow[] {
  const rows: HistoryRow[] = [];
  const N = 100;

  for (let t = 0; t < N; t++) {
    const p = t / (N - 1); // 0 → 1

    // Recoating degrades fastest (blade wear + rail deviation from humidity)
    const hr = Math.max(0.18, 0.96 - p * 0.72 + wave(t, 0.55, 0.018));

    // Printhead: moderate degradation with a contamination spike around t=55
    const spike = t > 55 ? (t - 55) * 0.008 : 0;
    const hp = Math.max(0.22, 0.94 - p * 0.45 - spike + wave(t, 0.38, 0.015));

    // Thermal: gentle drift, mostly stable
    const ht = Math.max(0.55, 0.97 - p * 0.28 + wave(t, 0.22, 0.012));

    // Environmental drivers
    const temperature = 22.4 + wave(t, 0.15, 2.8);
    const humidity    = 0.32 + p * 0.41 + wave(t, 0.25, 0.03);

    rows.push({
      t,
      temperature,
      humidity: Math.min(1, humidity),
      health_recoating: hr,
      health_printhead: hp,
      health_thermal:   ht,
      status_blade:  toStatus(hr),
      status_nozzle: toStatus(hp),
      status_heater: toStatus(ht),
    });
  }
  return rows;
}

export const MOCK_HISTORY: HistoryRow[] = generateHistory();

// ── Latest state (snapshot at t = 85, mid-degradation) ───────────────────────

const _t85 = MOCK_HISTORY[85];

export const MOCK_STATE: MachineState = {
  scenario_id: "humid_factory",
  run_number:  3,
  t:           85,

  recoating: {
    subsystem_health: _t85.health_recoating,
    blade: {
      health:       _t85.health_recoating + 0.04,
      status:       toStatus(_t85.health_recoating + 0.04),
      thickness_mm: 0.41,
    },
    motor: {
      health:           Math.min(1, _t85.health_recoating + 0.18),
      status:           toStatus(Math.min(1, _t85.health_recoating + 0.18)),
      vibration_mm_s:   3.7,
    },
    rail: {
      health:       _t85.health_recoating - 0.06,
      status:       toStatus(_t85.health_recoating - 0.06),
      deviation_um: 142,
    },
  },

  printhead: {
    subsystem_health: _t85.health_printhead,
    nozzle: {
      health:           _t85.health_printhead - 0.04,
      status:           toStatus(_t85.health_printhead - 0.04),
      clog_probability: 0.61,
    },
    resistor: {
      health:    Math.min(1, _t85.health_printhead + 0.12),
      status:    toStatus(Math.min(1, _t85.health_printhead + 0.12)),
      drift_pct: 4.2,
    },
    cleaning: {
      health:     _t85.health_printhead + 0.02,
      status:     toStatus(_t85.health_printhead + 0.02),
      efficiency: 0.54,
    },
  },

  thermal: {
    subsystem_health: _t85.health_thermal,
    heater: {
      health:          Math.min(1, _t85.health_thermal + 0.06),
      status:          toStatus(Math.min(1, _t85.health_thermal + 0.06)),
      resistance_ohm:  12.4,
    },
    sensor: {
      health:               Math.min(1, _t85.health_thermal + 0.02),
      status:               toStatus(Math.min(1, _t85.health_thermal + 0.02)),
      measurement_error_c:  0.8,
    },
    insulation: {
      health:            _t85.health_thermal - 0.03,
      status:            toStatus(_t85.health_thermal - 0.03),
      thermal_resistance: 1.82,
    },
  },
};
