from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

try:
    from .generate_dataset import (
        BLADE_INIT_MM,
        HEATER_R_NOMINAL,
        INSUL_R_MAX,
        MOTOR_V_NOMINAL,
        Phase1State,
        STATUS_MAP,
        Historian,
        SimulationConfig,
        _SCENARIO_SEED,
        _maintenance_level,
        sample_drivers,
        step_phase1,
    )
except ImportError:
    from generate_dataset import (
        BLADE_INIT_MM,
        HEATER_R_NOMINAL,
        INSUL_R_MAX,
        MOTOR_V_NOMINAL,
        Phase1State,
        STATUS_MAP,
        Historian,
        SimulationConfig,
        _SCENARIO_SEED,
        _maintenance_level,
        sample_drivers,
        step_phase1,
    )

SUBSYSTEMS: dict[str, tuple[str, ...]] = {
    "recoating": ("blade", "motor", "rail"),
    "printhead": ("nozzle", "resistor", "cleaning"),
    "thermal": ("heater", "sensor", "insulation"),
}

ACTION_TO_MAINTENANCE_LEVEL = {
    0: 0.0,
    1: 0.5,
    2: 1.0,
}

STATE_DIM = 10
_HEALTH_KEYS: tuple[str, ...] = (
    "health_blade", "health_motor", "health_rail",
    "health_nozzle", "health_resistor", "health_cleaning",
    "health_heater", "health_sensor", "health_insulation",
)


def continuous_state(state_report: dict[str, Any], steps_since_maint: int) -> torch.Tensor:
    values = [float(state_report[k]) for k in _HEALTH_KEYS]
    values.append(min(steps_since_maint / 100.0, 1.0))
    return torch.tensor(values, dtype=torch.float32)


