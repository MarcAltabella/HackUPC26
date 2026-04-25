"""
Dataset generator — Stage 1 neural-network training data.

Milestone 1 (context_stage_2.md §Implementation milestones):
  1.1  SimulationConfig and scenario / run identifiers
  1.2  Clock loop and time-step progression
  1.3  Deterministic driver generation
  1.4  Stochastic and chaos driver generation
  1.5  Implementation log (every driver profile, threshold, assumption logged)

Nine components modeled (stage-1.md §1.2):

  Recoating subsystem
    blade       – Recoater Blade        – Abrasive Wear  (Exponential Decay)
    motor       – Recoater Drive Motor  – Mechanical Fatigue (Weibull β=3)
    rail        – Linear Guide / Rail   – Mechanical Fatigue (Linear)

  Printhead subsystem
    nozzle      – Nozzle Plate          – Clogging + Thermal Fatigue (Weibull β=2.5)
    resistor    – Thermal Firing Res.   – Electrical Degradation (Arrhenius-style)
    cleaning    – Cleaning Interface    – Usage Wear (Linear)

  Thermal subsystem
    heater      – Heating Elements      – Electrical Degradation (Linear + Thermal)
    sensor      – Temperature Sensors   – Calibration Drift (Linear)
    insulation  – Insulation Panels     – Thermal Degradation (Linear, slow)

Cascading effects (previous-tick state to avoid circularity):
  blade health  → nozzle degradation rate   (bad blade = more powder contamination)
  motor health  → rail degradation rate     (vibration from worn motor)
  cleaning hlth → nozzle degradation rate   (poor cleaning = faster clogging)
  insul. health → heater degradation rate   (bad insulation = thermal overload)
  sensor health → heater degradation rate   (sensor drift = inaccurate control)

Persistence:
  PRIMARY  – SQLite  (data/simulation.db,   table simulation_log)
  FALLBACK – CSV     (data/training_dataset.csv)

Output also writes logs/implementation_log.md  (Milestone 1.5).
"""
from __future__ import annotations

import csv
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, NamedTuple

import numpy as np

# ══════════════════════════════════════════════════════════════
# 1.1  SimulationConfig and scenario identifiers
# ══════════════════════════════════════════════════════════════

EnvProfile = Literal["deterministic", "stochastic", "chaos"]


@dataclass
class SimulationConfig:
    scenario_id: str
    env_profile: EnvProfile
    total_steps: int = 1_000
    time_step_hours: float = 1.0
    chaos_prob: float = 0.02
    maintenance_schedule: str = "light"   # "none" | "light" | "fixed_100" | "full"


# Fixed seed offsets guarantee reproducibility across Python runs (hash() is not stable)
_SCENARIO_SEED: dict[str, int] = {
    "baseline_nominal": 0,
    "humid_factory":    1_000_000,
    "chaos_run":        2_000_000,
    "no_maintenance":   3_000_000,
    "fixed_schedule":   4_000_000,
}

SCENARIOS: list[SimulationConfig] = [
    SimulationConfig("baseline_nominal", "deterministic", chaos_prob=0.00, maintenance_schedule="light"),
    SimulationConfig("humid_factory",    "stochastic",    chaos_prob=0.01, maintenance_schedule="light"),
    SimulationConfig("chaos_run",        "chaos",         chaos_prob=0.05, maintenance_schedule="light"),
    SimulationConfig("no_maintenance",   "deterministic", chaos_prob=0.00, maintenance_schedule="none"),
    SimulationConfig("fixed_schedule",   "deterministic", chaos_prob=0.00, maintenance_schedule="fixed_100"),
]

RUNS_PER_SCENARIO = 20   # different seeds → diverse degradation trajectories

# ══════════════════════════════════════════════════════════════
# 1.2  Clock helpers
# ══════════════════════════════════════════════════════════════


class Drivers(NamedTuple):
    temperature: float        # °C  [15, 70]
    humidity: float           # [0.0, 1.0] — also proxy for contamination
    load: float               # cumulative simulated hours
    maintenance_level: float  # [0.0, 1.0]
    is_shock: bool


def _maintenance_level(schedule: str, t: int) -> float:
    if schedule == "none":
        return 0.0
    if schedule == "full":
        return 1.0
    if schedule == "fixed_100":
        return 1.0 if t % 100 == 0 else 0.0
    return 0.5 if t % 200 == 0 else 0.0   # "light"


# ══════════════════════════════════════════════════════════════
# 1.3  Deterministic driver generation
# ══════════════════════════════════════════════════════════════


def deterministic_drivers(t: int, cfg: SimulationConfig) -> Drivers:
    progress = t / cfg.total_steps
    return Drivers(
        temperature=20.0 + progress * 30.0,   # 20 °C → 50 °C linear ramp
        humidity=0.40,
        load=t * cfg.time_step_hours,
        maintenance_level=_maintenance_level(cfg.maintenance_schedule, t),
        is_shock=False,
    )


