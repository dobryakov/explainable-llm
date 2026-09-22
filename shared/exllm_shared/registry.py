"""Загрузчик реестра инструментов config/tools.yaml (эскиз §4, замена реестра признаков).

Реестр — единственный источник правды о доступных агенту инструментах и их
алиасах. Здесь только чтение и индексы; трёхуровневый матчинг имён (точное имя /
алиас / выдумка) живёт в сервисе audit, но опирается на поля отсюда.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

import yaml

DEFAULT_PATH = os.environ.get("TOOLS_PATH", "/config/tools.yaml")


@dataclass
class Tool:
    name: str
    display_name_ru: str
    description: str = ""
    # Извлекает ли инструмент источники (влияет на source_grounding).
    retrieves_sources: bool = False
    aliases: list[str] = field(default_factory=list)


@dataclass
class ToolRegistry:
    tools: list[Tool]

    def __post_init__(self) -> None:
        self._by_name = {t.name: t for t in self.tools}
        # Индекс алиас -> каноническое имя для матчинга (эскиз §4).
        self._by_alias: dict[str, str] = {}
        for t in self.tools:
            for a in t.aliases:
                self._by_alias[a.lower()] = t.name

    @property
    def names(self) -> list[str]:
        return [t.name for t in self.tools]

    def get(self, name: str) -> Optional[Tool]:
        return self._by_name.get(name)

    def resolve(self, claimed: str) -> Optional[str]:
        """Трёхуровневый матчинг: точное имя -> алиас -> None (выдумка)."""
        if claimed in self._by_name:
            return claimed
        return self._by_alias.get(claimed.lower())

    def __contains__(self, name: str) -> bool:
        return name in self._by_name


def load_registry(path: str = DEFAULT_PATH) -> ToolRegistry:
    with open(path, "r", encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh)
    tools = [Tool(**rec) for rec in raw["tools"]]
    return ToolRegistry(tools=tools)
