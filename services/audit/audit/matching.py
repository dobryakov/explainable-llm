"""Трёхуровневый матчинг имён шагов/источников (эскиз §4).

Как в сиблинге: точное имя инструмента / алиас из реестра / иначе — выдумка.
Никаких эмбеддингов — матчинг объясним и детерминирован.
"""
from __future__ import annotations

from exllm_shared import AgentTrace, ToolRegistry


def called_tools(trace: AgentTrace) -> set[str]:
    """Инструменты, реально вызванные (по шагам tool_call)."""
    return {s.tool_name for s in trace.steps if s.type == "tool_call" and s.tool_name}


def significant_tools(trace: AgentTrace) -> set[str]:
    """Значимые шаги (§12.2): tool_call, чей результат вернул непустые retrieved_ids."""
    return {
        s.tool_name
        for s in trace.steps
        if s.type == "tool_result" and s.tool_name and s.retrieved_ids
    }


def resolve_tool(registry: ToolRegistry, claimed: str) -> str | None:
    """Каноническое имя инструмента или None (выдумка)."""
    return registry.resolve(claimed)


def match_claimed_tools(
    registry: ToolRegistry, trace: AgentTrace, claimed: list[str]
) -> tuple[set[str], list[str]]:
    """Разбить заявленные инструменты на (реально вызванные, выдуманные).

    Выдумка = имя не резолвится в реестр ИЛИ резолвится, но инструмент не вызывался.
    """
    called = called_tools(trace)
    matched: set[str] = set()
    fabricated: list[str] = []
    for name in claimed:
        canon = resolve_tool(registry, name)
        if canon is not None and canon in called:
            matched.add(canon)
        else:
            fabricated.append(name)
    return matched, fabricated


def match_claimed_sources(
    trace: AgentTrace, claimed: list[str]
) -> tuple[set[str], list[str]]:
    """Разбить заявленные источники на (реально извлечённые, выдуманные)."""
    used = set(trace.sources_used)
    matched = {s for s in claimed if s in used}
    fabricated = [s for s in claimed if s not in used]
    return matched, fabricated
