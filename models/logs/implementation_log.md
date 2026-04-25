# Implementation Log — Dataset Generator

Generated: 2026-04-25T12:45:17.329364

## Milestone 1.1 — SimulationConfig

- `total_steps`: 1 000 (= 1 000 simulated hours per run, 1 h/tick)
- `time_step_hours`: 1.0
- Scenarios: ['baseline_nominal', 'humid_factory', 'chaos_run', 'no_maintenance', 'fixed_schedule']
- Runs per scenario: 20
- Max rows (no early stop): 100,000
- RNG seeding: `_SCENARIO_SEED[scenario_id] + run_id × 997` — stable across Python runs

---

## Milestone 1.2 — Clock loop

Per tick t = 0 … total_steps − 1:
1. `sample_drivers(t, cfg, rng)` → Drivers namedtuple
2. `step_phase1(state, drivers)` → (new_state, metrics_dict)
3. `historian.write(row)` → SQLite + CSV

Early-stop condition: all nine component statuses == FAILED.
SQLite commits batched every 2 000 rows (see Historian._COMMIT_EVERY).

---

## Milestone 1.3 — Deterministic driver profile

```
temperature = 20 + (t / total_steps) × 30    [20 °C → 50 °C linear ramp]
humidity    = 0.40                            [constant]
load        = t × time_step_hours             [cumulative hours]
```
Maintenance schedules:
| Schedule    | maintenance_level |
|-------------|-------------------|
| "none"      | 0.0 always        |
| "light"     | 0.5 every 200 steps |
| "fixed_100" | 1.0 every 100 steps |
| "full"      | 1.0 always        |

---

## Milestone 1.4 — Stochastic and chaos driver profiles

**Stochastic** (humid_factory, chaos_prob=0.01):
```
temperature += N(0, 2),    clipped [15, 70]
humidity    += N(0, 0.05), clipped [0, 1]
shock (p=0.01): humidity += 0.25
```
**Chaos** (chaos_run, chaos_prob=0.05):
```
temperature += N(0, 3),    clipped [15, 70]
humidity    += N(0, 0.07), clipped [0, 1]
shock (p=0.05):
  50% → humidity   += U(0.20, 0.50)   [contamination burst]
  50% → temperature += U(10, 25)      [thermal spike]
```

---

## Milestone 1.5 — All component model parameters

### Recoater Blade  (Exponential Decay — Recoating)
| Param | Value |
|---|---|
| Initial thickness | 2.0 mm |
| Failure threshold | 0.3 mm |
| Base wear rate | 0.002 per tick |
| Humidity coeff | 0.8 |
| Maint. recovery | 0.25 mm / unit |
| Expected failure (no maint, baseline) | ~700 ticks |

### Recoater Drive Motor  (Weibull β=3.0)
| Param | Value |
|---|---|
| Base age rate | 0.00095 per tick |
| Load coeff | 0.3 |
| Weibull η / β | 0.75 / 3.0 |
| Maint. recovery | 0.06 age-units / unit |
| Expected failure | ~800 ticks |

### Linear Guide / Rail  (Linear)
| Param | Value |
|---|---|
| Base rate | 0.0009 per tick |
| Motor-vibration cascade coeff | 0.25 |
| Maint. recovery | 0.05 deg / unit |
| Expected failure | ~900 ticks |

### Nozzle Plate  (Weibull β=2.5, η=0.6)
| Param | Value |
|---|---|
| Base age rate | 0.0007 per tick |
| Temp coeff | 1.2 |
| Contamination coeff | 0.9 |
| Blade-health cascade | 0.3 |
| Cleaning cascade | 0.4 |
| Maint. recovery | 0.15 age-units / unit |
| Expected failure | ~650 ticks |

### Thermal Firing Resistors  (Arrhenius-style)
| Param | Value |
|---|---|
| Base rate | 0.0008 per tick |
| Temp pivot | 30.0 °C |
| Temp coeff | 1.5 |
| Maint. recovery | 0.05 deg / unit |
| Expected failure | ~750 ticks |

### Cleaning Interface  (Linear, demand-driven)
| Param | Value |
|---|---|
| Base rate | 0.0012 per tick |
| Nozzle-demand cascade | 0.5 |
| Maint. recovery | 0.15 deg / unit |
| Expected failure | ~600 ticks |

### Heating Elements  (Linear + Thermal Fatigue)
| Param | Value |
|---|---|
| Base rate | 0.0008 per tick |
| Nominal temp | 35.0 °C |
| Thermal coeff | 1.5 |
| Insulation cascade | 0.35 |
| Sensor cascade | 0.2 |
| Resistance range | 10.0 – 25.0 Ω |
| Expected failure | ~850 ticks |

