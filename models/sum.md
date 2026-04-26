# 🚀 HackUPC 2026: HP Metal Jet S100 — Digital Co-Pilot

Welcome! If you are another AI agent or human teammate analyzing this directory, this is the master blueprint of the project. 

This repository implements a complete **predictive maintenance and Digital Co-Pilot system** for the **HP Metal Jet S100** 3D printer. It spans from synthetic data generation and Reinforcement Learning (RL) all the way to an LLM-powered agentic FastAPI backend.

---

## 🏗️ System Architecture & Directories

### 1. 🧠 ML & Reinforcement Learning (`/src/`, `/data/`)
This project involves predicting component health and optimizing maintenance schedules using RL.
*   **`src/generate_dataset.py`**: Synthetic historian data generator (populates `simulation.db`).
*   **`src/train_components.py` & `src/dense_training_base.py`**: Deep learning scripts for training predictive models on the 9 core components (blade, motor, rail, nozzle, resistor, cleaning, heater, sensor, insulation). *See `data.md` for their +99% validation accuracies.*
*   **`src/rl_agent.py` & `src/train_agent.py`**: Reinforcement Learning implementation. Look in `/data/` to find the trained weights:
    *   `data/dqn_checkpoint.pt`: Deep Q-Network weights.
    *   `data/q_table.pkl`: Tabular Q-learning backup/alternative.
*   **Jupyter Notebooks**: `src/stage_1_feature_analysis.ipynb` (and `stage_2_modelling.ipynb`) contain exploratory data analysis and feature engineering logic.

### 2. ⚙️ Hardware Simulation (`/components/`)
Contains Python modules acting as digital twins/simulators for the HP Metal Jet S100 subsystems:
*   **Recoating Subsystem:** `recoater_blade.py`, `recoater_drive_motor.py`, `linear_guide_rail.py`
*   **Printhead Subsystem:** `nozzle_plate.py`, `thermal_firing_resistors.py`, `cleaning_interface.py`
*   **Thermal Subsystem:** `heating_elements.py`, `temperature_sensors.py`, `insulation_panels.py`
*   **`hp_s100_engine.py`**: The core orchestrator wrapping these components.

### 3. 💬 The Digital Co-Pilot Backend (`api.py`)
This is "Stage 3 — Interact" of the challenge. A FastAPI application running an **Anthropic-powered AI Agent** capable of querying the live database via Tool Calling.
*   **DB Context:** Reads from `data/simulation.db` in **read-only mode**. 
*   **Endpoints:**
    *   `/latest`, `/history`, `/compare`: Fetches direct simulation data for scenarios.
    *   `/api/chat`: The core agent endpoint. The LLM is strictly instructed (via `_SYSTEM_PROMPT`) to *never* hallucinate health values. It must fetch them using specific tools (`_tool_latest_state`, `_tool_component_history`, `_tool_threshold_crossing`) and return a structured JSON response with explicit citations (run_id, tick `t`, field name), severity levels (CRITICAL/WARNING/INFO), and recommended actions.

### 4. 🧪 Testing & Validation (`/tests/`)
*   `tests/evaluate_accuracy.py`: Tests ML model accuracy against holdout data.
*   `tests/generate_test_dataset.py`: Utility to spin up edge-case scenarios.

---

## 🛠️ Tech Stack & Tooling

*   **Python 3.14+** (managed via `uv`, see `pyproject.toml` and `uv.lock`)
*   **AI/ML:** PyTorch 2.3+ (`torch`), Anthropic API (`anthropic`)
*   **Backend:** FastAPI 0.111+, Uvicorn
*   **Database:** SQLite3
*   **Strict Tooling:** `ruff` (formatting/linting), `pyright` (type checking)

## 🎮 How to Run

**1. Verify Environment (GPU/CUDA):**
```bash
python main.py
```

**2. Start the Co-Pilot Backend:**
```bash
uvicorn api:app --reload --port 8000
```

## ⚠️ Notes for AI Agents modifying this code
1.  **Strict Typing:** Enforce `pyright` and `ruff` rules. Avoid `Any` where possible.
2.  **API Schema:** If you touch `api.py`, be *extremely* careful modifying Pydantic models (like `MachineStateResponse` or `ChatResponse`). The Claude agent relies on the strict JSON schema to produce valid tool calls.
3.  **Read-Only DB:** The SQLite connection in `api.py` is `?mode=ro`. Write operations must be done via the `src/` simulation scripts, not the FastAPI backend.