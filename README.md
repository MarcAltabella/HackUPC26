# HP Metal Jet S100 — Digital Co-Pilot

> **HackUPC 2026** · HP Challenge — *When AI meets reality*

A full-stack Digital Twin of the HP Metal Jet S100 industrial 3D printer. The system models component degradation physics, simulates the machine's lifecycle, and exposes an agentic AI co-pilot that monitors, diagnoses, and explains printer health in real time — all grounded in the simulation data with zero hallucinations.

---

## What it does

| Layer | What it builds |
|---|---|
| **Phase 1 — Model (The Brain)** | Physics-based degradation engine for 9 components across 3 subsystems. Weibull / exponential decay / abrasive wear / thermal fatigue models. Outputs health index, operational status, and physical metrics per component per tick. |
| **Phase 2 — Simulate (The Clock)** | Time-advancing Digital Twin loop. Runs multiple scenarios (baseline, humid factory, chaos, no-maintenance, RL-scheduled). Writes every tick to a SQLite historian. Trains a DQN reinforcement-learning maintenance agent that outperforms fixed schedules. |
| **Phase 3 — Interact (The Co-Pilot)** | Agentic AI interface. Pattern C diagnosis: deterministic alert detection → tool-based historian retrieval → LLM reasoning over evidence only. 3D interactive machine view, proactive alerts, evidence citations, action playbooks. |

---

## Architecture

```
Phase 1 Engine (9 component classifiers)
    ↓
Phase 2 Simulation Clock  →  SQLite Historian (simulation.db)
                          →  DQN Maintenance Agent (dqn_checkpoint.pt)
    ↓
Phase 3 FastAPI Backend   →  Joined state: telemetry + classifier predictions + DQN actions
    ↓
Next.js Frontend
    ├── Dashboard (KPIs, health charts, scenario selector)
    ├── Logs (historian table, filters, evidence browser)
    └── 3D Machine (interactive HP S100 model, alert rail, co-pilot bar)
```

The frontend never derives health or alerts locally during normal operation — everything comes from the Phase 3 API. Mock data is kept only as an offline fallback.

---

## Components modeled

### Recoating System

- **Recoater Blade** — abrasive wear (Weibull), driven by contamination + load
- **Recoater Drive Motor** — mechanical fatigue, driven by production volume
- **Linear Guide / Rail** — deviation drift, driven by load + contamination

### Printhead Array

- **Nozzle Plate** — clogging + thermal fatigue, driven by temperature stress + contamination
- **Thermal Firing Resistors** — resistance drift, driven by thermal cycles
- **Cleaning Interface** — efficiency decay, affects nozzle plate health (cascading failure)

### Thermal Control

- **Heating Elements** — electrical degradation (exponential), driven by age + insulation state
- **Temperature Sensors** — measurement error drift
- **Insulation Panels** — thermal resistance decay; feeds back into heating element load

Cascading failure is modeled: a degraded recoater blade raises contamination, which accelerates nozzle plate clogging.

---

## Tech stack

| Layer | Stack |
|---|---|
| Physics models | Python · PyTorch · NumPy |
| Simulation / RL | Python · DQN (PyTorch) · Q-table · SQLite |
| Backend API | FastAPI · Uvicorn · Google GenAI / Anthropic SDK |
| Frontend | Next.js 16 · TypeScript · React 19 · Tailwind CSS v4 |
| 3D | `react-three-fiber` · `@react-three/drei` · Three.js |
| UI system | `shadcn/ui` · `prompt-kit` · `framer-motion` |
| Package managers | `uv` (Python) · `bun` (JS) |

---

## Repository structure

```
.
├── models/                     # Phase 1 + Phase 2
│   ├── components/             # 9 physics-based component models
│   │   ├── hp_s100_engine.py   # top-level Logic Engine
│   │   ├── recoater_blade.py
│   │   ├── recoater_drive_motor.py
│   │   ├── linear_guide_rail.py
│   │   ├── nozzle_plate.py
│   │   ├── thermal_firing_resistors.py
│   │   ├── cleaning_interface.py
│   │   ├── heating_elements.py
│   │   ├── temperature_sensors.py
│   │   └── insulation_panels.py
│   ├── src/
│   │   ├── generate_dataset.py     # synthetic telemetry generation
│   │   ├── train_components.py     # train 9 component classifiers
│   │   ├── rl_agent.py             # DQN architecture
│   │   ├── train_agent.py          # DQN training loop
│   │   ├── evaluate_agent.py       # RL vs fixed-schedule comparison
│   │   ├── predict_component.py    # inference helper
│   │   ├── stage_1_feature_analysis.ipynb
│   │   └── stage_2_modelling.ipynb
│   ├── artifacts/models/           # 9 trained classifier checkpoints (.pt)
│   ├── data/
│   │   ├── simulation.db           # SQLite historian (all scenario runs)
│   │   ├── dqn_checkpoint.pt       # trained DQN policy
│   │   ├── q_table.pkl             # Q-table (tabular RL baseline)
│   │   ├── rl_eval_runs.csv        # per-run RL evaluation results
│   │   └── rl_eval_summary.json    # RL vs fixed-schedule summary stats
│   ├── logs/
│   │   ├── implementation_log.md
│   │   ├── train.log
│   │   └── dqn_train.log
│   ├── main.py                     # Phase 2 simulation entry point
│   └── api.py                      # Phase 1 prediction API
│
├── backend/                    # Phase 3 serving layer
│   ├── main.py                 # FastAPI app (joined state + co-pilot endpoints)
│   ├── precompute.py           # pre-join simulation rows for low-latency serving
│   └── precomputed.json        # cached joined timeline
│
├── frontend/                   # Phase 3 UI
│   ├── app/
│   │   ├── page.tsx            # 3D Machine page (main experience)
│   │   ├── machine-experience.tsx  # Three.js HP S100 model + alert dots
│   │   ├── dashboard/          # KPI cards, health charts, scenario selector
│   │   └── logs/               # historian table with filters
│   ├── components/
│   │   ├── copilot-bar.tsx     # persistent bottom AI prompt bar
│   │   ├── nav-links.tsx
│   │   └── timeline-controls.tsx
│   └── lib/
│       ├── api.ts              # typed API client
│       ├── api-types.ts        # shared TypeScript types
│       └── mock-data.ts        # offline fallback (100-tick deterministic history)
│
└── context/                    # hackathon brief and design docs
```

