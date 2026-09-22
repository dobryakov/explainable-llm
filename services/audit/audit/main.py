"""Сервис audit (эскиз §4, §6): независимый оценщик верности.

Отделён от того, кто объясняет (narrator) и кто выполняет (agent-runtime).
Считает метрику верности над трассой детерминированно (без LLM-судьи). В Фазе 4
добавляется causal_validity через абляционные перезапуски agent-runtime (§5).
"""
from __future__ import annotations

import os

import httpx
import structlog
from fastapi import FastAPI
from pydantic import BaseModel

from exllm_shared import (
    AgentTrace,
    FaithfulnessResult,
    NarrateResponse,
    load_registry,
)

from audit import causal, faithfulness, store

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger()

TOOLS_PATH = os.environ.get("TOOLS_PATH", "/config/tools.yaml")
FAITHFUL_THRESHOLD = float(os.environ.get("FAITHFUL_THRESHOLD", "70"))
AGENT_RUNTIME_URL = os.environ.get("AGENT_RUNTIME_URL", "http://agent-runtime:12101")

app = FastAPI(title="audit", version="0.1.0")
_registry = None


def registry():
    global _registry
    if _registry is None:
        _registry = load_registry(TOOLS_PATH)
    return _registry


class FaithfulnessRequest(BaseModel):
    trace: AgentTrace
    narration: NarrateResponse
    # Считать causal_validity абляцией (дёргает agent-runtime). Выкл. -> провизорный балл.
    compute_causal: bool = True


def _ablation_run_fn(task: str, excluded: list[str]) -> str:
    """Перезапуск агента с убранным источником через agent-runtime (§5)."""
    resp = httpx.post(
        f"{AGENT_RUNTIME_URL}/v1/run",
        json={"task": task, "excluded_sources": excluded},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["trace"]["final_answer"]


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "audit"}


@app.post("/v1/faithfulness", response_model=FaithfulnessResult)
def faithfulness_endpoint(req: FaithfulnessRequest) -> FaithfulnessResult:
    causal_validity: float | None = None
    uncausal_claims: list[str] = []
    if req.compute_causal:
        try:
            causal_validity, uncausal_claims = causal.compute_causal(
                req.trace, req.narration, _ablation_run_fn
            )
        except Exception as exc:  # абляция недоступна -> провизорный балл, не падаем
            logger.warning("causal.failed", error=str(exc))
    result = faithfulness.compute(
        registry(), req.trace, req.narration,
        causal_validity=causal_validity,
        uncausal_claims=uncausal_claims,
        faithful_threshold=FAITHFUL_THRESHOLD,
    )
    try:
        store.save(req.trace.decision_id, req.narration.mode, result.score,
                   result.model_dump_json())
    except Exception as exc:  # хранилище не должно ронять оценку
        logger.warning("store.failed", error=str(exc))
    logger.info("faithfulness", mode=req.narration.mode, score=result.score,
                verdict=result.verdict, fabrication=result.fabrication_rate)
    return result
