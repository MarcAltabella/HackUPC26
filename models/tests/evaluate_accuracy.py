"""
Evaluate accuracy of the 9 trained component classifiers on the held-out test dataset.

Loads:  artifacts/models/{component}_classifier.pt
Data:   tests/data/test_simulation.db  (generate with tests/generate_test_dataset.py)

Reports per component:
  - Overall accuracy
  - Per-class and macro precision, recall, F1
  - Confusion matrix (4×4: FUNCTIONAL / DEGRADED / CRITICAL / FAILED)

Saves:  tests/results/accuracy_report.json

Usage:
  cd /path/to/models
  python -m tests.evaluate_accuracy
  python -m tests.evaluate_accuracy --scenario extreme_stress  # filter by scenario
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import torch

from src.dense_training_base import DenseClassifier, ClassifierConfig

ARTIFACTS_DIR = PROJECT_ROOT / "artifacts" / "models"
TESTS_DIR = PROJECT_ROOT / "tests"
TEST_DB = TESTS_DIR / "data" / "test_simulation.db"
RESULTS_DIR = TESTS_DIR / "results"

COMPONENTS = ["blade", "motor", "rail", "nozzle", "resistor", "cleaning", "heater", "sensor", "insulation"]
STATUS_LABELS = ["FUNCTIONAL", "DEGRADED", "CRITICAL", "FAILED"]

BASE_FEATURE_COLS = [
    "temperature", "humidity", "load", "maintenance", "is_shock",
    "steps_since_maintenance", "cumulative_shocks",
]
PREV_HEALTH_COLS = [
    "health_prev_blade", "health_prev_motor", "health_prev_rail",
    "health_prev_nozzle", "health_prev_resistor", "health_prev_cleaning",
    "health_prev_heater", "health_prev_sensor", "health_prev_insulation",
]


# ─────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────

def load_test_rows(db_path: Path, scenario_filter: str | None = None) -> list[dict[str, Any]]:
    if not db_path.exists():
        raise FileNotFoundError(
            f"Test dataset not found at {db_path}\n"
            "Run: python -m tests.generate_test_dataset"
        )

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    all_cols = (
        ["scenario_id", "run_id", "t"]
        + BASE_FEATURE_COLS
        + PREV_HEALTH_COLS
        + [f"label_{c}" for c in COMPONENTS]
        + [f"health_{c}" for c in COMPONENTS]
    )
    where = f" WHERE scenario_id = '{scenario_filter}'" if scenario_filter else ""
    rows = conn.execute(
        f"SELECT {', '.join(all_cols)} FROM simulation_log{where}"
        " ORDER BY scenario_id, run_id, t"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────
# Model loading
# ─────────────────────────────────────────────────────────────

def load_classifier(component: str) -> tuple[DenseClassifier, dict[str, Any]]:
    ckpt_path = ARTIFACTS_DIR / f"{component}_classifier.pt"
    if not ckpt_path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {ckpt_path}")

    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    cfg_dict = ckpt["config"]
    cfg = ClassifierConfig(
        input_dim=cfg_dict["input_dim"],
        output_dim=cfg_dict["output_dim"],
        hidden_dim=cfg_dict["hidden_dim"],
        dropout=cfg_dict["dropout"],
    )
    model = DenseClassifier(cfg)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return model, ckpt


# ─────────────────────────────────────────────────────────────
# Feature construction  (mirrors train_components._build_arrays)
# ─────────────────────────────────────────────────────────────

def build_features_and_labels(
    rows: list[dict[str, Any]],
    component: str,
    feature_cols: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Build (X, y) arrays from test rows for a single component."""
    use_temporal = len(feature_cols) > len(BASE_FEATURE_COLS) + len(PREV_HEALTH_COLS)

    ordered = sorted(rows, key=lambda r: (str(r["scenario_id"]), int(r["run_id"]), int(r["t"])))

    features: list[list[float]] = []
    labels: list[int] = []
    current_group = ""
    history: list[float] = []

    for row in ordered:
        group = f"{row['scenario_id']}#{int(row['run_id'])}"
        if group != current_group:
            current_group = group
            history = []

        base = [float(row[c]) for c in BASE_FEATURE_COLS + PREV_HEALTH_COLS]

        if not use_temporal:
            features.append(base)
        else:
            lag1 = float(row[f"health_prev_{component}"])
            lag2 = history[-1] if len(history) >= 1 else lag1
            lag3 = history[-2] if len(history) >= 2 else lag2
            lag4 = history[-3] if len(history) >= 3 else lag3
            roll3 = np.array([lag1, lag2, lag3], dtype=np.float32)
            roll5 = np.array([lag1, lag2, lag3, lag4, lag4], dtype=np.float32)
            temporal = [
                lag2, lag3, lag4,
                lag1 - lag2,
                lag1 - lag4,
                float(roll3.mean()), float(roll5.mean()), float(roll5.std()),
                (lag1 - lag4) / 3.0,
            ]
            features.append(base + temporal)

        labels.append(int(row[f"label_{component}"]))
        history.append(float(row[f"health_{component}"]))

    return np.asarray(features, dtype=np.float32), np.asarray(labels, dtype=np.int64)


