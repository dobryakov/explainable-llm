"""Общие контракты для всех сервисов Explainable-LLM-Agent демо.

Единственный источник правды для Pydantic-схем трассы, объяснений и метрики
верности. Импортируется всеми сервисами, чтобы API-контракты не разъезжались
между реализациями.
"""
from exllm_shared.models import (
    AgentTrace,
    ClaimedCause,
    ClaimedStep,
    FaithfulnessComponents,
    FaithfulnessResult,
    NarrateRequest,
    NarrateResponse,
    RunRequest,
    RunResponse,
    TraceStep,
)
from exllm_shared.registry import Tool, ToolRegistry, load_registry

__all__ = [
    "AgentTrace",
    "TraceStep",
    "RunRequest",
    "RunResponse",
    "NarrateRequest",
    "NarrateResponse",
    "ClaimedStep",
    "ClaimedCause",
    "FaithfulnessComponents",
    "FaithfulnessResult",
    "Tool",
    "ToolRegistry",
    "load_registry",
]
