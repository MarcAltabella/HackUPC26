from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

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
    health_signal = -0.5 * max(0.0, 0.3 - min_health)
    return alive_bonus + action_cost + failure_penalty + health_signal


def update_q(
    q_table: np.ndarray,
    state: tuple[int, int, int, int],
    action: int,
    reward: float,
    next_state: tuple[int, int, int, int],
    alpha: float = 0.1,
    gamma: float = 0.99,
    done: bool = False,
) -> None:
    best_next = 0.0 if done else float(np.max(q_table[next_state]))
    td_target = reward + gamma * best_next
    q_table[state][action] += alpha * (td_target - q_table[state][action])


def init_q_table() -> np.ndarray:
    return np.zeros((5, 5, 5, 3, 3), dtype=np.float32)


def save_q_table(q_table: np.ndarray, path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as handle:
        pickle.dump(q_table, handle)


def load_q_table(path: str | Path) -> np.ndarray:
    with Path(path).open("rb") as handle:
        return pickle.load(handle)


def get_epsilon(
    episode: int,
    n_episodes: int,
    eps_start: float = 1.0,
    eps_end: float = 0.05,
) -> float:
    if n_episodes <= 0:
        return eps_end
    return max(eps_end, eps_start - (eps_start - eps_end) * episode / n_episodes)


def pick_action(
    q_table: np.ndarray,
    state: tuple[int, int, int, int],
    epsilon: float,
    rng: np.random.Generator | None = None,
) -> int:
    sampler = rng if rng is not None else np.random.default_rng()
    if float(sampler.random()) < epsilon:
        return int(sampler.integers(3))
    return int(np.argmax(q_table[state]))


def action_to_maintenance_level(action: int) -> float:
    if action not in ACTION_TO_MAINTENANCE_LEVEL:
        raise ValueError(f"Unsupported RL action: {action}")
    return ACTION_TO_MAINTENANCE_LEVEL[action]


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
    q_table: np.ndarray,
    *,
    training: bool = False,
    epsilon: float = 0.0,
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
        action = pick_action(q_table, state, epsilon, rng=rng)
        maintenance_level = action_to_maintenance_level(action)
        steps_since_maint = 0 if action > 0 else steps_since_maint + 1

        drivers = sample_drivers(t, cfg, rng)
        drivers = drivers._replace(maintenance_level=maintenance_level)

        phase1_state, new_report = step_phase1(phase1_state, drivers)
        reward = compute_reward(new_report, action, state_report)
        done = is_terminal_state(new_report)
        next_state = discretise(new_report, steps_since_maint)

        if training:
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


__all__ = [
    "ACTION_TO_MAINTENANCE_LEVEL",
    "EpisodeResult",
    "RLConfig",
    "action_to_maintenance_level",
    "compute_reward",
    "discretise",
    "get_epsilon",
    "init_q_table",
    "initial_state_report",
    "is_terminal_state",
    "load_q_table",
    "pick_action",
    "run_rl_episode",
    "save_q_table",
    "subsystem_healths",
    "update_q",
]