### Temperature Sensors  (Linear drift)
| Param | Value |
|---|---|
| Base rate | 0.0007 per tick |
| Temp-cycling coeff | 0.8 |
| Max error | 15.0 °C |
| Expected failure | ~950 ticks |

### Insulation Panels  (Linear, slow)
| Param | Value |
|---|---|
| Base rate | 0.00065 per tick |
| Temp coeff | 0.6 |
| Thermal resistance range | 0 – 2.5 °C·m/W |
| Expected failure | ~1 000 ticks |

### Status thresholds (all components)
| health | Status | label |
|---|---|---|
| > 0.70 | FUNCTIONAL | 0 |
| > 0.40 | DEGRADED | 1 |
| > 0.20 | CRITICAL | 2 |
| ≤ 0.20 | FAILED | 3 |

### Cascading effects
| Source | Target | Coefficient |
|---|---|---|
| blade health ↓ | nozzle rate ↑ | 0.3 |
| motor health ↓ | rail rate ↑ | 0.25 |
| cleaning health ↓ | nozzle rate ↑ | 0.4 |
| insulation health ↓ | heater rate ↑ | 0.35 |
| sensor health ↓ | heater rate ↑ | 0.2 |

---

## Milestone 3 â€” Persistence backend

- Project-root output directory: `/home/swallow/Desktop/Projects/HackUPC2026/data`
- SQLite remains the primary persistence target: `/home/swallow/Desktop/Projects/HackUPC2026/data/simulation.db`
- CSV is used only as a fallback if SQLite is unavailable: `/home/swallow/Desktop/Projects/HackUPC2026/data/training_dataset.csv`
- Runtime backend selected at startup: `sqlite`

---

## Generation Summary

- Total rows: 100,000
- Persistence backend used: `sqlite`
- SQLite primary path: `/home/swallow/Desktop/Projects/HackUPC2026/data/simulation.db`
- CSV fallback path: `/home/swallow/Desktop/Projects/HackUPC2026/data/training_dataset.csv`
- NN input features: temperature, humidity, load, maintenance, is_shock, steps_since_maintenance, cumulative_shocks
- NN targets (per component): label_* (0=FUNCTIONAL 1=DEGRADED 2=CRITICAL 3=FAILED)
- Subsystem aggregate columns: health_recoating, health_printhead, health_thermal

---

## Milestone 6 - RL training run

- Timestamp: 2026-04-25T13:46:07.012000
- Episodes: 12
- Scenarios: baseline_nominal, humid_factory, chaos_run
- Resume mode: False
- Alpha: 0.1
- Gamma: 0.99
- Epsilon schedule: start=1.0, end=0.05
- Q-table path: data\q_table.pkl
- Mean episode reward: -1883.333
- Mean survival steps: 1000.00
- Failure rate: 0.000
- Final epsilon: 0.129

---

## Milestone 6 - RL evaluation run

- Timestamp: 2026-04-25T13:46:21.803228
- Scenarios: baseline_nominal, humid_factory, chaos_run
- Runs per scenario: 3
- Baseline schedule: fixed_100
- Q-table path: C:\Users\Marc\Desktop\Projects\Projects\HackUPC26\data\q_table.pkl
- Summary path: C:\Users\Marc\Desktop\Projects\Projects\HackUPC26\data\rl_eval_summary.json
- Runs path: C:\Users\Marc\Desktop\Projects\Projects\HackUPC26\data\rl_eval_runs.csv
- Overall RL mean TTF: 1000.0
- Overall baseline mean TTF: 1000.0
- Overall RL survival rate: 1.0
- Overall baseline survival rate: 1.0

---

## Milestone 6 - RL training run

- Timestamp: 2026-04-25T13:46:56.309612
- Episodes: 2
- Scenarios: baseline_nominal, humid_factory, chaos_run
- Resume mode: False
- Alpha: 0.1
- Gamma: 0.99
- Epsilon schedule: start=1.0, end=0.05
- Q-table path: C:\Users\Marc\Desktop\Projects\Projects\HackUPC26\data\q_table_smoke.pkl
- Mean episode reward: -2835.000
- Mean survival steps: 1000.00
- Failure rate: 0.000
- Final epsilon: 0.525

---

## Milestone 6 - RL evaluation run

- Timestamp: 2026-04-25T13:46:56.647552
- Scenarios: baseline_nominal, humid_factory, chaos_run
- Runs per scenario: 1
- Baseline schedule: fixed_100
- Q-table path: C:\Users\Marc\Desktop\Projects\Projects\HackUPC26\data\q_table.pkl
- Summary path: C:\Users\Marc\Desktop\Projects\Projects\HackUPC26\data\rl_eval_summary_smoke.json
- Runs path: C:\Users\Marc\Desktop\Projects\Projects\HackUPC26\data\rl_eval_runs_smoke.csv
- Overall RL mean TTF: 1000.0
- Overall baseline mean TTF: 1000.0
- Overall RL survival rate: 1.0
- Overall baseline survival rate: 1.0

