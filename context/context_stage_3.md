# Stage 3 — Interact: Architecture & Implementation Plan

## Overview

Stage 3 should be implemented as the **Digital Co-Pilot layer** on top of the Phase 2 Historian. The target is not a generic chatbot. It is an **agentic, proactive, grounded industrial companion** that:

- monitors the digital twin continuously
- raises proactive alerts before the user asks
- explains alerts with evidence and traceability
- proposes action paths and lets the operator execute them
- visualizes the machine in 3D and lets the user inspect the affected part
- behaves like an autonomous collaborator that logs work, prepares reports, and surfaces insights

For scoring and demo impact, the correct target is **Pattern C: Agentic Diagnosis**, while keeping retrieval and grounding deterministic.

---

## Strategic goal

The Stage 3 implementation should maximize the four evaluation pillars from the brief:

| Pillar | What we should show |
|---|---|
| Reliability | Every response and alert is tied to run ID, timestamp, component/subsystem, and historian evidence |
| Intelligence | Root-cause explanations, trend analysis, and multi-step diagnosis over the historian |
| Autonomy | Proactive alerts, recurring reports, automated task logging, surfaced insights |
| Versatility | Chat UI, alert feed, action panel, and interactive 3D machine view |

---

## Chosen approach

### Primary pattern

Use **Pattern C: Agentic Diagnosis** from `stage-3.md`.

The system should combine:

1. **Deterministic alert detection**
2. **Tool-based retrieval over the historian**
3. **LLM reasoning over retrieved evidence only**
4. **Structured action playbooks**
5. **Companion-style UI with chat + alerts + 3D scene**

This is the best tradeoff:

- safer than fully free-form agent behavior
- more impressive than simple RAG
- easier to defend in the demo because every answer is inspectable

---

## Product vision

The final experience should feel like an industrial version of Claude:

- calm, premium companion interface
- rich message cards instead of plain text dumps
- animated transitions between alerts, investigations, and actions
- visible reasoning summary and evidence trail
- persistent side panels for machine state and recommended next steps

The copilot should feel like a **teammate**, not a dashboard.

---

## Technical architecture

### High-level system

```text
Phase 1 Engine
    ↓
Phase 2 Simulation + Historian (SQLite)
    ↓
Stage 3 Query Layer / Historian Service
    ↓
Alert Engine ──────→ Alert Store / Task Log / Reports
    ↓
Agent Tools Layer
    ↓
LLM Reasoning Layer
    ↓
Next.js UI (chat + alerts + 3D machine + actions)
```

### Recommended stack

Because the current repo is Python-first and Phase 2 is already framed around a SQLite historian, the cleanest split is:

- **Backend:** Python `FastAPI`
- **Frontend:** `Next.js` + TypeScript
- **UI system:** `shadcn/ui` + `prompt-kit`
- **3D:** `react-three-fiber` + `@react-three/drei`
- **Animation:** `framer-motion`
- **Persistence:** existing SQLite historian + extra Stage 3 tables
- **LLM:** provider-agnostic tool-calling interface

### Why split frontend and backend

- Python remains the natural home for historian access, simulation integration, alert logic, and report generation.
- Next.js is the right place for a high-quality companion UI.
- This avoids forcing Stage 1/2 Python code into a frontend/serverless-only architecture.

---

## UI strategy

### UI libraries

Use:

- **shadcn/ui** for layout, panels, sheets, dialogs, tabs, tables, badges, tooltips, command menu, scroll areas
- **prompt-kit** for the AI interaction surfaces: messages, prompt input, system messages, markdown output

### MCP usage plan

For implementation, use both MCP sources as part of the UI workflow:

- **shadcn MCP** to browse/search/install core components and blocks
- **prompt-kit MCP/registry** to pull AI-specific chat primitives into the web app

This is the right setup because prompt-kit gives the chat shell, while shadcn gives the broader product UI and control surfaces.

### Global layout rule

The prompt bar should be a **persistent bottom bar** that is visible on every main page at all times. It should behave like the main companion input, not as a page-local widget.

Persistent layout elements:

- bottom: always-visible `PromptInput` bar
- top: global run/scenario selector and machine status summary
- page body: content changes by page

### Main pages