# ══════════════════════════════════════════════════════════════
# 1.4  Stochastic and chaos driver generation
# ══════════════════════════════════════════════════════════════


def stochastic_drivers(t: int, cfg: SimulationConfig, rng: np.random.Generator) -> Drivers:
    progress = t / cfg.total_steps
    temp = float(np.clip(20.0 + progress * 30.0 + rng.normal(0, 2.0), 15, 70))
    hum = float(np.clip(0.40 + rng.normal(0, 0.05), 0.0, 1.0))
    shock = bool(rng.random() < cfg.chaos_prob)
    if shock:
        hum = min(1.0, hum + 0.25)
    return Drivers(temp, hum, t * cfg.time_step_hours,
                   _maintenance_level(cfg.maintenance_schedule, t), shock)


def chaos_drivers(t: int, cfg: SimulationConfig, rng: np.random.Generator) -> Drivers:
    progress = t / cfg.total_steps
    temp = float(np.clip(20.0 + progress * 30.0 + rng.normal(0, 3.0), 15, 70))
    hum = float(np.clip(0.40 + rng.normal(0, 0.07), 0.0, 1.0))
    shock = bool(rng.random() < cfg.chaos_prob)
    if shock:
        if rng.random() < 0.5:
            hum = min(1.0, hum + float(rng.uniform(0.20, 0.50)))   # contamination burst
        else:
            temp = min(70.0, temp + float(rng.uniform(10, 25)))     # thermal spike
    return Drivers(temp, hum, t * cfg.time_step_hours,
                   _maintenance_level(cfg.maintenance_schedule, t), shock)


def sample_drivers(t: int, cfg: SimulationConfig, rng: np.random.Generator) -> Drivers:
    if cfg.env_profile == "deterministic":
        return deterministic_drivers(t, cfg)
    if cfg.env_profile == "stochastic":
        return stochastic_drivers(t, cfg, rng)
    return chaos_drivers(t, cfg, rng)


# ══════════════════════════════════════════════════════════════
# Phase 1 constants  (calibrated for ~1 000-tick lifetime at baseline)
# ══════════════════════════════════════════════════════════════

# ── Recoater Blade  (Exponential Decay) ──────────────────────
BLADE_INIT_MM   = 2.00    # initial thickness (mm)
BLADE_FAIL_MM   = 0.30    # failure threshold (mm)
BLADE_BASE_WEAR = 2.0e-3  # fractional wear per tick (no stress)
BLADE_HUM_COEF  = 0.80    # contamination amplifies wear
BLADE_RCVR      = 0.25    # mm restored per unit maintenance_level
# Expected failure (no maint, baseline): ~700 ticks

# ── Recoater Drive Motor  (Weibull β=3) ──────────────────────
MOTOR_BASE_RATE = 9.5e-4  # Weibull age added per tick (no load stress)
MOTOR_LOAD_COEF = 0.30    # load fraction amplifies wear
MOTOR_ETA       = 0.75    # Weibull scale η
MOTOR_BETA      = 3.0     # Weibull shape β (wear-out)
MOTOR_V_NOMINAL = 1.0     # mm/s vibration at new condition
MOTOR_V_MAX     = 12.0    # mm/s vibration at failure
MOTOR_RCVR      = 0.06    # Weibull age removed per unit maint.
# Expected failure: ~800 ticks

# ── Linear Guide / Rail  (Linear degradation) ────────────────
RAIL_BASE_RATE  = 9.0e-4  # degradation added per tick
RAIL_VIB_COEF   = 0.25    # motor vibration cascade on rail wear
RAIL_DEV_MAX    = 500.0   # µm deviation at full degradation
RAIL_RCVR       = 0.05    # deg removed per unit maint.
# Expected failure: ~900 ticks

# ── Nozzle Plate  (Weibull β=2.5 on accumulated age) ─────────
NOZZLE_BASE_RATE  = 7.0e-4  # age units per tick at baseline
NOZZLE_TEMP_COEF  = 1.20    # temperature stress coefficient
NOZZLE_CONT_COEF  = 0.90    # contamination coefficient
NOZZLE_BLADE_COEF = 0.30    # blade-degradation cascade on nozzle rate
NOZZLE_CLEAN_COEF = 0.40    # cleaning-degradation cascade on nozzle rate
NOZZLE_ETA        = 0.60    # Weibull scale η
NOZZLE_BETA       = 2.50    # Weibull shape β
NOZZLE_RCVR       = 0.15    # age removed per unit maint.
# Expected failure: ~650 ticks

# ── Thermal Firing Resistors  (Arrhenius-style linear) ───────
RESISTOR_BASE_RATE  = 8.0e-4  # deg per tick at nominal temp
RESISTOR_TEMP_PIVOT = 30.0    # °C pivot; stress above this
RESISTOR_TEMP_RANGE = 40.0    # normalisation range (30→70 °C)
RESISTOR_TEMP_COEF  = 1.50    # thermal amplification
RESISTOR_DRIFT_MAX  = 25.0    # % drift at full degradation
RESISTOR_RCVR       = 0.05    # deg removed per unit maint.
# Expected failure: ~750 ticks

