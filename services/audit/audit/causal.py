"""Причинная проверка через абляцию (эскиз §5, §12.3). Самая нетривиальная часть.

Для каждой заявленной причины «ответ Y потому что источник Z»:
  - если Z не извлекался (нет в sources_used) — причина ложная (выдумка);
  - иначе убрать Z и перезапустить агента; если ответ НЕ изменился — Z не был
    причиной (уходит в uncausal_claims, «оранжевый» в UI); если изменился — причина верна.

Абляция только по источникам (v1, §12.3). run_fn инъектируется, что позволяет
считать причинность и офлайн (fixture-реплей agent-runtime), и по сети.
"""
from __future__ import annotations

from typing import Callable

from exllm_shared import AgentTrace, NarrateResponse

# run_fn(task, excluded_sources) -> final_answer
RunFn = Callable[[str, list[str]], str]


def compute_causal(
    trace: AgentTrace, narration: NarrateResponse, run_fn: RunFn
) -> tuple[float, list[str]]:
    """Вернуть (causal_validity в [0,1], список не подтверждённых причин-источников).

    Знаменатель — все заявленные причины, ссылающиеся на источник. Нет таких —
    проверять нечего, причинность считается выполненной (1.0).
    """
    source_causes = [c.source_id for c in narration.claimed_because if c.source_id]
    if not source_causes:
        return 1.0, []

    used = set(trace.sources_used)
    reference = run_fn(trace.task, []).strip()

    valid = 0
    uncausal: list[str] = []
    for z in source_causes:
        if z not in used:
            uncausal.append(z)  # причина ссылается на не извлечённый источник
            continue
        ablated = run_fn(trace.task, [z]).strip()
        if ablated != reference:
            valid += 1  # убрали причину — ответ изменился => причина настоящая
        else:
            uncausal.append(z)  # ответ не изменился => Z не был причиной

    return valid / len(source_causes), uncausal