#### 1. Dashboard

Purpose:

- real-time state of all machines
- fleet or scenario overview
- time-series charts and KPIs
- current critical alerts and subsystem health

Main content:

- KPI cards for uptime, active alerts, failing components, RL maintenance actions
- charts for subsystem health over time
- recent historian events
- compact machine cards or run cards

#### 2. Logs and reports

Purpose:

- inspect historian entries, tags, alerts, actions, and reports
- provide traceability for everything the agent says or does

Main content:

- historian/log table
- filters by run, timestamp, severity, subsystem, component, tag
- generated reports
- task log and action execution history
- evidence browser for citations

#### 3. 3D machine page

Purpose:

- inspect the machine visually
- focus on broken or degraded parts
- monitor what the agent is doing proactively

Main content:

- center: realistic 3D machine render
- right rail: active alerts, recommended actions, current agent activity, evidence snippets
- contextual overlays on the 3D scene for selected parts

### 3D page layout

This page should be the most operator-focused page in the app.

- center canvas: machine render and component overlays
- right sidebar: alerts, action paths, currently executing tasks, status badges
- bottom persistent prompt bar: ask the copilot about the selected part or current alert

### Right-side alert/action rail

On the 3D page, the right panel should always contain:

- active alerts
- recommended actions
- action execution state
- evidence summary
- task log snippets

If the agent has already started acting proactively, the UI should show that clearly, for example:

- `Investigating recoater rail degradation`
- `Maintenance simulation running`
- `Post-action report being generated`

### Interaction style

The interface should be companion-first, not dashboard-first:

- rich messages with severity cards
- subtle page transitions and state changes
- animated alert appearance
- animated camera transitions in 3D scene
- expandable evidence sections
- quick actions under each alert
- persistent bottom prompt bar across all pages

---

## 3D machine modeling strategy

### What we know about the machine

From the hackathon brief and Phase 1:

- machine: **HP Metal Jet S100**
- process: binder jetting
- critical subsystems:
  - Recoating System
  - Printhead Array
  - Thermal Control

These are the elements that matter for the digital twin and for Stage 3 interaction.

### Modeling approach

The machine should have a **realistic appearance**, even if the geometry is not industrial-CAD accurate.

The right target is:

- realistic overall silhouette and proportions
- recognizable machine body, access panels, build zone, recoater path, printhead zone, and thermal area
- material treatment that feels like a real industrial machine
- subsystem and component overlays for interaction

Do not spend the project trying to match every physical detail. Aim for a **realistic visual impression with subsystem accuracy**.

The 3D model should include:

- machine chassis/body
- recoater carriage area
- printhead/jetting area
- thermal/cure area
- build unit / powder bed area
- access panels or housings that make the machine feel real

Then map the nine modeled components onto hotspots:

- Recoating: blade, motor, rail
- Printhead: nozzle plate, firing resistors, cleaning interface
- Thermal: heating elements, temperature sensors, insulation panels

### Recommended implementation path

#### V1

Start with a realistic low-poly or mid-poly `.glb` machine model and layer the interaction in `react-three-fiber`:

- realistic machine mesh
- component hotspot meshes
- orbit controls
- click-to-focus selection
- animated outlines or pulses for critical components
- camera presets for subsystems

#### V2

Refine the model with:

- better materials
- opened/exploded inspection states
- highlighted internal zones
- animated agent activity states such as "inspecting" or "maintenance in progress"

### 3D interactions

The user should be able to:

- rotate the machine
- zoom in/out
- click a subsystem or component
- isolate the selected component
- switch to an exploded or x-ray view
- see the current alert path overlaid on the 3D model
- see when the agent is already handling an issue

### Data binding in 3D

Each component node should be bound to historian/agent state:

- color by status: functional / degraded / critical / failed
- pulse if it is the source of an active alert
- show metric tooltip on hover
- focus camera when selected from chat or alert card
- show execution overlays such as `investigating`, `simulating repair`, or `resolved`

---

## Grounding and traceability protocol

This is the most important Stage 3 rule.

The LLM must never answer directly from prior knowledge about printers. It only reasons over retrieved historian evidence.

### Response contract

Every alert and chat answer should return structured data like:

