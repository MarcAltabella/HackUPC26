from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .generate_dataset import PROJECT_ROOT, SCENARIOS, SimulationConfig
from .rl_agent import (
    RLConfig,
    get_epsilon,
    init_q_table,
    load_q_table,
    run_rl_episode,
    save_q_table,
)


DEFAULT_Q_TABLE_PATH = PROJECT_ROOT / "data" / "q_table.pkl"
DEFAULT_LOG_PATH = PROJECT_ROOT / "logs" / "implementation_log.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the Stage 2 RL maintenance agent.")
    parser.add_argument("--episodes", type=int, default=5_000, help="Number of training episodes.")
    parser.add_argument(
        "--scenarios",
        nargs="+",
        default=["baseline_nominal", "humid_factory", "chaos_run"],
        help="Scenario ids used for training.",
    )
    parser.add_argument("--alpha", type=float, default=RLConfig.alpha)
    parser.add_argument("--gamma", type=float, default=RLConfig.gamma)
    parser.add_argument("--epsilon-start", type=float, default=RLConfig.epsilon_start)
    parser.add_argument("--epsilon-end", type=float, default=RLConfig.epsilon_end)
    parser.add_argument(
        "--q-table-path",
        type=Path,
        default=DEFAULT_Q_TABLE_PATH,
        help="Output path for the trained Q-table.",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Implementation log file.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Load an existing Q-table before training if one exists.",
    )
    return parser.parse_args()


def select_scenarios(scenario_ids: list[str]) -> list[SimulationConfig]:
    available = {cfg.scenario_id: cfg for cfg in SCENARIOS}
    missing = [scenario_id for scenario_id in scenario_ids if scenario_id not in available]
    if missing:
        raise ValueError(f"Unknown scenario ids: {', '.join(missing)}")
    return [available[scenario_id] for scenario_id in scenario_ids]


def append_training_log(
    log_path: Path,
    *,
    args: argparse.Namespace,
    summary: dict[str, float | int | str],
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.write_text("# Implementation Log\n\n", encoding="utf-8")

    body = [
        f"- Timestamp: {datetime.now().isoformat()}",
        f"- Episodes: {args.episodes}",
        f"- Scenarios: {', '.join(args.scenarios)}",
        f"- Resume mode: {args.resume}",
        f"- Alpha: {args.alpha}",
        f"- Gamma: {args.gamma}",
        f"- Epsilon schedule: start={args.epsilon_start}, end={args.epsilon_end}",
        f"- Q-table path: {args.q_table_path}",
        f"- Mean episode reward: {summary['mean_reward']:.3f}",
        f"- Mean survival steps: {summary['mean_steps']:.2f}",
        f"- Failure rate: {summary['failure_rate']:.3f}",
        f"- Final epsilon: {summary['final_epsilon']:.3f}",
    ]

    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("## Milestone 6 - RL training run\n\n")
        handle.write("\n".join(body))
        handle.write("\n\n---\n\n")


def resolve_project_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def main() -> None:
    args = parse_args()
    args.q_table_path = resolve_project_path(args.q_table_path)
    args.log_path = resolve_project_path(args.log_path)
    scenarios = select_scenarios(args.scenarios)

    if args.resume and args.q_table_path.exists():
        q_table = load_q_table(args.q_table_path)
    else:
        q_table = init_q_table()

    total_reward = 0.0
    total_steps = 0
    failure_count = 0
    last_epsilon = args.epsilon_end

    for episode in range(args.episodes):
        cfg = scenarios[episode % len(scenarios)]
        epsilon = get_epsilon(
            episode,
            args.episodes,
            eps_start=args.epsilon_start,
            eps_end=args.epsilon_end,
        )
        result = run_rl_episode(
            cfg,
            run_id=episode,
            q_table=q_table,
            training=True,
            epsilon=epsilon,
            alpha=args.alpha,
            gamma=args.gamma,
        )
        total_reward += result.total_reward
        total_steps += result.steps_survived
        failure_count += int(result.failed)
        last_epsilon = epsilon

        if (episode + 1) % 250 == 0 or episode == 0 or episode + 1 == args.episodes:
            print(
                f"[train] episode={episode + 1}/{args.episodes} "
                f"scenario={cfg.scenario_id} epsilon={epsilon:.3f} "
                f"steps={result.steps_survived} reward={result.total_reward:.3f}"
            )

    args.q_table_path.parent.mkdir(parents=True, exist_ok=True)
    save_q_table(q_table, args.q_table_path)

    summary = {
        "mean_reward": total_reward / max(args.episodes, 1),
        "mean_steps": total_steps / max(args.episodes, 1),
        "failure_rate": failure_count / max(args.episodes, 1),
        "final_epsilon": last_epsilon,
    }
    append_training_log(args.log_path, args=args, summary=summary)

    print("[train] completed")
    print(f"[train] q_table_path={args.q_table_path}")
    print(f"[train] summary={summary}")


if __name__ == "__main__":
    main()
