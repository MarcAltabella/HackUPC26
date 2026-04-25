from __future__ import annotations

import os
import sqlite3
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Annotated

import numpy as np
import torch
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = PROJECT_ROOT / "models"
MODELS_SRC_DIR = MODELS_DIR / "src"
DB_PATH = MODELS_DIR / "data" / "simulation.db"
ARTIFACTS_DIR = MODELS_DIR / "artifacts" / "models"
DQN_PATH = MODELS_DIR / "data" / "dqn.pt"

if str(MODELS_DIR) not in sys.path:
    sys.path.insert(0, str(MODELS_DIR))
if str(MODELS_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(MODELS_SRC_DIR))

from src.dense_training_base import ClassifierConfig, DenseClassifier  # noqa: E402
from src.rl_agent import DQN, compute_reward  # noqa: E402

LABEL_TO_STATUS = {
    0: "FUNCTIONAL",
    1: "DEGRADED",
    2: "CRITICAL",
    3: "FAILED",
}

ACTION_LABELS = {
    0: "do_nothing",
    1: "light_service",
    2: "full_maintenance",
}

ACTION_TO_MAINTENANCE = {
    0: 0.0,
    1: 0.5,
    2: 1.0,
}

COMPONENTS = [
    "blade",
    "motor",
    "rail",
    "nozzle",
    "resistor",
    "cleaning",
    "heater",
    "sensor",
    "insulation",
]

SUBSYSTEMS = {
    "recoating": ["blade", "motor", "rail"],
    "printhead": ["nozzle", "resistor", "cleaning"],
    "thermal": ["heater", "sensor", "insulation"],
}

COMPONENT_META = {
    "blade": {
        "display": "Blade",
        "subsystem": "Recoating",
        "metric_field": "thickness_mm",
        "metric_label": "thickness",
        "unit": "mm",
    },
    "motor": {
        "display": "Motor",
        "subsystem": "Recoating",
        "metric_field": "vibration_mm_s",
        "metric_label": "vibration",
        "unit": "mm/s",
    },
    "rail": {
        "display": "Rail",
        "subsystem": "Recoating",
        "metric_field": "deviation_um",
        "metric_label": "deviation",
        "unit": "um",
    },
    "nozzle": {
        "display": "Nozzle",
        "subsystem": "Printhead",
        "metric_field": "clog_probability",
        "metric_label": "clog probability",
        "unit": "",
    },
    "resistor": {
        "display": "Resistor",
        "subsystem": "Printhead",
        "metric_field": "drift_pct",
        "metric_label": "drift",
        "unit": "%",
    },
    "cleaning": {
        "display": "Cleaning",
        "subsystem": "Printhead",
        "metric_field": "efficiency",
        "metric_label": "efficiency",
        "unit": "",
    },
    "heater": {
        "display": "Heater",
        "subsystem": "Thermal",
        "metric_field": "resistance_ohm",
        "metric_label": "resistance",
        "unit": "ohm",
    },
    "sensor": {
        "display": "Sensor",
        "subsystem": "Thermal",
        "metric_field": "measurement_error_c",
        "metric_label": "measurement error",
        "unit": "C",
    },
    "insulation": {
        "display": "Insulation",
        "subsystem": "Thermal",
        "metric_field": "thermal_resistance",
        "metric_label": "thermal resistance",
        "unit": "",
    },
}


def get_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(status_code=500, detail=f"Simulation DB not found: {DB_PATH}")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


DB = Annotated[sqlite3.Connection, Depends(get_db)]

