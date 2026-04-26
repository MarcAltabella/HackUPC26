from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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


app = FastAPI(
    title="HP Metal Jet S100 Digital Co-Pilot API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    if not PRECOMPUTED_PATH.exists():
        raise RuntimeError(f"precomputed.json not found at {PRECOMPUTED_PATH} — run precompute.py first")
    return json.loads(PRECOMPUTED_PATH.read_text())


def _timeline() -> list[dict[str, Any]]:
    return _load()["timeline"]


def _history() -> list[dict[str, Any]]:
    return _load()["history"]


def _state_at(scenario_id: str, run_number: int, t: int) -> dict[str, Any]:
    data = _load()
    matches = [row for row in data["timeline"] if row["t"] == t]
    if not matches:
        raise HTTPException(status_code=404, detail=f"No state at t={t}")
    return matches[0]


@app.get("/api/health")
def health() -> dict[str, Any]:
    ok = PRECOMPUTED_PATH.exists()
    ticks = len(_load()["timeline"]) if ok else 0
    return {
        "status": "ok" if ok else "degraded",
        "precomputed_path": str(PRECOMPUTED_PATH),
        "precomputed_exists": ok,
        "ticks": ticks,
    }


@app.get("/api/scenarios")
def list_scenarios() -> list[dict[str, Any]]:
    tl = _load()["timeline"]
    return [
        {"scenario_id": sid, "run_count": 1, "min_t": tl[0]["t"], "max_t": tl[-1]["t"], "row_count": len(tl)}
        for sid in ("baseline_nominal", "humid_factory")
    ]


@app.get("/api/runs/{scenario_id}/timeline")
def get_timeline(
    scenario_id: str,
    run_number: int = Query(default=0, ge=0),
    start_t: int = Query(default=0, ge=0),
    end_t: int = Query(default=999, ge=0),
) -> list[dict[str, Any]]:
    if end_t < start_t:
        raise HTTPException(status_code=400, detail="end_t must be >= start_t")
    return [row for row in _load()["timeline"] if start_t <= row["t"] <= end_t]


@app.get("/api/runs/{scenario_id}/state/at/{t}")
def get_state_at(
    scenario_id: str,
    t: int,
    run_number: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return _state_at(scenario_id, run_number, t)


@app.get("/api/runs/{scenario_id}/state/latest")
def get_latest_state(
    scenario_id: str,
    run_number: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return _load()["timeline"][-1]


@app.get("/api/runs/{scenario_id}/alerts/at/{t}")
def get_alerts_at(
    scenario_id: str,
    t: int,
    run_number: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return _state_at(scenario_id, run_number, t)["alerts"]


@app.get("/api/runs/{scenario_id}/history")
def get_history(
    scenario_id: str,
    run_number: int = Query(default=0, ge=0),
    start_t: int = Query(default=0, ge=0),
    end_t: int = Query(default=999, ge=0),
) -> list[dict[str, Any]]:
    return [row for row in _load()["history"] if start_t <= row["t"] <= end_t]


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    t = req.t if req.t is not None else _load()["timeline"][-1]["t"]
    row = _state_at(req.scenario_id, req.run_number, t)
    c = row["_chat"]
    return ChatResponse(
        severity=c["severity"],
        summary=c["summary"],
        answer=c["answer"],
        reasoning_summary=c["reasoning_summary"],
        citations=[Citation(**cit) for cit in c["citations"]],
        recommended_actions=c["recommended_actions"],
    )
