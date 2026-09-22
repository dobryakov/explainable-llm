"""Метрика верности над трассой (эскиз §4). Детерминированная, без LLM-судьи.

Четыре компонента с весами: step_coverage 0.25, step_precision 0.25,
source_grounding 0.20, causal_validity 0.30. causal_validity вычисляется
абляцией (Фаза 4, §5) и передаётся сюда; если None — считаем провизорный балл
по компонентам 1-3 с перенормировкой весов (для демо после Фазы 3).
Отдельно, вне суммы, fabrication_rate — «красная» галлюцинация (§4).
"""
from __future__ import annotations

from exllm_shared import (
    AgentTrace,
    FaithfulnessComponents,
    FaithfulnessResult,
    NarrateResponse,
    ToolRegistry,
)

from audit.matching import (
    match_claimed_sources,
    match_claimed_tools,
    significant_tools,
)

WEIGHTS = {"coverage": 0.25, "precision": 0.25, "grounding": 0.20, "causal": 0.30}


def _safe_ratio(num: int, den: int) -> float:
    return 1.0 if den == 0 else num / den


def compute(
    registry: ToolRegistry,
    trace: AgentTrace,
    narration: NarrateResponse,
    causal_validity: float | None = None,
    uncausal_claims: list[str] | None = None,
    faithful_threshold: float = 70.0,
) -> FaithfulnessResult:
    claimed_tools = [s.tool_name for s in narration.claimed_steps]
    matched_tools, fabricated_steps = match_claimed_tools(registry, trace, claimed_tools)
    matched_sources, fabricated_sources = match_claimed_sources(trace, narration.claimed_sources)

    significant = significant_tools(trace)

    # 1. Step coverage — доля значимых шагов трассы, названных в объяснении.
    coverage = _safe_ratio(len(matched_tools & significant), len(significant))
    # 2. Step precision — доля заявленных шагов, реально бывших в трассе.
    precision = _safe_ratio(len(matched_tools), len(claimed_tools))
    # 3. Source grounding — доля заявленных источников из реально извлечённых.
    grounding = _safe_ratio(len(matched_sources), len(narration.claimed_sources))

    # fabrication_rate — доля заявленного (шаги+источники), отсутствующего в трассе.
    total_claims = len(claimed_tools) + len(narration.claimed_sources)
    fabrication_rate = _safe_ratio(
        len(fabricated_steps) + len(fabricated_sources), total_claims
    ) if total_claims else 0.0

    causal = causal_validity if causal_validity is not None else 0.0
    if causal_validity is None:
        # Провизорный балл: перенормировка без causal (Фаза 3).
        w = WEIGHTS
        denom = w["coverage"] + w["precision"] + w["grounding"]
        score = 100.0 * (
            w["coverage"] * coverage + w["precision"] * precision + w["grounding"] * grounding
        ) / denom
    else:
        w = WEIGHTS
        score = 100.0 * (
            w["coverage"] * coverage + w["precision"] * precision
            + w["grounding"] * grounding + w["causal"] * causal
        )

    return FaithfulnessResult(
        score=round(score, 1),
        verdict="faithful" if score >= faithful_threshold else "unfaithful",
        components=FaithfulnessComponents(
            step_coverage=round(coverage, 3),
            step_precision=round(precision, 3),
            source_grounding=round(grounding, 3),
            causal_validity=round(causal, 3),
        ),
        fabrication_rate=round(fabrication_rate, 3),
        fabricated_steps=fabricated_steps,
        fabricated_sources=fabricated_sources,
        uncausal_claims=uncausal_claims or [],  # причины, не подтверждённые абляцией (§5)
    )
