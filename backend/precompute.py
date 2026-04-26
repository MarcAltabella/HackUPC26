"""Generate precomputed.json — mirrors frontend/lib/mock-data.ts logic, outputs full API shapes."""
from __future__ import annotations

import json
import math
from pathlib import Path
import torch
import torch.nn as nn

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
            nn.Linear(hidden_dim, output_dim)
        )

    def forward(self, x):
        return self.net(x)

OUT = Path(__file__).parent / "precomputed.json"

MODELS_DIR = Path(__file__).parent.parent / "models" / "artifacts" / "models"

SCENARIO_ID = "humid_factory"
RUN_NUMBER = 0
N = 100  # ticks

LABEL_TO_STATUS = {0: "FUNCTIONAL", 1: "DEGRADED", 2: "CRITICAL", 3: "FAILED"}
ACTION_LABELS = {0: "do_nothing", 1: "light_service", 2: "full_maintenance"}
ACTION_TO_MAINTENANCE = {0: 0.0, 1: 0.5, 2: 1.0}

COMPONENTS = ["blade", "motor", "rail", "nozzle", "resistor", "cleaning", "heater", "sensor", "insulation"]

def load_models():
    models = {}
    scalers = {}
    for comp in COMPONENTS:
        model_path = MODELS_DIR / f"{comp}_classifier.pt"
        if not model_path.exists():
            continue
        try:
            import warnings
            warnings.filterwarnings("ignore")
            checkpoint = torch.load(model_path, weights_only=False, map_location='cpu')
            model = ComponentClassifier(**checkpoint['config'])
            model.load_state_dict(checkpoint['state_dict'])
            model.eval()
            models[comp] = model
            scalers[comp] = {
                'mean': torch.tensor(checkpoint['mean'], dtype=torch.float32),
                'std': torch.tensor(checkpoint['std'], dtype=torch.float32)
            }
        except Exception as e:
            print(f"Failed to load {comp}: {e}")
    return models, scalers

MODELS, SCALERS = load_models()

COMPONENT_META = {
    "blade":      {"display": "Blade",      "subsystem": "Recoating", "metric_field": "thickness_mm",       "metric_label": "thickness",         "unit": "mm"},
    "motor":      {"display": "Motor",      "subsystem": "Recoating", "metric_field": "vibration_mm_s",     "metric_label": "vibration",         "unit": "mm/s"},
    "rail":       {"display": "Rail",       "subsystem": "Recoating", "metric_field": "deviation_um",       "metric_label": "deviation",         "unit": "um"},
    "nozzle":     {"display": "Nozzle",     "subsystem": "Printhead", "metric_field": "clog_probability",   "metric_label": "clog probability",  "unit": ""},
    "resistor":   {"display": "Resistor",   "subsystem": "Printhead", "metric_field": "drift_pct",          "metric_label": "drift",             "unit": "%"},
    "cleaning":   {"display": "Cleaning",   "subsystem": "Printhead", "metric_field": "efficiency",         "metric_label": "efficiency",        "unit": ""},
    "heater":     {"display": "Heater",     "subsystem": "Thermal",   "metric_field": "resistance_ohm",     "metric_label": "resistance",        "unit": "ohm"},
    "sensor":     {"display": "Sensor",     "subsystem": "Thermal",   "metric_field": "measurement_error_c","metric_label": "measurement error", "unit": "C"},
    "insulation": {"display": "Insulation", "subsystem": "Thermal",   "metric_field": "thermal_resistance", "metric_label": "thermal resistance","unit": ""},
}

# Per-component health offsets from their subsystem health (matches MOCK_STATE)
HEALTH_OFFSETS = {
    "blade": +0.04, "motor": +0.18, "rail": -0.06,
    "nozzle": -0.04, "resistor": +0.12, "cleaning": +0.02,
    "heater": +0.06, "sensor": +0.02, "insulation": -0.03,
}


def wave(t: int, freq: float, amp: float) -> float:
    return math.sin(t * freq) * amp


def subsystem_health(t: int, p: float) -> tuple[float, float, float]:
    hr = max(0.18, 0.96 - p * 0.72 + wave(t, 0.55, 0.018))
    spike = (t - 55) * 0.008 if t > 55 else 0.0
    hp = max(0.22, 0.94 - p * 0.45 - spike + wave(t, 0.38, 0.015))
    ht = max(0.55, 0.97 - p * 0.28 + wave(t, 0.22, 0.012))
    return hr, hp, ht


def component_health(t: int, p: float) -> dict[str, float]:
    hr, hp, ht = subsystem_health(t, p)
    sub = {"blade": hr, "motor": hr, "rail": hr, "nozzle": hp, "resistor": hp,
           "cleaning": hp, "heater": ht, "sensor": ht, "insulation": ht}
    return {c: max(0.0, min(1.0, sub[c] + HEALTH_OFFSETS[c])) for c in COMPONENTS}


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
        return {
            "label": label,
            "status": LABEL_TO_STATUS[label],
            "confidence": 0.85,
            "probabilities": probs,
        }
    
    with torch.no_grad():
        x = torch.tensor([features], dtype=torch.float32)
        x = (x - SCALERS[comp]['mean']) / SCALERS[comp]['std']
        logits = MODELS[comp](x)
        probs = torch.softmax(logits, dim=1).squeeze(0).tolist()
    
    num_classes = len(probs)
    label = max(range(num_classes), key=lambda i: probs[i])
    status = LABEL_TO_STATUS[label]
    confidence = probs[label]
    
    full_probs = {LABEL_TO_STATUS[i]: round(probs[i] if i < num_classes else 0.0, 6) for i in range(4)}
    
    return {
        "label": label,
        "status": status,
        "confidence": confidence,
        "probabilities": full_probs,
    }