# ── Cleaning Interface  (Linear, demand-driven) ───────────────
CLEANING_BASE_RATE   = 1.2e-3  # wear per tick (minimal demand)
CLEANING_DEMAND_COEF = 0.50    # nozzle-health cascade: more clogged → more cleaning
CLEANING_RCVR        = 0.15    # deg removed per unit maint.
# Expected failure: ~600 ticks

# ── Heating Elements  (Linear + Thermal Fatigue) ─────────────
HEATER_NOMINAL_TEMP  = 35.0    # °C design point
HEATER_BASE_RATE     = 8.0e-4  # deg per tick at nominal temp
HEATER_THERMAL_COEF  = 1.50    # overstress amplification
HEATER_INSUL_COEF    = 0.35    # insulation-cascade on heater rate
HEATER_SENSOR_COEF   = 0.20    # sensor-drift cascade on heater rate
HEATER_R_NOMINAL     = 10.0    # Ω at new condition
HEATER_R_MAX         = 25.0    # Ω at failure
HEATER_RCVR          = 0.08    # deg removed per unit maint.
# Expected failure: ~850 ticks

# ── Temperature Sensors  (Linear drift) ──────────────────────
SENSOR_NOMINAL_TEMP  = 35.0    # °C target operating point
SENSOR_BASE_RATE     = 7.0e-4  # drift per tick
SENSOR_TEMP_COEF     = 0.80    # temp-cycling stress coefficient
SENSOR_ERROR_MAX     = 15.0    # °C max measurement error at failure
SENSOR_RCVR          = 0.04    # drift removed per unit maint.
# Expected failure: ~950 ticks

# ── Insulation Panels  (Linear, slow) ────────────────────────
INSUL_BASE_RATE  = 6.5e-4  # deg per tick
INSUL_TEMP_COEF  = 0.60    # temperature stress coefficient
INSUL_R_MAX      = 2.50    # °C·m/W thermal resistance (new)
INSUL_RCVR       = 0.03    # deg removed per unit maint.
# Expected failure: ~1 000 ticks

# ── Status thresholds (all components) ───────────────────────
STATUS_MAP = {"FUNCTIONAL": 0, "DEGRADED": 1, "CRITICAL": 2, "FAILED": 3}


def health_to_status(h: float) -> str:
    if h > 0.70:
        return "FUNCTIONAL"
    if h > 0.40:
        return "DEGRADED"
    if h > 0.20:
        return "CRITICAL"
    return "FAILED"


# ══════════════════════════════════════════════════════════════
# Phase 1 State  (mutable internal counters)
# ══════════════════════════════════════════════════════════════


@dataclass
class Phase1State:
    # Recoating
    blade_thickness: float = BLADE_INIT_MM
    motor_age:       float = 0.0
    rail_deg:        float = 0.0
    # Printhead
    nozzle_age:      float = 0.0
    resistor_deg:    float = 0.0
    cleaning_deg:    float = 0.0
    # Thermal
    heater_deg:      float = 0.0
    sensor_drift:    float = 0.0
    insulation_deg:  float = 0.0


# ══════════════════════════════════════════════════════════════
# Phase 1 Engine  (rule-based degradation — ground truth)
# ══════════════════════════════════════════════════════════════