app = FastAPI(
    title="HP Metal Jet S100 Digital Co-Pilot API",
    description="Phase 3 serving layer over joined Phase 1 classifiers and Phase 2 simulation/RL state.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Citation(BaseModel):
    run_id: str
    run_number: int = 0
    t: int
    field: str
    value: float | str | int | bool | None = None


class ChatRequest(BaseModel):
    message: str
    scenario_id: str = "baseline_nominal"
    run_number: int = 0
    t: int | None = None


class ChatResponse(BaseModel):
    severity: str
    summary: str
    answer: str
    reasoning_summary: list[str]
    citations: list[Citation]
    recommended_actions: list[str]


class ComponentClassifier:
    def __init__(self, component: str, checkpoint_path: Path) -> None:
        self.component = component
        self.checkpoint_path = checkpoint_path
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        cfg_dict = checkpoint["config"]
        cfg = ClassifierConfig(
            input_dim=int(cfg_dict["input_dim"]),
            output_dim=int(cfg_dict.get("output_dim", 4)),
            hidden_dim=int(cfg_dict["hidden_dim"]),
            dropout=float(cfg_dict["dropout"]),
        )
        self.feature_cols = list(checkpoint["feature_cols"])
        self.mean = np.asarray(checkpoint["mean"], dtype=np.float32)
        self.std = np.asarray(checkpoint["std"], dtype=np.float32)
        self.model = DenseClassifier(cfg)
        self.model.load_state_dict(checkpoint["state_dict"])
        self.model.eval()

    def predict(self, feature_values: dict[str, float]) -> dict[str, Any]:
        missing = [col for col in self.feature_cols if col not in feature_values]
        if missing:
            raise ValueError(f"{self.component} missing features: {', '.join(missing)}")
        x_raw = np.asarray([[float(feature_values[col]) for col in self.feature_cols]], dtype=np.float32)
        x = (x_raw - self.mean) / np.where(self.std < 1e-8, 1.0, self.std)
        with torch.no_grad():
            logits = self.model(torch.from_numpy(x))
            probabilities = torch.softmax(logits, dim=1).numpy()[0]
        label = int(np.argmax(probabilities))
        return {
            "label": label,
            "status": LABEL_TO_STATUS[label],
            "confidence": round(float(probabilities[label]), 6),
            "probabilities": {
                LABEL_TO_STATUS[i]: round(float(probabilities[i]), 6)
                for i in range(len(probabilities))
            },
        }


@lru_cache(maxsize=1)
def get_classifiers() -> dict[str, ComponentClassifier]:
    classifiers: dict[str, ComponentClassifier] = {}
    for component in COMPONENTS:
        path = ARTIFACTS_DIR / f"{component}_classifier.pt"
        if not path.exists():
            raise FileNotFoundError(f"Missing classifier checkpoint: {path}")
        classifiers[component] = ComponentClassifier(component, path)
    return classifiers


@lru_cache(maxsize=1)
def get_dqn() -> DQN:
    if not DQN_PATH.exists():
        raise FileNotFoundError(f"Missing DQN checkpoint: {DQN_PATH}")
    model = DQN()
    state_dict = torch.load(DQN_PATH, map_location="cpu", weights_only=False)
    model.load_state_dict(state_dict)
    model.eval()
    return model


def _query_rows(conn: sqlite3.Connection, scenario_id: str, run_number: int, end_t: int) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT *
        FROM simulation_log
        WHERE scenario_id = ? AND run_id = ? AND t BETWEEN 0 AND ?
        ORDER BY t
        """,
        (scenario_id, run_number, end_t),
    ).fetchall()
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No data for scenario_id={scenario_id!r} run_number={run_number}",
        )
    return rows


def _base_state_report(row: sqlite3.Row, predictions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for component in COMPONENTS:
        report[f"health_{component}"] = float(row[f"health_{component}"])
        report[f"status_{component}"] = predictions[component]["status"]
        report[f"label_{component}"] = predictions[component]["label"]
    report["health_recoating"] = float(row["health_recoating"])
    report["health_printhead"] = float(row["health_printhead"])
    report["health_thermal"] = float(row["health_thermal"])
    return report


def _component_state(
    row: sqlite3.Row,
    component: str,
    prediction: dict[str, Any],
) -> dict[str, Any]:
    metric_values = {
        "blade": {"thickness_mm": row["metric_blade_mm"]},
        "motor": {"vibration_mm_s": row["metric_motor_vib"]},
        "rail": {"deviation_um": row["metric_rail_dev"]},
        "nozzle": {"clog_probability": row["metric_nozzle_clog"]},
        "resistor": {"drift_pct": row["metric_resistor_pct"]},
        "cleaning": {"efficiency": row["metric_cleaning_eff"]},
        "heater": {"resistance_ohm": row["metric_heater_ohm"]},
        "sensor": {"measurement_error_c": row["metric_sensor_err"]},
        "insulation": {"thermal_resistance": row["metric_insulation_r"]},
    }
    return {
        "health": float(row[f"health_{component}"]),
        "status": prediction["status"],
        "label": prediction["label"],
        "confidence": prediction["confidence"],
        "probabilities": prediction["probabilities"],
        **{key: float(value) for key, value in metric_values[component].items()},
    }


def _pick_dqn_action(report: dict[str, Any], steps_since_maintenance: int) -> int:
    values = [float(report[f"health_{component}"]) for component in COMPONENTS]
    values.append(min(steps_since_maintenance / 100.0, 1.0))
    x = torch.tensor(values, dtype=torch.float32).unsqueeze(0)
    with torch.no_grad():
        return int(get_dqn()(x).argmax(dim=1).item())


def _format_metric(value: float, unit: str) -> str:
    if unit == "%":
        return f"{value:.1f}%"
    if unit:
        return f"{value:.2f} {unit}"
    return f"{value:.3f}"


def _make_alerts(joined: dict[str, Any]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    component_lookup = {
        "blade": joined["recoating"]["blade"],
        "motor": joined["recoating"]["motor"],
        "rail": joined["recoating"]["rail"],
        "nozzle": joined["printhead"]["nozzle"],
        "resistor": joined["printhead"]["resistor"],
        "cleaning": joined["printhead"]["cleaning"],
        "heater": joined["thermal"]["heater"],
        "sensor": joined["thermal"]["sensor"],
        "insulation": joined["thermal"]["insulation"],
    }
    for component, state in component_lookup.items():
        status = state["status"]
        if status == "FUNCTIONAL":
            continue
        severity = "CRITICAL" if status in {"CRITICAL", "FAILED"} else "WARNING"
        meta = COMPONENT_META[component]
        metric_value = float(state[meta["metric_field"]])
        metric_text = _format_metric(metric_value, meta["unit"])
        health_pct = state["health"] * 100.0
        alerts.append(
            {
                "id": f"{joined['scenario_id']}-{joined['run_number']}-{joined['t']}-{component}",
                "severity": severity,
                "subsystem": meta["subsystem"],
                "component": meta["display"],
                "component_key": component,
                "metric": metric_text,
                "summary": (
                    f"{meta['display']} is {status.lower()} at {health_pct:.1f}% health "
                    f"({meta['metric_label']} {metric_text})."
                ),
                "reasoning": [
                    f"Phase 1 classifier predicts {status} with {state['confidence'] * 100:.1f}% confidence.",
                    f"Historian health for {component} is {health_pct:.1f}% at t={joined['t']}.",
                    f"DQN recommends {joined['maintenance_recommendation']['action_label'].replace('_', ' ')} for this tick.",
                ],
                "actions": _recommended_actions(component, severity),
                "query": f"Diagnose the {meta['display'].lower()} {status.lower()} condition at t={joined['t']}.",
                "citations": [
                    {
                        "run_id": joined["scenario_id"],
                        "run_number": joined["run_number"],
                        "t": joined["t"],
                        "field": f"health_{component}",
                        "value": round(float(state["health"]), 6),
                    },
                    {
                        "run_id": joined["scenario_id"],
                        "run_number": joined["run_number"],
                        "t": joined["t"],
                        "field": f"status_{component}",
                        "value": status,
                    },
                    {
                        "run_id": joined["scenario_id"],
                        "run_number": joined["run_number"],
                        "t": joined["t"],
                        "field": f"metric_{component}",
                        "value": round(metric_value, 6),
                    },
                ],
            }
        )
    severity_rank = {"CRITICAL": 0, "WARNING": 1}
    return sorted(alerts, key=lambda alert: (severity_rank[alert["severity"]], alert["component"]))


def _recommended_actions(component: str, severity: str) -> list[str]:
    actions = {
        "blade": ["Inspect recoater blade edge", "Reduce recoating speed", "Schedule blade replacement"],
        "motor": ["Inspect motor bearings", "Check recoater alignment", "Lubricate drive assembly"],
        "rail": ["Recalibrate guide rail", "Inspect build-bed alignment", "Check rail contamination"],
        "nozzle": ["Run nozzle cleaning cycle", "Reduce humidity exposure", "Inspect nozzle plate"],
        "resistor": ["Recalibrate firing voltage", "Inspect printhead contacts", "Schedule resistor check"],
        "cleaning": ["Clean wiper assembly", "Run purge cycle", "Increase cleaning frequency"],
        "heater": ["Trend heater resistance", "Inspect thermal wiring", "Schedule heater check"],
        "sensor": ["Calibrate temperature sensor", "Check sensor drift", "Verify control loop readings"],
        "insulation": ["Inspect insulation panels", "Check thermal leakage", "Schedule panel inspection"],
    }[component]
    if severity == "CRITICAL":
        return actions
    return actions[:2]


# ── In-memory cache for joined rows ───────────────────────────────────────────
# Cache stores full timelines keyed by (scenario_id, run_number, max_t)
# This is efficient because each tick depends on previous state, so we must
# compute sequentially from t=0. We cache the full result and slice as needed.

_joined_rows_cache: dict[tuple[str, int, int], list[dict[str, Any]]] = {}


def _compute_full_timeline(
    conn: sqlite3.Connection,
    scenario_id: str,
    run_number: int,
    end_t: int,
) -> list[dict[str, Any]]:
    """Compute full timeline from t=0 to end_t. Results are stored with t as index."""
    rows = _query_rows(conn, scenario_id, run_number, end_t)
    classifiers = get_classifiers()
    prev_health = {component: 1.0 for component in COMPONENTS}
    cumulative_shocks = 0
    steps_since_maintenance = 0
    previous_report: dict[str, Any] | None = None
    all_joined: list[dict[str, Any]] = []

    for row in rows:
        if float(row["maintenance"] or 0.0) > 0:
            steps_since_maintenance = 0
        else:
            steps_since_maintenance += 1
        if bool(row["is_shock"]):
            cumulative_shocks += 1

        feature_values: dict[str, float] = {
            "temperature": float(row["temperature"]),
            "humidity": float(row["humidity"]),
            "load": float(row["load"]),
            "maintenance": float(row["maintenance"] or 0.0),
            "is_shock": float(row["is_shock"] or 0),
            "steps_since_maintenance": float(steps_since_maintenance),
            "cumulative_shocks": float(cumulative_shocks),
        }
        for component in COMPONENTS:
            feature_values[f"health_prev_{component}"] = float(prev_health[component])

        predictions = {
            component: classifiers[component].predict(feature_values)
            for component in COMPONENTS
        }
        report = _base_state_report(row, predictions)
        action = _pick_dqn_action(report, steps_since_maintenance)
        reward = compute_reward(report, action, previous_report)
        maintenance_level = ACTION_TO_MAINTENANCE[action]

        joined = {
            "scenario_id": row["scenario_id"],
            "run_number": int(row["run_id"]),
            "t": int(row["t"]),
            "drivers": {
                "temperature": float(row["temperature"]),
                "humidity": float(row["humidity"]),
                "load": float(row["load"]),
                "maintenance_level": float(row["maintenance"] or 0.0),
                "is_shock": bool(row["is_shock"]),
                "steps_since_maintenance": steps_since_maintenance,
                "cumulative_shocks": cumulative_shocks,
            },
            "recoating": {
                "subsystem_health": float(row["health_recoating"]),
                "blade": _component_state(row, "blade", predictions["blade"]),
                "motor": _component_state(row, "motor", predictions["motor"]),
                "rail": _component_state(row, "rail", predictions["rail"]),
            },
            "printhead": {
                "subsystem_health": float(row["health_printhead"]),
                "nozzle": _component_state(row, "nozzle", predictions["nozzle"]),
                "resistor": _component_state(row, "resistor", predictions["resistor"]),
                "cleaning": _component_state(row, "cleaning", predictions["cleaning"]),
            },
            "thermal": {
                "subsystem_health": float(row["health_thermal"]),
                "heater": _component_state(row, "heater", predictions["heater"]),
                "sensor": _component_state(row, "sensor", predictions["sensor"]),
                "insulation": _component_state(row, "insulation", predictions["insulation"]),
            },
            "model_predictions": predictions,
            "maintenance_recommendation": {
                "action": action,
                "action_label": ACTION_LABELS[action],
                "maintenance_level": maintenance_level,
                "reward": round(float(reward), 6),
            },
        }
        joined["alerts"] = _make_alerts(joined)
        all_joined.append(joined)

        for component in COMPONENTS:
            prev_health[component] = float(row[f"health_{component}"])
        previous_report = report

    return all_joined


def _build_joined_rows(
    conn: sqlite3.Connection,
    scenario_id: str,
    run_number: int,
    start_t: int,
    end_t: int,
) -> list[dict[str, Any]]:
    """
    Build joined rows for the specified range. Uses caching for efficiency.

    Since each tick depends on previous state, we must compute from t=0.
    We cache the full timeline up to end_t and slice the requested range.
    """
    cache_key = (scenario_id, run_number, end_t)

    # Check if we have cached results for this timeline
    if cache_key not in _joined_rows_cache:
        # Compute and cache the full timeline
        _joined_rows_cache[cache_key] = _compute_full_timeline(conn, scenario_id, run_number, end_t)

    # Return the requested slice
    full_timeline = _joined_rows_cache[cache_key]
    return [row for row in full_timeline if start_t <= row["t"] <= end_t]


def _state_at(conn: sqlite3.Connection, scenario_id: str, run_number: int, t: int) -> dict[str, Any]:
    rows = _build_joined_rows(conn, scenario_id, run_number, t, t)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No row at scenario_id={scenario_id!r} run_number={run_number} t={t}",
        )
    return rows[0]


@app.get("/api/health")
def health() -> dict[str, Any]:
    classifier_count = len(list(ARTIFACTS_DIR.glob("*_classifier.pt"))) if ARTIFACTS_DIR.exists() else 0
    loaded_classifiers = False
    loaded_dqn = False
    classifier_error = None
    dqn_error = None
    try:
        loaded_classifiers = len(get_classifiers()) == len(COMPONENTS)
    except Exception as exc:  # pragma: no cover - health endpoint should expose the issue
        classifier_error = str(exc)
    try:
        loaded_dqn = get_dqn() is not None
    except Exception as exc:  # pragma: no cover
        dqn_error = str(exc)
    return {
        "status": "ok" if DB_PATH.exists() and loaded_classifiers and loaded_dqn else "degraded",
        "db_path": str(DB_PATH),
        "db_exists": DB_PATH.exists(),
        "classifier_artifacts": classifier_count,
        "classifiers_loaded": loaded_classifiers,
        "classifier_error": classifier_error,
        "dqn_path": str(DQN_PATH),
        "dqn_loaded": loaded_dqn,
        "dqn_error": dqn_error,
        "cache_entries": len(_joined_rows_cache),
        "cache_keys": list(_joined_rows_cache.keys()),
    }


@app.post("/api/cache/clear")
def clear_cache() -> dict[str, Any]:
    """Clear the in-memory joined rows cache. Useful for development."""
    cleared_count = len(_joined_rows_cache)
    _joined_rows_cache.clear()
    return {
        "status": "ok",
        "message": f"Cleared {cleared_count} cache entries",
    }


@app.get("/api/scenarios")
def list_scenarios(db: DB) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT scenario_id,
               COUNT(DISTINCT run_id) AS run_count,
               MIN(t) AS min_t,
               MAX(t) AS max_t,
               COUNT(*) AS row_count
        FROM simulation_log
        GROUP BY scenario_id
        ORDER BY scenario_id
        """
    ).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/runs/{scenario_id}/timeline")
