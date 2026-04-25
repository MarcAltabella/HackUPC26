# Stage 2 — Simulate: Architecture & Implementation Plan

## Overview

Phase 2 transforms the Phase 1 Logic Engine into a running Digital Twin. It owns the **Clock** (simulation loop), the **Historian** (persistence layer), and the **RL Maintenance Agent** (bonus). Phase 1 is called as a pure function at every tick — Phase 2 is its driver.

---

## Architecture

### System components

```
SimulationConfig
      │
      ▼
┌─────────────────────────────────────────────────────┐
│  THE CLOCK (simulation loop)                        │
│  - owns simulated time t                            │
│  - generates / mutates environmental drivers        │
│  - optionally injects chaos events                  │
└──────────────┬──────────────────────────────────────┘
               │  drivers (temp, humidity, load, maint)
               ▼
┌─────────────────────────────────────────────────────┐
│  PHASE 1 ENGINE  (imported, called as function)     │
│  - stateless: same inputs → same outputs            │
│  - returns: health[], status[], metrics[]           │
└──────────────┬──────────────────────────────────────┘
               │  state report
               ▼
┌─────────────────────────────────────────────────────┐
│  THE HISTORIAN  (SQLite / CSV)                      │
│  - appends one row per tick                         │
│  - columns: t, scenario_id, drivers, health,        │
│    status, metrics, action_taken                    │
└──────────────┬──────────────────────────────────────┘
               │  reads latest state
               ▼
┌─────────────────────────────────────────────────────┐
│  RL MAINTENANCE AGENT  (bonus)                      │
│  - observes state vector s from Historian           │
│  - picks action a ∈ {0, 1, 2}                      │
│  - returns maintenance coefficient → back to Clock  │
│  - computes reward r, updates Q-table (train only)  │
└─────────────────────────────────────────────────────┘
```

### Data flow per tick

1. Clock increments `t` by one time step
2. Clock samples environmental drivers (deterministic profile or chaos-injected)
3. RL Agent (if active) picks action `a`; Clock sets `maintenance_level` accordingly
4. Phase 1 Engine called with `(temp, humidity, load, maintenance_level)`
5. Phase 1 returns state report `{health, status, metrics}` per component
6. Historian writes row: `(t, scenario_id, drivers, state_report, action_taken, reward)`
7. RL Agent computes reward, updates Q-table (training mode only)
8. Repeat until `t == total_duration` or any component reaches `FAILED`

---

## SimulationConfig schema

```python
@dataclass
class SimulationConfig:
    total_steps: int          # e.g. 1000
    time_step_hours: float    # e.g. 1.0  (each tick = 1 simulated hour)
    scenario_id: str          # e.g. "humid_factory" | "dry_lab" | "chaos_run"
    env_profile: str          # "deterministic" | "stochastic" | "chaos"
    chaos_prob: float = 0.02  # probability of a shock event per tick
    use_rl_agent: bool = False
    rl_mode: str = "deploy"   # "train" | "deploy"
    q_table_path: str = "q_table.pkl"
```

---

## Environmental profiles

### Deterministic (Pattern A — baseline)
Driver values follow a pre-defined sequence loaded from a CSV or hardcoded ramp.

```python
# Example: temperature ramps up linearly over the run
temp = 20 + (t / total_steps) * 30   # 20°C → 50°C
humidity = 0.4                        # constant
load = t                              # cumulative hours
```

### Stochastic (Pattern C — bonus)
Base profile plus Gaussian noise and Poisson shock events.

```python
import numpy as np

def sample_drivers(t, total_steps, chaos_prob=0.02):
    temp = 20 + (t / total_steps) * 30 + np.random.normal(0, 2)
    humidity = np.clip(0.4 + np.random.normal(0, 0.05), 0, 1)
    load = t
    # Chaos: random contamination burst
    shock = np.random.random() < chaos_prob
    humidity = min(1.0, humidity + (0.3 if shock else 0))
    return temp, humidity, load, shock
```

---

## Historian schema

### SQLite (recommended for queryability)

```sql
CREATE TABLE simulation_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id TEXT    NOT NULL,
    t           INTEGER NOT NULL,
    -- Environmental drivers
    temperature REAL,
    humidity    REAL,
    load        REAL,
    maintenance REAL,
    -- Component health indices (0.0 – 1.0)
    health_blade   REAL,
    health_nozzle  REAL,
    health_heater  REAL,
    -- Component statuses
    status_blade   TEXT,
    status_nozzle  TEXT,
    status_heater  TEXT,
    -- Component metrics (physical variables)
    metric_blade   REAL,   -- blade thickness mm
    metric_nozzle  REAL,   -- clog probability
    metric_heater  REAL,   -- resistance Ω
    -- RL columns
    action_taken   INTEGER,  -- 0 | 1 | 2 | NULL
    reward         REAL
);

CREATE INDEX idx_scenario ON simulation_log (scenario_id, t);
```

### CSV fallback

```
t,scenario_id,temperature,humidity,load,maintenance,
health_blade,health_nozzle,health_heater,
status_blade,status_nozzle,status_heater,
metric_blade,metric_nozzle,metric_heater,
action_taken,reward
```

---

## RL Maintenance Agent

### State space

State vector `s = (bin_blade, bin_nozzle, bin_heater, bin_time_since_maint)`.

| Dimension | Values | Bins |
|---|---|---|
| `health_blade` | 0.0 – 1.0 | 5 |
| `health_nozzle` | 0.0 – 1.0 | 5 |
| `health_heater` | 0.0 – 1.0 | 5 |
| `steps_since_maintenance` | 0 – ∞ | 3 (recent/medium/long) |

Total states: 5 × 5 × 5 × 3 = **375**

