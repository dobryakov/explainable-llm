"""Тесты причинной проверки (Фаза 4, §5). run_fn эмулирует fixture-абляцию
agent-runtime офлайн: reference vs ответ с убранным источником."""
from __future__ import annotations

import json
import os
from pathlib import Path

from exllm_shared import AgentTrace, NarrateResponse, load_registry

from audit import causal, faithfulness

def _find_repo(start: Path) -> Path:
    for c in [start, *start.parents]:
        if (c / "fixtures").is_dir():
            return c
    return start.parents[len(start.parents) - 1]


_REPO = _find_repo(Path(__file__).resolve())
FIXT = Path(os.environ.get("FIXTURES_DIR", _REPO / "fixtures"))
TOOLS = os.environ.get("TOOLS_PATH", str(_REPO / "config/tools.yaml"))
REG = load_registry(TOOLS)


def _fixture(task_id: str) -> dict:
    return json.loads((FIXT / f"agent/{task_id}.json").read_text(encoding="utf-8"))


def _make_run_fn(fixture: dict):
    ref_answer = fixture["trace"]["final_answer"]
    ablation = fixture.get("ablation", {})

    def run_fn(task: str, excluded: list[str]) -> str:
        if not excluded:
            return ref_answer
        entry = ablation.get(excluded[0])
        return entry["final_answer"] if entry else ref_answer  # нет записи => не изменился

    return run_fn


def _narr(mode: str, task_id: str) -> NarrateResponse:
    return NarrateResponse.model_validate(
        json.loads((FIXT / f"{mode}/{task_id}.json").read_text(encoding="utf-8"))
    )


def test_grounded_causal_full_t01():
    fx = _fixture("t-01")
    tr = AgentTrace.model_validate(fx["trace"])
    cv, uncausal = causal.compute_causal(tr, _narr("grounded", "t-01"), _make_run_fn(fx))
    assert cv == 1.0
    assert uncausal == []


def test_blind_causal_zero_t01():
    fx = _fixture("t-01")
    tr = AgentTrace.model_validate(fx["trace"])
    # blind ссылается на KB-200 (извлечён, но не причинён) и KB-201 (выдумка).
    cv, uncausal = causal.compute_causal(tr, _narr("blind", "t-01"), _make_run_fn(fx))
    assert cv == 0.0
    assert "KB-200" in uncausal  # оранжевый: в трассе, но не причина
    assert "KB-201" in uncausal  # ссылка на не извлечённый источник


def test_full_score_gap():
    for tid in ("t-01", "t-02"):
        fx = _fixture(tid)
        tr = AgentTrace.model_validate(fx["trace"])
        run_fn = _make_run_fn(fx)
        gv, gu = causal.compute_causal(tr, _narr("grounded", tid), run_fn)
        bv, bu = causal.compute_causal(tr, _narr("blind", tid), run_fn)
        g = faithfulness.compute(REG, tr, _narr("grounded", tid), gv, gu)
        b = faithfulness.compute(REG, tr, _narr("blind", tid), bv, bu)
        assert g.score - b.score >= 25  # порог CI (§12.5)
        assert g.components.causal_validity == 1.0
