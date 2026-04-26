# 🚀 Blue Lobster: HP Metal Jet S100 Digital Co-Pilot

Welcome to **Blue Lobster**! This repository contains the source code for a complete **predictive maintenance and Digital Co-Pilot system** designed for the **HP Metal Jet S100** 3D printer. 

This project was built for **HackUPC 2026** and spans from synthetic physics simulation and Reinforcement Learning (RL) all the way to an LLM-powered agentic FastAPI backend and an interactive 3D Next.js dashboard.

---

## 🏗️ System Architecture

Our system is structured into three tightly integrated layers:

### 1. 🧠 Physics & Machine Learning (`/models/`, `/src/`)
Instead of relying on a physical machine, we built a Digital Twin that simulates the physical degradation of 9 critical components across 3 subsystems.
* **Component Models:** Deep learning models trained on synthetic data for components like the recoater blade, thermal resistors, and heating elements.
* **Reinforcement Learning (RL):** We trained a Deep Q-Network (DQN) agent that learns optimal maintenance strategies by balancing intervention costs against failure risks, proving mathematically superior to fixed schedules.

### 2. 💬 The Digital Co-Pilot Backend (`/backend/`)
A high-performance FastAPI application acting as the bridge between the historian database and the AI Co-Pilot.
* **Zero-Hallucination AI:** Powered by **Google Gemini 3.1 Flash**, the agent is strictly constrained via prompt engineering and SQLite tool-calling. It only provides diagnostics grounded in explicit database ticks (`t`) and run IDs.
* **Token Compression (`pytoony`):** Because time-series JSON telemetry causes massive LLM context bloat, we built a custom compressor (`pytoony`) that serializes an 11-tick sliding window of telemetry into a highly efficient `TOON` format before sending it to Gemini.

### 3. 🖥️ Interactive 3D Frontend (`/frontend/`)
A Next.js (App Router) and Tailwind CSS dashboard with a "Cyberpunk / Industrial Engineer" aesthetic.
* **3D Digital Twin:** Built with React Three Fiber, allowing users to scrub through time and visually pinpoint hardware failures on the 3D model.
* **Telemetry Dashboards:** Real-time KPI tracking for Recoating, Printhead, and Thermal subsystems.
* **Floating Co-Pilot:** An integrated chat assistant that contextually understands the machine's state at the current timeline tick.

---

## 🛠️ Tech Stack

### Frontend
* **Framework:** Next.js (16.2.4) App Router
* **UI/Styling:** React, Tailwind CSS (v4), shadcn/ui, lucide-react
* **3D Rendering:** Three.js, React Three Fiber, Drei
* **Runtime:** Bun

### Backend
* **API:** FastAPI, Uvicorn
* **Database:** SQLite3 (Read-only mode for the AI agent)
* **AI Engine:** Google Gemini API (`google-genai`), Anthropic API
* **Package Management:** uv

### ML & Simulation
* **Frameworks:** PyTorch (2.3+), NumPy
* **Techniques:** Deep Q-Network (DQN), Tabular Q-learning, Weibull distribution modeling

---

## 🎮 How to Run

### 1. Backend (FastAPI)
Ensure you have `uv` installed.
```bash
cd backend
# Install dependencies
uv sync
# Run the server on port 8000
uv run uvicorn main:app --reload
```
*(Note: Do not run `precompute.py` unless you want to completely regenerate the synthetic 89MB `precomputed.json` database).*

### 2. Frontend (Next.js)
Ensure you have `bun` installed.
```bash
cd frontend
# Install dependencies
bun install
# Start the development server
bun --bun next dev
```
Open `http://localhost:3000` to view the 3D dashboard.

---

## ⚠️ Notes for AI Agents

If you are another AI agent analyzing this repo:
1.  **Frontend Caching:** The Next.js setup uses `"use client"` heavily due to fast-polling telemetry. Respect the `animTick` state when modifying views. Read `frontend/AGENTS.md` regarding Next.js 16 breaking changes.
2.  **Backend Prompts:** The LLM instruction logic lives in `backend/info.md`. The backend DB connection is strictly read-only.
3.  **Strict Typing:** The backend uses `pyright` and `ruff`. The frontend relies on strict TypeScript interfaces (`frontend/lib/api-types.ts`). Do not use `any`.