---

## Setup

### Prerequisites

- Python ≥ 3.14
- [`uv`](https://docs.astral.sh/uv/) package manager
- [`bun`](https://bun.sh/) runtime

### 1. Models (Phase 1 + Phase 2)

```bash
cd models
uv sync
```

To regenerate the simulation database and retrain classifiers from scratch:

```bash
# Generate synthetic telemetry and run all scenarios
uv run python src/generate_dataset.py

# Train the 9 component classifiers
uv run python src/train_components.py

# Train the DQN maintenance agent
uv run python src/train_agent.py

# Evaluate RL agent vs fixed-schedule baseline
uv run python src/evaluate_agent.py
```

The trained artifacts land in `models/artifacts/models/` and `models/data/`.

### 2. Backend (Phase 3 API)

```bash
cd backend
uv sync

# Optional: pre-compute joined timeline for faster serving
uv run python precompute.py

# Start the API server
uv run uvicorn main:app --reload --port 8000
```

The backend exposes:

| Endpoint | Description |
|---|---|
| `GET /api/health` | DB + classifier + DQN availability |
| `GET /api/scenarios` | Available scenario metadata |
| `GET /api/runs/{scenario_id}/timeline` | Full joined time series |
| `GET /api/runs/{scenario_id}/state/at/{t}` | State at a specific tick |
| `GET /api/runs/{scenario_id}/state/latest` | Latest state |
| `GET /api/runs/{scenario_id}/alerts/at/{t}` | Deterministic alerts at tick |
| `POST /api/chat` | Co-pilot chat (grounded, with citations) |

### 3. Frontend

```bash
cd frontend
bun install
bun dev
```

Open [http://localhost:3000](http://localhost:3000). The app connects to the backend at `localhost:8000` and falls back to mock data if the backend is unreachable.

---

## Scenarios

| Scenario ID | Profile | Chaos prob | Description |
|---|---|---|---|
| `baseline_nominal` | deterministic | 0.00 | Clean lab conditions |
| `humid_factory` | stochastic | 0.01 | High humidity drift |
| `chaos_run` | chaos | 0.05 | Frequent shock events |
| `no_maintenance` | deterministic | 0.00 | RL agent disabled, no interventions |
| `fixed_schedule` | deterministic | 0.00 | Full maintenance every 100 steps |

---

## AI Co-Pilot — how grounding works

The co-pilot implements **Pattern C: Agentic Diagnosis**. It never answers from model training knowledge. Every response is produced by:

1. Deterministic threshold rules detect a candidate alert.
2. The agent calls historian tools (`get_component_history`, `find_threshold_crossings`, `get_latest_state`, etc.) to retrieve evidence.
3. The LLM reasons over the retrieved data only and returns a structured response.

Every response includes a `severity`, `answer`, `reasoning_summary` bullets, and `citations` pointing to exact `(run_id, t, field)` tuples in the historian.

```json
{
  "severity": "CRITICAL",
  "summary": "Printhead Array health dropped below 0.30 at t=186.",
  "answer": "The nozzle plate clog probability spiked after a contamination burst at t=183.",
  "reasoning_summary": [
    "Contamination rose sharply at t=183 (humidity=0.89, is_shock=1).",
    "Nozzle clog probability jumped from 0.21 to 0.67 over three ticks.",
    "No comparable drop seen in thermal or recoating subsystems."
  ],
  "citations": [
    {"run_id": "chaos_run", "t": 183, "field": "humidity"},
    {"run_id": "chaos_run", "t": 186, "field": "metric_nozzle_clog"},
    {"run_id": "chaos_run", "t": 186, "field": "health_printhead"}
  ],
  "recommended_actions": [
    "Run printhead purge cycle",
    "Apply light maintenance",
    "Compare against baseline_nominal run"
  ]
}
```

---

## Simulation data contract

**Inputs per tick** (environmental / operational drivers):

| Driver | Unit | Description |
|---|---|---|
| `temperature` | °C | Ambient build temperature |
| `humidity` | 0–1 | Air moisture / powder contamination purity |
| `load` | print hours | Cumulative operational hours |
| `maintenance` | 0–1 | Maintenance level coefficient |

**Outputs per component**:

| Field | Type | Description |
|---|---|---|
| `health_*` | 0.0–1.0 | Remaining life (normalized) |
| `status_*` | enum | `FUNCTIONAL` / `DEGRADED` / `CRITICAL` / `FAILED` |
| `metric_*` | physical unit | E.g. blade thickness (mm), clog probability, resistance (Ω) |

---

## RL Maintenance Agent

A DQN agent observes per-subsystem minimum health (compact 9-component → 3-subsystem aggregation) and picks from three actions: do nothing, light service (−5 reward), or full maintenance (−10 reward). A component failure costs −100. The agent is trained for 5 000 episodes and compared against a fixed-schedule baseline.

The demo punchline: run `fixed_schedule` and `rl_agent_deploy` side-by-side for 1 000 steps with `chaos_prob=0.02` and plot mean time-to-first-failure across 50 runs. The DQN adapts maintenance timing to actual component health instead of the calendar.