def step_phase1(state: Phase1State, d: Drivers) -> tuple[Phase1State, dict]:
    """
    Advance all nine components by one tick.
    Cascading effects use the health values at tick entry (snapshot),
    so there are no circular dependencies within a single tick.
    Returns (new_state, metrics_dict).
    """
    s = Phase1State(
        state.blade_thickness, state.motor_age,    state.rail_deg,
        state.nozzle_age,      state.resistor_deg, state.cleaning_deg,
        state.heater_deg,      state.sensor_drift, state.insulation_deg,
    )

    # ── Snapshot health values for cascade calculations ───────
    prev_blade_health = float(np.clip(
        (state.blade_thickness - BLADE_FAIL_MM) / (BLADE_INIT_MM - BLADE_FAIL_MM), 0, 1))
    prev_motor_health = float(math.exp(
        -((state.motor_age / MOTOR_ETA) ** MOTOR_BETA)))
    prev_nozzle_health = float(math.exp(
        -((state.nozzle_age / NOZZLE_ETA) ** NOZZLE_BETA)))
    prev_cleaning_health = float(np.clip(1.0 - state.cleaning_deg, 0, 1))
    prev_insul_health = float(np.clip(1.0 - state.insulation_deg, 0, 1))
    prev_sensor_health = float(np.clip(1.0 - state.sensor_drift, 0, 1))

    load_factor = min(1.0, d.load / 1000.0)          # 0→1 over max load
    temp_stress = max(0.0, (d.temperature - 20.0) / 50.0)   # 0 at 20°C, 1 at 70°C

    # ── 1. Recoater Blade ────────────────────────────────────
    wear = BLADE_BASE_WEAR * (1.0 + BLADE_HUM_COEF * d.humidity)
    s.blade_thickness = max(BLADE_FAIL_MM, s.blade_thickness * (1.0 - wear))
    if d.maintenance_level > 0:
        s.blade_thickness = min(BLADE_INIT_MM,
                                s.blade_thickness + d.maintenance_level * BLADE_RCVR)
    blade_health = float(np.clip(
        (s.blade_thickness - BLADE_FAIL_MM) / (BLADE_INIT_MM - BLADE_FAIL_MM), 0, 1))

    # ── 2. Recoater Drive Motor ──────────────────────────────
    motor_rate = MOTOR_BASE_RATE * (1.0 + MOTOR_LOAD_COEF * load_factor)
    s.motor_age += motor_rate
    if d.maintenance_level > 0:
        s.motor_age = max(0.0, s.motor_age - d.maintenance_level * MOTOR_RCVR)
    motor_health = float(math.exp(-((s.motor_age / MOTOR_ETA) ** MOTOR_BETA)))
    motor_vibration = MOTOR_V_NOMINAL + (1.0 - motor_health) * (MOTOR_V_MAX - MOTOR_V_NOMINAL)

    # ── 3. Linear Guide / Rail  (cascade from motor) ─────────
    rail_rate = RAIL_BASE_RATE * (1.0 + RAIL_VIB_COEF * (1.0 - prev_motor_health))
    s.rail_deg = min(1.0, s.rail_deg + rail_rate)
    if d.maintenance_level > 0:
        s.rail_deg = max(0.0, s.rail_deg - d.maintenance_level * RAIL_RCVR)
    rail_health = float(np.clip(1.0 - s.rail_deg, 0, 1))
    rail_deviation = s.rail_deg * RAIL_DEV_MAX

    # ── 4. Nozzle Plate  (cascade from blade + cleaning) ─────
    blade_cascade   = NOZZLE_BLADE_COEF * (1.0 - prev_blade_health)
    clean_cascade   = NOZZLE_CLEAN_COEF * (1.0 - prev_cleaning_health)
    nozzle_rate = (NOZZLE_BASE_RATE
                   * (1.0 + NOZZLE_TEMP_COEF  * temp_stress)
                   * (1.0 + NOZZLE_CONT_COEF  * d.humidity)
                   * (1.0 + blade_cascade + clean_cascade))
    s.nozzle_age += nozzle_rate
    if d.maintenance_level > 0:
        s.nozzle_age = max(0.0, s.nozzle_age - d.maintenance_level * NOZZLE_RCVR)
    nozzle_health = float(math.exp(-((s.nozzle_age / NOZZLE_ETA) ** NOZZLE_BETA)))
    clog_prob = 1.0 - nozzle_health

    # ── 5. Thermal Firing Resistors  (Arrhenius-style) ───────
    resistor_stress = max(0.0, (d.temperature - RESISTOR_TEMP_PIVOT) / RESISTOR_TEMP_RANGE)
    resistor_rate = RESISTOR_BASE_RATE * (1.0 + RESISTOR_TEMP_COEF * resistor_stress)
    s.resistor_deg = min(1.0, s.resistor_deg + resistor_rate)
    if d.maintenance_level > 0:
        s.resistor_deg = max(0.0, s.resistor_deg - d.maintenance_level * RESISTOR_RCVR)
    resistor_health = float(np.clip(1.0 - s.resistor_deg, 0, 1))
    resistor_drift_pct = s.resistor_deg * RESISTOR_DRIFT_MAX

    # ── 6. Cleaning Interface  (cascade from nozzle health) ──
    cleaning_demand = CLEANING_DEMAND_COEF * (1.0 - prev_nozzle_health)
    cleaning_rate = CLEANING_BASE_RATE * (1.0 + cleaning_demand)
    s.cleaning_deg = min(1.0, s.cleaning_deg + cleaning_rate)
    if d.maintenance_level > 0:
        s.cleaning_deg = max(0.0, s.cleaning_deg - d.maintenance_level * CLEANING_RCVR)
    cleaning_health = float(np.clip(1.0 - s.cleaning_deg, 0, 1))

    # ── 7. Heating Elements  (cascade from insulation + sensor)
    temp_over = max(0.0, (d.temperature - HEATER_NOMINAL_TEMP) / HEATER_NOMINAL_TEMP)
    insul_cascade  = HEATER_INSUL_COEF  * (1.0 - prev_insul_health)
    sensor_cascade = HEATER_SENSOR_COEF * (1.0 - prev_sensor_health)
    heater_rate = HEATER_BASE_RATE * (1.0 + HEATER_THERMAL_COEF * temp_over
                                       + insul_cascade + sensor_cascade)
    s.heater_deg = min(1.0, s.heater_deg + heater_rate)
    if d.maintenance_level > 0:
        s.heater_deg = max(0.0, s.heater_deg - d.maintenance_level * HEATER_RCVR)
    heater_health = float(np.clip(1.0 - s.heater_deg, 0, 1))
    heater_resistance = HEATER_R_NOMINAL + s.heater_deg * (HEATER_R_MAX - HEATER_R_NOMINAL)

    # ── 8. Temperature Sensors  (thermal cycling stress) ─────
    temp_cycle = abs(d.temperature - SENSOR_NOMINAL_TEMP) / 50.0
    sensor_rate = SENSOR_BASE_RATE * (1.0 + SENSOR_TEMP_COEF * temp_cycle)
    s.sensor_drift = min(1.0, s.sensor_drift + sensor_rate)
    if d.maintenance_level > 0:
        s.sensor_drift = max(0.0, s.sensor_drift - d.maintenance_level * SENSOR_RCVR)
    sensor_health = float(np.clip(1.0 - s.sensor_drift, 0, 1))
    sensor_error_c = s.sensor_drift * SENSOR_ERROR_MAX

    # ── 9. Insulation Panels  (slow thermal degradation) ─────
    insul_rate = INSUL_BASE_RATE * (1.0 + INSUL_TEMP_COEF * temp_stress)
    s.insulation_deg = min(1.0, s.insulation_deg + insul_rate)
    if d.maintenance_level > 0:
        s.insulation_deg = max(0.0, s.insulation_deg - d.maintenance_level * INSUL_RCVR)
    insulation_health = float(np.clip(1.0 - s.insulation_deg, 0, 1))
    insulation_r = insulation_health * INSUL_R_MAX

    # ── Subsystem aggregate health (min across subsystem) ────
    health_recoating = min(blade_health, motor_health, rail_health)
    health_printhead = min(nozzle_health, resistor_health, cleaning_health)
    health_thermal   = min(heater_health, sensor_health, insulation_health)

    # ── Status strings ────────────────────────────────────────
    s_blade      = health_to_status(blade_health)
    s_motor      = health_to_status(motor_health)
    s_rail       = health_to_status(rail_health)
    s_nozzle     = health_to_status(nozzle_health)
    s_resistor   = health_to_status(resistor_health)
    s_cleaning   = health_to_status(cleaning_health)
    s_heater     = health_to_status(heater_health)
    s_sensor     = health_to_status(sensor_health)
    s_insulation = health_to_status(insulation_health)

    metrics = {
        # ── health ──
        "health_blade":      round(blade_health,      6),
        "health_motor":      round(motor_health,      6),
        "health_rail":       round(rail_health,        6),
        "health_nozzle":     round(nozzle_health,     6),
        "health_resistor":   round(resistor_health,   6),
        "health_cleaning":   round(cleaning_health,   6),
        "health_heater":     round(heater_health,     6),
        "health_sensor":     round(sensor_health,     6),
        "health_insulation": round(insulation_health, 6),
        # ── status ──
        "status_blade":      s_blade,
        "status_motor":      s_motor,
        "status_rail":       s_rail,
        "status_nozzle":     s_nozzle,
        "status_resistor":   s_resistor,
        "status_cleaning":   s_cleaning,
        "status_heater":     s_heater,
        "status_sensor":     s_sensor,
        "status_insulation": s_insulation,
        # ── physical metrics ──
        "metric_blade_mm":     round(s.blade_thickness,  4),
        "metric_motor_vib":    round(motor_vibration,     4),
        "metric_rail_dev":     round(rail_deviation,       4),
        "metric_nozzle_clog":  round(clog_prob,            4),
        "metric_resistor_pct": round(resistor_drift_pct,  4),
        "metric_cleaning_eff": round(cleaning_health,      4),
        "metric_heater_ohm":   round(heater_resistance,   4),
        "metric_sensor_err":   round(sensor_error_c,       4),
        "metric_insulation_r": round(insulation_r,         4),
        # ── subsystem aggregates ──
        "health_recoating": round(health_recoating, 6),
        "health_printhead": round(health_printhead, 6),
        "health_thermal":   round(health_thermal,   6),
        # ── integer labels for NN classification ──
        "label_blade":      STATUS_MAP[s_blade],
        "label_motor":      STATUS_MAP[s_motor],
        "label_rail":       STATUS_MAP[s_rail],
        "label_nozzle":     STATUS_MAP[s_nozzle],
        "label_resistor":   STATUS_MAP[s_resistor],
        "label_cleaning":   STATUS_MAP[s_cleaning],
        "label_heater":     STATUS_MAP[s_heater],
        "label_sensor":     STATUS_MAP[s_sensor],
        "label_insulation": STATUS_MAP[s_insulation],
        # RL columns (NULL during generation)
        "action_taken": None,
        "reward":       None,
    }
    return s, metrics


