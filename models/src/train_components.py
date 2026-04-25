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

from scr.dense_training_base import (
    ClassifierConfig,
    RegressorConfig,
    train_classifier,
    train_regressor,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts" / "models"

COMPONENTS = [
    "blade", "motor", "rail",
    "nozzle", "resistor", "cleaning",
    "heater", "sensor", "insulation",
]

BASE_FEATURE_COLS = [
    "temperature", "humidity", "load", "maintenance", "is_shock",
    "steps_since_maintenance", "cumulative_shocks",
]

PREV_HEALTH_COLS = [
    "health_prev_blade", "health_prev_motor", "health_prev_rail",
    "health_prev_nozzle", "health_prev_resistor", "health_prev_cleaning",
    "health_prev_heater", "health_prev_sensor", "health_prev_insulation",
]

LABEL_COLS = [
    "label_blade", "label_motor", "label_rail",
    "label_nozzle", "label_resistor", "label_cleaning",
    "label_heater", "label_sensor", "label_insulation",
]


def _load_rows(db_path: Path, csv_path: Path) -> list[dict[str, object]]:
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT scenario_id, run_id, t, "
            + ", ".join(BASE_FEATURE_COLS)
            + ", "
            + ", ".join(PREV_HEALTH_COLS)
            + ", "
            + ", ".join(f"health_{c}" for c in COMPONENTS)
            + ", "
            + ", ".join(LABEL_COLS)
            + " FROM simulation_log"
            + " ORDER BY scenario_id, run_id, t"
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
                "t": int(row["t"]),
            }
            for col in BASE_FEATURE_COLS:
                parsed[col] = float(row[col])
            for col in PREV_HEALTH_COLS:
                parsed[col] = float(row[col])
            for col in LABEL_COLS:
                parsed[col] = int(row[col])
            for c in COMPONENTS:
                parsed[f"health_{c}"] = float(row[f"health_{c}"])
            out.append(parsed)
        return out


def _feature_cols_for_component(component: str, use_temporal: bool) -> list[str]:
    if not use_temporal:
        return [*BASE_FEATURE_COLS, *PREV_HEALTH_COLS]

    temporal_cols = [
        f"health_lag2_{component}",
        f"health_lag3_{component}",
        f"health_lag4_{component}",
        f"health_diff1_{component}",
        f"health_diff3_{component}",
        f"health_roll_mean3_{component}",
        f"health_roll_mean5_{component}",
        f"health_roll_std5_{component}",
        f"health_slope3_{component}",
    ]
    return [*BASE_FEATURE_COLS, *PREV_HEALTH_COLS, *temporal_cols]


def _build_feature_row(
    row: dict[str, object],
    component: str,
    history: list[float],
    use_temporal: bool,
) -> list[float]:
    base = [*[float(row[c]) for c in BASE_FEATURE_COLS], *[float(row[c]) for c in PREV_HEALTH_COLS]]
    if not use_temporal:
        return base

    lag1 = float(row[f"health_prev_{component}"])
    lag2 = history[-1] if len(history) >= 1 else lag1
    lag3 = history[-2] if len(history) >= 2 else lag2
    lag4 = history[-3] if len(history) >= 3 else lag3
    roll3_values = np.asarray([lag1, lag2, lag3], dtype=np.float32)
    roll5_values = np.asarray([lag1, lag2, lag3, lag4, lag4], dtype=np.float32)

    return [
        *base,
        lag2,
        lag3,
        lag4,
        lag1 - lag2,
        lag1 - lag4,
        float(roll3_values.mean()),
        float(roll5_values.mean()),
        float(roll5_values.std()),
        (lag1 - lag4) / 3.0,
    ]


