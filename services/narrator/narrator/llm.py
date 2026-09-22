"""Клиент LLM для нарратора (эскиз §4, §12.6): OpenRouter, OpenAI-совместимый API.

Одна модель на оба режима (blind/grounded) — различие ТОЛЬКО во входе (наличие
трассы), никогда в модели/temperature/промпт-стиле. Используется в live-режиме.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from exllm_shared import NarrateRequest

PROMPTS_DIR = Path(os.environ.get("PROMPTS_DIR", "/prompts"))


class LLMJSONError(RuntimeError):
    """LLM вернул не разбираемый JSON."""


def get_client() -> Any:
    from openai import OpenAI

    return OpenAI(
        base_url=os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
    )


def load_prompt(mode: str) -> str:
    return (PROMPTS_DIR / f"{mode}.v1.md").read_text(encoding="utf-8")


def build_user_payload(req: NarrateRequest) -> dict:
    """Вход объяснителя. grounded получает трассу, blind — нет (§4)."""
    payload: dict[str, Any] = {"task": req.task, "final_answer": req.final_answer}
    if req.mode == "grounded" and req.trace is not None:
        payload["trace"] = req.trace.model_dump()
    return payload


def call_llm_json(client: Any, model: str, req: NarrateRequest) -> dict:
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": load_prompt(req.mode)},
            {"role": "user", "content": json.dumps(build_user_payload(req), ensure_ascii=False)},
        ],
    )
    raw = resp.choices[0].message.content or ""
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMJSONError(raw) from exc
