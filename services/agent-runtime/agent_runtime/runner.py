"""Тонкий tool-раннер с перехватом на уровне рантайма (эскиз §3, §12.1).

КЛЮЧЕВОЙ ИНВАРИАНТ: трассу пишет ЭТОТ цикл (обёртка над диспетчером инструментов),
а не сам агент «по памяти». Каждый вызов инструмента порождает неизменяемые шаги
tool_call/tool_result. Это прямой аналог того, что SHAP берётся из модели, а не из
слов LLM. Здесь же — точка, где абляция (excluded_sources) влияет на выдачу.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from exllm_shared import AgentTrace, TraceStep

from agent_runtime.tools import ToolBox

MAX_STEPS = 8


def _ulid_like() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_agent(
    task: str,
    toolbox: ToolBox,
    decide: Callable[[str, list[dict]], dict],
    *,
    model: str,
    prompt_version: str,
    code_version: str,
    excluded_sources: list[str] | None = None,
) -> AgentTrace:
    """Выполнить агента, перехватывая каждый шаг в трассу.

    `decide(task, history) -> {action, ...}` — стратегия выбора следующего шага
    (в live-режиме это вызов LLM). Раннер к ней агностичен, что и делает трассу
    эталоном: истина в том, что реально вызвано, а не в том, что агент расскажет.
    """
    excluded = set(excluded_sources or [])
    steps: list[TraceStep] = []
    sources_used: list[str] = []
    history: list[dict] = []

    steps.append(TraceStep(step_id=_ulid_like(), type="plan", ts=_now()))

    final_answer = ""
    for _ in range(MAX_STEPS):
        decision = decide(task, history)
        action = decision.get("action")

        if action == "final":
            final_answer = decision.get("answer", "")
            steps.append(TraceStep(step_id=_ulid_like(), type="final", ts=_now()))
            break

        if action != "tool_call":
            break

        tool_name = decision.get("tool_name", "")
        tool_input = decision.get("tool_input", {}) or {}
        t0 = time.monotonic()
        steps.append(
            TraceStep(
                step_id=_ulid_like(), type="tool_call", ts=_now(),
                tool_name=tool_name, tool_input=tool_input,
            )
        )
        result = toolbox.dispatch(tool_name, tool_input, excluded)
        latency = int((time.monotonic() - t0) * 1000)
        steps.append(
            TraceStep(
                step_id=_ulid_like(), type="tool_result", ts=_now(),
                tool_name=tool_name,
                tool_output_digest=result.output_digest,
                retrieved_ids=result.retrieved_ids,
                latency_ms=latency,
            )
        )
        for sid in result.retrieved_ids:
            if sid not in sources_used:
                sources_used.append(sid)
        history.append(
            {"tool_name": tool_name, "tool_input": tool_input,
             "retrieved_ids": result.retrieved_ids, "digest": result.output_digest}
        )

    return AgentTrace(
        decision_id=_ulid_like(),
        created_at=_now(),
        task=task,
        steps=steps,
        sources_used=sources_used,
        tools_available=["search_kb", "get_ticket", "sql_query", "web_fetch"],
        final_answer=final_answer,
        model=model,
        prompt_version=prompt_version,
        temperature=0.0,
        code_version=code_version,
    )
