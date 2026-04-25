from __future__ import annotations

import argparse
import io
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import torch
import torch.optim as optim

try:
    from .generate_dataset import PROJECT_ROOT, SCENARIOS, SimulationConfig
    from .rl_agent import (
        DEVICE,
        DQN,
        ReplayBuffer,
        RLConfig,
        collect_episode,
        get_epsilon,
        load_dqn,
        run_dqn_episode,
        save_dqn,
        update_dqn,
    )
except ImportError:
    from generate_dataset import PROJECT_ROOT, SCENARIOS, SimulationConfig
    from rl_agent import (
        DEVICE,
        DQN,
        ReplayBuffer,
        RLConfig,
        collect_episode,
        get_epsilon,
        load_dqn,
        run_dqn_episode,
        save_dqn,
        update_dqn,
    )

DEFAULT_DQN_PATH = PROJECT_ROOT / "data" / "dqn.pt"
DEFAULT_LOG_PATH = PROJECT_ROOT / "logs" / "implementation_log.md"
_FORK_CTX = multiprocessing.get_context("fork")


# ---------------------------------------------------------------------------
# Fork worker — runs one episode on CPU, returns serialisable transitions
# ---------------------------------------------------------------------------

def _collect_worker(args: tuple) -> tuple[float, int, bool, list]:
    state_dict_bytes, scenario_id, run_id, epsilon = args
    import io as _io
    import torch as _torch
    from src.rl_agent import DQN as _DQN, collect_episode as _collect
    from src.generate_dataset import SCENARIOS as _S

    cfg = next(c for c in _S if c.scenario_id == scenario_id)
    model = _DQN()
    model.load_state_dict(_torch.load(_io.BytesIO(state_dict_bytes), map_location="cpu", weights_only=True))
    model.cpu().eval()
    result, transitions = _collect(cfg, run_id, model, epsilon=epsilon)
    return result.total_reward, result.steps_survived, result.failed, transitions


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def checkpoint_path(dqn_path: Path) -> Path:
    return dqn_path.with_name(dqn_path.stem + "_checkpoint.pt")


def periodic_path(dqn_path: Path, episode: int) -> Path:
    return dqn_path.with_name(f"{dqn_path.stem}_ep{episode}.pt")


def save_checkpoint(policy_net: DQN, episode: int, dqn_path: Path) -> None:
    ckpt = {"state_dict": policy_net.state_dict(), "episode": episode}
    torch.save(ckpt, checkpoint_path(dqn_path))