class DQN(nn.Module):
    def __init__(self, state_dim: int = STATE_DIM, action_dim: int = 3, hidden: int = 64) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, action_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class ReplayBuffer:
    def __init__(self, capacity: int = 50_000) -> None:
        self._buf: deque[tuple] = deque(maxlen=capacity)

    def push(
        self,
        state: torch.Tensor,
        action: int,
        reward: float,
        next_state: torch.Tensor,
        done: bool,
    ) -> None:
        self._buf.append((state.cpu(), action, reward, next_state.cpu(), float(done)))

    def sample(
        self, batch_size: int
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        batch = random.sample(self._buf, batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)
        return (
            torch.stack(states).to(DEVICE),
            torch.tensor(actions, dtype=torch.long, device=DEVICE),
            torch.tensor(rewards, dtype=torch.float32, device=DEVICE),
            torch.stack(next_states).to(DEVICE),
            torch.tensor(dones, dtype=torch.float32, device=DEVICE),
        )

    def __len__(self) -> int:
        return len(self._buf)


@dataclass(frozen=True)
class RLConfig:
    alpha: float = 0.1
    gamma: float = 0.99
    epsilon_start: float = 1.0
    epsilon_end: float = 0.05
    q_table_path: str = "q_table.pkl"


@dataclass(frozen=True)
class EpisodeResult:
    total_reward: float
    steps_survived: int
    failed: bool


def subsystem_healths(state_report: dict[str, Any]) -> dict[str, float]:
    return {
        name: min(float(state_report[f"health_{key}"]) for key in keys)
        for name, keys in SUBSYSTEMS.items()
    }


def discretise(state_report: dict[str, Any], steps_since_maint: int) -> tuple[int, int, int, int]:
    def bin5(value: float) -> int:
        return min(int(value * 5), 4)

    def bin_time(steps: int) -> int:
        if steps < 20:
            return 0
        if steps < 60:
            return 1
        return 2

    mins = subsystem_healths(state_report)
    return (
        bin5(mins["recoating"]),
        bin5(mins["printhead"]),
        bin5(mins["thermal"]),
        bin_time(steps_since_maint),
    )


def compute_reward(
    state_report: dict[str, Any],
    action: int,
    prev_state_report: dict[str, Any] | None = None,
) -> float:
    mins = subsystem_healths(state_report)
    min_health = min(mins.values())

    any_failed = any(
        value == "FAILED"
        for key, value in state_report.items()
        if key.startswith("status_")
    )

    action_cost = {0: 0, 1: -5, 2: -10}[action]
    failure_penalty = -100 if any_failed else 0
    alive_bonus = 1
    if prev_state_report is not None:
        prev_min = min(subsystem_healths(prev_state_report).values())
        health_signal = 2.0 * (min_health - prev_min) - 0.3 * (1.0 - min_health)
    else:
        health_signal = -0.5 * (1.0 - min_health)
    return alive_bonus + action_cost + failure_penalty + health_signal


def update_q(
    q_table: torch.Tensor,
    state: tuple[int, int, int, int],
    action: int,
    reward: float,
    next_state: tuple[int, int, int, int],
    alpha: float = 0.1,
    gamma: float = 0.99,
    done: bool = False,
) -> None:
    best_next = 0.0 if done else float(q_table[next_state].max().item())
    td_target = reward + gamma * best_next
    q_table[state][action] += alpha * (td_target - q_table[state][action].item())


def init_q_table() -> torch.Tensor:
    return torch.zeros((5, 5, 5, 3, 3), dtype=torch.float32, device=DEVICE)


def save_q_table(q_table: torch.Tensor, path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(q_table, output_path)


def load_q_table(path: str | Path) -> torch.Tensor:
    return torch.load(Path(path), map_location=DEVICE, weights_only=True)


def update_dqn(
    policy_net: DQN,
    target_net: DQN,
    optimizer: optim.Optimizer,
    buffer: ReplayBuffer,
    *,
    batch_size: int = 64,
    gamma: float = 0.99,
) -> float:
    if len(buffer) < batch_size:
        return 0.0
    states, actions, rewards, next_states, dones = buffer.sample(batch_size)
    current_q = policy_net(states).gather(1, actions.unsqueeze(1)).squeeze(1)
    with torch.no_grad():
        next_q = target_net(next_states).max(1)[0]
        target_q = rewards + gamma * next_q * (1.0 - dones)
    loss = F.mse_loss(current_q, target_q)
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()
    return loss.item()


def pick_action_dqn(
    policy_net: DQN,
    state: torch.Tensor,
    epsilon: float,
    rng: np.random.Generator | None = None,
) -> int:
    sampler = rng if rng is not None else np.random.default_rng()
    if float(sampler.random()) < epsilon:
        return int(sampler.integers(3))
    with torch.no_grad():
        return int(policy_net(state.unsqueeze(0).to(DEVICE)).argmax(dim=1).item())


def save_dqn(model: DQN, path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), output_path)


def load_dqn(path: str | Path) -> DQN:
    model = DQN()
    model.load_state_dict(torch.load(Path(path), map_location=DEVICE, weights_only=True))
    model.to(DEVICE)
    model.eval()
    return model


def get_epsilon(
    episode: int,
    n_episodes: int,
    eps_start: float = 1.0,
    eps_end: float = 0.05,
) -> float:
    if n_episodes <= 0:
        return eps_end
    decay = (eps_end / eps_start) ** (1.0 / n_episodes)
    return max(eps_end, eps_start * (decay ** episode))


def pick_action(
    q_table: torch.Tensor,
    state: tuple[int, int, int, int],
    epsilon: float,
    rng: np.random.Generator | None = None,
) -> int:
    sampler = rng if rng is not None else np.random.default_rng()
    if float(sampler.random()) < epsilon:
        return int(sampler.integers(3))
    return int(q_table[state].argmax().item())


def action_to_maintenance_level(action: int) -> float:
    if action not in ACTION_TO_MAINTENANCE_LEVEL:
        raise ValueError(f"Unsupported RL action: {action}")
    return ACTION_TO_MAINTENANCE_LEVEL[action]


def maintenance_level_to_action(maintenance_level: float) -> int:
    for action, level in ACTION_TO_MAINTENANCE_LEVEL.items():
        if abs(level - maintenance_level) < 1e-9:
            return action
    raise ValueError(f"Unsupported maintenance level: {maintenance_level}")


def is_terminal_state(state_report: dict[str, Any]) -> bool:
    return any(
        value == "FAILED"
        for key, value in state_report.items()
        if key.startswith("status_")
    )


def initial_state_report() -> dict[str, Any]:
    report = {
        "health_blade": 1.0,
        "health_motor": 1.0,
        "health_rail": 1.0,
        "health_nozzle": 1.0,
        "health_resistor": 1.0,
        "health_cleaning": 1.0,
        "health_heater": 1.0,
        "health_sensor": 1.0,
        "health_insulation": 1.0,
        "status_blade": "FUNCTIONAL",
        "status_motor": "FUNCTIONAL",
        "status_rail": "FUNCTIONAL",
        "status_nozzle": "FUNCTIONAL",
        "status_resistor": "FUNCTIONAL",
        "status_cleaning": "FUNCTIONAL",
        "status_heater": "FUNCTIONAL",
        "status_sensor": "FUNCTIONAL",
        "status_insulation": "FUNCTIONAL",
        "metric_blade_mm": BLADE_INIT_MM,
        "metric_motor_vib": MOTOR_V_NOMINAL,
        "metric_rail_dev": 0.0,
        "metric_nozzle_clog": 0.0,
        "metric_resistor_pct": 0.0,
        "metric_cleaning_eff": 1.0,
        "metric_heater_ohm": HEATER_R_NOMINAL,
        "metric_sensor_err": 0.0,
        "metric_insulation_r": INSUL_R_MAX,
        "health_recoating": 1.0,
        "health_printhead": 1.0,
        "health_thermal": 1.0,
        "label_blade": STATUS_MAP["FUNCTIONAL"],
        "label_motor": STATUS_MAP["FUNCTIONAL"],
        "label_rail": STATUS_MAP["FUNCTIONAL"],
        "label_nozzle": STATUS_MAP["FUNCTIONAL"],
        "label_resistor": STATUS_MAP["FUNCTIONAL"],
        "label_cleaning": STATUS_MAP["FUNCTIONAL"],
        "label_heater": STATUS_MAP["FUNCTIONAL"],
        "label_sensor": STATUS_MAP["FUNCTIONAL"],
        "label_insulation": STATUS_MAP["FUNCTIONAL"],
        "action_taken": None,
        "reward": None,
    }
    return report


def run_rl_episode(
    cfg: SimulationConfig,
    run_id: int,
    q_table: torch.Tensor,
    *,
    training: bool = False,
    epsilon: float = 0.0,
    alpha: float = 0.1,
    gamma: float = 0.99,
    historian: Historian | None = None,
) -> EpisodeResult:
    def rl_policy(
        _t: int,
        state: tuple[int, int, int, int],
        _state_report: dict[str, Any],
        _steps_since_maint: int,
        rng: np.random.Generator,
    ) -> tuple[int, float]:
        action = pick_action(q_table, state, epsilon, rng=rng)
        return action, action_to_maintenance_level(action)

    return _run_episode(
        cfg,
        run_id,
        rl_policy,
        q_table=q_table,
        training=training,
        alpha=alpha,
        gamma=gamma,
        historian=historian,
    )


def run_schedule_episode(
    cfg: SimulationConfig,
    run_id: int,
    maintenance_schedule: str = "fixed_100",
    *,
    historian: Historian | None = None,
) -> EpisodeResult:
    def schedule_policy(
        t: int,
        _state: tuple[int, int, int, int],
        _state_report: dict[str, Any],
        _steps_since_maint: int,
        _rng: np.random.Generator,
    ) -> tuple[int, float]:
        maintenance_level = _maintenance_level(maintenance_schedule, t)
        action = maintenance_level_to_action(maintenance_level)
        return action, maintenance_level

    return _run_episode(
        cfg,
        run_id,
        schedule_policy,
        historian=historian,
    )


def _run_episode(
    cfg: SimulationConfig,
    run_id: int,
    policy: Callable[
        [int, tuple[int, int, int, int], dict[str, Any], int, np.random.Generator],
        tuple[int, float],
    ],
    *,
    q_table: torch.Tensor | None = None,
    training: bool = False,
    alpha: float = 0.1,
    gamma: float = 0.99,
    historian: Historian | None = None,
) -> EpisodeResult:
    seed = _SCENARIO_SEED[cfg.scenario_id] + run_id * 997
    rng = np.random.default_rng(seed)

    phase1_state = Phase1State()
    state_report = initial_state_report()
    steps_since_maint = 0
    total_reward = 0.0
    failed = False
    ticks = 0

    for t in range(cfg.total_steps):
        state = discretise(state_report, steps_since_maint)
        action, maintenance_level = policy(t, state, state_report, steps_since_maint, rng)
        steps_since_maint = 0 if action > 0 else steps_since_maint + 1

        drivers = sample_drivers(t, cfg, rng)
        drivers = drivers._replace(maintenance_level=maintenance_level)

        phase1_state, new_report = step_phase1(phase1_state, drivers)
        reward = compute_reward(new_report, action, state_report)
        done = is_terminal_state(new_report)
        next_state = discretise(new_report, steps_since_maint)

        if training:
            if q_table is None:
                raise ValueError("Q-table is required when training=True")
            update_q(
                q_table,
                state,
                action,
                reward,
                next_state,
                alpha=alpha,
                gamma=gamma,
                done=done,
            )

        if historian is not None:
            historian.write(
                {
                    "scenario_id": cfg.scenario_id,
                    "run_id": run_id,
                    "t": t,
                    "temperature": round(drivers.temperature, 3),
                    "humidity": round(drivers.humidity, 4),
                    "load": round(drivers.load, 1),
                    "maintenance": drivers.maintenance_level,
                    "is_shock": int(drivers.is_shock),
                    **new_report,
                    "action_taken": action,
                    "reward": reward,
                }
            )

        total_reward += reward
        ticks = t + 1
        state_report = new_report
        failed = done
        if done:
            break

    return EpisodeResult(total_reward=total_reward, steps_survived=ticks, failed=failed)


def run_dqn_episode(
    cfg: SimulationConfig,
    run_id: int,
    policy_net: DQN,
    *,
    training: bool = False,
    epsilon: float = 0.0,
    optimizer: optim.Optimizer | None = None,
    buffer: ReplayBuffer | None = None,
    target_net: DQN | None = None,
    batch_size: int = 64,
    gamma: float = 0.99,
    historian: Historian | None = None,
) -> EpisodeResult:
    seed = _SCENARIO_SEED[cfg.scenario_id] + run_id * 997
    rng = np.random.default_rng(seed)

    phase1_state = Phase1State()
    state_report = initial_state_report()
    steps_since_maint = 0
    total_reward = 0.0
    failed = False
    ticks = 0

    for t in range(cfg.total_steps):
        state_vec = continuous_state(state_report, steps_since_maint)
        action = pick_action_dqn(policy_net, state_vec, epsilon, rng=rng)
        maintenance_level = action_to_maintenance_level(action)
        steps_since_maint = 0 if action > 0 else steps_since_maint + 1

        drivers = sample_drivers(t, cfg, rng)
        drivers = drivers._replace(maintenance_level=maintenance_level)

        phase1_state, new_report = step_phase1(phase1_state, drivers)
        reward = compute_reward(new_report, action, state_report)
        done = is_terminal_state(new_report)
        next_state_vec = continuous_state(new_report, steps_since_maint)

        if training:
            if buffer is None or optimizer is None or target_net is None:
                raise ValueError("buffer, optimizer, and target_net required when training=True")
            buffer.push(state_vec, action, reward, next_state_vec, done)
            update_dqn(policy_net, target_net, optimizer, buffer, batch_size=batch_size, gamma=gamma)

        if historian is not None:
            historian.write(
                {
                    "scenario_id": cfg.scenario_id,
                    "run_id": run_id,
                    "t": t,
                    "temperature": round(drivers.temperature, 3),
                    "humidity": round(drivers.humidity, 4),
                    "load": round(drivers.load, 1),
                    "maintenance": drivers.maintenance_level,
                    "is_shock": int(drivers.is_shock),
                    **new_report,
                    "action_taken": action,
                    "reward": reward,
                }
            )

        total_reward += reward
        ticks = t + 1
        state_report = new_report
        failed = done
        if done:
            break

    return EpisodeResult(total_reward=total_reward, steps_survived=ticks, failed=failed)


__all__ = [
    "ACTION_TO_MAINTENANCE_LEVEL",
    "DEVICE",
    "DQN",
    "EpisodeResult",
    "RLConfig",
    "ReplayBuffer",
    "STATE_DIM",
    "action_to_maintenance_level",
    "compute_reward",
    "continuous_state",
    "discretise",
    "get_epsilon",
    "init_q_table",
    "initial_state_report",
    "is_terminal_state",
    "load_dqn",
    "load_q_table",
    "maintenance_level_to_action",
    "pick_action",
    "pick_action_dqn",
    "run_dqn_episode",
    "run_rl_episode",
    "run_schedule_episode",
    "save_dqn",
    "save_q_table",
    "subsystem_healths",
    "update_dqn",
    "update_q",
]
