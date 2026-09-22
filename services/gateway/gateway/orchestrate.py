"""Оркестрация цепочки для одной задачи (эскиз §6, §8).

agent-runtime (трасса) -> narrator (blind и grounded) -> audit (верность каждого).
Единственное различие между режимами — вход нарратора (трасса grounded, blind без).
"""
from __future__ import annotations

import os

import httpx

AGENT_RUNTIME_URL = os.environ.get("AGENT_RUNTIME_URL", "http://agent-runtime:12101")
NARRATOR_URL = os.environ.get("NARRATOR_URL", "http://narrator:12102")
AUDIT_URL = os.environ.get("AUDIT_URL", "http://audit:12103")

TIMEOUT = 60.0


def analyze(task: str, client: httpx.Client) -> dict:
    run = client.post(f"{AGENT_RUNTIME_URL}/v1/run",
                      json={"task": task, "excluded_sources": []}, timeout=TIMEOUT)
    run.raise_for_status()
    trace = run.json()["trace"]

    modes: dict[str, dict] = {}
    for mode in ("blind", "grounded"):
        payload = {"mode": mode, "task": task, "final_answer": trace["final_answer"],
                   "trace": trace if mode == "grounded" else None}
        nr = client.post(f"{NARRATOR_URL}/v1/narrate", json=payload, timeout=TIMEOUT)
        nr.raise_for_status()
        narration = nr.json()

        ar = client.post(f"{AUDIT_URL}/v1/faithfulness",
                         json={"trace": trace, "narration": narration, "compute_causal": True},
                         timeout=TIMEOUT)
        ar.raise_for_status()
        modes[mode] = {"narration": narration, "faithfulness": ar.json()}

    return {"task": task, "trace": trace, "modes": modes,
            "gap": round(modes["grounded"]["faithfulness"]["score"]
                         - modes["blind"]["faithfulness"]["score"], 1)}
