from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import torch.optim as optim

try:
    from .generate_dataset import PROJECT_ROOT, SCENARIOS, SimulationConfig
    from .rl_agent import (
        DEVICE,
        DQN,
        ReplayBuffer,
        RLConfig,
        get_epsilon,
        load_dqn,
        run_dqn_episode,
        save_dqn,
    )
except ImportError:
    from generate_dataset import PROJECT_ROOT, SCENARIOS, SimulationConfig
    from rl_agent import (
        DEVICE,
        DQN,
        ReplayBuffer,
        RLConfig,
        get_epsilon,
        load_dqn,
        run_dqn_episode,
        save_dqn,
    )


DEFAULT_DQN_PATH = PROJECT_ROOT / "data" / "dqn.pt"
DEFAULT_LOG_PATH = PROJECT_ROOT / "logs" / "implementation_log.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the DQN maintenance agent.")
    parser.add_argument("--episodes", type=int, default=5_000)
    parser.add_argument(
        "--scenarios",
        nargs="+",
        default=["baseline_nominal", "humid_factory", "chaos_run"],
    )
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--gamma", type=float, default=RLConfig.gamma)
    parser.add_argument("--epsilon-start", type=float, default=RLConfig.epsilon_start)
    parser.add_argument("--epsilon-end", type=float, default=RLConfig.epsilon_end)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--buffer-capacity", type=int, default=50_000)
    parser.add_argument(
        "--target-update-freq",
        type=int,
        default=10,
        help="Sync target network every N episodes.",
    )
    parser.add_argument("--dqn-path", type=Path, default=DEFAULT_DQN_PATH)
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def select_scenarios(scenario_ids: list[str]) -> list[SimulationConfig]:
    available = {cfg.scenario_id: cfg for cfg in SCENARIOS}
    missing = [s for s in scenario_ids if s not in available]
    if missing:
        raise ValueError(f"Unknown scenario ids: {', '.join(missing)}")
    return [available[s] for s in scenario_ids]


def resolve_project_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def main() -> None:
    args = parse_args()
    args.dqn_path = resolve_project_path(args.dqn_path)
    args.log_path = resolve_project_path(args.log_path)
    scenarios = select_scenarios(args.scenarios)

    print(f"[dqn-train] device={DEVICE}")

    if args.resume and args.dqn_path.exists():
        policy_net = load_dqn(args.dqn_path)
        policy_net.train()
    else:
        policy_net = DQN().to(DEVICE)

    target_net = DQN().to(DEVICE)
    target_net.load_state_dict(policy_net.state_dict())
    target_net.eval()

    optimizer = optim.Adam(policy_net.parameters(), lr=args.lr)
    buffer = ReplayBuffer(capacity=args.buffer_capacity)

    total_reward = 0.0
    total_steps = 0
    failure_count = 0

    for episode in range(args.episodes):
        cfg = scenarios[episode % len(scenarios)]
        epsilon = get_epsilon(
            episode,
            args.episodes,
            eps_start=args.epsilon_start,
            eps_end=args.epsilon_end,
        )
        result = run_dqn_episode(
            cfg,
            run_id=episode,
            policy_net=policy_net,
            training=True,
            epsilon=epsilon,
            optimizer=optimizer,
            buffer=buffer,
            target_net=target_net,
            batch_size=args.batch_size,
            gamma=args.gamma,
        )
        total_reward += result.total_reward
        total_steps += result.steps_survived
        failure_count += int(result.failed)

        if (episode + 1) % args.target_update_freq == 0:
            target_net.load_state_dict(policy_net.state_dict())

        if (episode + 1) % 250 == 0 or episode == 0 or episode + 1 == args.episodes:
            print(
                f"[dqn-train] episode={episode + 1}/{args.episodes} "
                f"scenario={cfg.scenario_id} epsilon={epsilon:.3f} "
                f"steps={result.steps_survived} reward={result.total_reward:.3f} "
                f"buffer={len(buffer)}"
            )

    policy_net.eval()
    args.dqn_path.parent.mkdir(parents=True, exist_ok=True)
    save_dqn(policy_net, args.dqn_path)

    summary = {
        "mean_reward": total_reward / max(args.episodes, 1),
        "mean_steps": total_steps / max(args.episodes, 1),
        "failure_rate": failure_count / max(args.episodes, 1),
        "final_epsilon": get_epsilon(args.episodes - 1, args.episodes, eps_start=args.epsilon_start, eps_end=args.epsilon_end),
    }

    log_path = args.log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.write_text("# Implementation Log\n\n", encoding="utf-8")
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"## DQN training run\n\n")
        handle.write(f"- Timestamp: {datetime.now().isoformat()}\n")
        handle.write(f"- Episodes: {args.episodes}\n")
        handle.write(f"- Scenarios: {', '.join(args.scenarios)}\n")
        handle.write(f"- lr={args.lr}, gamma={args.gamma}, batch={args.batch_size}\n")
        handle.write(f"- Mean reward: {summary['mean_reward']:.3f}\n")
        handle.write(f"- Failure rate: {summary['failure_rate']:.3f}\n")
        handle.write("\n---\n\n")

    print("[dqn-train] completed")
    print(f"[dqn-train] dqn_path={args.dqn_path}")
    print(f"[dqn-train] summary={summary}")


if __name__ == "__main__":
    main()