def _build_arrays(
    rows: list[dict[str, object]],
    component: str,
    mode: str,
    use_temporal: bool,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    ordered_rows = sorted(rows, key=lambda r: (str(r["scenario_id"]), int(r["run_id"]), int(r["t"])))
    feature_cols = _feature_cols_for_component(component, use_temporal)
    features: list[list[float]] = []
    targets: list[float] = []
    groups: list[str] = []
    current_group = ""
    history: list[float] = []

    for row in ordered_rows:
        group = f"{row['scenario_id']}#{int(row['run_id'])}"
        if group != current_group:
            current_group = group
            history = []

        features.append(_build_feature_row(row, component, history, use_temporal))
        if mode == "classification":
            targets.append(int(row[f"label_{component}"]))
        else:
            targets.append(float(row[f"health_{component}"]))
        groups.append(group)
        history.append(float(row[f"health_prev_{component}"]))

    x = np.asarray(features, dtype=np.float32)
    if mode == "classification":
        y = np.asarray(targets, dtype=np.int64)
    else:
        y = np.asarray(targets, dtype=np.float32)
    group = np.asarray(groups, dtype=object)
    return x, y, group, feature_cols


def _split_by_group(group: np.ndarray, val_ratio: float, seed: int) -> np.ndarray:
    uniq = np.unique(group)
    rng = np.random.default_rng(seed)
    rng.shuffle(uniq)
    n_val = max(1, int(len(uniq) * val_ratio))
    val_groups = set(uniq[:n_val].tolist())
    return np.asarray([g in val_groups for g in group], dtype=bool)


def _standardize_train_val(
    x_train: np.ndarray,
    x_val: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    mean = x_train.mean(axis=0, keepdims=True)
    std = x_train.std(axis=0, keepdims=True)
    std = np.where(std < 1e-8, 1.0, std)
    return (x_train - mean) / std, (x_val - mean) / std, mean.astype(np.float32), std.astype(np.float32)


def _build_class_weights(y_train: np.ndarray, num_classes: int) -> torch.Tensor:
    counts = np.bincount(y_train, minlength=num_classes).astype(np.float32)
    counts = np.where(counts < 1.0, 1.0, counts)
    weights = counts.sum() / (len(counts) * counts)
    return torch.tensor(weights, dtype=torch.float32)


def _train_classifier_component(
    x_train: np.ndarray,
    x_val: np.ndarray,
    y_train: np.ndarray,
    y_val: np.ndarray,
    component: str,
    feature_cols: list[str],
    cfg: ClassifierConfig,
    mean: np.ndarray,
    std: np.ndarray,
) -> dict[str, float]:
    train_ds = TensorDataset(torch.from_numpy(x_train), torch.from_numpy(y_train))
    val_ds = TensorDataset(torch.from_numpy(x_val), torch.from_numpy(y_val))
    train_loader = DataLoader(train_ds, batch_size=cfg.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=cfg.batch_size, shuffle=False)
    class_weights = _build_class_weights(y_train, cfg.output_dim)

    model, metrics = train_classifier(
        cfg,
        train_loader,
        val_loader,
        class_weights=class_weights,
        component_name=component,
    )

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "mode": "classification",
            "component": component,
            "feature_cols": feature_cols,
            "mean": mean,
            "std": std,
            "state_dict": model.state_dict(),
            "class_weights": class_weights.numpy(),
            "config": {
                "input_dim": cfg.input_dim,
                "output_dim": cfg.output_dim,
                "hidden_dim": cfg.hidden_dim,
                "dropout": cfg.dropout,
            },
            "metrics": metrics,
        },
        ARTIFACTS_DIR / f"{component}_classifier.pt",
    )

    return {
        "val_loss": float(metrics["val_loss"]),
        "val_acc": float(metrics["val_acc"]),
        "train_rows": float(len(x_train)),
        "val_rows": float(len(x_val)),
    }