```json
{
  "severity": "WARNING",
  "summary": "Recoating subsystem health dropped sharply in the last 18 steps.",
  "answer": "The recoater rail is the most likely source of the degradation spike.",
  "reasoning_summary": [
    "Subsystem minimum health is dominated by the rail.",
    "The decline starts after a contamination increase.",
    "No comparable drop is seen in the thermal subsystem."
  ],
  "citations": [
    {"run_id": "chaos_run", "t": 184, "field": "health_rail"},
    {"run_id": "chaos_run", "t": 181, "field": "humidity"},
    {"run_id": "chaos_run", "t": 184, "field": "status_blade"}
  ],
  "recommended_actions": [
    "Inspect rail alignment",
    "Apply light maintenance",
    "Re-run scenario from last safe checkpoint"
  ]
}
```

### Important design rule

Expose:

- evidence citations
- tool trace
- concise reasoning summary

Do **not** expose hidden chain-of-thought. The operator needs traceability, not internal reasoning tokens.

---

## Stage 3 data model

In addition to the Phase 2 historian, add Stage 3 tables.

### Suggested tables

#### `alerts`

- `id`
- `run_id`
- `component_id`
- `subsystem_id`
- `severity`
- `status`
- `title`
- `summary`
- `reasoning_summary_json`
- `citations_json`
- `recommended_actions_json`
- `created_at`
- `resolved_at`

#### `task_log`

- `id`
- `run_id`
- `source` (`agent` | `user` | `system`)
- `task_type`
- `title`
- `details_json`
- `status`
- `created_at`
- `completed_at`

#### `reports`

- `id`
- `run_id`
- `report_type`
- `time_window`
- `summary_markdown`
- `citations_json`
- `created_at`

#### `insights`

- `id`
- `run_id`
- `category`
- `title`
- `summary`
- `evidence_json`
- `priority`
- `created_at`

---

## Agent system design

### Principle

Use a **hybrid system**:

- rules detect events
- tools retrieve evidence
- LLM explains, compares, prioritizes, and proposes actions

This is safer than asking the LLM to detect anomalies on its own.

### Required agent tools

The diagnosis agent should have a small, explicit toolset:

1. `get_latest_state(run_id)`
2. `get_component_history(run_id, component_id, start_t, end_t)`
3. `get_subsystem_history(run_id, subsystem_id, start_t, end_t)`
4. `get_recent_alerts(run_id)`
5. `compare_runs(run_ids, field, start_t, end_t)`
6. `find_threshold_crossings(run_id, field, threshold)`
7. `root_cause_trace(run_id, component_id, lookback_steps)`
8. `list_action_playbooks(component_id, severity)`
9. `execute_simulated_action(run_id, action_id, params)`
10. `generate_report(run_id, window, report_type)`

### Agent roles

#### 1. Alert explanation agent

- takes a triggered alert
- gathers evidence
- produces grounded summary and action suggestions

#### 2. Diagnostic chat agent

- answers operator questions
- investigates via tools
- cites historian records

#### 3. Collaborator agent

- prepares reports
- surfaces recurring patterns
- creates task log entries automatically

---

## Proactive alerting plan

### Alerting strategy

Use a background watcher that consumes new historian rows and runs deterministic checks.

### Trigger examples

- component status becomes `CRITICAL` or `FAILED`
- subsystem minimum health drops below a threshold
- health slope falls faster than expected over a window
- thermal stress remains above threshold for `N` consecutive steps
- contamination spike is followed by printhead degradation
- RL action recommendation diverges from actual operator behavior

### Alert pipeline

1. new historian tick arrives
2. rules create candidate alert
3. candidate alert is enriched with evidence
4. diagnosis agent writes explanation and action path
5. alert is stored and pushed to UI
6. UI highlights affected machine zone in 3D

### Alert lifecycle

- `candidate`
- `active`
- `acknowledged`
- `actioned`
- `resolved`
- `dismissed`

---

## Reasoning on alerts

Each alert should support:

- what happened
- why the system thinks it happened
- what evidence supports that diagnosis
- what to do next
- what happens if ignored

### Example alert experience

`CRITICAL: Printhead Array degradation accelerating`

Expandable sections:

