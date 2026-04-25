# Phase 1 -> Phase 2 -> Phase 3 Integration Implementation Plan

## Summary

This implementation joins the project into one continuous pipeline:

- **Phase 1** provides the trained component classifiers from `models/artifacts/models`.
- **Phase 2** uses `models/data/simulation.db` as the simulation clock/historian and `models/data/dqn.pt` as the RL maintenance agent.
- **Phase 3** rewrites the backend into the serving layer that exposes frontend-ready machine state, alerts, timelines, and co-pilot responses.

The frontend consumes only the Phase 3 API during normal operation. It should not derive health, alerts, or maintenance recommendations locally except as an offline fallback.

## Milestone 1 - Phase 1 Model Adapter

Create a backend/model adapter that loads the nine trained component classifiers.

### Goals

- Load all classifiers from `models/artifacts/models`.
- Preserve each checkpoint's saved `feature_cols`, normalization stats, config, and state dict.
- Expose a single prediction interface for all components.

### Implementation

- Load these files:
  - `blade_classifier.pt`
  - `motor_classifier.pt`
  - `rail_classifier.pt`
  - `nozzle_classifier.pt`
  - `resistor_classifier.pt`
  - `cleaning_classifier.pt`
  - `heater_classifier.pt`
  - `sensor_classifier.pt`
  - `insulation_classifier.pt`
- For each component, return:
  - `label`
  - `status`
  - `confidence`
  - `probabilities`

### Acceptance Criteria

- All nine classifiers load successfully.
- Each classifier receives exactly the feature count expected by its checkpoint.
- Predictions return valid labels/statuses for a sample tick.

## Milestone 2 - Phase 2 Joiner

Build the joiner that combines simulation telemetry, Phase 1 predictions, and DQN maintenance actions.

### Goals

- Use `models/data/simulation.db` as the tick source.
- Reconstruct classifier input features per tick.
- Run Phase 1 classifiers at every tick.
- Run the DQN maintenance policy at every tick.
- Produce one joined machine-state object per tick.

### Implementation

For every `(scenario_id, run_id, t)` row:

- Read drivers and telemetry from `simulation.db`.
- Reconstruct Phase 1 features:
  - `temperature`
  - `humidity`
  - `load`
  - `maintenance`
  - `is_shock`
  - `steps_since_maintenance`
  - `cumulative_shocks`
  - `health_prev_*`
- Use DB health/metric fields as numeric telemetry.
- Use classifier outputs as categorical predictions.
- Load `models/data/dqn.pt` into the existing DQN architecture.
- Build the DQN state vector:
  - nine component health values
  - normalized `steps_since_maintenance`
- Return telemetry, classifier predictions, DQN action, action label, maintenance level, and reward.

### Acceptance Criteria

- Joined rows include all current `simulation_log` fields needed by the app.
- Joined rows include Phase 1 model prediction metadata.
- Joined rows include DQN recommendation fields.
- Output is deterministic for the same scenario/run/tick.

## Milestone 3 - Backend Rewrite

Rewrite the backend as the Phase 3 serving layer over joined Phase 2 state.

### Goals

- Replace the current backend with a frontend-ready API.
- Compute joined rows lazily from DB + classifiers + DQN.
- Keep response shapes stable and directly usable by the frontend.

### Endpoints

- `GET /api/health`
- `GET /api/scenarios`
- `GET /api/runs/{scenario_id}/timeline?run_number=0&start_t=0&end_t=999`
- `GET /api/runs/{scenario_id}/state/at/{t}?run_number=0`
- `GET /api/runs/{scenario_id}/state/latest?run_number=0`
- `GET /api/runs/{scenario_id}/alerts/at/{t}?run_number=0`
- `POST /api/chat`

### Timeline Row Contract

Each timeline row includes:

- `scenario_id`
- `run_number`
- `t`
- `drivers`
- `recoating`
- `printhead`
- `thermal`
- `model_predictions`
- `maintenance_recommendation`
- `alerts`