# ─────────────────────────────────────────────────────────────
# Metrics  (no sklearn — pure numpy)
# ─────────────────────────────────────────────────────────────

def confusion_matrix(y_true: np.ndarray, y_pred: np.ndarray, num_classes: int) -> np.ndarray:
    cm = np.zeros((num_classes, num_classes), dtype=np.int64)
    for t, p in zip(y_true.tolist(), y_pred.tolist()):
        cm[t][p] += 1
    return cm


def class_metrics(cm: np.ndarray) -> dict[str, list[float]]:
    num_classes = cm.shape[0]
    precision, recall, f1 = [], [], []
    for c in range(num_classes):
        tp = int(cm[c, c])
        fp = int(cm[:, c].sum()) - tp
        fn = int(cm[c, :].sum()) - tp
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec  = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1c  = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        precision.append(round(prec, 4))
        recall.append(round(rec, 4))
        f1.append(round(f1c, 4))
    return {"precision": precision, "recall": recall, "f1": f1}


def macro_avg(metrics: dict[str, list[float]]) -> dict[str, float]:
    return {k: round(float(np.mean(v)), 4) for k, v in metrics.items()}


# ─────────────────────────────────────────────────────────────
# Evaluation loop
# ─────────────────────────────────────────────────────────────

def evaluate_component(
    component: str,
    rows: list[dict[str, Any]],
    device: torch.device,
) -> dict[str, Any]:
    model, ckpt = load_classifier(component)
    model = model.to(device)

    feature_cols: list[str] = ckpt["feature_cols"]
    mean: np.ndarray = ckpt["mean"].squeeze()   # shape (input_dim,)
    std: np.ndarray  = ckpt["std"].squeeze()
    num_classes: int = ckpt["config"]["output_dim"]
    train_metrics: dict = ckpt.get("metrics", {})

    X, y_true = build_features_and_labels(rows, component, feature_cols)

    # Normalize with training statistics
    X_norm = (X - mean) / np.where(std < 1e-8, 1.0, std)

    # Batch inference
    batch_size = 4096
    all_preds: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, len(X_norm), batch_size):
            xb = torch.from_numpy(X_norm[start : start + batch_size]).to(device)
            logits = model(xb)
            preds = logits.argmax(dim=1).cpu().numpy()
            all_preds.append(preds)

    y_pred = np.concatenate(all_preds)
    accuracy = float((y_pred == y_true).mean())

    cm = confusion_matrix(y_true, y_pred, num_classes)
    per_class = class_metrics(cm)
    macro = macro_avg(per_class)

    # Support per class (how many test samples per class)
    support = [int(cm[c, :].sum()) for c in range(num_classes)]

    return {
        "accuracy": round(accuracy, 4),
        "macro_precision": macro["precision"],
        "macro_recall": macro["recall"],
        "macro_f1": macro["f1"],
        "per_class": {
            STATUS_LABELS[c]: {
                "precision": per_class["precision"][c],
                "recall":    per_class["recall"][c],
                "f1":        per_class["f1"][c],
                "support":   support[c],
            }
            for c in range(num_classes)
        },
        "confusion_matrix": cm.tolist(),
        "n_samples": len(y_true),
        "train_val_acc": round(float(train_metrics.get("val_acc", 0.0)), 4),
        "feature_dim": len(feature_cols),
    }


