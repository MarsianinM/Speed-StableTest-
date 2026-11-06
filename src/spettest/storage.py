"""Локальна історія замірів у SQLite (без хмарної синхронізації)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from spettest.paths import database_path
from spettest.report import SpeedResult, StableResult


@dataclass(frozen=True)
class HistoryRow:
    id: int
    created_at: str
    public_ip: str | None
    test_type: str
    download_mbps: float | None
    upload_mbps: float | None
    ping_ms: float | None
    duration_s: int | None
    ping_avg_ms: float | None
    ping_min_ms: float | None
    ping_max_ms: float | None
    jitter_ms: float | None
    loss_percent: float | None
    verdict: str | None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS measurements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    public_ip TEXT,
    test_type TEXT NOT NULL,
    download_mbps REAL,
    upload_mbps REAL,
    ping_ms REAL,
    duration_s INTEGER,
    ping_avg_ms REAL,
    ping_min_ms REAL,
    ping_max_ms REAL,
    jitter_ms REAL,
    loss_percent REAL,
    verdict TEXT
);
CREATE INDEX IF NOT EXISTS idx_measurements_created ON measurements(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_measurements_ip ON measurements(public_ip);
"""


def _connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def save_speed(result: SpeedResult, public_ip: str | None) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO measurements (
                created_at, public_ip, test_type,
                download_mbps, upload_mbps, ping_ms
            ) VALUES (?, ?, 'speed', ?, ?, ?)
            """,
            (
                _now_iso(),
                public_ip,
                result.download_mbps,
                result.upload_mbps,
                result.ping_ms,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def save_stable(result: StableResult, public_ip: str | None) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO measurements (
                created_at, public_ip, test_type,
                duration_s, ping_avg_ms, ping_min_ms, ping_max_ms,
                jitter_ms, loss_percent, verdict
            ) VALUES (?, ?, 'stable', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _now_iso(),
                public_ip,
                result.duration_s,
                result.ping_avg_ms,
                result.ping_min_ms,
                result.ping_max_ms,
                result.jitter_ms,
                result.loss_percent,
                result.verdict,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def _row_from_db(row: sqlite3.Row) -> HistoryRow:
    return HistoryRow(
        id=int(row["id"]),
        created_at=str(row["created_at"]),
        public_ip=row["public_ip"],
        test_type=str(row["test_type"]),
        download_mbps=row["download_mbps"],
        upload_mbps=row["upload_mbps"],
        ping_ms=row["ping_ms"],
        duration_s=row["duration_s"],
        ping_avg_ms=row["ping_avg_ms"],
        ping_min_ms=row["ping_min_ms"],
        ping_max_ms=row["ping_max_ms"],
        jitter_ms=row["jitter_ms"],
        loss_percent=row["loss_percent"],
        verdict=row["verdict"],
    )


def list_history(
    *,
    public_ip: str | None = None,
    on_date: date | None = None,
    limit: int = 100,
) -> list[HistoryRow]:
    """Історія від новіших до старіших; опційний фільтр по IP та даті (локальний календарний день)."""
    clauses: list[str] = []
    params: list[Any] = []

    if public_ip:
        clauses.append("public_ip = ?")
        params.append(public_ip)
    if on_date is not None:
        # Порівняння префікса ISO-дати в локальному записі (YYYY-MM-DD…).
        clauses.append("substr(created_at, 1, 10) = ?")
        params.append(on_date.isoformat())

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT * FROM measurements
        {where}
        ORDER BY datetime(created_at) DESC, id DESC
        LIMIT ?
    """
    params.append(limit)

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_from_db(r) for r in rows]


def count_history() -> int:
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM measurements").fetchone()
    return int(row["c"]) if row else 0