### Acceptance Criteria

- `/api/health` confirms DB, nine classifiers, and DQN availability.
- `/api/scenarios` returns all available scenario metadata.
- `/timeline` returns ordered joined rows.
- `/state/at/{t}` matches the corresponding timeline row.
- `/alerts/at/{t}` returns deterministic alerts.

## Milestone 4 - Alert Engine

Move alert generation from the frontend into the backend.

### Goals

- Backend owns alert severity and diagnostic text.
- Alerts cite exact scenario/run/tick/field values.
- Frontend renders alerts without deriving them.

### Implementation

Generate alerts from joined state:

- `CRITICAL` if status is `CRITICAL` or `FAILED`.
- `WARNING` if status is `DEGRADED`.
- No alert for `FUNCTIONAL`.

Each alert includes:

- `id`
- `severity`
- `subsystem`
- `component`
- `metric`
- `summary`
- `reasoning`
- `actions`
- `citations`
- `query`

### Acceptance Criteria

- Alerts are stable for the same tick.
- Alerts map correctly to frontend machine hotspots.
- Alerts include citations suitable for co-pilot grounding.

## Milestone 5 - Co-Pilot API

Update `/api/chat` to use the joined backend state.

### Goals

- Chat answers should be grounded in the same data shown in the UI.
- Responses must cite joined state fields.
- If no LLM API key exists, return deterministic local diagnostics instead of failing.

### Implementation

- Keep the structured response shape:
  - `severity`
  - `summary`
  - `answer`
  - `reasoning_summary`
  - `citations`
  - `recommended_actions`
- Give the chat path access to:
  - latest joined state
  - component history
  - threshold crossings
  - active alerts
  - DQN recommendation

### Acceptance Criteria

- Chat can answer questions about current machine state.
- Chat citations reference real fields and ticks.
- Backend does not crash when LLM credentials are missing.

## Milestone 6 - Frontend Integration

Replace mock-driven frontend behavior with API-driven state.

### Goals

- Frontend consumes only the Phase 3 API.
- Remove local derivation of alerts, health offsets, and maintenance behavior during normal operation.
- Keep mock data only as offline fallback.

### Implementation

- Add `frontend/lib/api-types.ts`.
- Add `frontend/lib/api.ts`.
- Update Machine page:
  - fetch `/timeline`
  - animate through joined rows
  - render API alerts
  - render API DQN action banner
- Update Dashboard:
  - chart API timeline/history data
- Update Logs:
  - render real per-component values
- Update Copilot:
  - keep using `/api/chat`
  - pass current scenario/run/tick when relevant

### Acceptance Criteria

- Machine page works from backend timeline.
- Dashboard uses real backend data.
- Logs use real component health/status values.
- Copilot answers match current UI state.
- Mock fallback appears only when backend is unreachable.

## Milestone 7 - Verification

Validate the whole Phase 1 -> Phase 2 -> Phase 3 pipeline.

### Backend Tests

- Classifier loading test.
- DQN loading test.
- Joined row construction test.
- Timeline endpoint smoke test.
- Alert generation test.
- Chat fallback test.

### Frontend Tests

- Backend running: no demo banner.
- Backend stopped: mock fallback works.
- Machine hotspots match component statuses.
- Dashboard charts render timeline values.
- Logs table shows real component health.
- Copilot returns structured responses.

### Final Acceptance Criteria

- Phase 1 classifiers are used for categorical component predictions.
- Phase 2 simulation data and DQN are used for telemetry and maintenance recommendations.
- Phase 3 backend exposes joined frontend-ready data.
- Frontend no longer relies on local mock derivation during normal operation.

## Assumptions

- `models/data/simulation.db` remains the numeric source for health and physical metrics.
- Phase 1 classifiers are classification-only and own status/label prediction.
- `models/data/dqn.pt` is the final RL policy.
- Backend can be rewritten rather than preserving the previous implementation.
- Joined rows are computed lazily for v1; a precomputed `simulation_joined.db` can be added later if latency requires it.