- **Summary:** thermal stress and contamination jointly increased clogging risk
- **Evidence:** citations to `t=184`, `t=185`, `t=186`
- **Reasoning:** short causal sequence
- **Action path:** inspect cleaning interface, run light maintenance, compare to baseline run
- **3D focus:** highlight printhead area automatically

---

## Action paths and execution

This is a major differentiator for valuation.

The copilot should not stop at diagnosis. It should offer executable playbooks.

### Playbook structure

Each action path should contain:

- title
- severity
- target component/subsystem
- expected effect
- estimated downtime impact
- ordered steps
- machine UI focus targets
- execution mode

### Example playbooks

#### Recoating subsystem degradation

- inspect blade wear
- inspect rail alignment
- apply light or full maintenance
- rerun the twin for 100 steps after intervention
- compare new projection vs no-action projection

#### Printhead clogging risk

- inspect cleaning interface
- reduce load / switch scenario
- apply maintenance
- generate before/after comparison

#### Thermal instability

- inspect sensor drift
- inspect insulation degradation
- trigger thermal maintenance simulation
- estimate remaining safe operating window

### Execution meaning in the hackathon context

Execution should mean **digital twin actions**, not real machine control:

- write to task log
- acknowledge alert
- trigger maintenance input in simulation
- rerun or fork scenario
- create report
- update UI state
- show the operator that the agent is currently handling the issue

This is defendable and realistic for the hackathon scope.

### Execution UX

Because the agent is proactive, the 3D page does not need to feel like a manual repair console.

Instead, the UI should emphasize:

- what the issue is
- what the agent recommends
- what the agent is already doing
- whether the operator wants to approve, pause, or inspect that process

Good examples of visible execution states:

- `Analyzing root cause`
- `Simulating light maintenance`
- `Comparing against baseline run`
- `Preparing intervention report`

---

## Autonomous collaborator plan

This feature should make the system feel proactive even when the operator is idle.

### Capabilities

#### 1. Task log

Automatically log:

- alerts created
- playbooks recommended
- actions executed
- reports generated
- comparisons performed

#### 2. Automated reports

Generate:

- shift summary
- end-of-run summary
- maintenance recommendation report
- anomaly digest
- run comparison report

#### 3. Proactively surfaced insights

Examples:

- "Recoating failures happen 25% earlier in `humid_factory` than in `baseline_nominal`."
- "Rail degradation is repeatedly the earliest bottleneck across chaos scenarios."
- "The current run matches the failure signature from the previous printhead incident."

#### 4. Session memory

Remember:

- favorite scenario or run
- frequent queries
- preferred report types
- unresolved tasks

For the hackathon, this memory can stay simple and local.

---

## Implementation milestones

- [x] **Milestone 1 — Grounded query foundation**
- [x] `1.1` FastAPI service over SQLite historian
- [x] `1.2` Query endpoints for latest state, history, scenario comparison
- [x] `1.3` Structured response schema with citations
- [x] `1.4` Basic companion UI shell with persistent bottom prompt bar
- [x] `1.5` Logging rule: every completed task, endpoint, and schema decision must be written to a running implementation log so lost context can be recovered quickly
Success criteria: user can ask about a component/run and get a grounded answer with citations. ✅ DONE

- [x] **Milestone 2 — Page structure and core UI**
- [x] `2.1` Dashboard page: KPI cards + Input Drivers section (SVG line charts for Temperature and Humidity over simulation ticks) + Component Degradation timeline (horizontal color-coded bars per component, one segment per tick, green→yellow→orange→red as health degrades) + demo-mode fallback banner; mock-data module provides 100-tick deterministic history (sine-wave degradation curves) used when backend is unreachable
- [x] `2.2` Logs page with historian table, scenario/run/tick-range/status filters, pagination
- [x] `2.3` 3D machine page with center canvas and right-side alert/action rail — MachineExperience canvas + sidebar merged into page.tsx
- [x] `2.4` Global navigation and shared persistent bottom prompt bar
- [x] `2.5` Milestone progress tracked in context_stage_3.md; new pages logged in commit messages
Success criteria: the app has the three intended pages and the prompt bar is always available. ✅ DONE

