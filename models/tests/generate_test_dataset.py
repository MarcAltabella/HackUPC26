"""
Generate a held-out test dataset for model accuracy evaluation.

Uses the same simulation engine as training data, but with:
  - Existing 5 scenarios, run IDs 20–34 (not seen during training which used 0–19)
  - 2 OOD scenarios: extreme_stress and optimal_care

Output:
  tests/data/test_simulation.db   (primary SQLite)
  tests/data/test_dataset.csv     (CSV fallback)

Usage:
  cd /path/to/models
  python -m tests.generate_test_dataset
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import src.generate_dataset as _gen

TESTS_DIR = PROJECT_ROOT / "tests"
OUT_DIR = TESTS_DIR / "data"

# Run IDs 20-34: different seeds from training (0-19), same scenario distributions
TEST_RUN_ID_START = 20
TEST_RUNS_PER_SCENARIO = 15  # 15 × 5 = 75K baseline rows

# OOD scenarios — add seeds to the module dict so run_simulation can look them up
_gen._SCENARIO_SEED["extreme_stress"] = 5_000_000
_gen._SCENARIO_SEED["optimal_care"] = 6_000_000

OOD_SCENARIOS = [
    _gen.SimulationConfig(
        scenario_id="extreme_stress",
        env_profile="chaos",
        chaos_prob=0.10,
        maintenance_schedule="none",
    ),
    _gen.SimulationConfig(
        scenario_id="optimal_care",
        env_profile="stochastic",
        chaos_prob=0.00,
        maintenance_schedule="full",
    ),
]
OOD_RUNS = 10


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    db_path = OUT_DIR / "test_simulation.db"
    csv_path = OUT_DIR / "test_dataset.csv"

    # Remove stale DB so we start fresh
    if db_path.exists():
        db_path.unlink()
        print(f"Removed existing {db_path.name}")

    historian = _gen.Historian(db_path, csv_path)
    total_rows = 0

    # Held-out runs of the 5 training scenarios
    for cfg in _gen.SCENARIOS:
        scenario_rows = 0
        for run_offset in range(TEST_RUNS_PER_SCENARIO):
            run_id = TEST_RUN_ID_START + run_offset
            n = _gen.run_simulation(cfg, run_id, historian)
            scenario_rows += n
        total_rows += scenario_rows
        print(f"  [{cfg.scenario_id:20s}]  {TEST_RUNS_PER_SCENARIO} runs  ->  {scenario_rows:,} rows")

    # OOD scenarios
    for cfg in OOD_SCENARIOS:
        scenario_rows = 0
        for run_id in range(OOD_RUNS):
            n = _gen.run_simulation(cfg, run_id, historian)
            scenario_rows += n
        total_rows += scenario_rows
        print(f"  [{cfg.scenario_id:20s}]  {OOD_RUNS} runs  ->  {scenario_rows:,} rows (OOD)")

    historian.close()

    if historian.backend == "sqlite":
        print(f"\nSQLite  ->  {db_path}  ({total_rows:,} rows)")
    else:
        print(f"\nCSV     ->  {csv_path}  ({total_rows:,} rows)")


if __name__ == "__main__":
    main()
