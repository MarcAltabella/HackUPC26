from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import torch

from scr.dense_training_base import (
    ClassifierConfig,
    DenseClassifier,
    DenseRegressor,
    RegressorConfig,
    health_to_label,
)

LABEL_TO_STATUS = {0: "FUNCTIONAL", 1: "DEGRADED", 2: "CRITICAL", 3: "FAILED"}

COMPONENTS = [
    "blade", "motor", "rail",
    "nozzle", "resistor", "cleaning",
    "heater", "sensor", "insulation",
]


def _history_from_args(args: argparse.Namespace, component: str) -> tuple[float, float, float, float]:
    lag1 = float(getattr(args, f"prev_{component}"))
    lag2_arg = getattr(args, f"lag2_{component}")
    lag3_arg = getattr(args, f"lag3_{component}")
    lag4_arg = getattr(args, f"lag4_{component}")
    lag2 = lag1 if lag2_arg is None else float(lag2_arg)
    lag3 = lag2 if lag3_arg is None else float(lag3_arg)
    lag4 = lag3 if lag4_arg is None else float(lag4_arg)
    return lag1, lag2, lag3, lag4


def _feature_value(args: argparse.Namespace, column: str) -> float:
    base_values = {
        "temperature": args.temperature,
        "humidity": args.humidity,
        "load": args.load,
        "maintenance": args.maintenance,
        "is_shock": args.is_shock,
        "steps_since_maintenance": args.steps_since_maintenance,
        "cumulative_shocks": args.cumulative_shocks,
    }
    if column in base_values:
        return float(base_values[column])

    if column.startswith("health_prev_"):
        component = column.removeprefix("health_prev_")
        return float(getattr(args, f"prev_{component}"))

    temporal_prefixes = [
        "health_lag2_",
        "health_lag3_",
        "health_lag4_",
        "health_diff1_",
        "health_diff3_",
        "health_roll_mean3_",
        "health_roll_mean5_",
        "health_roll_std5_",
        "health_slope3_",
    ]
    matching_prefix = next((prefix for prefix in temporal_prefixes if column.startswith(prefix)), None)
    if matching_prefix is not None:
        component = column.removeprefix(matching_prefix)
        lag1, lag2, lag3, lag4 = _history_from_args(args, component)
        roll3 = np.asarray([lag1, lag2, lag3], dtype=np.float32)
        roll5 = np.asarray([lag1, lag2, lag3, lag4, lag4], dtype=np.float32)
        derived = {
            f"health_lag2_{component}": lag2,
            f"health_lag3_{component}": lag3,
            f"health_lag4_{component}": lag4,
            f"health_diff1_{component}": lag1 - lag2,
            f"health_diff3_{component}": lag1 - lag4,
            f"health_roll_mean3_{component}": float(roll3.mean()),
            f"health_roll_mean5_{component}": float(roll5.mean()),
            f"health_roll_std5_{component}": float(roll5.std()),
            f"health_slope3_{component}": (lag1 - lag4) / 3.0,
        }
        return float(derived[column])

    raise KeyError(f"Unsupported feature column in checkpoint: {column}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Predict component health from a trained regressor checkpoint")
    parser.add_argument("--checkpoint",              type=Path,  required=True)
    parser.add_argument("--temperature",             type=float, required=True)
    parser.add_argument("--humidity",                type=float, required=True)
    parser.add_argument("--load",                    type=float, required=True)
    parser.add_argument("--maintenance",             type=float, required=True)
    parser.add_argument("--is-shock",                type=float, default=0.0)
    parser.add_argument("--steps-since-maintenance", type=float, default=0.0)
    parser.add_argument("--cumulative-shocks",       type=float, default=0.0)
    # Lag-1 health for each component (default 1.0 = brand-new)
    for comp in COMPONENTS:
        parser.add_argument(f"--prev-{comp}", type=float, default=1.0,
                            metavar="H", help=f"Previous-tick health for {comp}")
        parser.add_argument(f"--lag2-{comp}", type=float, default=None,
                            metavar="H", help=f"Two-ticks-back health for {comp}")
        parser.add_argument(f"--lag3-{comp}", type=float, default=None,
                            metavar="H", help=f"Three-ticks-back health for {comp}")
        parser.add_argument(f"--lag4-{comp}", type=float, default=None,
                            metavar="H", help=f"Four-ticks-back health for {comp}")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    ckpt = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    mode = ckpt.get("mode", "regression")
    cfg_dict = ckpt["config"]
    if mode == "classification":
        cfg = ClassifierConfig(
            input_dim=int(cfg_dict["input_dim"]),
            output_dim=int(cfg_dict.get("output_dim", 4)),
            hidden_dim=int(cfg_dict["hidden_dim"]),
            dropout=float(cfg_dict["dropout"]),
        )
        model = DenseClassifier(cfg)
    else:
        cfg = RegressorConfig(
            input_dim=int(cfg_dict["input_dim"]),
            hidden_dim=int(cfg_dict["hidden_dim"]),
            dropout=float(cfg_dict["dropout"]),
        )
        model = DenseRegressor(cfg)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()

    feature_cols = ckpt.get("feature_cols")
    if feature_cols is None:
        feature_cols = [
            "temperature", "humidity", "load", "maintenance", "is_shock",
            "steps_since_maintenance", "cumulative_shocks",
            *[f"health_prev_{c}" for c in COMPONENTS],
        ]
    x_raw = np.asarray([[ _feature_value(args, col) for col in feature_cols ]], dtype=np.float32)

    mean = np.asarray(ckpt["mean"], dtype=np.float32)
    std  = np.asarray(ckpt["std"],  dtype=np.float32)
    x = (x_raw - mean) / np.where(std < 1e-8, 1.0, std)

    component = ckpt.get("component", "unknown")

    with torch.no_grad():
        output = model(torch.from_numpy(x))

    if mode == "classification":
        logits = output
        probs = torch.softmax(logits, dim=1).numpy()[0]
        label = int(np.argmax(probs))
        status = LABEL_TO_STATUS[label]
        print(f"mode={mode}")
        print(f"component={component}")
        print(f"predicted_label={label}")
        print(f"predicted_status={status}")
        print(f"class_probabilities={probs.tolist()}")
        return

    health = float(output.item())
    label = int(health_to_label(np.array([health]))[0])
    status = LABEL_TO_STATUS[label]
    print(f"mode={mode}")
    print(f"component={component}")
    print(f"predicted_health={health:.4f}")
    print(f"predicted_label={label}")
    print(f"predicted_status={status}")


if __name__ == "__main__":
    main()
