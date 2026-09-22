"""Клиент LLM для агента (эскиз §12.6): OpenRouter, OpenAI-совместимый API.

Одна модель на агента и нарратора — различие только во входе (§4). Используется
только в live-режиме (запись фикстур); в fixture-режиме LLM не вызывается.
"""
from __future__ import annotations

import json
import os
from typing import Any


class LLMJSONError(RuntimeError):
    """LLM вернул не разбираемый JSON."""


def get_client() -> Any:
    from openai import OpenAI

    return OpenAI(
        base_url=os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
    )


AGENT_SYSTEM = (
    "Ты — ассистент поддержки, решающий задачу через инструменты. "
    "На каждом шаге верни СТРОГО JSON одного из двух видов:\n"
    '  {\"action\": \"tool_call\", \"tool_name\": \"<имя>\", \"tool_input\": {...}}\n'
    '  {\"action\": \"final\", \"answer\": \"<финальный ответ клиенту>\"}\n'
    "Доступные инструменты: search_kb(query), get_ticket(ticket_id), "
    "sql_query(query_tag), web_fetch(url). Не выдумывай инструменты."
)


def decide_next(client: Any, model: str, task: str, history: list[dict]) -> dict:
    """Один шаг решения агента: следующий tool_call или final (live-режим)."""
    user = {"task": task, "steps_so_far": history}
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": AGENT_SYSTEM},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
    )
    raw = resp.choices[0].message.content or ""
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMJSONError(raw) from exc
