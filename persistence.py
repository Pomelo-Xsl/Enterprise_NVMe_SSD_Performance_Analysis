"""Persistence boundary for imported analyses and their derived records.

SQLite keeps a deployment self-contained. Schema creation, JSON payload storage
and alert acknowledgement are grouped here so callers do not depend on table
layout or transaction details.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def timestamp() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class Repository:
    """Small transactional repository used by CLI and Web API workflows."""

    def __init__(self, database: str | Path) -> None:
        self.database = str(database)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS simulation_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    scenario_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    workload_kind TEXT NOT NULL,
                    cache_algorithm TEXT NOT NULL,
                    sample_count INTEGER NOT NULL DEFAULT 0,
                    result_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER,
                    created_at TEXT NOT NULL,
                    code TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    source TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    threshold_json TEXT NOT NULL,
                    acknowledged INTEGER NOT NULL DEFAULT 0,
                    acknowledged_at TEXT,
                    FOREIGN KEY(run_id) REFERENCES simulation_runs(id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_alerts_run_id
                    ON alerts(run_id);
                CREATE INDEX IF NOT EXISTS idx_alerts_severity
                    ON alerts(severity, acknowledged);
                """
            )

    def save_run(self, result: dict) -> int:
        configuration = result.get("configuration", {})
        scenario = configuration.get("scenario", {})
        workload = configuration.get("workload", {})
        cache = configuration.get("cache", {})
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO simulation_runs (
                    created_at,
                    scenario_name,
                    status,
                    workload_kind,
                    cache_algorithm,
                    sample_count,
                    result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.get("generated_at", timestamp()),
                    scenario.get("name", "unnamed"),
                    "completed",
                    workload.get("kind", "unknown"),
                    cache.get("algorithm", "unknown"),
                    int(result.get("sample_count", 0)),
                    json.dumps(result, ensure_ascii=False, sort_keys=True),
                ),
            )
            run_id = int(cursor.lastrowid)
            for event in result.get("alerts", {}).get("events", []):
                self._insert_alert(connection, run_id, event)
            return run_id

    def _insert_alert(
        self,
        connection: sqlite3.Connection,
        run_id: int | None,
        event: dict,
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO alerts (
                run_id,
                created_at,
                code,
                severity,
                message,
                source,
                value_json,
                threshold_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                timestamp(),
                event.get("code", "unknown"),
                event.get("severity", "info"),
                event.get("message", ""),
                event.get("source", "system"),
                json.dumps(event.get("value"), ensure_ascii=False),
                json.dumps(event.get("threshold"), ensure_ascii=False),
            ),
        )
        return int(cursor.lastrowid)

    def list_runs(self, limit: int = 50) -> list[dict]:
        safe_limit = max(1, min(int(limit), 500))
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, scenario_name, status,
                       workload_kind, cache_algorithm, sample_count
                FROM simulation_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_run(self, run_id: int) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT result_json FROM simulation_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        return json.loads(row["result_json"]) if row else None

    def list_alerts(
        self,
        run_id: int | None = None,
        severity: str | None = None,
        acknowledged: bool | None = None,
        limit: int = 100,
    ) -> list[dict]:
        clauses = []
        parameters: list = []
        if run_id is not None:
            clauses.append("run_id = ?")
            parameters.append(run_id)
        if severity is not None:
            clauses.append("severity = ?")
            parameters.append(severity)
        if acknowledged is not None:
            clauses.append("acknowledged = ?")
            parameters.append(int(acknowledged))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(max(1, min(int(limit), 1000)))
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM alerts
                {where}
                ORDER BY id DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        events = []
        for row in rows:
            event = dict(row)
            event["value"] = json.loads(event.pop("value_json"))
            event["threshold"] = json.loads(event.pop("threshold_json"))
            event["acknowledged"] = bool(event["acknowledged"])
            events.append(event)
        return events

    def acknowledge_alert(self, alert_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE alerts
                SET acknowledged = 1, acknowledged_at = ?
                WHERE id = ? AND acknowledged = 0
                """,
                (timestamp(), alert_id),
            )
            return cursor.rowcount > 0

    def delete_run(self, run_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM simulation_runs WHERE id = ?",
                (run_id,),
            )
            return cursor.rowcount > 0
