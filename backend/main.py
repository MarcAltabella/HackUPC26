"""
Stage 3 — Interact: FastAPI backend
Milestones 1.1 (FastAPI service over SQLite historian) and
           1.2 (query endpoints for latest state, history, scenario comparison)
           1.3 (agentic chat with tool-calling LLM and structured response contract)

Run with:
    uvicorn api:app --reload --port 8000
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Annotated, Optional

import anthropic as ant
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
DB_PATH = Path(__file__).parent.parent / "models" / "data" / "simulation.db"


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
    allow_origins=[
        "http://localhost:3000",
        "https://100.98.98.88:3000",
        "http://100.98.98.88:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ════════════════════════════════════════════════════════════════════════════════
# Pydantic schemas
# ════════════════════════════════════════════════════════════════════════════════


class EnvironmentalDrivers(BaseModel):
    temperature: float  # °C
    humidity: float  # 0–1  (contamination proxy)
    load: float  # cumulative simulated hours
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
    subsystem_health: float  # min(blade, motor, rail)
    blade: BladeState
    motor: MotorState
    rail: RailState


class PrintheadSubsystem(BaseModel):
    subsystem_health: float  # min(nozzle, resistor, cleaning)
    nozzle: NozzleState
    resistor: ResistorState
    cleaning: CleaningState


class ThermalSubsystem(BaseModel):
    subsystem_health: float  # min(heater, sensor, insulation)
    heater: HeaterState
    sensor: SensorState
    insulation: InsulationState


# ── Top-level machine state ───────────────────────────────────────────────────


class MachineStateResponse(BaseModel):
    # Identifiers / traceability (citation anchors for Stage 3 LLM layer)
    scenario_id: str
    run_number: int  # integer run_id inside the scenario (0–19)
    t: int  # simulation tick (time step)
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
    run_number: Optional[int] = Query(
        default=None, description="Integer run index (0–19). Omit to use run_id=0."
    ),
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
        log.warning(
            "  → 404: scenario_id=%s run_number=%d not found", scenario_id, run_number
        )
        raise HTTPException(
            status_code=404,
            detail=f"No data for scenario_id='{scenario_id}' run_number={run_number}",
        )

    state = _row_to_state(row)
    log.info(
        "  → t=%d  recoating=%.3f  printhead=%.3f  thermal=%.3f",
        state.t,
        state.recoating.subsystem_health,
        state.printhead.subsystem_health,
        state.thermal.subsystem_health,
    )
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
        scenario_id,
        run_number,
        start_t,
        end_t,
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
    log.info(
        "GET /api/compare  scenarios=%s  run_number=%d  t=[%d,%d]",
        scenario_ids,
        run_number,
        start_t,
        end_t,
    )
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


# ════════════════════════════════════════════════════════════════════════════════
# Milestone 1.3 — Agentic Chat with Tool-Calling LLM
# ════════════════════════════════════════════════════════════════════════════════

# ── Pydantic schemas for chat ─────────────────────────────────────────────────


class Citation(BaseModel):
    run_id: str
    t: int
    field: str
    value: float | str | None = None


class ChatRequest(BaseModel):
    message: str
    scenario_id: str = "baseline_nominal"
    run_number: int = 0


class ChatResponse(BaseModel):
    severity: str  # INFO | WARNING | CRITICAL
    summary: str
    answer: str
    reasoning_summary: list[str]
    citations: list[Citation]
    recommended_actions: list[str]


# ── Anthropic client (lazy singleton) ────────────────────────────────────────

_ant_client: ant.Anthropic | None = None


def _get_ant() -> ant.Anthropic:
    global _ant_client
    if _ant_client is None:
        _ant_client = ant.Anthropic()  # reads ANTHROPIC_API_KEY from env
    return _ant_client


# ── Tool implementations (read-only SQLite queries) ───────────────────────────


def _tool_latest_state(
    conn: sqlite3.Connection, scenario_id: str, run_number: int
) -> dict:
    row = conn.execute(
        """
        SELECT t, temperature, humidity, maintenance,
               health_recoating, health_printhead, health_thermal,
               health_blade, status_blade, metric_blade_mm,
               health_motor, status_motor, metric_motor_vib,
               health_rail,  status_rail,  metric_rail_dev,
               health_nozzle,   status_nozzle,   metric_nozzle_clog,
               health_resistor, status_resistor, metric_resistor_pct,
               health_cleaning, status_cleaning, metric_cleaning_eff,
               health_heater,    status_heater,    metric_heater_ohm,
               health_sensor,    status_sensor,    metric_sensor_err,
               health_insulation,status_insulation,metric_insulation_r
        FROM simulation_log
        WHERE scenario_id = ? AND run_id = ?
        ORDER BY t DESC LIMIT 1
        """,
        (scenario_id, run_number),
    ).fetchone()
    if row is None:
        return {
            "error": f"No data for scenario_id={scenario_id!r} run_number={run_number}"
        }
    return dict(row)


def _tool_component_history(
    conn: sqlite3.Connection,
    scenario_id: str,
    run_number: int,
    start_t: int,
    end_t: int,
) -> list[dict]:
    rows = conn.execute(
        """
        SELECT t,
               health_recoating, health_printhead, health_thermal,
               health_blade, health_motor, health_rail,
               health_nozzle, health_resistor, health_cleaning,
               health_heater, health_sensor, health_insulation,
               status_blade, status_motor, status_rail,
               status_nozzle, status_resistor, status_cleaning,
               status_heater, status_sensor, status_insulation,
               temperature, humidity
        FROM simulation_log
        WHERE scenario_id = ? AND run_id = ? AND t BETWEEN ? AND ?
        ORDER BY t
        LIMIT 200
        """,
        (scenario_id, run_number, start_t, end_t),
    ).fetchall()
    return [dict(r) for r in rows]


def _tool_threshold_crossing(
    conn: sqlite3.Connection,
    scenario_id: str,
    run_number: int,
    component: str,
    threshold: float,
) -> dict:
    col = f"health_{component}"
    row = conn.execute(
        f"SELECT t, {col} FROM simulation_log "  # noqa: S608
        "WHERE scenario_id = ? AND run_id = ? AND "
        f"{col} < ? ORDER BY t ASC LIMIT 1",
        (scenario_id, run_number, threshold),
    ).fetchone()
    if row is None:
        return {
            "crossed": False,
            "message": f"{component} never dropped below {threshold}",
        }
    return {
        "crossed": True,
        "component": component,
        "threshold": threshold,
        "t": row["t"],
        "health": row[col],
    }


# ── Tool definitions sent to the LLM ─────────────────────────────────────────

_TOOLS: list[dict] = [
    {
        "name": "get_latest_state",
        "description": (
            "Return the latest full machine-state snapshot for a scenario run: "
            "all 9 component health values, status strings, and sensor metrics. "
            "Always call this first to get the current picture."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scenario_id": {
                    "type": "string",
                    "description": "e.g. 'baseline_nominal'",
                },
                "run_number": {
                    "type": "integer",
                    "description": "Integer replica index (0–19)",
                    "default": 0,
                },
            },
            "required": ["scenario_id"],
        },
    },
    {
        "name": "get_component_history",
        "description": (
            "Return per-tick health values for all 9 components over a time window. "
            "Use to detect degradation trends or compare pre/post-event states. "
            "Returns at most 200 ticks."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scenario_id": {"type": "string"},
                "run_number": {"type": "integer", "default": 0},
                "start_t": {"type": "integer", "default": 0},
                "end_t": {"type": "integer", "default": 999},
            },
            "required": ["scenario_id"],
        },
    },
    {
        "name": "find_threshold_crossing",
        "description": (
            "Find the first simulation tick where a specific component's health dropped below "
            "a threshold. Useful for estimating time-to-failure or maintenance windows."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scenario_id": {"type": "string"},
                "run_number": {"type": "integer", "default": 0},
                "component": {
                    "type": "string",
                    "enum": [
                        "blade",
                        "motor",
                        "rail",
                        "nozzle",
                        "resistor",
                        "cleaning",
                        "heater",
                        "sensor",
                        "insulation",
                    ],
                },
                "threshold": {
                    "type": "number",
                    "description": "Health threshold 0.0–1.0",
                },
            },
            "required": ["scenario_id", "component", "threshold"],
        },
    },
    {
        "name": "produce_response",
        "description": (
            "Emit the final structured response. Call this EXACTLY ONCE when you have "
            "retrieved all necessary data and are ready to answer the user."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "severity": {
                    "type": "string",
                    "enum": ["INFO", "WARNING", "CRITICAL"],
                    "description": "CRITICAL if any component is FAILED; WARNING if any health<0.7; else INFO.",
                },
                "summary": {
                    "type": "string",
                    "description": "One-sentence summary ≤140 characters.",
                },
                "answer": {
                    "type": "string",
                    "description": "Full markdown answer to the user's question, grounded in tool data.",
                },
                "reasoning_summary": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "3–5 bullet points tracing the analysis chain.",
                },
                "citations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "run_id": {"type": "string"},
                            "t": {"type": "integer"},
                            "field": {"type": "string"},
                            "value": {
                                "description": "Raw numeric or string value at this tick."
                            },
                        },
                        "required": ["run_id", "t", "field"],
                    },
                },
                "recommended_actions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific, actionable maintenance steps.",
                },
            },
            "required": [
                "severity",
                "summary",
                "answer",
                "reasoning_summary",
                "citations",
                "recommended_actions",
            ],
        },
    },
]

_SYSTEM_PROMPT = """\
You are the HP Metal Jet S100 Digital Co-Pilot — an expert predictive-maintenance AI.

