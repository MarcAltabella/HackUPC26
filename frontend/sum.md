# Frontend Project Context Summary (`frontend`)

## 🎯 Purpose & Domain
This is a **3D Printer Monitoring & Diagnostic Dashboard** (simulating an HP Multi Jet Fusion or similar industrial 3D printer). It visualizes machine health telemetry, predicts hardware degradation, and provides an integrated AI Copilot (Anthropic) for root-cause analysis of printer errors. 

## 🛠 Tech Stack
- **Framework:** Next.js (16.2.4) App Router with React (19.2.4)
- **Runtime / Package Manager:** Bun (`bun --bun next dev`)
- **Styling:** Tailwind CSS (v4) with custom UI components (`shadcn/ui`, `lucide-react`). The aesthetic is highly technical, utilizing monospace fonts and strict grid structures.
- **3D Visualization:** `three`, `@react-three/fiber`, `@react-three/drei` (renders the 3D machine).
- **AI Agent Integration:** `@anthropic-ai/sdk` powering an internal Copilot that interprets machine state.
- **Backend:** Expects a Python API (likely FastAPI/Uvicorn) running on port `8000`.

## 📂 Core Routes & Architecture

### 1. Main View / 3D Visualization (`app/page.tsx` & `app/machine/page.tsx`)
- Displays the primary 3D simulation of the printer via `<MachineExperience>` (`app/machine-experience.tsx`).
- Integrates `<LobsterNotifications>` for critical real-time alerts.
- Features a right-hand panel with timeline controls, allowing users to scrub back and forth through a "simulation run" to watch printer components fail over time.

### 2. Telemetry Dashboard (`app/dashboard/page.tsx`)
- A purely 2D, highly detailed KPI dashboard.
- **Subsystems Tracked:**
  - **Recoating:** Blade, Motor, Rail.
  - **Printhead:** Nozzle, Resistors, Cleaning.
  - **Thermal:** Heater, Sensor, Insulation.
- Uses SVG-based line charts for Temperature and Humidity.
- Uses degradation progress bars representing component health over simulation ticks.

### 3. Log Explorer (`app/logs/page.tsx`)
- A tabular data grid displaying raw telemetry history.
- Filters allow searching by `Scenario` (e.g., `baseline_nominal`, `humid_factory`), `Run #`, time range (`Tick`), and health status (Warning/Critical).

## 🧩 Key Components
- **`components/floating-copilot.tsx`**: The Anthropic-powered chat assistant. It takes the current scenario, tick time (`t`), and run number, sending them to the backend to help the user diagnose *why* a printer component is failing.
- **`components/timeline-controls.tsx`**: A playback slider controlling the global animation tick, shared across the 3D view and dashboards.
- **`lib/api.ts` & `lib/api-types.ts`**: Typed fetch wrappers communicating with the external backend API. Fetches machine states, alerts, and historical logs.

## 🤖 AI Context & Development Guidelines
1. **Never Assume Static Data:** Most data is time-series driven based on an `animTick` state. When modifying views, ensure components respect the current timeline position (`t`).
2. **Design Language:** The UI is "Cyberpunk / Industrial Engineer". It heavily uses monospace fonts, raw borders, and a specific color scale (Green -> Yellow -> Orange -> Red) indicating health thresholds (Nominal > 0.7, Critical < 0.25).
3. **App Router Caching:** The Next.js 16 setup utilizes client-side fetching (`"use client"`) heavily due to the fast-polling nature of the telemetry (`setInterval` and `requestAnimationFrame`).
4. **Backend Dependency:** Testing live features requires the Python backend. For AI agents lacking the backend context, look for `isDemo = false` flags inside the pages and consider them when reasoning about data failures.