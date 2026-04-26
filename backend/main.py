from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from pydantic import BaseModel
from pytoony import json2toon

GEMINI_API_KEY = "AIzaSyCuVb7jbseAlOG9FOKvp8AKAa3sIqDiid0"
GEMINI_MODEL = "gemini-3-flash-preview"

PRECOMPUTED_PATH = Path(__file__).parent / "precomputed.json"


class Citation(BaseModel):
    run_id: str
    run_number: int = 0
    t: int
    field: str
    value: float | str | int | bool | None = None


class ChatRequest(BaseModel):
    message: str
    scenario_id: str = "humid_factory"
    run_number: int = 0
    t: int | None = None


class ChatResponse(BaseModel):
    severity: str
    summary: str
    answer: str
    reasoning_summary: list[str]
    citations: list[Citation]
    recommended_actions: list[str]
    reply: str | None = None


app = FastAPI(title="HP Metal Jet S100 Digital Co-Pilot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    """Load precomputed.json once and build O(1) index: {scenario_id: {t: row}}."""
    if not PRECOMPUTED_PATH.exists():
        raise RuntimeError(f"precomputed.json not found — run precompute.py first")

    raw = json.loads(PRECOMPUTED_PATH.read_text())

    # Support both multi-scenario and legacy single-scenario formats
    if "scenarios" in raw:
        scenarios_raw = raw["scenarios"]
    else:
        sid = raw.get("scenario_id", "unknown")
        scenarios_raw = {sid: raw}

    # Build index and collect metadata
    index: dict[str, dict[int, dict]] = {}
    meta: dict[str, dict] = {}

    for sid, sdata in scenarios_raw.items():
        tl = sdata["timeline"]
        index[sid] = {row["t"]: row for row in tl}
        t_values = list(index[sid].keys())
        meta[sid] = {
            "scenario_id": sid,
            "env_profile": sdata.get("env_profile", "unknown"),
            "maintenance_schedule": sdata.get("maintenance_schedule", "unknown"),
            "run_number": sdata.get("run_number", 0),
            "min_t": min(t_values),
            "max_t": max(t_values),
            "tick_count": len(t_values),
        }

    return {"index": index, "meta": meta}


def _index() -> dict[str, dict[int, dict]]:
    return _load()["index"]


def _meta() -> dict[str, dict]:
    return _load()["meta"]


def _require_scenario(scenario_id: str) -> dict[int, dict]:
    idx = _index()
    if scenario_id not in idx:
        raise HTTPException(
            status_code=404, detail=f"Scenario '{scenario_id}' not found"
        )
    return idx[scenario_id]


def _state_at(scenario_id: str, t: int) -> dict[str, Any]:
    sc = _require_scenario(scenario_id)
    row = sc.get(t)
    if row is None:
        m = _meta()[scenario_id]
        raise HTTPException(
            status_code=404,
            detail=f"t={t} not found in '{scenario_id}' (range {m['min_t']}–{m['max_t']})",
        )
    return row


def _nearest_state_at(scenario_id: str, t: int) -> dict[str, Any]:
    sc = _require_scenario(scenario_id)
    if t in sc:
        return sc[t]
    nearest_t = min(sc.keys(), key=lambda existing_t: abs(existing_t - t))
    return sc[nearest_t]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/api/health")
def health() -> dict[str, Any]:
    ok = PRECOMPUTED_PATH.exists()
    if ok:
        m = _meta()
        total_ticks = sum(v["tick_count"] for v in m.values())
        scenario_count = len(m)
    else:
        total_ticks = scenario_count = 0
    return {
        "status": "ok" if ok else "degraded",
        "precomputed_path": str(PRECOMPUTED_PATH),
        "precomputed_exists": ok,
        "scenario_count": scenario_count,
        "total_ticks": total_ticks,
    }


@app.get("/api/scenarios")
def list_scenarios() -> list[dict[str, Any]]:
    return list(_meta().values())


@app.get("/api/runs/{scenario_id}/state/at/{t}")
def get_state_at(
    scenario_id: str,
    t: int,
    run_number: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return _state_at(scenario_id, t)


@app.get("/api/runs/{scenario_id}/state/latest")
def get_latest_state(
    scenario_id: str,
    run_number: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    sc = _require_scenario(scenario_id)
    return sc[max(sc)]


@app.get("/api/runs/{scenario_id}/alerts/at/{t}")
def get_alerts_at(
    scenario_id: str,
    t: int,
    run_number: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return _state_at(scenario_id, t)["alerts"]


@app.get("/api/runs/{scenario_id}/timeline")
def get_timeline(
    scenario_id: str,
    run_number: int = Query(default=0, ge=0),
    start_t: int = Query(default=0, ge=0),
    end_t: int = Query(default=999, ge=0),
) -> list[dict[str, Any]]:
    if end_t < start_t:
        raise HTTPException(status_code=400, detail="end_t must be >= start_t")
    sc = _require_scenario(scenario_id)
    return [sc[t] for t in range(start_t, end_t + 1) if t in sc]


@app.get("/api/runs/{scenario_id}/history")
def get_history(
    scenario_id: str,
    run_number: int = Query(default=0, ge=0),
    start_t: int = Query(default=0, ge=0),
    end_t: int = Query(default=999, ge=0),
) -> list[dict[str, Any]]:
    if end_t < start_t:
        raise HTTPException(status_code=400, detail="end_t must be >= start_t")
    sc = _require_scenario(scenario_id)
    rows = [sc[t] for t in range(start_t, end_t + 1) if t in sc]
    return [
        {
            "t": r["t"],
            "temperature": r["drivers"]["temperature"],
            "humidity": r["drivers"]["humidity"],
            "health_recoating": r["recoating"]["subsystem_health"],
            "health_printhead": r["printhead"]["subsystem_health"],
            "health_thermal": r["thermal"]["subsystem_health"],
            "status_blade": r["recoating"]["blade"]["status"],
            "status_nozzle": r["printhead"]["nozzle"]["status"],
            "status_heater": r["thermal"]["heater"]["status"],
            **{
                f"health_{c}": r["recoating"][c]["health"]
                for c in ["blade", "motor", "rail"]
            },
            **{
                f"health_{c}": r["printhead"][c]["health"]
                for c in ["nozzle", "resistor", "cleaning"]
            },
            **{
                f"health_{c}": r["thermal"][c]["health"]
                for c in ["heater", "sensor", "insulation"]
            },
        }
        for r in rows
    ]


class LLMRequest(BaseModel):
    message: str
    scenario_id: str = "humid_factory"
    run_number: int = 0
    t: int | None = None


def _slice_toon(scenario_id: str, t: int, window: int = 5) -> str:
    sc = _require_scenario(scenario_id)
    t_values = sorted(sc.keys())
    center = min(t_values, key=lambda x: abs(x - t))
    idx = t_values.index(center)
    sliced = [sc[t_values[i]] for i in range(max(0, idx - window), min(len(t_values), idx + window + 1))]
    return json2toon(json.dumps(sliced))


def _severity_from_row(row: dict[str, Any]) -> str:
    severities = [alert.get("severity") for alert in row.get("alerts", [])]
    if "CRITICAL" in severities:
        return "CRITICAL"
    if "WARNING" in severities:
        return "WARNING"
    return "INFO"


def _summary_from_row(row: dict[str, Any]) -> str:
    alerts = row.get("alerts", [])
    if alerts:
        return alerts[0].get("summary", "Machine telemetry requires attention.")
    return f"All monitored components are functional at t={row['t']}."


def _plain_text_answer(answer: str) -> str:
    text = answer.strip()
    text = re.sub(r"\$([^$]+)\$", r"\1", text)
    text = text.replace("**", "")
    text = text.replace("__", "")
    text = re.sub(r"(?m)^\s*\*\s+", "- ", text)
    return text


def _citations_from_row(row: dict[str, Any]) -> list[Citation]:
    citations: list[Citation] = []
    for alert in row.get("alerts", [])[:3]:
        for citation in alert.get("citations", [])[:2]:
            citations.append(Citation(**citation))
    if citations:
        return citations[:4]

    return [
        Citation(
            run_id=row["scenario_id"],
            run_number=row.get("run_number", 0),
            t=row["t"],
            field="health_recoating",
            value=row["recoating"]["subsystem_health"],
        ),
        Citation(
            run_id=row["scenario_id"],
            run_number=row.get("run_number", 0),
            t=row["t"],
            field="health_printhead",
            value=row["printhead"]["subsystem_health"],
        ),
        Citation(
            run_id=row["scenario_id"],
            run_number=row.get("run_number", 0),
            t=row["t"],
            field="health_thermal",
            value=row["thermal"]["subsystem_health"],
        ),
    ]


def _reasoning_from_row(row: dict[str, Any]) -> list[str]:
    alerts = row.get("alerts", [])
    if alerts:
        return [
            reason
            for alert in alerts[:2]
            for reason in alert.get("reasoning", [])[:2]
        ][:4]

    action = row["maintenance_recommendation"]["action_label"]
    return [
        "No diagnostic alerts are active at this tick.",
        f"Maintenance policy currently recommends {action}.",
    ]


def _actions_from_row(row: dict[str, Any]) -> list[str]:
    actions = [
        action
        for alert in row.get("alerts", [])[:2]
        for action in alert.get("actions", [])[:2]
    ]
    if actions:
        return actions[:4]

    action = row["maintenance_recommendation"]["action_label"]
    if action == "do_nothing":
        return ["Continue monitoring", "Keep current maintenance plan"]
    return [action.replace("_", " ").capitalize()]


@app.post("/api/llm", response_model=ChatResponse)
def llm_chat(req: LLMRequest) -> ChatResponse:
    sc = _require_scenario(req.scenario_id)
    t = req.t if req.t is not None else max(sc)
    row = _nearest_state_at(req.scenario_id, t)
    context_t = row["t"]
    context = _slice_toon(req.scenario_id, context_t)
    prompt = (
        "You are an HP Metal Jet S100 maintenance co-pilot. "
        "Answer the user's question using only the telemetry context. "
        "Be concise, operational, and mention relevant tick numbers or metrics when useful. "
        "Do not invent components, thresholds, or maintenance actions.\n\n"
        "Use plain text only. Do not use Markdown emphasis, Markdown tables, or LaTeX math delimiters.\n\n"
        f"Machine telemetry context (TOON format, 11 ticks around t={context_t}):\n\n"
        f"{context}\n\n"
        f"User question: {req.message}"
    )
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    answer = _plain_text_answer(response.text or "No LLM response was returned.")
    return ChatResponse(
        severity=_severity_from_row(row),
        summary=_summary_from_row(row),
        answer=answer,
        reasoning_summary=_reasoning_from_row(row),
        citations=_citations_from_row(row),
        recommended_actions=_actions_from_row(row),
        reply=answer,
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    sc = _require_scenario(req.scenario_id)
    t = req.t if req.t is not None else max(sc)
    row = _state_at(req.scenario_id, t)
    c = row["_chat"]
    return ChatResponse(
        severity=c["severity"],
        summary=c["summary"],
        answer=c["answer"],
        reasoning_summary=c["reasoning_summary"],
        citations=[Citation(**cit) for cit in c["citations"]],
        recommended_actions=c["recommended_actions"],
    )
