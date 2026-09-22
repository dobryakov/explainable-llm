"""CI-guard (эскиз §7, §12.5): прогон всех демо-задач, сводная таблица верности,
проверка разрыва grounded-blind. Завершается с кодом 1, если средний разрыв
меньше порога CI_GAP_THRESHOLD (старт 25). Охраняет смысл проекта."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

from gateway.orchestrate import analyze

TASKS_PATH = os.environ.get("TASKS_PATH", "/tasks/demo_tasks.json")
THRESHOLD = float(os.environ.get("CI_GAP_THRESHOLD", "25"))


def main() -> int:
    tasks = json.loads(Path(TASKS_PATH).read_text(encoding="utf-8"))["tasks"]
    rows: list[tuple[str, float, float, float]] = []
    with httpx.Client() as client:
        for t in tasks:
            res = analyze(t["task"], client)
            g = res["modes"]["grounded"]["faithfulness"]["score"]
            b = res["modes"]["blind"]["faithfulness"]["score"]
            rows.append((t["task_id"], g, b, res["gap"]))

    print(f"\n{'task':10} {'grounded':>9} {'blind':>7} {'gap':>7}")
    print("-" * 36)
    for tid, g, b, gap in rows:
        print(f"{tid:10} {g:9.1f} {b:7.1f} {gap:7.1f}")
    avg_gap = sum(r[3] for r in rows) / len(rows) if rows else 0.0
    min_gap = min((r[3] for r in rows), default=0.0)
    print("-" * 36)
    print(f"avg gap = {avg_gap:.1f}  min gap = {min_gap:.1f}  threshold = {THRESHOLD:.0f}")

    if avg_gap < THRESHOLD:
        print(f"\nFAIL: средний разрыв {avg_gap:.1f} < порога {THRESHOLD:.0f}", file=sys.stderr)
        return 1
    print(f"\nOK: разрыв верности выше порога ({avg_gap:.1f} >= {THRESHOLD:.0f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