# ══════════════════════════════════════════════════════════════
# Historian  — SQLite primary, CSV fallback
# ══════════════════════════════════════════════════════════════

_DDL = """
CREATE TABLE IF NOT EXISTS simulation_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id         TEXT    NOT NULL,
    run_id              INTEGER NOT NULL,
    t                   INTEGER NOT NULL,
    -- Environmental drivers
    temperature         REAL,
    humidity            REAL,
    load                REAL,
    maintenance         REAL,
    is_shock            INTEGER,
    -- Recoating subsystem
    health_blade        REAL,
    health_motor        REAL,
    health_rail         REAL,
    status_blade        TEXT,
    status_motor        TEXT,
    status_rail         TEXT,
    metric_blade_mm     REAL,   -- blade thickness (mm)
    metric_motor_vib    REAL,   -- vibration (mm/s)
    metric_rail_dev     REAL,   -- rail deviation (µm)
    -- Printhead subsystem
    health_nozzle       REAL,
    health_resistor     REAL,
    health_cleaning     REAL,
    status_nozzle       TEXT,
    status_resistor     TEXT,
    status_cleaning     TEXT,
    metric_nozzle_clog  REAL,   -- clog probability
    metric_resistor_pct REAL,   -- resistance drift (%)
    metric_cleaning_eff REAL,   -- cleaning efficiency
    -- Thermal subsystem
    health_heater       REAL,
    health_sensor       REAL,
    health_insulation   REAL,
    status_heater       TEXT,
    status_sensor       TEXT,
    status_insulation   TEXT,
    metric_heater_ohm   REAL,   -- resistance (Ω)
    metric_sensor_err   REAL,   -- measurement error (°C)
    metric_insulation_r REAL,   -- thermal resistance (°C·m/W)
    -- Subsystem aggregate health (min across subsystem components)
    health_recoating    REAL,
    health_printhead    REAL,
    health_thermal      REAL,
    -- Classification labels  (0=FUNCTIONAL 1=DEGRADED 2=CRITICAL 3=FAILED)
    label_blade         INTEGER,
    label_motor         INTEGER,
    label_rail          INTEGER,
    label_nozzle        INTEGER,
    label_resistor      INTEGER,
    label_cleaning      INTEGER,
    label_heater        INTEGER,
    label_sensor        INTEGER,
    label_insulation    INTEGER,
    -- RL columns (NULL during dataset generation)
    action_taken        INTEGER,
    reward              REAL
);
CREATE INDEX IF NOT EXISTS idx_scenario ON simulation_log (scenario_id, t);
CREATE INDEX IF NOT EXISTS idx_run      ON simulation_log (scenario_id, run_id, t);
"""

