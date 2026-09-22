"""Сервис gateway (эскиз §6, §8): оркестрация цепочки + отдача UI.

Наружу торчит только этот сервис (порт 12100). Отдаёт список демо-задач, гоняет
всю цепочку для выбранной задачи и статический UI трёх зон.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from gateway.orchestrate import analyze

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger()

TASKS_PATH = os.environ.get("TASKS_PATH", "/tasks/demo_tasks.json")
UI_DIR = Path(os.environ.get("UI_DIR", "/app/ui"))

app = FastAPI(title="gateway", version="0.1.0")


class AnalyzeRequest(BaseModel):
    task: str


def _tasks() -> list[dict]:
    raw = json.loads(Path(TASKS_PATH).read_text(encoding="utf-8"))
    return [{"task_id": t["task_id"], "task": t["task"]} for t in raw.get("tasks", [])]


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "gateway"}


@app.get("/v1/tasks")
def tasks() -> dict:
    return {"tasks": _tasks()}


@app.post("/v1/analyze")
def analyze_endpoint(req: AnalyzeRequest) -> dict:
    try:
        with httpx.Client() as client:
            result = analyze(req.task, client)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"upstream: {exc}") from exc
    logger.info("analyze", task=req.task[:50], gap=result["gap"])
    return result


@app.get("/")
def index() -> FileResponse:
    path = UI_DIR / "index.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="ui not found")
    return FileResponse(path)
