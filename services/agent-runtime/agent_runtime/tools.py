"""Fixture-инструменты агента над корпусом (эскиз §3, §7).

Каждый инструмент детерминирован: по входу возвращает фиксированный вывод из
config/corpus.yaml и список retrieved_ids. `excluded_sources` — для абляционного
перезапуска (§5, §12.3): скрытый источник исключается из выдачи, будто агент его
не доставал. Это единственная точка, через которую абляция влияет на инструменты.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any, Callable

import yaml

CORPUS_PATH = os.environ.get("CORPUS_PATH", "/config/corpus.yaml")


@dataclass
class ToolResult:
    output_digest: str
    retrieved_ids: list[str]


def _digest(text: str) -> str:
    """Компактный дайджест вывода (в трассу пишем не сырой вывод, §3)."""
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"{text[:80]} …[{h}]" if len(text) > 80 else f"{text} [{h}]"


class ToolBox:
    """Реестр вызываемых инструментов над корпусом."""

    def __init__(self, corpus_path: str = CORPUS_PATH):
        with open(corpus_path, "r", encoding="utf-8") as fh:
            self.corpus: dict[str, Any] = yaml.safe_load(fh)

    def _hits(self, records: list[dict], query: str, excluded: set[str]) -> ToolResult:
        """Наивный подстрочный матч по query; исключённые источники выпадают."""
        q = query.lower()
        ids, texts = [], []
        for rec in records:
            if rec["id"] in excluded:
                continue
            blob = f"{rec.get('title', '')} {rec.get('text', '')} {rec.get('query_tag', '')}".lower()
            if not q or any(tok in blob for tok in q.split()):
                ids.append(rec["id"])
                texts.append(rec.get("text", ""))
        return ToolResult(output_digest=_digest(" | ".join(texts) or "нет результатов"), retrieved_ids=ids)

    def search_kb(self, tool_input: dict, excluded: set[str]) -> ToolResult:
        return self._hits(self.corpus.get("documents", []), tool_input.get("query", ""), excluded)

    def get_ticket(self, tool_input: dict, excluded: set[str]) -> ToolResult:
        tid = tool_input.get("ticket_id", "")
        recs = [r for r in self.corpus.get("tickets", []) if r["id"] == tid]
        return self._hits(recs, "", excluded)

    def sql_query(self, tool_input: dict, excluded: set[str]) -> ToolResult:
        tag = tool_input.get("query_tag", tool_input.get("query", ""))
        recs = [r for r in self.corpus.get("sql_rows", []) if tag and tag in (r.get("query_tag", ""))]
        return self._hits(recs or self.corpus.get("sql_rows", []), tag, excluded)

    def web_fetch(self, tool_input: dict, excluded: set[str]) -> ToolResult:
        url = tool_input.get("url", "")
        recs = [r for r in self.corpus.get("web", []) if r.get("url") == url]
        return self._hits(recs, "", excluded)

    def dispatch(self, tool_name: str, tool_input: dict, excluded: set[str]) -> ToolResult:
        fn: Callable[[dict, set[str]], ToolResult] | None = getattr(self, tool_name, None)
        if fn is None or tool_name not in {"search_kb", "get_ticket", "sql_query", "web_fetch"}:
            raise ValueError(f"unknown tool: {tool_name}")
        return fn(tool_input, excluded)
