# Backend Architecture & Context (HackUPC 2026)

**Purpose:** This file (`sum.md`) serves as the core context document for AI agents (like yourself) operating within this backend directory. It provides technical mapping, dependencies, and business logic for the **HP Metal Jet S100 Digital Co-Pilot**.

---

## 1. Project Overview
We are building an intelligent diagnostics co-pilot for HP's Metal Jet S100 3D printers. The system monitors machine telemetry, detects stateful physics degradation, and uses a Large Language Model (Google Gemini 3.1 Flash) to diagnose issues, provide reasoning, and recommend actions. 

**Core Stack:**
*   **API Framework:** FastAPI
*   **Package Manager:** `uv` (Fast & strict Python packaging)
*   **LLM Integration:** `google-genai` (Gemini model)
*   **Data Compression:** `pytoony` (Compresses JSON telemetry into a highly token-efficient format called TOON for LLM context windows).
*   **Simulation / ML:** PyTorch (`torch`), `numpy` (used in precomputing physics degradation datasets).

---

## 2. Key Files & their Roles

### `main.py`
The FastAPI application entry point. It acts as the bridge between the frontend application, the precomputed machine simulation data, and the Gemini LLM.
*   **Data Loading:** Uses LRU caching to load `precomputed.json` into memory. 
*   **Context Windowing (`_slice_toon`):** Extracts an 11-tick window of telemetry data (5 ticks before, current tick, 5 ticks after) and serializes it to TOON format before passing to Gemini.
*   **Key Endpoints:**
    *   `GET /api/runs/{scenario_id}/*`: Exposes machine state, timelines, alerts, and history.
    *   `POST /api/chat`: Returns **pre-cached** chat responses generated during the simulation phase (useful for instantaneous UI updates).
    *   `POST /api/llm`: The **live** endpoint. It reads the local state at `t`, formats the 11-tick telemetry window as a TOON string, applies the system instruction (`info.md`), and prompts Gemini live.

### `precompute.py`
The simulation and ML engine. Instead of a live physical machine, we simulate 7 different failure/degradation scenarios.
*   **Physics Simulation:** Uses custom PyTorch neural networks (`ComponentClassifier`) and stateful loops (`step_phase1`) to generate realistic telemetry drift and machine failures.
*   **Output:** Generates `precomputed.json` (the entire dataset used by `main.py`) and `output.toon` (serialized representations).
*   *Note for AI Agents:* Do not touch `precompute.py` unless you are explicitly asked to modify the underlying physics, scenarios, or dataset generation pipeline.

### The Dataset
*   **`precomputed.json`**: (89MB) The generated database of telemetry per scenario and tick (`t`). Do not attempt to read this fully into context.
*   **`output.toon`**: (47MB) Serialized TOON file for raw inspection. 
*   **`info.md`**: The strict System Prompt injected into Gemini. It forces the LLM to remain in character as a highly specialized industrial diagnostic AI.

---

## 3. Data Flow & LLM Interaction (`/api/llm`)

When a user asks a question about the machine:
1.  **Request:** Frontend sends `message`, `scenario_id`, and time `t`.
2.  **Context Assembly:** Backend retrieves 11 contiguous ticks of telemetry around `t`.
3.  **Compression:** The JSON telemetry is converted to TOON format using `pytoony`. This is critical for token-efficiency.
4.  **Prompting:** The TOON text + `info.md` + user `message` is sent to Gemini via `google-genai`.
5.  **Parsing:** The LLM's response is parsed and supplemented with severity, summaries, citations, and recommended actions extracted from the nearest simulated state.

---

## 4. Instructions for Future AI Agents

*   **Dependencies:** If you add a library, use `uv add <package>`. Do not use `pip install`.
*   **Running the Server:** Use `uv run uvicorn main:app --reload` or `uv run fastapi dev main.py`.
*   **Adding Endpoints:** Follow the existing `BaseModel` patterns in `main.py`. Ensure endpoints handle `scenario_id` and time `t` appropriately, defaulting to the latest `t` if none is provided.
*   **Testing AI Prompts:** If adjusting the LLM's behavior, modify `info.md` first. It acts as the system instruction.
*   **Do NOT Recompute Blindly:** Running `precompute.py` takes time and will overwrite `precomputed.json`. Only run it if the simulation logic changes.