_INSERT_COLS = [
    "scenario_id", "run_id", "t",
    "temperature", "humidity", "load", "maintenance", "is_shock",
    "health_blade", "health_motor", "health_rail",
    "status_blade", "status_motor", "status_rail",
    "metric_blade_mm", "metric_motor_vib", "metric_rail_dev",
    "health_nozzle", "health_resistor", "health_cleaning",
    "status_nozzle", "status_resistor", "status_cleaning",
    "metric_nozzle_clog", "metric_resistor_pct", "metric_cleaning_eff",
    "health_heater", "health_sensor", "health_insulation",
    "status_heater", "status_sensor", "status_insulation",
    "metric_heater_ohm", "metric_sensor_err", "metric_insulation_r",
    "health_recoating", "health_printhead", "health_thermal",
    "label_blade", "label_motor", "label_rail",
    "label_nozzle", "label_resistor", "label_cleaning",
    "label_heater", "label_sensor", "label_insulation",
    "action_taken", "reward",
]

_INSERT_SQL = (
    f"INSERT INTO simulation_log ({', '.join(_INSERT_COLS)}) "
    f"VALUES ({', '.join('?' * len(_INSERT_COLS))})"
)

_CSV_FIELDS = _INSERT_COLS   # same column order for CSV fallback


class Historian:
    """Writes one row per tick to SQLite (primary) and CSV (fallback)."""

    _COMMIT_EVERY = 2_000   # batch commits for SQLite performance

    def __init__(self, db_path: Path, csv_path: Path) -> None:
        self._db_path = db_path
        self._pending = 0
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript(_DDL)
        self._conn.commit()
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        self._csv_file = open(csv_path, "w", newline="", encoding="utf-8")
        self._csv_writer = csv.DictWriter(self._csv_file, fieldnames=_CSV_FIELDS)
        self._csv_writer.writeheader()

    def write(self, row: dict) -> None:
        values = tuple(row[c] for c in _INSERT_COLS)
        self._conn.execute(_INSERT_SQL, values)
        self._csv_writer.writerow({c: row[c] for c in _CSV_FIELDS})
        self._pending += 1
        if self._pending >= self._COMMIT_EVERY:
            self._conn.commit()
            self._pending = 0

    def close(self) -> None:
        self._conn.commit()
        self._conn.close()
        self._csv_file.close()


# ══════════════════════════════════════════════════════════════
# 1.5  Implementation log
# ══════════════════════════════════════════════════════════════


