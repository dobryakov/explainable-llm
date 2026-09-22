"""Неизменяемое хранилище оценок верности (эскиз §1: decision_traces, supersedes).

Минимальный sqlite-стор: одна строка на оценку (decision_id + mode), запись
append-only. Переоценка пишет новую строку со ссылкой supersedes на предыдущую,
старые не переписываются.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Optional

DB_PATH = os.environ.get("DB_PATH", "/data/audit.db")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            score REAL NOT NULL,
            result_json TEXT NOT NULL,
            supersedes INTEGER,
            created_at REAL NOT NULL
        )"""
    )
    return conn


def save(decision_id: str, mode: str, score: float, result_json: str) -> int:
    conn = _conn()
    try:
        prev = conn.execute(
            "SELECT id FROM evaluations WHERE decision_id=? AND mode=? "
            "ORDER BY id DESC LIMIT 1",
            (decision_id, mode),
        ).fetchone()
        cur = conn.execute(
            "INSERT INTO evaluations (decision_id, mode, score, result_json, "
            "supersedes, created_at) VALUES (?,?,?,?,?,?)",
            (decision_id, mode, score, result_json, prev[0] if prev else None, time.time()),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()
