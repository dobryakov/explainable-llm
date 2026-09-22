"""Тесты метрики верности (Фаза 3). Проверяют, что blind оценивается ниже
grounded и что выдуманные шаги/источники ловятся (эскиз §4)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from exllm_shared import AgentTrace, NarrateResponse, load_registry

from audit import faithfulness

# Пути устойчивы и в репозитории, и в контейнере (env), см. docker-compose.
def _find_repo(start: Path) -> Path:
    for c in [start, *start.parents]:
        if (c / "fixtures").is_dir():
            return c
    return start.parents[len(start.parents) - 1]


_REPO = _find_repo(Path(__file__).resolve())
FIXT = Path(os.environ.get("FIXTURES_DIR", _REPO / "fixtures"))
TOOLS = os.environ.get("TOOLS_PATH", str(_REPO / "config/tools.yaml"))
REG = load_registry(TOOLS)


def _trace(task_id: str) -> AgentTrace:
    data = json.loads((FIXT / f"agent/{task_id}.json").read_text(encoding="utf-8"))
    return AgentTrace.model_validate(data["trace"])


def _narr(mode: str, task_id: str) -> NarrateResponse:
    data = json.loads((FIXT / f"{mode}/{task_id}.json").read_text(encoding="utf-8"))
    return NarrateResponse.model_validate(data)


def test_grounded_beats_blind_t01():
    tr = _trace("t-01")
    g = faithfulness.compute(REG, tr, _narr("grounded", "t-01"))
    b = faithfulness.compute(REG, tr, _narr("blind", "t-01"))
    assert g.score > b.score
    assert g.fabrication_rate == 0.0
    assert b.fabrication_rate > 0.0


def test_blind_fabrications_detected_t01():
    tr = _trace("t-01")
    b = faithfulness.compute(REG, tr, _narr("blind", "t-01"))
    # web_fetch не вызывался, KB-201 не извлекался.
    assert "web_fetch" in b.fabricated_steps
    assert "KB-201" in b.fabricated_sources


def test_grounded_perfect_components_t01():
    tr = _trace("t-01")
    g = faithfulness.compute(REG, tr, _narr("grounded", "t-01"))
    c = g.components
    assert c.step_coverage == 1.0
    assert c.step_precision == 1.0
    assert c.source_grounding == 1.0


def test_gap_present_both_tasks():
    for tid in ("t-01", "t-02"):
        tr = _trace(tid)
        g = faithfulness.compute(REG, tr, _narr("grounded", tid))
        b = faithfulness.compute(REG, tr, _narr("blind", tid))
        assert g.score - b.score > 0