def metric_value(t: int, p: float, component: str) -> float:
    return {
        "blade":      max(0.10, 0.55 - p * 0.25 + wave(t, 0.30, 0.020)),
        "motor":      1.2 + p * 4.5 + wave(t, 0.40, 0.30),
        "rail":       max(0.0, p * 180 + wave(t, 0.50, 8.0)),
        "nozzle":     min(0.99, p * 0.80 + wave(t, 0.35, 0.040)),
        "resistor":   max(0.0, p * 8.0 + wave(t, 0.20, 0.50)),
        "cleaning":   max(0.10, 0.95 - p * 0.50 + wave(t, 0.25, 0.020)),
        "heater":     10.0 + p * 4.0 + wave(t, 0.18, 0.20),
        "sensor":     max(0.0, p * 2.0 + wave(t, 0.30, 0.10)),
        "insulation": max(1.0, 2.5 - p * 0.80 + wave(t, 0.20, 0.05)),
    }[component]


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


def make_alerts(t: int, components: dict[str, dict], action_label: str) -> list[dict]:
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
        alerts.append({
            "id": f"{SCENARIO_ID}-{RUN_NUMBER}-{t}-{comp}",
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
                f"Phase 1 classifier predicts {status} with 85.0% confidence.",
                f"Historian health for {comp} is {health_pct:.1f}% at t={t}.",
                f"Q-table recommends {action_label.replace('_', ' ')} for this tick.",
            ],
            "actions": recommended_actions(comp, severity),
            "query": f"Diagnose the {meta['display'].lower()} {status.lower()} condition at t={t}.",
            "citations": [
                {"run_id": SCENARIO_ID, "run_number": RUN_NUMBER, "t": t, "field": f"health_{comp}",  "value": round(state["health"], 6)},
                {"run_id": SCENARIO_ID, "run_number": RUN_NUMBER, "t": t, "field": f"status_{comp}", "value": status},
                {"run_id": SCENARIO_ID, "run_number": RUN_NUMBER, "t": t, "field": f"metric_{comp}", "value": round(mval, 6)},
            ],
        })
    return sorted(alerts, key=lambda a: (severity_rank[a["severity"]], a["component"]))


def build_timeline() -> list[dict]:
    timeline = []
    steps_since_maint = 0
    cumulative_shocks = 0
    prev_healths = {c: 1.0 for c in COMPONENTS}

    for t in range(N):
        p = t / (N - 1) if N > 1 else 0.0
        hr, hp, ht = subsystem_health(t, p)
        healths = component_health(t, p)

        temperature = 22.4 + wave(t, 0.15, 2.8)
        humidity = min(1.0, 0.32 + p * 0.41 + wave(t, 0.25, 0.03))
        load = round(0.6 + wave(t, 0.1, 0.15), 3)
        is_shock = t in {12, 47, 73}
        if is_shock:
            cumulative_shocks += 1

        action = pick_action(hr, hp, ht, steps_since_maint)
        action_label = ACTION_LABELS[action]
        maintenance_level = ACTION_TO_MAINTENANCE[action]
        
        features = [
            temperature,
            humidity,
            load,
            maintenance_level,
            float(is_shock),
            float(steps_since_maint),
            float(cumulative_shocks),
        ] + [prev_healths[c] for c in COMPONENTS]

        predictions = {c: make_prediction(c, features) for c in COMPONENTS}

        if action > 0:
            steps_since_maint = 0
        else:
            steps_since_maint += 1

        comp_states: dict[str, dict] = {}
        for c in COMPONENTS:
            mval = metric_value(t, p, c)
            meta = COMPONENT_META[c]
            comp_states[c] = {
                "health": round(healths[c], 6),
                **predictions[c],
                meta["metric_field"]: round(mval, 6),
            }

        alerts = make_alerts(t, comp_states, action_label)

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
            chat_citations = [{"run_id": SCENARIO_ID, "run_number": RUN_NUMBER, "t": t, "field": "health_recoating", "value": round(hr, 6)}]
            chat_actions = ["Continue monitoring", "Keep current maintenance plan"]

        row = {
            "scenario_id": SCENARIO_ID,
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
                "reward": round(0.8 - p * 0.6, 6),
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
        }
        timeline.append(row)
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
    print("Computing timeline…")
    timeline = build_timeline()
    history = build_history(timeline)

    payload = {
        "scenario_id": SCENARIO_ID,
        "run_number": RUN_NUMBER,
        "timeline": timeline,
        "history": history,
    }

    OUT.write_text(json.dumps(payload, indent=2))
    print(f"Written {len(timeline)} ticks → {OUT}")
