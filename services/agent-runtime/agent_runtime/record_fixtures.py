"""Перезапись fixtures/agent/ реальными прогонами (эскиз §12.4, §12.6).

Для каждой демо-задачи: (1) прогон агента -> эталонная трасса; (2) по каждому
использованному источнику — абляционный перезапуск (тот же маршрут, источник
скрыт) -> запись изменённого ответа в таблицу. Запускается вручную в live-режиме,
требует OPENROUTER_API_KEY. CI работает на уже записанных фикстурах офлайн.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from agent_runtime.llm import decide_next, get_client
from agent_runtime.runner import run_agent
from agent_runtime.tools import ToolBox

TASKS_PATH = os.environ.get("TASKS_PATH", "/tasks/demo_tasks.json")
OUT_DIR = Path(os.environ.get("FIXTURES_DIR", "/fixtures")) / "agent"
MODEL = os.environ.get("NARRATOR_MODEL", "moonshotai/kimi-k2")
CODE_VERSION = os.environ.get("CODE_VERSION", "dev")


def main() -> None:
    client = get_client()
    toolbox = ToolBox(os.environ.get("CORPUS_PATH", "/config/corpus.yaml"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tasks = json.loads(Path(TASKS_PATH).read_text(encoding="utf-8"))["tasks"]

    def decide(task, hist):
        return decide_next(client, MODEL, task, hist)

    for t in tasks:
        ref = run_agent(
            t["task"], toolbox, decide,
            model=MODEL, prompt_version="agent.v1", code_version=CODE_VERSION,
        )
        ablation: dict[str, dict] = {}
        for sid in ref.sources_used:
            variant = run_agent(
                t["task"], toolbox, decide,
                model=MODEL, prompt_version="agent.v1", code_version=CODE_VERSION,
                excluded_sources=[sid],
            )
            changed = variant.final_answer.strip() != ref.final_answer.strip()
            if changed:  # причинные источники — только те, что меняют ответ (§4)
                ablation[sid] = {"final_answer": variant.final_answer, "changed": True}

        out = {"trace": ref.model_dump(), "ablation": ablation}
        (OUT_DIR / f"{t['task_id']}.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"recorded {t['task_id']}: {len(ref.sources_used)} sources, "
              f"{len(ablation)} causal")


if __name__ == "__main__":
    main()