---

## Milestone 6 - RL training run

- Timestamp: 2026-04-25T14:11:27.668856
- Episodes: 1
- Scenarios: baseline_nominal, humid_factory, chaos_run
- Resume mode: False
- Alpha: 0.1
- Gamma: 0.99
- Epsilon schedule: start=1.0, end=0.05
- Q-table path: /home/swallow/Desktop/Projects/HackUPC2026/models/data/q_table.pkl
- Mean episode reward: -4110.000
- Mean survival steps: 1000.00
- Failure rate: 0.000
- Final epsilon: 1.000

---

## Milestone 6 - RL training run

- Timestamp: 2026-04-25T14:15:15.165566
- Episodes: 5000
- Scenarios: baseline_nominal, humid_factory, chaos_run
- Resume mode: False
- Alpha: 0.1
- Gamma: 0.99
- Epsilon schedule: start=1.0, end=0.05
- Q-table path: /home/swallow/Desktop/Projects/HackUPC2026/models/data/q_table.pkl
- Mean episode reward: -1627.770
- Mean survival steps: 1000.00
- Failure rate: 0.000
- Final epsilon: 0.050

---

## Milestone 6 - RL training run

- Timestamp: 2026-04-25T14:15:27.478041
- Episodes: 10
- Scenarios: baseline_nominal, humid_factory, chaos_run
- Resume mode: False
- Alpha: 0.1
- Gamma: 0.99
- Epsilon schedule: start=1.0, end=0.05
- Q-table path: /home/swallow/Desktop/Projects/HackUPC2026/models/data/q_table.pkl
- Mean episode reward: -1955.000
- Mean survival steps: 1000.00
- Failure rate: 0.000
- Final epsilon: 0.145

---

## Milestone 6 - RL training run

- Timestamp: 2026-04-25T14:23:12.907625
- Episodes: 5000
- Scenarios: baseline_nominal, humid_factory, chaos_run
- Resume mode: False
- Alpha: 0.1
- Gamma: 0.99
- Epsilon schedule: start=1.0, end=0.05
- Q-table path: /home/swallow/Desktop/Projects/HackUPC2026/models/data/q_table.pkl
- Mean episode reward: -1627.770
- Mean survival steps: 1000.00
- Failure rate: 0.000
- Final epsilon: 0.050

---


---

## Stage 3 - Milestone 1/2 bootstrap (2026-04-25T15:52:13+02:00)

### Completed tasks

- Implemented grounded historian query layer in Next.js server runtime (`frontend/lib/historian.ts`) backed by SQLite CLI queries against `models/data/simulation.db`.
- Added structured response contracts for Stage 3 grounded outputs and alert cards (`frontend/lib/contracts.ts`).
- Added deterministic diagnosis and proactive alert derivation logic (`frontend/lib/diagnosis.ts`).
- Added shared HTTP query parsing and API response helpers (`frontend/lib/http.ts`).
- Added Next.js API routes for core Milestone 1 tools:
  - `GET /api/runs`
  - `GET /api/state/latest`
  - `GET /api/history/component`
  - `GET /api/history/subsystem`
  - `GET /api/compare`
  - `GET /api/alerts`
  - `GET /api/chat`
- Replaced default app scaffold with Stage 3 companion shell:
  - top global navigation with run/scenario selector
  - persistent bottom co-pilot prompt bar (global)
  - dashboard page with KPI cards + active alerts
  - logs page with historian evidence tables
  - machine page with machine view + right alert/action rail

### Endpoint and schema decisions

- Chosen implementation: Bun + Next.js full-stack routes instead of separate FastAPI service for this stage bootstrap.
- Query layer returns JSON objects rooted in historian rows and adds explicit `citations` arrays in Stage 3 endpoints.
- `/api/chat` returns grounded response contract fields:
  - `severity`
  - `summary`
  - `answer`
  - `reasoning_summary`
  - `citations`
  - `recommended_actions`
- `/api/chat` additionally returns `tool_trace` for inspectable retrieval provenance.
- Alerts are currently deterministic from latest tick component statuses (`CRITICAL`/`FAILED`) and include recommended actions from per-component playbooks.

### UI decisions

- Persistent prompt bar mounted in root layout to satisfy global availability on all main pages.
- Main navigation includes three required Stage 3 pages:
  - Dashboard
  - Logs & Reports
  - 3D Machine