You have exclusive access to real-time historian data through the provided tools.

RULES (non-negotiable):
1. NEVER state a health value or status without first retrieving it via a tool.
2. Cite every data point: record scenario_id as run_id, the exact tick (t), and the field name.
3. When you have sufficient data to answer, call produce_response EXACTLY ONCE.
4. Severity: CRITICAL if any component status is FAILED; WARNING if any health < 0.7; else INFO.
5. reasoning_summary: 3–5 concise bullet points tracing your analysis chain.
6. recommended_actions: specific, actionable steps (e.g. "Replace blade — thickness 0.41 mm at t=87").

Subsystems and components:
• Recoating : blade, motor, rail
• Printhead  : nozzle, resistor, cleaning
• Thermal    : heater, sensor, insulation
"""


# ── Endpoint ──────────────────────────────────────────────────────────────────


@app.post("/api/chat", response_model=ChatResponse, tags=["Milestone 1.3"])
def chat(req: ChatRequest):
    """Agentic chat: LLM with tool use grounded in the historian DB."""
    log.info(
        "POST /api/chat  scenario=%s run=%d  q=%r",
        req.scenario_id,
        req.run_number,
        req.message[:80],
    )

    client = _get_ant()
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    messages: list[dict] = [{"role": "user", "content": req.message}]

    try:
        for iteration in range(10):
            resp = client.messages.create(
                model="claude-opus-4-7",
                max_tokens=4096,
                thinking={"type": "adaptive"},
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=_TOOLS,
                messages=messages,
            )
            log.info("  iter=%d stop_reason=%s", iteration, resp.stop_reason)

            # Preserve full content (including thinking blocks) for next turn
            messages.append({"role": "assistant", "content": resp.content})

            if resp.stop_reason == "end_turn":
                raise HTTPException(
                    500, detail="LLM ended without calling produce_response"
                )

            if resp.stop_reason != "tool_use":
                raise HTTPException(
                    500, detail=f"Unexpected stop_reason: {resp.stop_reason!r}"
                )

            tool_results: list[dict] = []
            final_payload: dict | None = None

            for block in resp.content:
                if block.type != "tool_use":
                    continue

                name = block.name
                inp = block.input
                sc = inp.get("scenario_id", req.scenario_id)
                run = int(inp.get("run_number", req.run_number))

                if name == "produce_response":
                    final_payload = inp
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "Response recorded.",
                        }
                    )
                    break  # done — don't execute further tools this turn

                try:
                    if name == "get_latest_state":
                        result = _tool_latest_state(conn, sc, run)
                    elif name == "get_component_history":
                        result = _tool_component_history(
                            conn,
                            sc,
                            run,
                            int(inp.get("start_t", 0)),
                            int(inp.get("end_t", 999)),
                        )
                    elif name == "find_threshold_crossing":
                        result = _tool_threshold_crossing(
                            conn,
                            sc,
                            run,
                            inp["component"],
                            float(inp["threshold"]),
                        )
                    else:
                        result = {"error": f"Unknown tool: {name!r}"}
                except Exception as exc:
                    result = {"error": str(exc)}

                log.info("    tool=%s → %s", name, str(result)[:120])
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    }
                )

            if final_payload is not None:
                return ChatResponse(
                    severity=final_payload["severity"],
                    summary=final_payload["summary"],
                    answer=final_payload["answer"],
                    reasoning_summary=final_payload.get("reasoning_summary", []),
                    citations=[
                        Citation(
                            run_id=c.get("run_id", req.scenario_id),
                            t=c["t"],
                            field=c["field"],
                            value=c.get("value"),
                        )
                        for c in final_payload.get("citations", [])
                    ],
                    recommended_actions=final_payload.get("recommended_actions", []),
                )

            messages.append({"role": "user", "content": tool_results})

        raise HTTPException(
            500, detail="Agentic loop exhausted without produce_response"
        )

    finally:
        conn.close()
