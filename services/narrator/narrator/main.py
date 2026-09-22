"""Сервис narrator (эскиз §4, §6): объяснитель в двух режимах.

- blind: получает задачу и финальный ответ, но НЕ трассу — рационализирует.
- grounded: получает ещё и трассу, обязан объяснять только по ней.
Одна модель, один промпт-стиль, различие только во входе. Fixture-режим по
умолчанию (офлайн, детерминизм), live — через OpenRouter.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import structlog
from fastapi import FastAPI, HTTPException

from exllm_shared import NarrateRequest, NarrateResponse

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger()

LLM_MODE = os.environ.get("LLM_MODE", "fixture")
FIXTURES_DIR = Path(os.environ.get("FIXTURES_DIR", "/fixtures"))
TASKS_PATH = os.environ.get("TASKS_PATH", "/tasks/demo_tasks.json")
MODEL = os.environ.get("NARRATOR_MODEL", "moonshotai/kimi-k2")

app = FastAPI(title="narrator", version="0.1.0")


def _task_id(task: str) -> str | None:
    try:
        raw = json.loads(Path(TASKS_PATH).read_text(encoding="utf-8"))
        return {t["task"]: t["task_id"] for t in raw.get("tasks", [])}.get(task)
    except FileNotFoundError:
        return None


def _fixture_response(req: NarrateRequest) -> NarrateResponse:
    task_id = _task_id(req.task)
    if task_id is None:
        raise HTTPException(status_code=404, detail=f"нет задачи: {req.task[:60]}")
    path = FIXTURES_DIR / req.mode / f"{task_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"фикстура не найдена: {req.mode}/{task_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("mode", req.mode)
    data.setdefault("llm_model", MODEL)
    data.setdefault("prompt_version", f"{req.mode}.v1")
    data.setdefault("source", "fixture")
    return NarrateResponse.model_validate(data)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "narrator", "mode": LLM_MODE}


@app.post("/v1/narrate", response_model=NarrateResponse)
def narrate(req: NarrateRequest) -> NarrateResponse:
    t0 = time.monotonic()
    if LLM_MODE == "live":
        from narrator.llm import call_llm_json, get_client

        raw = call_llm_json(get_client(), MODEL, req)
        resp = NarrateResponse(
            mode=req.mode,
            narrative_ru=raw.get("narrative_ru", ""),
            claimed_steps=raw.get("claimed_steps", []),
            claimed_sources=raw.get("claimed_sources", []),
            claimed_because=raw.get("claimed_because", []),
            confidence_self_report=float(raw.get("confidence_self_report", 0.0)),
            llm_model=MODEL,
            prompt_version=f"{req.mode}.v1",
            temperature=0.0,
            source="live",
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
    else:
        resp = _fixture_response(req)
        resp.latency_ms = int((time.monotonic() - t0) * 1000)
    logger.info("narrate", mode=req.mode, source=resp.source,
                claimed_steps=len(resp.claimed_steps))
    return resp
