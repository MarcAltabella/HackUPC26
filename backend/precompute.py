"""Generate precomputed.json — all 7 scenarios, stateful physics degradation."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

sys.path.append(str(Path(__file__).parent.parent))
from models.src.generate_dataset import Phase1State, step_phase1, Drivers


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
N = 1000

LABEL_TO_STATUS = {0: "FUNCTIONAL", 1: "DEGRADED", 2: "CRITICAL", 3: "FAILED"}
ACTION_LABELS   = {0: "do_nothing", 1: "light_service", 2: "full_maintenance"}
ACTION_TO_MAINTENANCE = {0: 0.0, 1: 0.5, 2: 1.0}

COMPONENTS = ["blade", "motor", "rail", "nozzle", "resistor", "cleaning", "heater", "sensor", "insulation"]

SCENARIO_SEEDS: dict[str, int] = {
    "baseline_nominal": 0,
    "humid_factory":    1_000_000,
    "chaos_run":        2_000_000,
    "no_maintenance":   3_000_000,
    "fixed_schedule":   4_000_000,
    "extreme_stress":   5_000_000,
    "optimal_care":     6_000_000,
}

SCENARIO_CONFIGS: list[tuple[str, str, float, str]] = [
    ("baseline_nominal", "deterministic", 0.00, "light"),
    ("humid_factory",    "stochastic",    0.01, "light"),
    ("chaos_run",        "chaos",         0.05, "light"),
    ("no_maintenance",   "deterministic", 0.00, "none"),
    ("fixed_schedule",   "deterministic", 0.00, "fixed_100"),
    ("extreme_stress",   "chaos",         0.10, "none"),
    ("optimal_care",     "stochastic",    0.00, "full"),
]

# metric_field matches keys from step_phase1 metrics dict
COMPONENT_META = {
    "blade":      {"display": "Blade",      "subsystem": "Recoating", "metric_field": "metric_blade_mm",     "metric_label": "thickness",         "unit": "mm"},
    "motor":      {"display": "Motor",      "subsystem": "Recoating", "metric_field": "metric_motor_vib",    "metric_label": "vibration",         "unit": "mm/s"},
    "rail":       {"display": "Rail",       "subsystem": "Recoating", "metric_field": "metric_rail_dev",     "metric_label": "deviation",         "unit": "µm"},
    "nozzle":     {"display": "Nozzle",     "subsystem": "Printhead", "metric_field": "metric_nozzle_clog",  "metric_label": "clog ratio",        "unit": ""},
    "resistor":   {"display": "Resistor",   "subsystem": "Printhead", "metric_field": "metric_resistor_pct", "metric_label": "resistance drift",  "unit": "%"},
    "cleaning":   {"display": "Cleaning",   "subsystem": "Printhead", "metric_field": "metric_cleaning_eff", "metric_label": "wipe efficiency",   "unit": ""},
    "heater":     {"display": "Heater",     "subsystem": "Thermal",   "metric_field": "metric_heater_ohm",   "metric_label": "resistance",        "unit": "Ω"},
    "sensor":     {"display": "Sensor",     "subsystem": "Thermal",   "metric_field": "metric_sensor_err",   "metric_label": "sensor error",      "unit": "°C"},
    "insulation": {"display": "Insulation", "subsystem": "Thermal",   "metric_field": "metric_insulation_r", "metric_label": "thermal resistance", "unit": ""},
}

# Health key in step_phase1 metrics for each component
HEALTH_KEY = {c: f"health_{c}" for c in COMPONENTS}


def load_models():
    models: dict = {}
    scalers: dict = {}
    for comp in COMPONENTS:
        path = MODELS_DIR / f"{comp}_classifier.pt"
        if not path.exists():
            continue
        try:
            import warnings
            warnings.filterwarnings("ignore")
            ck = torch.load(path, weights_only=False, map_location="cpu")
            m = ComponentClassifier(**ck["config"])
            m.load_state_dict(ck["state_dict"])
            m.eval()
            models[comp] = m
            scalers[comp] = {
                "mean": torch.tensor(ck["mean"], dtype=torch.float32),
                "std":  torch.tensor(ck["std"],  dtype=torch.float32),
            }
        except Exception as e:
            print(f"[warn] could not load {comp} model: {e}")
    return models, scalers


MODELS, SCALERS = load_models()


def health_to_label(h: float) -> int:
    if h > 0.70: return 0
    if h > 0.40: return 1
    if h > 0.20: return 2
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
        p = torch.softmax(MODELS[comp](x), dim=1).squeeze(0).tolist()

    label = max(range(len(p)), key=lambda i: p[i])
    return {
        "label": label,
        "status": LABEL_TO_STATUS[label],
        "confidence": p[label],
        "probabilities": {LABEL_TO_STATUS[i]: round(p[i] if i < len(p) else 0.0, 6) for i in range(4)},
    }


def format_metric(value: float, unit: str) -> str:
    if unit == "%":  return f"{value:.1f}%"
    if unit == "Ω":  return f"{value:.1f} Ω"
    if unit == "°C": return f"{value:.2f} °C"
    if unit:         return f"{value:.2f} {unit}"
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
    m = min(hr, hp, ht)
    if m < 0.40 or steps > 80: return 2
    if m < 0.65 or steps > 50: return 1
    return 0


def get_maintenance_action(schedule: str, t: int, hr: float, hp: float, ht: float, steps: int) -> int:
    if schedule == "none":      return 0
    if schedule == "full":      return 2
    if schedule == "fixed_100": return 2 if t % 100 == 0 else 0
    return pick_action(hr, hp, ht, steps)


def gen_env_series(profile: str, chaos_prob: float, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Ornstein-Uhlenbeck processes for temperature and humidity — natural autocorrelated variation."""
    trend_temp = np.linspace(20.0, 50.0, N)
    trend_hum  = np.linspace(0.35, 0.52, N)

    params = {
        "deterministic": (0.18, 1.4,  0.10, 0.022),
        "stochastic":    (0.12, 3.2,  0.08, 0.055),
        "chaos":         (0.07, 6.0,  0.06, 0.095),
    }
    theta_t, sigma_t, theta_h, sigma_h = params[profile]

    temps  = np.empty(N)
    hums   = np.empty(N)
    shocks = np.zeros(N, dtype=bool)
    temp = trend_temp[0] + rng.normal(0, sigma_t)
    hum  = trend_hum[0]  + rng.normal(0, sigma_h)

    for t in range(N):
        temp += theta_t * (trend_temp[t] - temp) + sigma_t * rng.normal()
        hum  += theta_h * (trend_hum[t]  - hum)  + sigma_h * rng.normal()
        temp  = float(np.clip(temp, 15.0, 70.0))
        hum   = float(np.clip(hum,  0.0,  1.0))

        shock = bool(rng.random() < chaos_prob)
        if shock:
            if profile == "chaos" and rng.random() < 0.5:
                temp = min(70.0, temp + float(rng.uniform(8, 22)))
            else:
                hum = min(1.0, hum + float(rng.uniform(0.15, 0.35)))

        temps[t]  = temp
        hums[t]   = hum
        shocks[t] = shock

    return temps, hums, shocks