def _train_regressor_component(
    x_train: np.ndarray,
    x_val: np.ndarray,
    y_train: np.ndarray,
    y_val: np.ndarray,
    component: str,
    feature_cols: list[str],
    cfg: RegressorConfig,
    mean: np.ndarray,
    std: np.ndarray,
) -> dict[str, float]:
    train_ds = TensorDataset(torch.from_numpy(x_train), torch.from_numpy(y_train))
    val_ds = TensorDataset(torch.from_numpy(x_val), torch.from_numpy(y_val))
    train_loader = DataLoader(train_ds, batch_size=cfg.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=cfg.batch_size, shuffle=False)

    model, metrics = train_regressor(cfg, train_loader, val_loader, component_name=component)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "mode": "regression",
            "component": component,
            "feature_cols": feature_cols,
            "mean": mean,
            "std": std,
            "state_dict": model.state_dict(),
            "config": {
                "input_dim": cfg.input_dim,
                "hidden_dim": cfg.hidden_dim,
                "dropout": cfg.dropout,
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
        "val_rows": float(len(x_val)),
    }


def _train_one_component(
    rows: list[dict[str, object]],
    component: str,
    args: argparse.Namespace,
) -> dict[str, float]:
    x, y, group, feature_cols = _build_arrays(rows, component, args.mode, args.temporal_features)
    is_val = _split_by_group(group, val_ratio=0.2, seed=args.seed)

    x_train, x_val = x[~is_val], x[is_val]
    y_train, y_val = y[~is_val], y[is_val]
    x_train, x_val, mean, std = _standardize_train_val(x_train, x_val)

    if args.mode == "classification":
        cfg = ClassifierConfig(
            input_dim=x.shape[1],
            output_dim=int(np.max(y) + 1),
            hidden_dim=args.hidden_dim,
            dropout=args.dropout,
            batch_size=args.batch_size,
            epochs=args.epochs,
            lr=args.lr,
            weight_decay=args.weight_decay,
            patience=args.patience,
            seed=args.seed,
        )
        return _train_classifier_component(
            x_train,
            x_val,
            y_train,
            y_val,
            component,
            feature_cols,
            cfg,
            mean,
            std,
        )

    cfg = RegressorConfig(
        input_dim=x.shape[1],
        hidden_dim=args.hidden_dim,
        dropout=args.dropout,
        batch_size=args.batch_size,
        epochs=args.epochs,
        lr=args.lr,
        weight_decay=args.weight_decay,
        patience=args.patience,
        seed=args.seed,
    )
    return _train_regressor_component(
        x_train,
        x_val,
        y_train,
        y_val,
        component,
        feature_cols,
        cfg,
        mean,
        std,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train per-component HP S100 models")
    parser.add_argument("--component", type=str, default="all", choices=["all", *COMPONENTS])
    parser.add_argument("--mode", type=str, default="classification", choices=["classification", "regression"])
    parser.add_argument("--temporal-features", action="store_true")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--hidden-dim", type=int, default=128)
    parser.add_argument("--dropout", type=float, default=0.15)
    parser.add_argument("--lr", type=float, default=5e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--patience", type=int, default=7)
    parser.add_argument("--seed", type=int, default=42)
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
    summary: dict[str, dict[str, float]] = {}

    for component in targets:
        t0 = time.perf_counter()
        print(f"\nTraining component: {component}", flush=True)
        stats = _train_one_component(rows, component, args)
        elapsed = time.perf_counter() - t0
        summary[component] = {"mode": args.mode, **stats}

        if args.mode == "classification":
            print(
                f"[{component:10s}] val_loss={stats['val_loss']:.4f}  "
                f"val_acc={stats['val_acc']:.4f}  "
                f"train={int(stats['train_rows'])}  val={int(stats['val_rows'])}  "
                f"time={elapsed:.1f}s",
                flush=True,
            )
        else:
            print(
                f"[{component:10s}] val_mse={stats['val_mse']:.5f}  "
                f"val_mae={stats['val_mae']:.4f}  derived_acc={stats['val_acc']:.4f}  "
                f"train={int(stats['train_rows'])}  val={int(stats['val_rows'])}  "
                f"time={elapsed:.1f}s",
                flush=True,
            )

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    generic_summary_path = ARTIFACTS_DIR / "training_summary.json"
    mode_summary_path = ARTIFACTS_DIR / f"training_summary_{args.mode}.json"
    with open(generic_summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    with open(mode_summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary saved to {generic_summary_path}")
    print(f"Mode summary saved to {mode_summary_path}")


if __name__ == "__main__":
    main()
