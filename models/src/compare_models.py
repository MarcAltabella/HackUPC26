"""Compare all DQN checkpoints against the Q-table baseline.

Usage:
    python -m src.compare_models                  # all dqn_ep*.pt + dqn.pt
    python -m src.compare_models --runs 50        # more runs for tighter estimates
    python -m src.compare_models --model data/dqn_ep3000.pt  # single model
    python -m src.compare_models --workers 4      # override parallelism
"""
from __future__ import annotations

import argparse
import multiprocessing
import os
import statistics
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

# NOTE: rl_agent NOT imported here — keeps CUDA uninitialised in the parent
# process so fork-based workers can initialise it cleanly themselves.
try:
    from .generate_dataset import PROJECT_ROOT, SCENARIOS
except ImportError:
    from generate_dataset import PROJECT_ROOT, SCENARIOS

DATA = PROJECT_ROOT / "data"
Q_TABLE_PATH = DATA / "q_table.pkl"
_MP_CTX = multiprocessing.get_context("fork")


# --- worker functions (module-level so they're picklable) ---

def _dqn_worker(args: tuple) -> tuple[float, int, bool]:
    import os
    os.environ["CUDA_VISIBLE_DEVICES"] = ""  # force CPU before torch imports
    path_str, scenario_id, run_id = args
    import torch
    from src.rl_agent import DQN, DEVICE, run_dqn_episode
    from src.generate_dataset import SCENARIOS as _S
    cfg = next(c for c in _S if c.scenario_id == scenario_id)
    model = DQN()
    model.load_state_dict(torch.load(path_str, map_location=DEVICE, weights_only=True))
    model.to(DEVICE).eval()
    r = run_dqn_episode(cfg, run_id, model, training=False, epsilon=0.0)
    return r.total_reward, r.steps_survived, r.failed


def _qtable_worker(args: tuple) -> tuple[float, int, bool]:
    import os
    os.environ["CUDA_VISIBLE_DEVICES"] = ""  # force CPU before torch imports
    path_str, scenario_id, run_id = args
    import torch
    from src.rl_agent import DEVICE, run_rl_episode
    from src.generate_dataset import SCENARIOS as _S
    cfg = next(c for c in _S if c.scenario_id == scenario_id)
    q_table = torch.load(path_str, map_location=DEVICE, weights_only=True)
    r = run_rl_episode(cfg, run_id, q_table, training=False, epsilon=0.0)
    return r.total_reward, r.steps_survived, r.failed


# --- evaluation helpers ---

def _run_parallel(worker_fn, tasks: list, n_workers: int) -> list[tuple]:
    with ProcessPoolExecutor(max_workers=n_workers, mp_context=_MP_CTX) as pool:
        return list(pool.map(worker_fn, tasks))


def eval_dqn(label: str, model_path: Path, scenarios, runs: int, n_workers: int) -> dict:
    tasks = [(str(model_path), cfg.scenario_id, r) for cfg in scenarios for r in range(runs)]
    return _stats(label, _run_parallel(_dqn_worker, tasks, n_workers))


def eval_qtable(label: str, q_table_path: Path, scenarios, runs: int, n_workers: int) -> dict:
    tasks = [(str(q_table_path), cfg.scenario_id, r) for cfg in scenarios for r in range(runs)]
    return _stats(label, _run_parallel(_qtable_worker, tasks, n_workers))


def _stats(label: str, raw: list[tuple]) -> dict:
    rewards = [r[0] for r in raw]
    steps = [r[1] for r in raw]
    survival = sum(1 for r in raw if not r[2]) / len(raw)
    return {
        "label": label,
        "mean_reward": statistics.fmean(rewards),
        "mean_ttf": statistics.fmean(steps),
        "survival": survival,
    }


def print_table(rows: list[dict]) -> None:
    header = f"{'model':<26}  {'mean reward':>11}  {'mean TTF':>8}  {'survival':>8}"
    print(header)
    print("-" * len(header))
    for row in rows:
        bar = "█" * int(row["survival"] * 10)
        print(
            f"{row['label']:<26}  {row['mean_reward']:>11.1f}  {row['mean_ttf']:>8.1f}"
            f"  {row['survival']:>7.0%} {bar}"
        )


# --- CLI ---

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare DQN checkpoints vs Q-table.")
    parser.add_argument("--runs", type=int, default=30, help="Runs per scenario.")
    parser.add_argument(
        "--scenarios",
        nargs="+",
        default=["baseline_nominal", "humid_factory", "chaos_run"],
    )
    parser.add_argument("--model", type=Path, default=None, help="Evaluate a single model.")
    parser.add_argument("--q-table", type=Path, default=Q_TABLE_PATH)
    parser.add_argument(
        "--workers",
        type=int,
        default=min(os.cpu_count() or 4, 8),
        help="Parallel worker processes.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    available = {cfg.scenario_id: cfg for cfg in SCENARIOS}
    scenarios = [available[s] for s in args.scenarios]

    models = [args.model] if args.model else sorted(DATA.glob("dqn_ep*.pt")) + [DATA / "dqn.pt"]

    print(f"\nScenarios: {', '.join(args.scenarios)}  |  runs/scenario: {args.runs}  |  workers: {args.workers}\n")

    rows: list[dict] = []
    rows.append(eval_qtable("q_table", args.q_table, scenarios, args.runs, args.workers))
    for pt in models:
        if Path(pt).exists():
            rows.append(eval_dqn(pt.name, Path(pt), scenarios, args.runs, args.workers))

    print_table(rows)
    print()


if __name__ == "__main__":
    main()
