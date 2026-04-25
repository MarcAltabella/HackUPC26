"""
Stage 3 — Interact: FastAPI backend
Milestones 1.1 (FastAPI service over SQLite historian) and
           1.2 (query endpoints for latest state, history, scenario comparison)

Run with:
    uvicorn api:app --reload --port 8000
"""
import logging
import sqlite3
from pathlib import Path
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Milestone 1.5: logging ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("copilot.api")

# ── DB path (relative to project root / models/) ─────────────────────────────
DB_PATH = Path(__file__).parent / "data" / "simulation.db"


# ── DB dependency — read-only connection per request ─────────────────────────
def get_db():
    """Yields a read-only SQLite connection with row-dict access."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


DB = Annotated[sqlite3.Connection, Depends(get_db)]

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="HP Metal Jet S100 — Digital Co-Pilot API",
    description="Grounded historian service for Stage 3 (Milestone 1.1 / 1.2)",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ════════════════════════════════════════════════════════════════════════════════
# Pydantic schemas
# ════════════════════════════════════════════════════════════════════════════════


class EnvironmentalDrivers(BaseModel):
    temperature: float        # °C
    humidity: float           # 0–1  (contamination proxy)
    load: float               # cumulative simulated hours
    maintenance_level: float  # 0–1
    is_shock: bool


# ── Per-component state models ────────────────────────────────────────────────

class BladeState(BaseModel):
    health: float
    status: str
    thickness_mm: float


class MotorState(BaseModel):
    health: float
    status: str
    vibration_mm_s: float


class RailState(BaseModel):
    health: float
    status: str
    deviation_um: float


class NozzleState(BaseModel):
    health: float
    status: str
    clog_probability: float


class ResistorState(BaseModel):
    health: float
    status: str
    drift_pct: float


class CleaningState(BaseModel):
    health: float
    status: str
    efficiency: float


class HeaterState(BaseModel):
    health: float
    status: str
    resistance_ohm: float


class SensorState(BaseModel):
    health: float
    status: str
    measurement_error_c: float


class InsulationState(BaseModel):
    health: float
    status: str
    thermal_resistance: float


# ── Subsystem aggregates ──────────────────────────────────────────────────────

class RecoatingSubsystem(BaseModel):
    subsystem_health: float   # min(blade, motor, rail)
    blade: BladeState
    motor: MotorState
    rail: RailState


class PrintheadSubsystem(BaseModel):
    subsystem_health: float   # min(nozzle, resistor, cleaning)
    nozzle: NozzleState
    resistor: ResistorState
    cleaning: CleaningState


class ThermalSubsystem(BaseModel):
    subsystem_health: float   # min(heater, sensor, insulation)
    heater: HeaterState
    sensor: SensorState
    insulation: InsulationState


# ── Top-level machine state ───────────────────────────────────────────────────

class MachineStateResponse(BaseModel):
    # Identifiers / traceability (citation anchors for Stage 3 LLM layer)
    scenario_id: str
    run_number: int           # integer run_id inside the scenario (0–19)
    t: int                    # simulation tick (time step)
    # Environmental context
    drivers: EnvironmentalDrivers
    # Subsystems
    recoating: RecoatingSubsystem
    printhead: PrintheadSubsystem
    thermal: ThermalSubsystem


# ── Compact row for history / comparison endpoints ────────────────────────────

class HistoryRow(BaseModel):
    t: int
    temperature: float
    humidity: float
    health_recoating: float
    health_printhead: float
    health_thermal: float
    status_blade: str
    status_nozzle: str
    status_heater: str


class ScenarioMeta(BaseModel):
    scenario_id: str
    run_count: int
    min_t: int
    max_t: int


# ════════════════════════════════════════════════════════════════════════════════
# Helper: row → MachineStateResponse
# ════════════════════════════════════════════════════════════════════════════════


def _row_to_state(row: sqlite3.Row) -> MachineStateResponse:
    r = dict(row)
    return MachineStateResponse(
        scenario_id=r["scenario_id"],
        run_number=r["run_id"],
        t=r["t"],
        drivers=EnvironmentalDrivers(
            temperature=r["temperature"],
            humidity=r["humidity"],
            load=r["load"],
            maintenance_level=r["maintenance"],
            is_shock=bool(r["is_shock"]),
        ),
        recoating=RecoatingSubsystem(
            subsystem_health=r["health_recoating"],
            blade=BladeState(
                health=r["health_blade"],
                status=r["status_blade"],
                thickness_mm=r["metric_blade_mm"],
            ),
            motor=MotorState(
                health=r["health_motor"],
                status=r["status_motor"],
                vibration_mm_s=r["metric_motor_vib"],
            ),
            rail=RailState(
                health=r["health_rail"],
                status=r["status_rail"],
                deviation_um=r["metric_rail_dev"],
            ),
        ),
        printhead=PrintheadSubsystem(
            subsystem_health=r["health_printhead"],
            nozzle=NozzleState(
                health=r["health_nozzle"],
                status=r["status_nozzle"],
                clog_probability=r["metric_nozzle_clog"],
            ),
            resistor=ResistorState(
                health=r["health_resistor"],
                status=r["status_resistor"],
                drift_pct=r["metric_resistor_pct"],
            ),
            cleaning=CleaningState(
                health=r["health_cleaning"],
                status=r["status_cleaning"],
                efficiency=r["metric_cleaning_eff"],
            ),
        ),
        thermal=ThermalSubsystem(
            subsystem_health=r["health_thermal"],
            heater=HeaterState(
                health=r["health_heater"],
                status=r["status_heater"],
                resistance_ohm=r["metric_heater_ohm"],
            ),
            sensor=SensorState(
                health=r["health_sensor"],
                status=r["status_sensor"],
                measurement_error_c=r["metric_sensor_err"],
            ),
            insulation=InsulationState(
                health=r["health_insulation"],
                status=r["status_insulation"],
                thermal_resistance=r["metric_insulation_r"],
            ),
        ),
    )


# ════════════════════════════════════════════════════════════════════════════════
# Endpoints
# ════════════════════════════════════════════════════════════════════════════════


@app.get("/api/scenarios", response_model=list[ScenarioMeta], tags=["Milestone 1.2"])
def list_scenarios(db: DB):
    """List all available scenarios with run counts and time range."""
    log.info("GET /api/scenarios")
    rows = db.execute(
        """
        SELECT scenario_id,
               COUNT(DISTINCT run_id) AS run_count,
               MIN(t)                 AS min_t,
               MAX(t)                 AS max_t
        FROM simulation_log
        GROUP BY scenario_id
        ORDER BY scenario_id
        """
    ).fetchall()
    return [ScenarioMeta(**dict(r)) for r in rows]


@app.get(
    "/api/runs/{scenario_id}/state/latest",
    response_model=MachineStateResponse,
    tags=["Milestone 1.1"],
)
def get_latest_state(
    scenario_id: str,
    db: DB,
    run_number: Optional[int] = Query(default=None, description="Integer run index (0–19). Omit to use run_id=0."),
):
    """
    Return the latest tick state for a given scenario_id (and optionally a specific run_number).

    In Stage 3 citation format, scenario_id is what the brief calls 'run_id'
    (e.g. 'chaos_run', 'baseline_nominal').  run_number is the integer replica index.
    """
    run_number = run_number if run_number is not None else 0
    log.info("GET /api/runs/%s/state/latest  run_number=%d", scenario_id, run_number)

    row = db.execute(
        """
        SELECT *
        FROM simulation_log
        WHERE scenario_id = ? AND run_id = ?
        ORDER BY t DESC
        LIMIT 1
        """,
        (scenario_id, run_number),
    ).fetchone()

    if row is None:
        log.warning("  → 404: scenario_id=%s run_number=%d not found", scenario_id, run_number)
        raise HTTPException(
            status_code=404,
            detail=f"No data for scenario_id='{scenario_id}' run_number={run_number}",
        )

    state = _row_to_state(row)
    log.info("  → t=%d  recoating=%.3f  printhead=%.3f  thermal=%.3f",
             state.t, state.recoating.subsystem_health,
             state.printhead.subsystem_health, state.thermal.subsystem_health)
    return state


@app.get(
    "/api/runs/{scenario_id}/history",
    response_model=list[HistoryRow],
    tags=["Milestone 1.2"],
)
def get_history(
    scenario_id: str,
    db: DB,
    run_number: int = Query(default=0, description="Integer run index (0–19)."),
    start_t: int = Query(default=0, ge=0),
    end_t: int = Query(default=999, ge=0),
):
    """
    Return subsystem health over a time window for trend analysis and chart data.
    Used by the dashboard and the Stage 3 LLM tool `get_subsystem_history`.
    """
    log.info(
        "GET /api/runs/%s/history  run_number=%d  t=[%d,%d]",
        scenario_id, run_number, start_t, end_t,
    )
    rows = db.execute(
        """
        SELECT t, temperature, humidity,
               health_recoating, health_printhead, health_thermal,
               status_blade, status_nozzle, status_heater
        FROM simulation_log
        WHERE scenario_id = ? AND run_id = ? AND t BETWEEN ? AND ?
        ORDER BY t
        """,
        (scenario_id, run_number, start_t, end_t),
    ).fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No history for scenario_id='{scenario_id}' run_number={run_number} t=[{start_t},{end_t}]",
        )

    log.info("  → %d ticks returned", len(rows))
    return [HistoryRow(**dict(r)) for r in rows]


@app.get(
    "/api/runs/{scenario_id}/state/at/{t}",
    response_model=MachineStateResponse,
    tags=["Milestone 1.2"],
)
def get_state_at(
    scenario_id: str,
    t: int,
    db: DB,
    run_number: int = Query(default=0),
):
    """Return the exact machine state at tick t (for citation lookup and evidence retrieval)."""
    log.info("GET /api/runs/%s/state/at/%d  run_number=%d", scenario_id, t, run_number)

    row = db.execute(
        "SELECT * FROM simulation_log WHERE scenario_id = ? AND run_id = ? AND t = ?",
        (scenario_id, run_number, t),
    ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No row at scenario_id='{scenario_id}' run_number={run_number} t={t}",
        )

    return _row_to_state(row)


@app.get(
    "/api/compare",
    response_model=dict[str, list[HistoryRow]],
    tags=["Milestone 1.2"],
)
def compare_scenarios(
    db: DB,
    scenario_ids: list[str] = Query(description="Two or more scenario_ids to compare."),
    run_number: int = Query(default=0),
    start_t: int = Query(default=0, ge=0),
    end_t: int = Query(default=999, ge=0),
):
    """
    Return subsystem health time series for multiple scenarios side-by-side.
    Used by the LLM tool `compare_runs` and the dashboard comparison chart.
    """
    log.info("GET /api/compare  scenarios=%s  run_number=%d  t=[%d,%d]",
             scenario_ids, run_number, start_t, end_t)
    result: dict[str, list[HistoryRow]] = {}
    for sid in scenario_ids:
        rows = db.execute(
            """
            SELECT t, temperature, humidity,
                   health_recoating, health_printhead, health_thermal,
                   status_blade, status_nozzle, status_heater
            FROM simulation_log
            WHERE scenario_id = ? AND run_id = ? AND t BETWEEN ? AND ?
            ORDER BY t
            """,
            (sid, run_number, start_t, end_t),
        ).fetchall()
        result[sid] = [HistoryRow(**dict(r)) for r in rows]
    return result
