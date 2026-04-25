from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset

from scr.dense_training_base import RegressorConfig, DenseRegressor, train_regressor

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts" / "models"

COMPONENTS = [
    "blade", "motor", "rail",
    "nozzle", "resistor", "cleaning",
    "heater", "sensor", "insulation",
]

FEATURE_COLS = [
    "temperature", "humidity", "load", "maintenance", "is_shock",
    "steps_since_maintenance", "cumulative_shocks",
    "health_prev_blade", "health_prev_motor", "health_prev_rail",
    "health_prev_nozzle", "health_prev_resistor", "health_prev_cleaning",
    "health_prev_heater", "health_prev_sensor", "health_prev_insulation",
]


def _load_rows(db_path: Path, csv_path: Path) -> list[dict[str, object]]:
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT scenario_id, run_id, "
            + ", ".join(FEATURE_COLS)
            + ", "
            + ", ".join(f"health_{c}" for c in COMPONENTS)
            + " FROM simulation_log"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    if not csv_path.exists():
        raise FileNotFoundError(
            f"No dataset found. Expected {db_path} or {csv_path}. "
            "Run: python -m scr.generate_dataset"
        )

    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        out: list[dict[str, object]] = []
        for row in reader:
            parsed: dict[str, object] = {
                "scenario_id": row["scenario_id"],
                "run_id": int(row["run_id"]),
            }
            for col in FEATURE_COLS:
                parsed[col] = float(row[col])
            for c in COMPONENTS:
                parsed[f"health_{c}"] = float(row[f"health_{c}"])
            out.append(parsed)
        return out


def _build_arrays(rows: list[dict[str, object]], component: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = np.asarray([[float(r[c]) for c in FEATURE_COLS] for r in rows], dtype=np.float32)
    y = np.asarray([float(r[f"health_{component}"]) for r in rows], dtype=np.float32)
    group = np.asarray([f"{r['scenario_id']}#{int(r['run_id'])}" for r in rows], dtype=object)
    return x, y, group


def _split_by_group(group: np.ndarray, val_ratio: float, seed: int) -> np.ndarray:
    uniq = np.unique(group)
    rng = np.random.default_rng(seed)
    rng.shuffle(uniq)
    n_val = max(1, int(len(uniq) * val_ratio))
    val_groups = set(uniq[:n_val].tolist())
    return np.asarray([g in val_groups for g in group], dtype=bool)


def _standardize_train_val(
    x_train: np.ndarray, x_val: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    mean = x_train.mean(axis=0, keepdims=True)
    std = x_train.std(axis=0, keepdims=True)
    std = np.where(std < 1e-8, 1.0, std)
    return (x_train - mean) / std, (x_val - mean) / std, mean.astype(np.float32), std.astype(np.float32)


def _train_one_component(
    rows: list[dict[str, object]], component: str, cfg: RegressorConfig
) -> dict[str, float]:
    x, y, group = _build_arrays(rows, component)
    is_val = _split_by_group(group, val_ratio=0.2, seed=cfg.seed)

    x_train, x_val = x[~is_val], x[is_val]
    y_train, y_val = y[~is_val], y[is_val]
    x_train, x_val, mean, std = _standardize_train_val(x_train, x_val)

    train_ds = TensorDataset(torch.from_numpy(x_train), torch.from_numpy(y_train))
    val_ds   = TensorDataset(torch.from_numpy(x_val),   torch.from_numpy(y_val))
    train_loader = DataLoader(train_ds, batch_size=cfg.batch_size, shuffle=True)
    val_loader   = DataLoader(val_ds,   batch_size=cfg.batch_size, shuffle=False)

    model, metrics = train_regressor(cfg, train_loader, val_loader, component_name=component)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "mode":         "regression",
            "component":    component,
            "feature_cols": FEATURE_COLS,
            "mean":         mean,
            "std":          std,
            "state_dict":   model.state_dict(),
            "config": {
                "input_dim":  cfg.input_dim,
                "hidden_dim": cfg.hidden_dim,
                "dropout":    cfg.dropout,
            },
            "metrics": metrics,
        },
        ARTIFACTS_DIR / f"{component}_regressor.pt",
    )

    return {
        "val_mse": float(metrics["val_mse"]),
        "val_mae": float(metrics["val_mae"]),
        "val_acc": float(metrics["val_acc"]),
        "train_rows": float(len(x_train)),
        "val_rows":   float(len(x_val)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train health regressors per HP S100 component")
    parser.add_argument("--component", type=str, default="all",
                        choices=["all", *COMPONENTS])
    parser.add_argument("--epochs",       type=int,   default=30)
    parser.add_argument("--batch-size",   type=int,   default=256)
    parser.add_argument("--hidden-dim",   type=int,   default=128)
    parser.add_argument("--dropout",      type=float, default=0.15)
    parser.add_argument("--lr",           type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--patience",     type=int,   default=7)
    parser.add_argument("--seed",         type=int,   default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    print(f"Training device: {device} ({gpu_name})", flush=True)

    rows = _load_rows(DATA_DIR / "simulation.db", DATA_DIR / "training_dataset.csv")
    if not rows:
        raise RuntimeError("Dataset is empty. Run: python -m scr.generate_dataset")

    targets = COMPONENTS if args.component == "all" else [args.component]
    cfg = RegressorConfig(
        input_dim=len(FEATURE_COLS),
        hidden_dim=args.hidden_dim,
        dropout=args.dropout,
        batch_size=args.batch_size,
        epochs=args.epochs,
        lr=args.lr,
        weight_decay=args.weight_decay,
        patience=args.patience,
        seed=args.seed,
    )

    summary: dict[str, dict[str, float]] = {}
    for component in targets:
        t0 = time.perf_counter()
        print(f"\nTraining component: {component}", flush=True)
        stats = _train_one_component(rows, component, cfg)
        elapsed = time.perf_counter() - t0
        summary[component] = stats
        print(
            f"[{component:10s}] val_mse={stats['val_mse']:.5f}  "
            f"val_mae={stats['val_mae']:.4f}  derived_acc={stats['val_acc']:.4f}  "
            f"train={int(stats['train_rows'])}  val={int(stats['val_rows'])}  "
            f"time={elapsed:.1f}s",
            flush=True,
        )

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = ARTIFACTS_DIR / "training_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary saved to {summary_path}")


if __name__ == "__main__":
    main()