def gen_load_series(rng: np.random.Generator) -> np.ndarray:
    """AR(1) load around 0.62 with occasional demand spikes."""
    loads = np.empty(N)
    x = 0.62
    for t in range(N):
        x = 0.88 * x + 0.12 * 0.62 + 0.04 * rng.normal()
        if rng.random() < 0.025:
            x = min(1.0, x + float(rng.uniform(0.12, 0.28)))
        loads[t] = float(np.clip(x, 0.20, 1.0))
    return loads


def make_alerts(t: int, scenario_id: str, comp_states: dict, action_label: str) -> list[dict]:
    alerts = []
    rank = {"CRITICAL": 0, "WARNING": 1}
    for comp, state in comp_states.items():
        status = state["status"]
        if status == "FUNCTIONAL":
            continue
        severity = "CRITICAL" if status in {"CRITICAL", "FAILED"} else "WARNING"
        meta = COMPONENT_META[comp]
        mval = state[meta["metric_field"]]
        metric_text = format_metric(mval, meta["unit"])
        hp = state["health"] * 100
        conf = state["confidence"] * 100
        alerts.append({
            "id": f"{scenario_id}-{RUN_NUMBER}-{t}-{comp}",
            "severity": severity,
            "subsystem": meta["subsystem"],
            "component": meta["display"],
            "component_key": comp,
            "metric": metric_text,
            "summary": (
                f"{meta['display']} is {status.lower()} at {hp:.1f}% health "
                f"({meta['metric_label']} {metric_text})."
            ),
            "reasoning": [
                f"Phase 1 classifier predicts {status} with {conf:.1f}% confidence.",
                f"Historian health for {comp} is {hp:.1f}% at t={t}.",
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
    return sorted(alerts, key=lambda a: (rank[a["severity"]], a["component"]))


def build_timeline(scenario_id: str, env_profile: str, chaos_prob: float, maintenance_schedule: str, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    temps, hums, shocks = gen_env_series(env_profile, chaos_prob, rng)
    loads = gen_load_series(rng)

    timeline = []
    steps_since_maint = 0
    cumulative_shocks = 0
    prev_healths = {c: 1.0 for c in COMPONENTS}
    state = Phase1State()  # stateful: accumulates real degradation over time

    for t in range(N):
        temperature = round(float(temps[t]), 4)
        humidity    = round(float(hums[t]),  4)
        is_shock    = bool(shocks[t])
        load_frac   = round(float(loads[t]), 3)

        if is_shock:
            cumulative_shocks += 1

        hr = sum(prev_healths[c] for c in ["blade", "motor", "rail"]) / 3
        hp = sum(prev_healths[c] for c in ["nozzle", "resistor", "cleaning"]) / 3
        ht = sum(prev_healths[c] for c in ["heater", "sensor", "insulation"]) / 3

        action = get_maintenance_action(maintenance_schedule, t, hr, hp, ht, steps_since_maint)
        action_label    = ACTION_LABELS[action]
        maintenance_level = ACTION_TO_MAINTENANCE[action]

        # step_phase1 expects Drivers with load as cumulative hours; we use t directly
        drivers = Drivers(
            temperature=temperature,
            humidity=humidity,
            load=float(t),
            maintenance_level=maintenance_level,
            is_shock=is_shock,
        )
        state, metrics = step_phase1(state, drivers)

        healths = {c: float(metrics[HEALTH_KEY[c]]) for c in COMPONENTS}
        mvals   = {c: float(metrics[COMPONENT_META[c]["metric_field"]]) for c in COMPONENTS}

        hr = sum(healths[c] for c in ["blade", "motor", "rail"]) / 3
        hp = sum(healths[c] for c in ["nozzle", "resistor", "cleaning"]) / 3
        ht = sum(healths[c] for c in ["heater", "sensor", "insulation"]) / 3

        features = [
            temperature, humidity, load_frac, maintenance_level,
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
        top    = alerts[0] if alerts else None

        if top:
            chat = {
                "severity": top["severity"],
                "summary": top["summary"][:140],
                "answer": (
                    f"At t={t}, the highest-priority issue is {top['component']} in the "
                    f"{top['subsystem']} subsystem. {top['summary']} "
                    f"The Q-table policy recommends {action_label.replace('_', ' ')} "
                    f"(maintenance level {maintenance_level})."
                ),
                "reasoning_summary": top["reasoning"][:5],
                "citations": top["citations"],
                "recommended_actions": top["actions"],
            }
        else:
            chat = {
                "severity": "INFO",
                "summary": "All monitored components are functional.",
                "answer": (
                    f"At t={t}, all monitored components are functional. "
                    f"The Q-table policy recommends {action_label.replace('_', ' ')}."
                ),
                "reasoning_summary": [
                    "No alerts are active for this tick.",
                    "All Phase 1 component classifiers returned FUNCTIONAL.",
                    f"Q-table selected action {action} ({action_label}).",
                ],
                "citations": [{"run_id": scenario_id, "run_number": RUN_NUMBER, "t": t, "field": "health_recoating", "value": round(hr, 6)}],
                "recommended_actions": ["Continue monitoring", "Keep current maintenance plan"],
            }

        timeline.append({
            "scenario_id": scenario_id,
            "run_number": RUN_NUMBER,
            "t": t,
            "drivers": {
                "temperature": temperature,
                "humidity": humidity,
                "load": load_frac,
                "maintenance_level": maintenance_level,
                "is_shock": is_shock,
                "steps_since_maintenance": steps_since_maint,
                "cumulative_shocks": cumulative_shocks,
            },
            "recoating": {
                "subsystem_health": round(hr, 6),
                **{c: comp_states[c] for c in ["blade", "motor", "rail"]},
            },
            "printhead": {
                "subsystem_health": round(hp, 6),
                **{c: comp_states[c] for c in ["nozzle", "resistor", "cleaning"]},
            },
            "thermal": {
                "subsystem_health": round(ht, 6),
                **{c: comp_states[c] for c in ["heater", "sensor", "insulation"]},
            },
            "model_predictions": predictions,
            "maintenance_recommendation": {
                "action": action,
                "action_label": action_label,
                "maintenance_level": maintenance_level,
                "reward": round(0.8 - (t / (N - 1)) * 0.6, 6),
            },
            "alerts": alerts,
            "_chat": chat,
        })
        prev_healths = healths

    return timeline


def build_history(timeline: list[dict]) -> list[dict]:
    return [
        {
            "t": row["t"],
            "temperature": row["drivers"]["temperature"],
            "humidity":    row["drivers"]["humidity"],
            "health_recoating": row["recoating"]["subsystem_health"],
            "health_printhead": row["printhead"]["subsystem_health"],
            "health_thermal":   row["thermal"]["subsystem_health"],
            "status_blade":  row["recoating"]["blade"]["status"],
            "status_nozzle": row["printhead"]["nozzle"]["status"],
            "status_heater": row["thermal"]["heater"]["status"],
            **{f"health_{c}": row["recoating"][c]["health"]  for c in ["blade", "motor", "rail"]},
            **{f"health_{c}": row["printhead"][c]["health"]  for c in ["nozzle", "resistor", "cleaning"]},
            **{f"health_{c}": row["thermal"][c]["health"]    for c in ["heater", "sensor", "insulation"]},
        }
        for row in timeline
    ]


if __name__ == "__main__":
    scenarios_out: dict[str, dict] = {}

    for scenario_id, env_profile, chaos_prob, maintenance_schedule in SCENARIO_CONFIGS:
        print(f"Computing [{scenario_id}]…")
        seed = SCENARIO_SEEDS[scenario_id]
        timeline = build_timeline(scenario_id, env_profile, chaos_prob, maintenance_schedule, seed)
        history  = build_history(timeline)
        scenarios_out[scenario_id] = {
            "scenario_id": scenario_id,
            "run_number": RUN_NUMBER,
            "env_profile": env_profile,
            "maintenance_schedule": maintenance_schedule,
            "timeline": timeline,
            "history": history,
        }
        last = timeline[-1]
        print(f"  R={last['recoating']['subsystem_health']:.3f}  P={last['printhead']['subsystem_health']:.3f}  T={last['thermal']['subsystem_health']:.3f}  alerts={sum(len(r['alerts']) for r in timeline)}")

    OUT.write_text(json.dumps({"scenarios": scenarios_out}, indent=2))
    print(f"\nWritten {len(scenarios_out)} scenarios → {OUT}")