def get_timeline(
    scenario_id: str,
    db: DB,
    run_number: int = Query(default=0, ge=0),
    start_t: int = Query(default=0, ge=0),
    end_t: int = Query(default=999, ge=0),
) -> list[dict[str, Any]]:
    if end_t < start_t:
        raise HTTPException(status_code=400, detail="end_t must be >= start_t")
    return _build_joined_rows(db, scenario_id, run_number, start_t, end_t)


@app.get("/api/runs/{scenario_id}/state/at/{t}")
def get_state_at(
    scenario_id: str,
    t: int,
    db: DB,
    run_number: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return _state_at(db, scenario_id, run_number, t)


@app.get("/api/runs/{scenario_id}/state/latest")
def get_latest_state(
    scenario_id: str,
    db: DB,
    run_number: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    row = db.execute(
        "SELECT MAX(t) AS max_t FROM simulation_log WHERE scenario_id = ? AND run_id = ?",
        (scenario_id, run_number),
    ).fetchone()
    if row is None or row["max_t"] is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _state_at(db, scenario_id, run_number, int(row["max_t"]))


@app.get("/api/runs/{scenario_id}/alerts/at/{t}")
def get_alerts_at(
    scenario_id: str,
    t: int,
    db: DB,
    run_number: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return _state_at(db, scenario_id, run_number, t)["alerts"]


@app.get("/api/runs/{scenario_id}/history")
def get_history(
    scenario_id: str,
    db: DB,
    run_number: int = Query(default=0, ge=0),
    start_t: int = Query(default=0, ge=0),
    end_t: int = Query(default=999, ge=0),
) -> list[dict[str, Any]]:
    timeline = _build_joined_rows(db, scenario_id, run_number, start_t, end_t)
    return [
        {
            "t": row["t"],
            "temperature": row["drivers"]["temperature"],
            "humidity": row["drivers"]["humidity"],
            "health_recoating": row["recoating"]["subsystem_health"],
            "health_printhead": row["printhead"]["subsystem_health"],
            "health_thermal": row["thermal"]["subsystem_health"],
            "status_blade": row["recoating"]["blade"]["status"],
            "status_nozzle": row["printhead"]["nozzle"]["status"],
            "status_heater": row["thermal"]["heater"]["status"],
            "health_blade": row["recoating"]["blade"]["health"],
            "health_motor": row["recoating"]["motor"]["health"],
            "health_rail": row["recoating"]["rail"]["health"],
            "health_nozzle": row["printhead"]["nozzle"]["health"],
            "health_resistor": row["printhead"]["resistor"]["health"],
            "health_cleaning": row["printhead"]["cleaning"]["health"],
            "health_heater": row["thermal"]["heater"]["health"],
            "health_sensor": row["thermal"]["sensor"]["health"],
            "health_insulation": row["thermal"]["insulation"]["health"],
        }
        for row in timeline
    ]


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: DB) -> ChatResponse:
    row = (
        _state_at(db, req.scenario_id, req.run_number, req.t)
        if req.t is not None
        else get_latest_state(req.scenario_id, db, req.run_number)
    )
    alerts = row["alerts"]
    top_alert = alerts[0] if alerts else None
    severity = top_alert["severity"] if top_alert else "INFO"
    maintenance = row["maintenance_recommendation"]

    if top_alert:
        summary = top_alert["summary"][:140]
        answer = (
            f"At t={row['t']}, the highest-priority issue is {top_alert['component']} in the "
            f"{top_alert['subsystem']} subsystem. {top_alert['summary']} "
            f"The DQN policy recommends {maintenance['action_label'].replace('_', ' ')} "
            f"(maintenance level {maintenance['maintenance_level']})."
        )
        reasoning = top_alert["reasoning"]
        citations = [Citation(**citation) for citation in top_alert["citations"]]
        actions = top_alert["actions"]
    else:
        summary = "All monitored components are functional."
        answer = (
            f"At t={row['t']}, Phase 1 predicts all monitored components as functional. "
            f"The DQN policy recommends {maintenance['action_label'].replace('_', ' ')}."
        )
        reasoning = [
            "No backend alerts are active for this tick.",
            "All Phase 1 component classifiers returned FUNCTIONAL.",
            f"DQN selected action {maintenance['action']} ({maintenance['action_label']}).",
        ]
        citations = [
            Citation(
                run_id=row["scenario_id"],
                run_number=row["run_number"],
                t=row["t"],
                field="health_recoating",
                value=row["recoating"]["subsystem_health"],
            )
        ]
        actions = ["Continue monitoring", "Keep current maintenance plan"]

    # The deterministic path is intentionally used when no provider key is present.
    if not os.getenv("ANTHROPIC_API_KEY"):
        return ChatResponse(
            severity=severity,
            summary=summary,
            answer=answer,
            reasoning_summary=reasoning[:5],
            citations=citations,
            recommended_actions=actions,
        )

    return ChatResponse(
        severity=severity,
        summary=summary,
        answer=answer,
        reasoning_summary=reasoning[:5],
        citations=citations,
        recommended_actions=actions,
    )
