"""Сервис agent-runtime (эскиз §6): выполняет агента и отдаёт трассу.

Два режима:
- fixture (по умолчанию, офлайн): реплеит записанную эталонную трассу; абляция
  (excluded_sources) обслуживается предвычисленной таблицей — детерминизм §12.4.
- live: реальный прогон tool-раннера с LLM, пишет трассу перехватом (§3).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import structlog
from fastapi import FastAPI, HTTPException

from exllm_shared import AgentTrace, RunRequest, RunResponse

from agent_runtime.tools import ToolBox

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
FIXTURES_DIR = Path(os.environ.get("FIXTURES_DIR", "/fixtures")) / "agent"
TASKS_PATH = os.environ.get("TASKS_PATH", "/tasks/demo_tasks.json")
MODEL = os.environ.get("NARRATOR_MODEL", "moonshotai/kimi-k2")
CODE_VERSION = os.environ.get("CODE_VERSION", "dev")

app = FastAPI(title="agent-runtime", version="0.1.0")


def _task_index() -> dict[str, str]:
    """Отображение текста задачи -> task_id (для поиска фикстуры)."""
    try:
        raw = json.loads(Path(TASKS_PATH).read_text(encoding="utf-8"))
        return {t["task"]: t["task_id"] for t in raw.get("tasks", [])}
    except FileNotFoundError:
        return {}


def _load_fixture(task: str) -> dict:
    task_id = _task_index().get(task)
    if task_id is None:
        raise HTTPException(status_code=404, detail=f"нет фикстуры для задачи: {task[:60]}")
    path = FIXTURES_DIR / f"{task_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"фикстура не найдена: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _apply_ablation(fixture: dict, excluded: list[str]) -> AgentTrace:
    """Собрать вариант трассы для абляционного перезапуска (§12.3, только источники)."""
    trace = AgentTrace.model_validate(fixture["trace"])
    if not excluded:
        return trace
    ablation = fixture.get("ablation", {})
    # v1: абляция по одному источнику за раз (audit так и вызывает).
    z = excluded[0]
    ex = set(excluded)
    # Вычистить исключённые источники из трассы, будто агент их не доставал.
    trace.sources_used = [s for s in trace.sources_used if s not in ex]
    for step in trace.steps:
        step.retrieved_ids = [s for s in step.retrieved_ids if s not in ex]
    # Финальный ответ берём из предвычисленной таблицы; нет записи -> ответ не изменился.
    entry = ablation.get(z)
    if entry is not None:
        trace.final_answer = entry.get("final_answer", trace.final_answer)
    return trace


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "agent-runtime", "mode": LLM_MODE}


@app.post("/v1/run", response_model=RunResponse)
def run(req: RunRequest) -> RunResponse:
    if LLM_MODE == "live":
        from agent_runtime.llm import decide_next, get_client
        from agent_runtime.runner import run_agent

        client = get_client()
        toolbox = ToolBox(os.environ.get("CORPUS_PATH", "/config/corpus.yaml"))
        trace = run_agent(
            req.task, toolbox,
            lambda task, hist: decide_next(client, MODEL, task, hist),
            model=MODEL, prompt_version="agent.v1", code_version=CODE_VERSION,
            excluded_sources=req.excluded_sources,
        )
        return RunResponse(trace=trace, source="live")

    fixture = _load_fixture(req.task)
    trace = _apply_ablation(fixture, req.excluded_sources)
    logger.info("run.fixture", task_id=trace.decision_id, excluded=req.excluded_sources)
    return RunResponse(trace=trace, source="fixture")