```python
def discretise(health_blade, health_nozzle, health_heater, steps_since_maint):
    def bin5(v): return min(int(v * 5), 4)
    def bin_time(n):
        if n < 20: return 0
        if n < 60: return 1
        return 2
    return (bin5(health_blade), bin5(health_nozzle),
            bin5(health_heater), bin_time(steps_since_maint))
```

### Action space

| Action | Meaning | Maintenance coefficient | Reward penalty |
|---|---|---|---|
| `0` | Do nothing | 0.0 | 0 |
| `1` | Light service | 0.5 | −5 |
| `2` | Full maintenance | 1.0 | −10 |

### Reward function

```python
def compute_reward(state_report, action, prev_min_health):
    min_health = min(
        state_report["health_blade"],
        state_report["health_nozzle"],
        state_report["health_heater"]
    )
    any_failed = any(
        s == "FAILED" for s in [
            state_report["status_blade"],
            state_report["status_nozzle"],
            state_report["status_heater"]
        ]
    )
    action_cost = {0: 0, 1: -5, 2: -10}[action]
    failure_penalty = -100 if any_failed else 0
    alive_bonus = +1
    # Shaped intermediate signal: penalise health below 0.3
    health_signal = -0.5 * max(0, 0.3 - min_health)

    return alive_bonus + action_cost + failure_penalty + health_signal
```

### Q-learning update

```python
import numpy as np

def update_q(q_table, s, a, r, s_next, alpha=0.1, gamma=0.99, done=False):
    best_next = 0 if done else np.max(q_table[s_next])
    td_target = r + gamma * best_next
    q_table[s][a] += alpha * (td_target - q_table[s][a])
```

### Q-table initialisation and persistence

```python
import pickle, numpy as np

# Init: 375 states × 3 actions
q_table = np.zeros((5, 5, 5, 3, 3))

# Save after training
with open("q_table.pkl", "wb") as f:
    pickle.dump(q_table, f)

# Load at deploy time
with open("q_table.pkl", "rb") as f:
    q_table = pickle.load(f)
```

### ε-greedy exploration schedule

```python
def get_epsilon(episode, n_episodes, eps_start=1.0, eps_end=0.05):
    return max(eps_end, eps_start - (eps_start - eps_end) * episode / n_episodes)

def pick_action(q_table, s, epsilon):
    if np.random.random() < epsilon:
        return np.random.randint(3)          # explore
    return int(np.argmax(q_table[s]))        # exploit
```

---

## Training loop

```python
N_EPISODES = 5000
MAX_STEPS  = 1200   # hard cap per episode

for episode in range(N_EPISODES):
    epsilon = get_epsilon(episode, N_EPISODES)
    steps_since_maint = 0
    # Reset Phase 1 internal state / counters as needed
    state_report = phase1_engine.reset()

    for t in range(MAX_STEPS):
        s = discretise(
            state_report["health_blade"],
            state_report["health_nozzle"],
            state_report["health_heater"],
            steps_since_maint
        )
        a = pick_action(q_table, s, epsilon)
        maintenance_level = {0: 0.0, 1: 0.5, 2: 1.0}[a]
        if a > 0:
            steps_since_maint = 0
        else:
            steps_since_maint += 1

        drivers = sample_drivers(t, MAX_STEPS)
        new_report = phase1_engine.step(*drivers, maintenance_level)

        r = compute_reward(new_report, a, state_report)
        done = any(s == "FAILED" for s in [
            new_report["status_blade"],
            new_report["status_nozzle"],
            new_report["status_heater"]
        ])

        s_next = discretise(
            new_report["health_blade"],
            new_report["health_nozzle"],
            new_report["health_heater"],
            steps_since_maint
        )
        update_q(q_table, s, a, r, s_next, done=done)
        state_report = new_report

        if done:
            break

    if episode % 500 == 0:
        print(f"Episode {episode} | ε={epsilon:.2f} | survived {t} steps")

with open("q_table.pkl", "wb") as f:
    pickle.dump(q_table, f)
```

---

## What-if scenarios

Run two or more `SimulationConfig` instances with different profiles. Tag each with a unique `scenario_id`. Query the Historian by `scenario_id` for comparison plots.

| Scenario ID | Profile | chaos_prob | Notes |
|---|---|---|---|
| `baseline_nominal` | deterministic | 0.00 | Clean lab conditions |
| `humid_factory` | stochastic | 0.01 | High humidity drift |
| `chaos_run` | chaos | 0.05 | Frequent shocks |
| `no_maintenance` | deterministic | 0.00 | RL agent disabled, action always 0 |
| `fixed_schedule` | deterministic | 0.00 | Full maintenance every 100 steps |

---

## Deliverables checklist

- [ ] `simulation_engine.py` — Clock loop, driver sampling, chaos injection
- [ ] `historian.py` — SQLite writer with `simulation_log` schema
- [ ] `rl_agent.py` — Q-table, discretise, pick_action, update_q, reward
- [ ] `train_agent.py` — offline training loop, saves `q_table.pkl`
- [ ] `run_simulation.py` — CLI entry point, accepts `--scenario`, `--rl`
- [ ] `q_table.pkl` — trained policy artefact
- [ ] `simulation.db` — Historian output (or per-scenario CSVs)
- [ ] `visualise.py` — time-series health plot, agent vs baseline comparison

---

## Demo punchline

Run `fixed_schedule` (full maintenance every 100 steps) and `rl_agent_deploy` side-by-side for 1 000 steps with `chaos_prob=0.02`. Plot mean time-to-first-failure across 50 runs. The RL agent should outlast the fixed schedule by adapting maintenance timing to actual component health rather than a calendar. Show both curves on the same chart.