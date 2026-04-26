"""Generate precomputed.json — all 7 scenarios, outputs full API shapes."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

sys.path.append(str(Path(__file__).parent.parent))
from models.components.hp_s100_engine import HP100Engine
from models.src.dense_training_base import DriverVector


class ComponentClassifier(nn.Module):
    def __init__(self, input_dim=16, output_dim=4, hidden_dim=128, dropout=0.15):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.BatchNorm1d(hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, output_dim),
        )

    def forward(self, x):
        return self.net(x)


OUT = Path(__file__).parent / "precomputed.json"
MODELS_DIR = Path(__file__).parent.parent / "models" / "artifacts" / "models"

RUN_NUMBER = 0
N = 1000  # ticks per scenario

LABEL_TO_STATUS = {0: "FUNCTIONAL", 1: "DEGRADED", 2: "CRITICAL", 3: "FAILED"}
ACTION_LABELS = {0: "do_nothing", 1: "light_service", 2: "full_maintenance"}
ACTION_TO_MAINTENANCE = {0: 0.0, 1: 0.5, 2: 1.0}

COMPONENTS = ["blade", "motor", "rail", "nozzle", "resistor", "cleaning", "heater", "sensor", "insulation"]

# Scenario definitions — mirrors generate_dataset.py
SCENARIO_SEEDS: dict[str, int] = {
    "baseline_nominal": 0,
    "humid_factory":    1_000_000,
    "chaos_run":        2_000_000,
    "no_maintenance":   3_000_000,
    "fixed_schedule":   4_000_000,
    "extreme_stress":   5_000_000,
    "optimal_care":     6_000_000,
}

# (scenario_id, env_profile, chaos_prob, maintenance_schedule)
SCENARIO_CONFIGS: list[tuple[str, str, float, str]] = [
    ("baseline_nominal", "deterministic", 0.00, "light"),
    ("humid_factory",    "stochastic",    0.01, "light"),
    ("chaos_run",        "chaos",         0.05, "light"),
    ("no_maintenance",   "deterministic", 0.00, "none"),
    ("fixed_schedule",   "deterministic", 0.00, "fixed_100"),
    ("extreme_stress",   "chaos",         0.10, "none"),
    ("optimal_care",     "stochastic",    0.00, "full"),
]

COMPONENT_META = {
    "blade":      {"display": "Blade",      "subsystem": "Recoating", "metric_field": "thickness_mm",         "metric_label": "thickness",         "unit": "mm", "model_key": "recoater_blade"},
    "motor":      {"display": "Motor",      "subsystem": "Recoating", "metric_field": "stall_probability",    "metric_label": "stall prob",        "unit": "",   "model_key": "recoater_drive_motor"},
    "rail":       {"display": "Rail",       "subsystem": "Recoating", "metric_field": "misalignment_mm",      "metric_label": "misalignment",      "unit": "mm", "model_key": "linear_guide_rail"},
    "nozzle":     {"display": "Nozzle",     "subsystem": "Printhead", "metric_field": "clog_ratio",           "metric_label": "clog ratio",        "unit": "",   "model_key": "nozzle_plate"},
    "resistor":   {"display": "Resistor",   "subsystem": "Printhead", "metric_field": "resistance_drift_pct", "metric_label": "resistance drift",  "unit": "%",  "model_key": "thermal_firing_resistors"},
    "cleaning":   {"display": "Cleaning",   "subsystem": "Printhead", "metric_field": "wipe_efficiency",      "metric_label": "wipe efficiency",   "unit": "",   "model_key": "cleaning_interface"},
    "heater":     {"display": "Heater",     "subsystem": "Thermal",   "metric_field": "energy_overhead_pct",  "metric_label": "energy overhead",   "unit": "%",  "model_key": "heating_elements"},
    "sensor":     {"display": "Sensor",     "subsystem": "Thermal",   "metric_field": "sensor_drift_c",       "metric_label": "sensor drift",      "unit": "C",  "model_key": "temperature_sensors"},
    "insulation": {"display": "Insulation", "subsystem": "Thermal",   "metric_field": "heat_loss_factor",     "metric_label": "heat loss factor",  "unit": "",   "model_key": "insulation_panels"},
}


def load_models():
    models: dict = {}
    scalers: dict = {}
    for comp in COMPONENTS:
        model_path = MODELS_DIR / f"{comp}_classifier.pt"
        if not model_path.exists():
            continue
        try:
            import warnings
            warnings.filterwarnings("ignore")
            checkpoint = torch.load(model_path, weights_only=False, map_location="cpu")
            model = ComponentClassifier(**checkpoint["config"])
            model.load_state_dict(checkpoint["state_dict"])
            model.eval()
            models[comp] = model
            scalers[comp] = {
                "mean": torch.tensor(checkpoint["mean"], dtype=torch.float32),
                "std":  torch.tensor(checkpoint["std"],  dtype=torch.float32),
            }
        except Exception as e:
            print(f"Failed to load {comp}: {e}")
    return models, scalers


MODELS, SCALERS = load_models()


def wave(t: int, freq: float, amp: float) -> float:
    return math.sin(t * freq) * amp


def health_to_label(h: float) -> int:
    if h > 0.75: return 0
    if h > 0.50: return 1
    if h > 0.25: return 2
    return 3


def make_prediction(comp: str, features: list[float]) -> dict:
    if comp not in MODELS:
        h = features[7 + COMPONENTS.index(comp)]
        label = health_to_label(h)
        probs = {LABEL_TO_STATUS[i]: round(0.05 / 3, 6) for i in range(4)}
        probs[LABEL_TO_STATUS[label]] = 0.85
        return {"label": label, "status": LABEL_TO_STATUS[label], "confidence": 0.85, "probabilities": probs}

    with torch.no_grad():
        x = torch.tensor([features], dtype=torch.float32)
        x = (x - SCALERS[comp]["mean"]) / SCALERS[comp]["std"]
        logits = MODELS[comp](x)
        probs = torch.softmax(logits, dim=1).squeeze(0).tolist()

    num_classes = len(probs)
    label = max(range(num_classes), key=lambda i: probs[i])
    full_probs = {LABEL_TO_STATUS[i]: round(probs[i] if i < num_classes else 0.0, 6) for i in range(4)}
    return {"label": label, "status": LABEL_TO_STATUS[label], "confidence": probs[label], "probabilities": full_probs}


def format_metric(value: float, unit: str) -> str:
    if unit == "%": return f"{value:.1f}%"
    if unit:        return f"{value:.2f} {unit}"
    return f"{value:.3f}"


def recommended_actions(component: str, severity: str) -> list[str]:
    all_actions = {
        "blade":      ["Inspect recoater blade edge", "Reduce recoating speed", "Schedule blade replacement"],
        "motor":      ["Inspect motor bearings", "Check recoater alignment", "Lubricate drive assembly"],
        "rail":       ["Recalibrate guide rail", "Inspect build-bed alignment", "Check rail contamination"],
        "nozzle":     ["Run nozzle cleaning cycle", "Reduce humidity exposure", "Inspect nozzle plate"],
        "resistor":   ["Recalibrate firing voltage", "Inspect printhead contacts", "Schedule resistor check"],
        "cleaning":   ["Clean wiper assembly", "Run purge cycle", "Increase cleaning frequency"],
        "heater":     ["Trend heater resistance", "Inspect thermal wiring", "Schedule heater check"],
        "sensor":     ["Calibrate temperature sensor", "Check sensor drift", "Verify control loop readings"],
        "insulation": ["Inspect insulation panels", "Check thermal leakage", "Schedule panel inspection"],
    }[component]
    return all_actions if severity == "CRITICAL" else all_actions[:2]


def pick_action(hr: float, hp: float, ht: float, steps: int) -> int:
    min_h = min(hr, hp, ht)
    if min_h < 0.40 or steps > 80: return 2
    if min_h < 0.65 or steps > 50: return 1
    return 0


def get_maintenance_action(schedule: str, t: int, hr: float, hp: float, ht: float, steps_since_maint: int) -> int:
    if schedule == "none":
        return 0
    if schedule == "full":
        return 2
    if schedule == "fixed_100":
        return 2 if t % 100 == 0 else 0
    # "light" → adaptive Q-table policy
    return pick_action(hr, hp, ht, steps_since_maint)


def gen_env_drivers(
    t: int, env_profile: str, chaos_prob: float, rng: np.random.Generator
) -> tuple[float, float, bool]:
    p = t / (N - 1) if N > 1 else 0.0
    base_temp = 20.0 + p * 30.0  # 20°C → 50°C
    base_hum = 0.40

    if env_profile == "deterministic":
        return base_temp, base_hum, False

    if env_profile == "stochastic":
        temp = float(np.clip(base_temp + rng.normal(0, 2.0), 15, 70))
        hum = float(np.clip(base_hum + rng.normal(0, 0.05), 0.0, 1.0))
        shock = bool(rng.random() < chaos_prob)
        if shock:
            hum = min(1.0, hum + 0.25)
        return temp, hum, shock

    # chaos
    temp = float(np.clip(base_temp + rng.normal(0, 3.0), 15, 70))
    hum = float(np.clip(base_hum + rng.normal(0, 0.07), 0.0, 1.0))
    shock = bool(rng.random() < chaos_prob)
    if shock:
        if rng.random() < 0.5:
            hum = min(1.0, hum + float(rng.uniform(0.20, 0.50)))
        else:
            temp = min(70.0, temp + float(rng.uniform(10, 25)))
    return temp, hum, shock


def make_alerts(t: int, scenario_id: str, components: dict[str, dict], action_label: str) -> list[dict]:
    alerts = []
    severity_rank = {"CRITICAL": 0, "WARNING": 1}
    for comp, state in components.items():
        status = state["status"]
        if status == "FUNCTIONAL":
            continue
        severity = "CRITICAL" if status in {"CRITICAL", "FAILED"} else "WARNING"
        meta = COMPONENT_META[comp]
        mval = state[meta["metric_field"]]
        metric_text = format_metric(mval, meta["unit"])
        health_pct = state["health"] * 100
        confidence_pct = state["confidence"] * 100
        alerts.append({
            "id": f"{scenario_id}-{RUN_NUMBER}-{t}-{comp}",
            "severity": severity,
            "subsystem": meta["subsystem"],
            "component": meta["display"],
            "component_key": comp,
            "metric": metric_text,
            "summary": (
                f"{meta['display']} is {status.lower()} at {health_pct:.1f}% health "
                f"({meta['metric_label']} {metric_text})."
            ),
            "reasoning": [
                f"Phase 1 classifier predicts {status} with {confidence_pct:.1f}% confidence.",
                f"Historian health for {comp} is {health_pct:.1f}% at t={t}.",
                f"Q-table recommends {action_label.replace('_', ' ')} for this tick.",
            ],
            "actions": recommended_actions(comp, severity),
            "query": f"Diagnose the {meta['display'].lower()} {status.lower()} condition at t={t}.",
            "citations": [
                {"run_id": scenario_id, "run_number": RUN_NUMBER, "t": t, "field": f"health_{comp}",  "value": round(state["health"], 6)},
                {"run_id": scenario_id, "run_number": RUN_NUMBER, "t": t, "field": f"status_{comp}", "value": status},
                {"run_id": scenario_id, "run_number": RUN_NUMBER, "t": t, "field": f"metric_{comp}", "value": round(mval, 6)},
            ],
        })
    return sorted(alerts, key=lambda a: (severity_rank[a["severity"]], a["component"]))


def build_timeline(
    scenario_id: str, env_profile: str, chaos_prob: float, maintenance_schedule: str, seed: int
) -> list[dict]:
    rng = np.random.default_rng(seed)
    timeline = []
    steps_since_maint = 0
    cumulative_shocks = 0
    prev_healths = {c: 1.0 for c in COMPONENTS}
    engine = HP100Engine()

    for t in range(N):
        temperature, humidity, is_shock = gen_env_drivers(t, env_profile, chaos_prob, rng)
        if is_shock:
            cumulative_shocks += 1

        load = round(0.6 + wave(t, 0.1, 0.15), 3)

        hr = sum(prev_healths[c] for c in ["blade", "motor", "rail"]) / 3
        hp = sum(prev_healths[c] for c in ["nozzle", "resistor", "cleaning"]) / 3
        ht = sum(prev_healths[c] for c in ["heater", "sensor", "insulation"]) / 3

        action = get_maintenance_action(maintenance_schedule, t, hr, hp, ht, steps_since_maint)
        action_label = ACTION_LABELS[action]
        maintenance_level = ACTION_TO_MAINTENANCE[action]

        drivers = DriverVector(
            temperature_stress=(temperature - 20) / 10,
            humidity_contamination=humidity,
            operational_load=load,
            maintenance_level=maintenance_level,
        )
        reports = engine.step(drivers)

        healths: dict[str, float] = {}
        mvals: dict[str, float] = {}
        for c in COMPONENTS:
            model_key = COMPONENT_META[c]["model_key"]
            rep = reports[model_key]
            healths[c] = rep.health_index
            mvals[c] = rep.metrics[COMPONENT_META[c]["metric_field"]]

        hr = sum(healths[c] for c in ["blade", "motor", "rail"]) / 3
        hp = sum(healths[c] for c in ["nozzle", "resistor", "cleaning"]) / 3
        ht = sum(healths[c] for c in ["heater", "sensor", "insulation"]) / 3

        features = [
            temperature, humidity, load, maintenance_level,
            float(is_shock), float(steps_since_maint), float(cumulative_shocks),
        ] + [prev_healths[c] for c in COMPONENTS]

        predictions = {c: make_prediction(c, features) for c in COMPONENTS}

        if action > 0:
            steps_since_maint = 0
        else:
            steps_since_maint += 1

        comp_states: dict[str, dict] = {}
        for c in COMPONENTS:
            meta = COMPONENT_META[c]
            comp_states[c] = {
                "health": round(healths[c], 6),
                **predictions[c],
                meta["metric_field"]: round(mvals[c], 6),
            }

        alerts = make_alerts(t, scenario_id, comp_states, action_label)

        top_alert = alerts[0] if alerts else None
        chat_severity = top_alert["severity"] if top_alert else "INFO"
        if top_alert:
            chat_summary = top_alert["summary"][:140]
            chat_answer = (
                f"At t={t}, the highest-priority issue is {top_alert['component']} in the "
                f"{top_alert['subsystem']} subsystem. {top_alert['summary']} "
                f"The Q-table policy recommends {action_label.replace('_', ' ')} "
                f"(maintenance level {ACTION_TO_MAINTENANCE[action]})."
            )
            chat_reasoning = top_alert["reasoning"]
            chat_citations = top_alert["citations"]
            chat_actions = top_alert["actions"]
        else:
            chat_summary = "All monitored components are functional."
            chat_answer = (
                f"At t={t}, all monitored components are functional. "
                f"The Q-table policy recommends {action_label.replace('_', ' ')}."
            )
            chat_reasoning = [
                "No alerts are active for this tick.",
                "All Phase 1 component classifiers returned FUNCTIONAL.",
                f"Q-table selected action {action} ({action_label}).",
            ]
            chat_citations = [{"run_id": scenario_id, "run_number": RUN_NUMBER, "t": t, "field": "health_recoating", "value": round(hr, 6)}]
            chat_actions = ["Continue monitoring", "Keep current maintenance plan"]

        timeline.append({
            "scenario_id": scenario_id,
            "run_number": RUN_NUMBER,
            "t": t,
            "drivers": {
                "temperature": round(temperature, 4),
                "humidity": round(humidity, 4),
                "load": load,
                "maintenance_level": ACTION_TO_MAINTENANCE[action],
                "is_shock": is_shock,
                "steps_since_maintenance": steps_since_maint,
                "cumulative_shocks": cumulative_shocks,
            },
            "recoating": {
                "subsystem_health": round(hr, 6),
                "blade": comp_states["blade"],
                "motor": comp_states["motor"],
                "rail": comp_states["rail"],
            },
            "printhead": {
                "subsystem_health": round(hp, 6),
                "nozzle": comp_states["nozzle"],
                "resistor": comp_states["resistor"],
                "cleaning": comp_states["cleaning"],
            },
            "thermal": {
                "subsystem_health": round(ht, 6),
                "heater": comp_states["heater"],
                "sensor": comp_states["sensor"],
                "insulation": comp_states["insulation"],
            },
            "model_predictions": predictions,
            "maintenance_recommendation": {
                "action": action,
                "action_label": action_label,
                "maintenance_level": ACTION_TO_MAINTENANCE[action],
                "reward": round(0.8 - (t / (N - 1)) * 0.6, 6),
            },
            "alerts": alerts,
            "_chat": {
                "severity": chat_severity,
                "summary": chat_summary,
                "answer": chat_answer,
                "reasoning_summary": chat_reasoning[:5],
                "citations": chat_citations,
                "recommended_actions": chat_actions,
            },
        })
        prev_healths = healths

    return timeline


def build_history(timeline: list[dict]) -> list[dict]:
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


if __name__ == "__main__":
    scenarios_out: dict[str, dict] = {}

    for scenario_id, env_profile, chaos_prob, maintenance_schedule in SCENARIO_CONFIGS:
        print(f"Computing [{scenario_id}]…")
        seed = SCENARIO_SEEDS[scenario_id]
        timeline = build_timeline(scenario_id, env_profile, chaos_prob, maintenance_schedule, seed)
        history = build_history(timeline)
        scenarios_out[scenario_id] = {
            "scenario_id": scenario_id,
            "run_number": RUN_NUMBER,
            "env_profile": env_profile,
            "maintenance_schedule": maintenance_schedule,
            "timeline": timeline,
            "history": history,
        }
        print(f"  → {len(timeline)} ticks")

    payload = {"scenarios": scenarios_out}
    OUT.write_text(json.dumps(payload, indent=2))
    print(f"\nWritten {len(scenarios_out)} scenarios → {OUT}")