# ─────────────────────────────────────────────────────────────
# Reporting helpers
# ─────────────────────────────────────────────────────────────

def print_component_report(component: str, result: dict[str, Any]) -> None:
    line = "─" * 60
    print(f"\n{line}")
    print(f"  {component.upper():12s}  n={result['n_samples']:,}  features={result['feature_dim']}")
    print(line)
    print(f"  {'Accuracy':20s}  {result['accuracy']:.4f}   (train val: {result['train_val_acc']:.4f})")
    print(f"  {'Macro Precision':20s}  {result['macro_precision']:.4f}")
    print(f"  {'Macro Recall':20s}  {result['macro_recall']:.4f}")
    print(f"  {'Macro F1':20s}  {result['macro_f1']:.4f}")
    print()
    header = f"  {'Class':<12} {'Prec':>6}  {'Rec':>6}  {'F1':>6}  {'Support':>8}"
    print(header)
    print(f"  {'-'*48}")
    for label, m in result["per_class"].items():
        print(
            f"  {label:<12} {m['precision']:>6.4f}  {m['recall']:>6.4f}"
            f"  {m['f1']:>6.4f}  {m['support']:>8,}"
        )
    print()
    cm = np.array(result["confusion_matrix"])
    num_cls = cm.shape[0]
    col_labels = STATUS_LABELS[:num_cls]
    print("  Confusion matrix  (rows=true, cols=pred):")
    header_labels = "  " + "".join(f"  {s[:4]:>6}" for s in col_labels)
    print(header_labels)
    for i, row_label in enumerate(col_labels):
        row_str = "  ".join(f"{v:6,}" for v in cm[i])
        print(f"  {row_label[:4]:<6}  {row_str}")


def print_summary(report: dict[str, Any]) -> None:
    print("\n" + "═" * 60)
    print("  SUMMARY — all components")
    print("═" * 60)
    print(f"  {'Component':<12} {'Acc':>6}  {'F1':>6}  {'Prec':>6}  {'Rec':>6}")
    print(f"  {'-'*48}")
    accs, f1s = [], []
    for comp in COMPONENTS:
        r = report[comp]
        print(
            f"  {comp:<12} {r['accuracy']:>6.4f}  {r['macro_f1']:>6.4f}"
            f"  {r['macro_precision']:>6.4f}  {r['macro_recall']:>6.4f}"
        )
        accs.append(r["accuracy"])
        f1s.append(r["macro_f1"])
    print(f"  {'-'*48}")
    print(f"  {'mean':<12} {np.mean(accs):>6.4f}  {np.mean(f1s):>6.4f}")
    print()


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate component classifier accuracy")
    parser.add_argument("--scenario", type=str, default=None,
                        help="Filter test data to a single scenario_id")
    parser.add_argument("--component", type=str, default="all",
                        choices=["all"] + COMPONENTS,
                        help="Evaluate only one component")
    parser.add_argument("--no-save", action="store_true",
                        help="Skip saving the JSON report")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    if args.scenario:
        print(f"Scenario filter: {args.scenario}")

    print(f"Loading test data from {TEST_DB} …", flush=True)
    rows = load_test_rows(TEST_DB, scenario_filter=args.scenario)
    print(f"  {len(rows):,} rows loaded")

    targets = COMPONENTS if args.component == "all" else [args.component]
    report: dict[str, Any] = {}

    for comp in targets:
        print(f"\nEvaluating {comp} …", flush=True)
        result = evaluate_component(comp, rows, device)
        report[comp] = result
        print_component_report(comp, result)

    if args.component == "all":
        print_summary(report)

    if not args.no_save:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        suffix = f"_{args.scenario}" if args.scenario else ""
        out_path = RESULTS_DIR / f"accuracy_report{suffix}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"Report saved to {out_path}")


if __name__ == "__main__":
    main()