def load_checkpoint(dqn_path: Path) -> tuple[DQN, int]:
    ckpt_path = checkpoint_path(dqn_path)
    if ckpt_path.exists():
        ckpt = torch.load(ckpt_path, map_location=DEVICE, weights_only=True)
        model = DQN()
        model.load_state_dict(ckpt["state_dict"])
        model.to(DEVICE)
        return model, int(ckpt["episode"])
    model = load_dqn(dqn_path)
    return model, 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

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
    parser.add_argument(
        "--update-every",
        type=int,
        default=4,
        help="Gradient update every N transitions collected (default 4 = 4x fewer updates).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel env workers for experience collection (fork-based, CPU inference).",
    )
    parser.add_argument(
        "--checkpoint-freq",
        type=int,
        default=1_000,
        help="Save a periodic checkpoint every N episodes.",
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


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    args.dqn_path = resolve_project_path(args.dqn_path)
    args.log_path = resolve_project_path(args.log_path)
    scenarios = select_scenarios(args.scenarios)

    print(f"[dqn-train] device={DEVICE}  workers={args.workers}  update_every={args.update_every}")

    start_episode = 0
    if args.resume and (args.dqn_path.exists() or checkpoint_path(args.dqn_path).exists()):
        policy_net, start_episode = load_checkpoint(args.dqn_path)
        policy_net.train()
        print(f"[dqn-train] resumed from episode {start_episode}")
    else:
        policy_net = DQN().to(DEVICE)

    total_episodes = start_episode + args.episodes

    target_net = DQN().to(DEVICE)
    target_net.load_state_dict(policy_net.state_dict())
    target_net.eval()

    optimizer = optim.Adam(policy_net.parameters(), lr=args.lr)
    buffer = ReplayBuffer(capacity=args.buffer_capacity)

    total_reward = 0.0
    total_steps = 0
    failure_count = 0
    grad_updates = 0

    args.dqn_path.parent.mkdir(parents=True, exist_ok=True)

    pool = ProcessPoolExecutor(max_workers=args.workers, mp_context=_FORK_CTX) if args.workers > 1 else None

    try:
        i = 0
        while i < args.episodes:
            batch = min(args.workers, args.episodes - i)

            if pool is not None:
                # Serialise current weights for workers (CPU inference)
                buf = io.BytesIO()
                torch.save(policy_net.state_dict(), buf)
                state_dict_bytes = buf.getvalue()

                tasks = []
                for j in range(batch):
                    ep = start_episode + i + j
                    cfg = scenarios[ep % len(scenarios)]
                    eps = get_epsilon(ep, total_episodes, eps_start=args.epsilon_start, eps_end=args.epsilon_end)
                    tasks.append((state_dict_bytes, cfg.scenario_id, ep, eps))

                worker_results = list(pool.map(_collect_worker, tasks))
            else:
                # Single-worker: collect directly on GPU (no serialisation overhead)
                ep = start_episode + i
                cfg = scenarios[ep % len(scenarios)]
                eps = get_epsilon(ep, total_episodes, eps_start=args.epsilon_start, eps_end=args.epsilon_end)
                result, transitions = collect_episode(cfg, ep, policy_net, epsilon=eps)
                worker_results = [(result.total_reward, result.steps_survived, result.failed, transitions)]

            # Push transitions and do gradient updates
            for rwd, steps, failed, transitions in worker_results:
                total_reward += rwd
                total_steps += steps
                failure_count += int(failed)
                for s, a, r, ns, d in transitions:
                    buffer.push(
                        torch.tensor(s, dtype=torch.float32),
                        a, r,
                        torch.tensor(ns, dtype=torch.float32),
                        d,
                    )
                    grad_updates += 1
                    if grad_updates % args.update_every == 0:
                        update_dqn(
                            policy_net, target_net, optimizer, buffer,
                            batch_size=args.batch_size, gamma=args.gamma,
                        )

            # Target net sync
            episode_end = start_episode + i + batch
            if episode_end % args.target_update_freq < batch:
                target_net.load_state_dict(policy_net.state_dict())

            # Checkpoint
            if episode_end % args.checkpoint_freq < batch:
                save_dqn(policy_net, periodic_path(args.dqn_path, episode_end))
                save_checkpoint(policy_net, episode_end, args.dqn_path)
                print(f"[dqn-train] checkpoint saved at episode {episode_end}")

            # Logging
            if (i + batch) % 250 < batch or i == 0 or i + batch >= args.episodes:
                last_ep = start_episode + i + batch - 1
                last_eps = get_epsilon(last_ep, total_episodes, eps_start=args.epsilon_start, eps_end=args.epsilon_end)
                last_rwd = worker_results[-1][0]
                last_steps = worker_results[-1][1]
                print(
                    f"[dqn-train] episode={episode_end}/{total_episodes} "
                    f"epsilon={last_eps:.3f} steps={last_steps} "
                    f"reward={last_rwd:.2f} buffer={len(buffer)} grad_updates={grad_updates}"
                )

            i += batch

    finally:
        if pool:
            pool.shutdown()

    policy_net.eval()
    save_dqn(policy_net, args.dqn_path)

    summary = {
        "mean_reward": total_reward / max(args.episodes, 1),
        "mean_steps": total_steps / max(args.episodes, 1),
        "failure_rate": failure_count / max(args.episodes, 1),
        "episodes_trained": total_episodes,
        "grad_updates": grad_updates,
        "final_epsilon": get_epsilon(total_episodes - 1, total_episodes, eps_start=args.epsilon_start, eps_end=args.epsilon_end),
    }

    args.log_path.parent.mkdir(parents=True, exist_ok=True)
    if not args.log_path.exists():
        args.log_path.write_text("# Implementation Log\n\n", encoding="utf-8")
    with args.log_path.open("a", encoding="utf-8") as f:
        f.write("## DQN training run\n\n")
        f.write(f"- Timestamp: {datetime.now().isoformat()}\n")
        f.write(f"- Episodes: {args.episodes}  workers={args.workers}  update_every={args.update_every}\n")
        f.write(f"- Scenarios: {', '.join(args.scenarios)}\n")
        f.write(f"- lr={args.lr}, gamma={args.gamma}, batch={args.batch_size}\n")
        f.write(f"- Mean reward: {summary['mean_reward']:.3f}\n")
        f.write(f"- Failure rate: {summary['failure_rate']:.3f}\n")
        f.write(f"- Grad updates: {grad_updates}\n")
        f.write("\n---\n\n")

    print("[dqn-train] completed")
    print(f"[dqn-train] dqn_path={args.dqn_path}")
    print(f"[dqn-train] summary={summary}")


if __name__ == "__main__":
    main()
