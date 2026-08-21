"""Append-only audit events for safe NVMe Insight workflows."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


def timestamp() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def initialise(con: sqlite3.Connection) -> None:
    con.execute(
        """CREATE TABLE IF NOT EXISTS audit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
        category TEXT NOT NULL, action TEXT NOT NULL, subject TEXT NOT NULL,
        details TEXT NOT NULL DEFAULT '{}')"""
    )


def record(
    con: sqlite3.Connection,
    category: str,
    action: str,
    subject: str,
    details: dict | None = None,
) -> int:
    cursor = con.execute(
        "INSERT INTO audit_events (created_at,category,action,subject,details) VALUES (?,?,?,?,?)",
        (
            timestamp(),
            category,
            action,
            subject,
            json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
        ),
    )
    return cursor.lastrowid


def recent(con: sqlite3.Connection, limit: int = 50) -> list[dict]:
    limit = max(1, min(int(limit), 200))
    rows = con.execute(
        "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [{**dict(row), "details": json.loads(row["details"])} for row in rows]
