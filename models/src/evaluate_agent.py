from __future__ import annotations

import argparse
import csv
import json
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .generate_dataset import PROJECT_ROOT, SCENARIOS, SimulationConfig
from .rl_agent import load_dqn, load_q_table, run_dqn_episode, run_rl_episode, run_schedule_episode


DEFAULT_Q_TABLE_PATH = PROJECT_ROOT / "data" / "q_table.pkl"
DEFAULT_DQN_PATH = PROJECT_ROOT / "data" / "dqn.pt"
DEFAULT_LOG_PATH = PROJECT_ROOT / "logs" / "implementation_log.md"
DEFAULT_SUMMARY_PATH = PROJECT_ROOT / "data" / "rl_eval_summary.json"
DEFAULT_RUNS_PATH = PROJECT_ROOT / "data" / "rl_eval_runs.csv"


@dataclass(frozen=True)
class EvaluationRow:
    policy: str
    scenario_id: str
    run_id: int
    steps_survived: int
    failed: bool
    total_reward: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the Stage 2 RL maintenance agent.")
    parser.add_argument(
        "--scenarios",
        nargs="+",
        default=["baseline_nominal", "humid_factory", "chaos_run"],
        help="Scenario ids used for evaluation.",
    )
    parser.add_argument("--runs", type=int, default=50, help="Runs per policy per scenario.")
    parser.add_argument(
        "--baseline-schedule",
        default="fixed_100",
        help="Baseline maintenance schedule used for comparison.",
    )
    parser.add_argument(
        "--q-table-path",
        type=Path,
        default=DEFAULT_Q_TABLE_PATH,
        help="Path to the trained Q-table.",
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=DEFAULT_SUMMARY_PATH,
        help="JSON file with aggregate evaluation metrics.",
    )
    parser.add_argument(
        "--runs-path",
        type=Path,
        default=DEFAULT_RUNS_PATH,
        help="CSV file with per-run evaluation rows.",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Implementation log file.",
    )
    parser.add_argument(
        "--dqn-path",
        type=Path,
        default=None,
        help="Path to a trained DQN model. When provided, DQN is evaluated alongside the Q-table.",
    )
    return parser.parse_args()


def select_scenarios(scenario_ids: list[str]) -> list[SimulationConfig]:
    available = {cfg.scenario_id: cfg for cfg in SCENARIOS}
    missing = [scenario_id for scenario_id in scenario_ids if scenario_id not in available]
    if missing:
        raise ValueError(f"Unknown scenario ids: {', '.join(missing)}")
    return [available[scenario_id] for scenario_id in scenario_ids]


def summarize_rows(rows: list[EvaluationRow]) -> dict[str, float]:
    steps = [row.steps_survived for row in rows]
    rewards = [row.total_reward for row in rows]
    failures = [int(row.failed) for row in rows]
    return {
        "mean_time_to_first_failure": round(statistics.fmean(steps), 3),
        "median_time_to_first_failure": round(statistics.median(steps), 3),
        "mean_total_reward": round(statistics.fmean(rewards), 3),
        "survival_rate": round(1.0 - statistics.fmean(failures), 3),
        "failure_rate": round(statistics.fmean(failures), 3),
    }


def append_evaluation_log(
    log_path: Path,
    *,
    args: argparse.Namespace,
    summary: dict[str, object],
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.write_text("# Implementation Log\n\n", encoding="utf-8")

    body = [
        f"- Timestamp: {datetime.now().isoformat()}",
        f"- Scenarios: {', '.join(args.scenarios)}",
        f"- Runs per scenario: {args.runs}",
        f"- Baseline schedule: {args.baseline_schedule}",
        f"- Q-table path: {args.q_table_path}",
        f"- Summary path: {args.summary_path}",
        f"- Runs path: {args.runs_path}",
        f"- Overall RL mean TTF: {summary['overall']['rl']['mean_time_to_first_failure']}",
        f"- Overall baseline mean TTF: {summary['overall']['baseline']['mean_time_to_first_failure']}",
        f"- Overall RL survival rate: {summary['overall']['rl']['survival_rate']}",
        f"- Overall baseline survival rate: {summary['overall']['baseline']['survival_rate']}",
    ]

    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("## Milestone 6 - RL evaluation run\n\n")
        handle.write("\n".join(body))
        handle.write("\n\n---\n\n")


def resolve_project_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def main() -> None:
    args = parse_args()
    args.q_table_path = resolve_project_path(args.q_table_path)
    args.summary_path = resolve_project_path(args.summary_path)
    args.runs_path = resolve_project_path(args.runs_path)
    args.log_path = resolve_project_path(args.log_path)
    q_table = load_q_table(args.q_table_path)
    dqn = load_dqn(args.dqn_path) if (args.dqn_path is not None and args.dqn_path.exists()) else None
    scenarios = select_scenarios(args.scenarios)
    policies = ["rl", "baseline"] + (["dqn"] if dqn is not None else [])

    rows: list[EvaluationRow] = []

    for cfg in scenarios:
        for run_id in range(args.runs):
            rl_result = run_rl_episode(cfg, run_id=run_id, q_table=q_table, training=False, epsilon=0.0)
            rows.append(
                EvaluationRow(
                    policy="rl",
                    scenario_id=cfg.scenario_id,
                    run_id=run_id,
                    steps_survived=rl_result.steps_survived,
                    failed=rl_result.failed,
                    total_reward=round(rl_result.total_reward, 6),
                )
            )

            baseline_result = run_schedule_episode(
                cfg,
                run_id=run_id,
                maintenance_schedule=args.baseline_schedule,
            )
            rows.append(
                EvaluationRow(
                    policy="baseline",
                    scenario_id=cfg.scenario_id,
                    run_id=run_id,
                    steps_survived=baseline_result.steps_survived,
                    failed=baseline_result.failed,
                    total_reward=round(baseline_result.total_reward, 6),
                )
            )

            if dqn is not None:
                dqn_result = run_dqn_episode(cfg, run_id=run_id, policy_net=dqn, training=False, epsilon=0.0)
                rows.append(
                    EvaluationRow(
                        policy="dqn",
                        scenario_id=cfg.scenario_id,
                        run_id=run_id,
                        steps_survived=dqn_result.steps_survived,
                        failed=dqn_result.failed,
                        total_reward=round(dqn_result.total_reward, 6),
                    )
                )

    per_scenario: dict[str, dict[str, dict[str, float]]] = {}
    for cfg in scenarios:
        scenario_rows = [row for row in rows if row.scenario_id == cfg.scenario_id]
        per_scenario[cfg.scenario_id] = {
            p: summarize_rows([row for row in scenario_rows if row.policy == p]) for p in policies
        }

    summary = {
        "generated_at": datetime.now().isoformat(),
        "baseline_schedule": args.baseline_schedule,
        "runs_per_scenario": args.runs,
        "scenarios": args.scenarios,
        "overall": {
            p: summarize_rows([row for row in rows if row.policy == p]) for p in policies
        },
        "per_scenario": per_scenario,
    }

    args.summary_path.parent.mkdir(parents=True, exist_ok=True)
    args.runs_path.parent.mkdir(parents=True, exist_ok=True)

    with args.summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)

    with args.runs_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))

    append_evaluation_log(args.log_path, args=args, summary=summary)

    print("[eval] completed")
    print(f"[eval] summary_path={args.summary_path}")
    print(f"[eval] runs_path={args.runs_path}")
    print(json.dumps(summary["overall"], indent=2))


if __name__ == "__main__":
    main()