class ImplementationLog:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Implementation Log — Dataset Generator\n\nGenerated: {datetime.now().isoformat()}\n\n")
        self._path = path

    def section(self, title: str, body: str) -> None:
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(f"## {title}\n\n{body.strip()}\n\n---\n\n")


# ══════════════════════════════════════════════════════════════
# Simulation runner
# ══════════════════════════════════════════════════════════════


def run_simulation(cfg: SimulationConfig, run_id: int, historian: Historian) -> int:
    seed = _SCENARIO_SEED[cfg.scenario_id] + run_id * 997
    rng = np.random.default_rng(seed)
    state = Phase1State()
    ticks = 0

    for t in range(cfg.total_steps):
        d = sample_drivers(t, cfg, rng)
        state, metrics = step_phase1(state, d)

        historian.write({
            "scenario_id": cfg.scenario_id,
            "run_id":      run_id,
            "t":           t,
            "temperature": round(d.temperature, 3),
            "humidity":    round(d.humidity,    4),
            "load":        round(d.load,         1),
            "maintenance": d.maintenance_level,
            "is_shock":    int(d.is_shock),
            **metrics,
        })
        ticks += 1

        # Early stop when all nine components have failed
        if all(metrics[f"status_{c}"] == "FAILED"
               for c in ("blade", "motor", "rail",
                          "nozzle", "resistor", "cleaning",
                          "heater", "sensor", "insulation")):
            break

    return ticks


# ══════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════