- Right rail on machine page persistently shows active alerts + recommended action snippets.
- The machine center view is currently a stylized interactive subsystem map placeholder, ready to swap with a real `.glb` + `react-three-fiber` implementation in Milestone 6.

### Open follow-up

- Stage 3 DB tables (`alerts`, `task_log`, `reports`, `insights`) are not yet created; current implementation computes alerts in memory from historian state.
- No background watcher process yet; alert feed is polling-based from deterministic recomputation.
## Milestone 6 - RL training run

- Timestamp: 2026-04-25T15:57:51.234170
- Episodes: 10000
- Scenarios: baseline_nominal, humid_factory, chaos_run
- Resume mode: False
- Alpha: 0.1
- Gamma: 0.99
- Epsilon schedule: start=1.0, end=0.05
- Q-table path: /home/swallow/Desktop/Projects/HackUPC2026/models/data/q_table.pkl
- Mean episode reward: -1626.036
- Mean survival steps: 1000.00
- Failure rate: 0.000
- Final epsilon: 0.050

---

## Milestone 6 - RL evaluation run

- Timestamp: 2026-04-25T16:22:42.033467
- Scenarios: baseline_nominal, humid_factory, chaos_run
- Runs per scenario: 50
- Baseline schedule: fixed_100
- Q-table path: /home/swallow/Desktop/Projects/HackUPC2026/models/data/q_table.pkl
- Summary path: /home/swallow/Desktop/Projects/HackUPC2026/models/data/rl_eval_summary.json
- Runs path: /home/swallow/Desktop/Projects/HackUPC2026/models/data/rl_eval_runs.csv
- Overall RL mean TTF: 1000.0
- Overall baseline mean TTF: 1000.0
- Overall RL survival rate: 1.0
- Overall baseline survival rate: 1.0

---

## Milestone 6 - RL training run

- Timestamp: 2026-04-25T16:43:41.856352
- Episodes: 10000
- Scenarios: baseline_nominal, humid_factory, chaos_run
- Resume mode: False
- Alpha: 0.1
- Gamma: 0.99
- Epsilon schedule: start=1.0, end=0.05
- Q-table path: /home/swallow/Desktop/Projects/HackUPC2026/models/data/q_table.pkl
- Mean episode reward: -1626.078
- Mean survival steps: 1000.00
- Failure rate: 0.000
- Final epsilon: 0.050

---

## Milestone 6 - RL training run

- Timestamp: 2026-04-25T17:00:27.816299
- Episodes: 10000
- Scenarios: baseline_nominal, humid_factory, chaos_run
- Resume mode: False
- Alpha: 0.1
- Gamma: 0.99
- Epsilon schedule: start=1.0, end=0.05
- Q-table path: /home/swallow/Desktop/Projects/HackUPC2026/models/data/q_table.pkl
- Mean episode reward: -598.590
- Mean survival steps: 1000.00
- Failure rate: 0.000
- Final epsilon: 0.050

---

## Milestone 6 - RL evaluation run

- Timestamp: 2026-04-25T17:02:11.694078
- Scenarios: baseline_nominal, humid_factory, chaos_run
- Runs per scenario: 50
- Baseline schedule: fixed_100
- Q-table path: /home/swallow/Desktop/Projects/HackUPC2026/models/data/q_table.pkl
- Summary path: /home/swallow/Desktop/Projects/HackUPC2026/models/data/rl_eval_summary.json
- Runs path: /home/swallow/Desktop/Projects/HackUPC2026/models/data/rl_eval_runs.csv
- Overall RL mean TTF: 1000.0
- Overall baseline mean TTF: 1000.0
- Overall RL survival rate: 1.0
- Overall baseline survival rate: 1.0

---

## Milestone 6 - RL evaluation run

- Timestamp: 2026-04-25T17:11:47.285256
- Scenarios: baseline_nominal, humid_factory, chaos_run
- Runs per scenario: 50
- Baseline schedule: light
- Q-table path: /home/swallow/Desktop/Projects/HackUPC2026/models/data/q_table.pkl
- Summary path: /home/swallow/Desktop/Projects/HackUPC2026/models/data/rl_eval_summary.json
- Runs path: /home/swallow/Desktop/Projects/HackUPC2026/models/data/rl_eval_runs.csv
- Overall RL mean TTF: 1000.0
- Overall baseline mean TTF: 526.813
- Overall RL survival rate: 1.0
- Overall baseline survival rate: 0.0

---

## DQN training run

- Timestamp: 2026-04-25T20:25:23.049173
- Episodes: 5000
- Scenarios: baseline_nominal, humid_factory, chaos_run
- lr=0.001, gamma=0.99, batch=64
- Mean reward: -595.770
- Failure rate: 0.000

---

