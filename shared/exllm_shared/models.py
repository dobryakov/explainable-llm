"""Pydantic-схемы всех API-контрактов (эскиз §3, §4).

Эти модели — контракт между сервисами. Менять поля здесь = менять контракт
для всех четырёх сервисов. Центральная сущность — `AgentTrace`: неизменяемый
след выполнения агента, «эталон правды», с которым audit сверяет объяснения.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# --- Типы шагов и режимов -----------------------------------------------------
StepType = Literal["plan", "tool_call", "tool_result", "final"]
NarrateMode = Literal["blind", "grounded"]


# --- Трасса выполнения агента (эскиз §3) --------------------------------------
class TraceStep(BaseModel):
    """Один шаг выполнения. Пишется перехватом рантайма, не самим агентом."""

    step_id: str
    type: StepType
    ts: str
    tool_name: Optional[str] = None
    tool_input: Optional[dict[str, Any]] = None
    # Дайджест вывода (не сырой вывод) — чтобы трасса оставалась компактной.
    tool_output_digest: Optional[str] = None
    retrieved_ids: list[str] = Field(default_factory=list)
    latency_ms: Optional[int] = None


class AgentTrace(BaseModel):
    """Одна запись на решение. Неизменяема после записи (эскиз §3)."""

    decision_id: str
    created_at: str
    task: str
    steps: list[TraceStep] = Field(default_factory=list)
    # Идентификаторы реально извлечённых документов/записей (из retrieved_ids).
    sources_used: list[str] = Field(default_factory=list)
    # Реестр инструментов, доступных агенту на момент решения.
    tools_available: list[str] = Field(default_factory=list)
    final_answer: str = ""
    model: str = ""
    prompt_version: str = ""
    temperature: float = 0.0
    code_version: str = "dev"


# --- agent-runtime: /v1/run ---------------------------------------------------
class RunRequest(BaseModel):
    task: str
    # Для абляционного перезапуска (эскиз §5, §12.3): источники, скрытые от агента.
    excluded_sources: list[str] = Field(default_factory=list)


class RunResponse(BaseModel):
    trace: AgentTrace
    source: Literal["fixture", "live"]


# --- narrator: /v1/narrate ----------------------------------------------------
class ClaimedStep(BaseModel):
    """Шаг/инструмент, который объяснение утверждает как выполненный."""

    tool_name: str
    # Свободное описание того, что объяснение приписывает этому шагу.
    purpose: str = ""


class ClaimedCause(BaseModel):
    """Причинная связь «ответ Y потому что шаг/источник Z» (эскиз §4)."""

    source_id: Optional[str] = None
    step_tool: Optional[str] = None
    because: str = ""


class NarrateRequest(BaseModel):
    mode: NarrateMode
    task: str
    final_answer: str
    # grounded получает трассу; blind — нет (единственное различие во входе).
    trace: Optional[AgentTrace] = None


class NarrateResponse(BaseModel):
    mode: NarrateMode
    narrative_ru: str
    claimed_steps: list[ClaimedStep] = Field(default_factory=list)
    claimed_sources: list[str] = Field(default_factory=list)
    claimed_because: list[ClaimedCause] = Field(default_factory=list)
    confidence_self_report: float = 0.0
    llm_model: str = ""
    prompt_version: str = ""
    temperature: float = 0.0
    source: Literal["fixture", "live"] = "fixture"
    latency_ms: int = 0


# --- audit: /v1/faithfulness --------------------------------------------------
class FaithfulnessComponents(BaseModel):
    step_coverage: float
    step_precision: float
    source_grounding: float
    causal_validity: float


class FaithfulnessResult(BaseModel):
    score: float
    verdict: Literal["faithful", "unfaithful"]
    components: FaithfulnessComponents
    # Доля claimed_steps+claimed_sources, отсутствующих в трассе/реестре (эскиз §4).
    fabrication_rate: float
    # Заявленные шаги/источники, которых нет в трассе (подсветка красным в UI).
    fabricated_steps: list[str] = Field(default_factory=list)
    fabricated_sources: list[str] = Field(default_factory=list)
    # Причины, не подтверждённые абляцией (подсветка оранжевым в UI).
    uncausal_claims: list[str] = Field(default_factory=list)
