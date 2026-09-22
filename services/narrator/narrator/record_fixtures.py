"""Перезапись fixtures/{blind,grounded}/ реальными ответами нарратора (§12.6).

Берёт трассу и финальный ответ из записанных agent-фикстур, вызывает LLM в обоих
режимах и сохраняет NarrateResponse. Запускается вручную в live-режиме.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from exllm_shared import AgentTrace, NarrateRequest

from narrator.llm import call_llm_json, get_client

FIXTURES_DIR = Path(os.environ.get("FIXTURES_DIR", "/fixtures"))
MODEL = os.environ.get("NARRATOR_MODEL", "moonshotai/kimi-k2")


def main() -> None:
    client = get_client()
    agent_dir = FIXTURES_DIR / "agent"
    for path in sorted(agent_dir.glob("*.json")):
        task_id = path.stem
        fixture = json.loads(path.read_text(encoding="utf-8"))
        trace = AgentTrace.model_validate(fixture["trace"])
        for mode in ("blind", "grounded"):
            req = NarrateRequest(
                mode=mode, task=trace.task, final_answer=trace.final_answer,
                trace=trace if mode == "grounded" else None,
            )
            raw = call_llm_json(client, MODEL, req)
            out = {
                "mode": mode,
                "narrative_ru": raw.get("narrative_ru", ""),
                "claimed_steps": raw.get("claimed_steps", []),
                "claimed_sources": raw.get("claimed_sources", []),
                "claimed_because": raw.get("claimed_because", []),
                "confidence_self_report": float(raw.get("confidence_self_report", 0.0)),
                "llm_model": MODEL, "prompt_version": f"{mode}.v1",
                "temperature": 0.0, "source": "fixture", "latency_ms": 0,
            }
            dest = FIXTURES_DIR / mode / f"{task_id}.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"recorded {mode}/{task_id}")


if __name__ == "__main__":
    main()