def main() -> None:
    out_dir = Path("data")
    log_dir = Path("logs")
    out_dir.mkdir(exist_ok=True)
    log_dir.mkdir(exist_ok=True)

    log = ImplementationLog(log_dir / "implementation_log.md")

    log.section("Milestone 1.1 — SimulationConfig", f"""
- `total_steps`: 1 000 (= 1 000 simulated hours per run, 1 h/tick)
- `time_step_hours`: 1.0
- Scenarios: {[s.scenario_id for s in SCENARIOS]}
- Runs per scenario: {RUNS_PER_SCENARIO}
- Max rows (no early stop): {len(SCENARIOS) * RUNS_PER_SCENARIO * 1_000:,}
- RNG seeding: `_SCENARIO_SEED[scenario_id] + run_id × 997` — stable across Python runs
""")

    log.section("Milestone 1.2 — Clock loop", """
Per tick t = 0 … total_steps − 1:
1. `sample_drivers(t, cfg, rng)` → Drivers namedtuple
2. `step_phase1(state, drivers)` → (new_state, metrics_dict)
3. `historian.write(row)` → SQLite + CSV

Early-stop condition: all nine component statuses == FAILED.
SQLite commits batched every 2 000 rows (see Historian._COMMIT_EVERY).
""")

    log.section("Milestone 1.3 — Deterministic driver profile", f"""
```
temperature = 20 + (t / total_steps) × 30    [20 °C → 50 °C linear ramp]
humidity    = 0.40                            [constant]
load        = t × time_step_hours             [cumulative hours]
```
Maintenance schedules:
| Schedule    | maintenance_level |
|-------------|-------------------|
| "none"      | 0.0 always        |
| "light"     | 0.5 every 200 steps |
| "fixed_100" | 1.0 every 100 steps |
| "full"      | 1.0 always        |
""")

    log.section("Milestone 1.4 — Stochastic and chaos driver profiles", f"""
**Stochastic** (humid_factory, chaos_prob=0.01):
```
temperature += N(0, 2),    clipped [15, 70]
humidity    += N(0, 0.05), clipped [0, 1]
shock (p=0.01): humidity += 0.25
```
**Chaos** (chaos_run, chaos_prob=0.05):
```
temperature += N(0, 3),    clipped [15, 70]
humidity    += N(0, 0.07), clipped [0, 1]
shock (p=0.05):
  50% → humidity   += U(0.20, 0.50)   [contamination burst]
  50% → temperature += U(10, 25)      [thermal spike]
```
""")

    log.section("Milestone 1.5 — All component model parameters", f"""
### Recoater Blade  (Exponential Decay — Recoating)
| Param | Value |
|---|---|
| Initial thickness | {BLADE_INIT_MM} mm |
| Failure threshold | {BLADE_FAIL_MM} mm |
| Base wear rate | {BLADE_BASE_WEAR} per tick |
| Humidity coeff | {BLADE_HUM_COEF} |
| Maint. recovery | {BLADE_RCVR} mm / unit |
| Expected failure (no maint, baseline) | ~700 ticks |

### Recoater Drive Motor  (Weibull β={MOTOR_BETA})
| Param | Value |
|---|---|
| Base age rate | {MOTOR_BASE_RATE} per tick |
| Load coeff | {MOTOR_LOAD_COEF} |
| Weibull η / β | {MOTOR_ETA} / {MOTOR_BETA} |
| Maint. recovery | {MOTOR_RCVR} age-units / unit |
| Expected failure | ~800 ticks |

### Linear Guide / Rail  (Linear)
| Param | Value |
|---|---|
| Base rate | {RAIL_BASE_RATE} per tick |
| Motor-vibration cascade coeff | {RAIL_VIB_COEF} |
| Maint. recovery | {RAIL_RCVR} deg / unit |
| Expected failure | ~900 ticks |

### Nozzle Plate  (Weibull β={NOZZLE_BETA}, η={NOZZLE_ETA})
| Param | Value |
|---|---|
| Base age rate | {NOZZLE_BASE_RATE} per tick |
| Temp coeff | {NOZZLE_TEMP_COEF} |
| Contamination coeff | {NOZZLE_CONT_COEF} |
| Blade-health cascade | {NOZZLE_BLADE_COEF} |
| Cleaning cascade | {NOZZLE_CLEAN_COEF} |
| Maint. recovery | {NOZZLE_RCVR} age-units / unit |
| Expected failure | ~650 ticks |

### Thermal Firing Resistors  (Arrhenius-style)
| Param | Value |
|---|---|
| Base rate | {RESISTOR_BASE_RATE} per tick |
| Temp pivot | {RESISTOR_TEMP_PIVOT} °C |
| Temp coeff | {RESISTOR_TEMP_COEF} |
| Maint. recovery | {RESISTOR_RCVR} deg / unit |
| Expected failure | ~750 ticks |

### Cleaning Interface  (Linear, demand-driven)
| Param | Value |
|---|---|
| Base rate | {CLEANING_BASE_RATE} per tick |
| Nozzle-demand cascade | {CLEANING_DEMAND_COEF} |
| Maint. recovery | {CLEANING_RCVR} deg / unit |
| Expected failure | ~600 ticks |

### Heating Elements  (Linear + Thermal Fatigue)
| Param | Value |
|---|---|
| Base rate | {HEATER_BASE_RATE} per tick |
| Nominal temp | {HEATER_NOMINAL_TEMP} °C |
| Thermal coeff | {HEATER_THERMAL_COEF} |
| Insulation cascade | {HEATER_INSUL_COEF} |
| Sensor cascade | {HEATER_SENSOR_COEF} |
| Resistance range | {HEATER_R_NOMINAL} – {HEATER_R_MAX} Ω |
| Expected failure | ~850 ticks |

### Temperature Sensors  (Linear drift)
| Param | Value |
|---|---|
| Base rate | {SENSOR_BASE_RATE} per tick |
| Temp-cycling coeff | {SENSOR_TEMP_COEF} |
| Max error | {SENSOR_ERROR_MAX} °C |
| Expected failure | ~950 ticks |

### Insulation Panels  (Linear, slow)
| Param | Value |
|---|---|
| Base rate | {INSUL_BASE_RATE} per tick |
| Temp coeff | {INSUL_TEMP_COEF} |
| Thermal resistance range | 0 – {INSUL_R_MAX} °C·m/W |
| Expected failure | ~1 000 ticks |

### Status thresholds (all components)
| health | Status | label |
|---|---|---|
| > 0.70 | FUNCTIONAL | 0 |
| > 0.40 | DEGRADED | 1 |
| > 0.20 | CRITICAL | 2 |
| ≤ 0.20 | FAILED | 3 |

### Cascading effects
| Source | Target | Coefficient |
|---|---|---|
| blade health ↓ | nozzle rate ↑ | {NOZZLE_BLADE_COEF} |
| motor health ↓ | rail rate ↑ | {RAIL_VIB_COEF} |
| cleaning health ↓ | nozzle rate ↑ | {NOZZLE_CLEAN_COEF} |
| insulation health ↓ | heater rate ↑ | {HEATER_INSUL_COEF} |
| sensor health ↓ | heater rate ↑ | {HEATER_SENSOR_COEF} |
""")

    db_path  = out_dir / "simulation.db"
    csv_path = out_dir / "training_dataset.csv"
    historian = Historian(db_path, csv_path)

    total_rows = 0
    for cfg in SCENARIOS:
        scenario_rows = 0
        for run_id in range(RUNS_PER_SCENARIO):
            n = run_simulation(cfg, run_id, historian)
            scenario_rows += n
        total_rows += scenario_rows
        print(f"  [{cfg.scenario_id:20s}]  {RUNS_PER_SCENARIO} runs  →  {scenario_rows:,} rows")

    historian.close()

    print(f"\nSQLite  →  {db_path}  ({total_rows:,} rows)")
    print(f"CSV     →  {csv_path}")
    print(f"Log     →  {log_dir / 'implementation_log.md'}")

    log.section("Generation Summary", f"""
- Total rows: {total_rows:,}
- SQLite: `{db_path}`
- CSV fallback: `{csv_path}`
- NN input features: temperature, humidity, load, maintenance, is_shock
- NN targets (per component): label_* (0=FUNCTIONAL 1=DEGRADED 2=CRITICAL 3=FAILED)
- Subsystem aggregate columns: health_recoating, health_printhead, health_thermal
""")


if __name__ == "__main__":
    main()