- [x] **Milestone 3 — Agentic diagnosis**
- [x] `3.1` Tool-based diagnosis layer — get_latest_state, get_component_history, find_threshold_crossing tools + agentic loop in POST /api/chat
- [-] `3.2` Root-cause investigation flow — LLM can chain tools to investigate, but no dedicated root_cause_trace tool yet
- [x] `3.3` Evidence and reasoning summary rendering — copilot-bar displays severity badge, citations, reasoning bullets, action chips; conversation history (all exchanges shown as chat thread); listens for copilot-query CustomEvent from alert cards
- [x] `3.4` Alert explanation cards — expandable diagnosis cards in Machine page right rail: severity badge, metric value, 3-step reasoning trail, action chips, "Ask co-pilot ↗" button that fires copilot-query event; works offline with MOCK_STATE; shows WARNING+DEGRADED+CRITICAL+FAILED
- [x] `3.5` Logs page shows MOCK_HISTORY (100 ticks) when backend is unreachable instead of error; demo banner consistent with dashboard
Success criteria: the system can answer "why did this fail?" with a traceable explanation. ✅ DONE

- [ ] **Milestone 4 — Proactive alerts**
- [ ] `4.1` Background alert watcher
- [ ] `4.2` Alert lifecycle state machine
- [ ] `4.3` Real-time alert feed in UI
- [ ] `4.4` Right-side rail on the 3D page showing alerts, recommendations, and current agent activity
- [ ] `4.5` Logging rule: every threshold, alert type, and lifecycle transition must be documented in the log
Success criteria: the user sees alerts before asking anything and can inspect them from the 3D page.

- [ ] **Milestone 5 — Action paths and visible execution**
- [ ] `5.1` Playbook catalog
- [ ] `5.2` Execute-simulated-action flow
- [ ] `5.3` Action log and status updates
- [ ] `5.4` 3D/UI states for `investigating`, `simulating repair`, `reporting`, and `resolved`
- [ ] `5.5` Report generation after action execution
- [ ] `5.6` Logging rule: every action path and execution outcome must be logged for replay and context recovery
Success criteria: the operator can see what the agent is doing and track an issue from alert to action to report.

- [-] **Milestone 6 — Realistic 3D machine experience**
- [x] `6.1` Realistic HP Metal Jet S100-inspired model — procedural three.js model with correct proportions, materials, ControlTower, BuildBed, FrontCabinets, leveling feet
- [ ] `6.2` Component hotspots for the nine modeled parts — no clickable hotspots yet
- [x] `6.3` Orbit/focus/explode interactions — OrbitControls with pan-lock, polar angle clamp, min/max distance
- [ ] `6.4` Severity coloring, alert overlays, and component info panels — no data binding to health state yet
- [ ] `6.5` Camera presets for recoating, printhead, and thermal views
- [ ] `6.6` Logging rule: every 3D asset source, interaction behavior, and component mapping must be logged
Success criteria: the user can rotate the machine, inspect failing parts, and understand machine state visually. 🔄 PARTIAL

- [ ] **Milestone 7 — Autonomous collaborator polish**
- [ ] `7.1` Report scheduler
- [ ] `7.2` Surfaced insights rail
- [ ] `7.3` Task memory
- [ ] `7.4` Companion UI animations and response polish
- [ ] `7.5` Logging rule: reports, surfaced insights, and automated collaborator tasks must be persisted in both product logs and implementation logs
Success criteria: the system feels proactive and collaborative during the demo.

---

## Prioritization order

If time is limited, implement in this order:

1. grounded historian API
2. chat with citations
3. proactive alerts
4. reasoning summary + root-cause flow
5. action playbooks
6. stylized 3D model
7. autonomous reports and memory polish

The critical rule is: **do not start with the 3D model**. Start with grounding and alerts first.

---

## Recommended UI component set

### From `prompt-kit`

- `Message`
- `PromptInput`
- `SystemMessage`
- markdown renderer for responses

### From `shadcn/ui`

- `Card`
- `Button`
- `Badge`
- `Dialog`
- `Sheet`
- `Tabs`
- `Table`
- `Tooltip`
- `ScrollArea`
- `Command`
- `Separator`
- `Skeleton`

These are enough to build the full Stage 3 shell cleanly.
