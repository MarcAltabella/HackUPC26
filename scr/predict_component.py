from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import torch

from scr.dense_training_base import DenseRegressor, RegressorConfig, health_to_label

LABEL_TO_STATUS = {0: "FUNCTIONAL", 1: "DEGRADED", 2: "CRITICAL", 3: "FAILED"}

COMPONENTS = [
    "blade", "motor", "rail",
    "nozzle", "resistor", "cleaning",
    "heater", "sensor", "insulation",
]


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
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    ckpt = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    cfg_dict = ckpt["config"]
    cfg = RegressorConfig(
        input_dim=int(cfg_dict["input_dim"]),
        hidden_dim=int(cfg_dict["hidden_dim"]),
        dropout=float(cfg_dict["dropout"]),
    )

    model = DenseRegressor(cfg)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()

    prev_health = [getattr(args, f"prev_{c}") for c in COMPONENTS]
    x_raw = np.asarray([[
        args.temperature, args.humidity, args.load, args.maintenance, args.is_shock,
        args.steps_since_maintenance, args.cumulative_shocks,
        *prev_health,
    ]], dtype=np.float32)

    mean = np.asarray(ckpt["mean"], dtype=np.float32)
    std  = np.asarray(ckpt["std"],  dtype=np.float32)
    x = (x_raw - mean) / np.where(std < 1e-8, 1.0, std)

    with torch.no_grad():
        health = float(model(torch.from_numpy(x)).item())

    label  = int(health_to_label(np.array([health]))[0])
    status = LABEL_TO_STATUS[label]
    component = ckpt.get("component", "unknown")

    print(f"component={component}")
    print(f"predicted_health={health:.4f}")
    print(f"predicted_label={label}")
    print(f"predicted_status={status}")


if __name__ == "__main__":
    main()
