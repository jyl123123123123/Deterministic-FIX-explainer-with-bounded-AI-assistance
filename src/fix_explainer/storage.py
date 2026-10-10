"""SQLite persistence for raw FIX messages and normalized trading records."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .events import TradingEvent

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS stream_runs (
    run_id TEXT PRIMARY KEY,
    seed INTEGER NOT NULL,
    total_messages INTEGER NOT NULL CHECK (total_messages BETWEEN 1000 AND 2000),
    rate INTEGER NOT NULL CHECK (rate BETWEEN 10 AND 100),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'RUNNING', 'PAUSED', 'COMPLETED', 'STOPPED', 'FAILED'))
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    sequence INTEGER NOT NULL,
    raw_message BLOB NOT NULL,
    message_type TEXT,
    received_at TEXT NOT NULL,
    parse_status TEXT NOT NULL CHECK (parse_status IN ('ACCEPTED', 'REJECTED')),
    parse_error TEXT,
    UNIQUE (run_id, sequence),
    FOREIGN KEY (run_id) REFERENCES stream_runs(run_id)
);

CREATE TABLE IF NOT EXISTS orders (
    cl_ord_id TEXT PRIMARY KEY,
    order_id TEXT UNIQUE,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    order_qty INTEGER NOT NULL CHECK (order_qty >= 0),
    cum_qty INTEGER NOT NULL DEFAULT 0 CHECK (cum_qty >= 0),
    leaves_qty INTEGER NOT NULL DEFAULT 0 CHECK (leaves_qty >= 0),
    status TEXT NOT NULL,
    avg_price REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS executions (
    exec_id TEXT PRIMARY KEY,
    cl_ord_id TEXT,
    order_id TEXT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    last_qty INTEGER NOT NULL CHECK (last_qty >= 0),
    last_price REAL,
    exec_type TEXT,
    order_status TEXT,
    received_at TEXT NOT NULL,
    is_duplicate INTEGER NOT NULL DEFAULT 0 CHECK (is_duplicate IN (0, 1)),
    FOREIGN KEY (cl_ord_id) REFERENCES orders(cl_ord_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_received_at ON messages(received_at);
CREATE INDEX IF NOT EXISTS idx_executions_symbol_received_at
    ON executions(symbol, received_at);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


class SQLiteTradingRepository:
    """Small transactional repository for the Person A data service."""

    def __init__(self, database: str | Path = ":memory:") -> None:
        self.database = str(database)
        self._connection = sqlite3.connect(self.database, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.executescript(SCHEMA)
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLiteTradingRepository":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self._connection
        except Exception:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    def create_run(self, run_id: str, seed: int, total_messages: int, rate: int) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO stream_runs
                    (run_id, seed, total_messages, rate, started_at, status)
                VALUES (?, ?, ?, ?, ?, 'PENDING')
                """,
                (run_id, seed, total_messages, rate, utc_now()),
            )

    def update_run(self, run_id: str, status: str, finished: bool = False) -> None:
        finished_at = utc_now() if finished else None
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE stream_runs
                SET status = ?, finished_at = COALESCE(?, finished_at)
                WHERE run_id = ?
                """,
                (status, finished_at, run_id),
            )

    def save_message(
        self,
        *,
        run_id: str | None,
        sequence: int,
        raw_message: bytes,
        message_type: str | None,
        accepted: bool,
        parse_error: str | None = None,
        received_at: str | None = None,
    ) -> int:
        with self.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO messages
                    (run_id, sequence, raw_message, message_type, received_at,
                     parse_status, parse_error)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    sequence,
                    raw_message,
                    message_type,
                    received_at or utc_now(),
                    "ACCEPTED" if accepted else "REJECTED",
                    parse_error,
                ),
            )
            return int(cursor.lastrowid)

    def upsert_order(self, event: TradingEvent, order_qty: int) -> None:
        if event.cl_ord_id is None:
            raise ValueError("order event requires cl_ord_id")
        timestamp = event.timestamp.isoformat()
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO orders
                    (cl_ord_id, order_id, symbol, side, order_qty, cum_qty,
                     leaves_qty, status, avg_price, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cl_ord_id) DO UPDATE SET
                    order_id = excluded.order_id,
                    symbol = excluded.symbol,
                    side = excluded.side,
                    order_qty = excluded.order_qty,
                    cum_qty = excluded.cum_qty,
                    leaves_qty = excluded.leaves_qty,
                    status = excluded.status,
                    avg_price = excluded.avg_price,
                    updated_at = excluded.updated_at
                """,
                (
                    event.cl_ord_id,
                    event.order_id,
                    event.symbol,
                    event.side.value,
                    order_qty,
                    event.cum_qty or 0,
                    event.leaves_qty if event.leaves_qty is not None else order_qty,
                    event.order_status.value if event.order_status else event.event_type.value,
                    float(event.last_px) if event.last_px is not None else None,
                    timestamp,
                    timestamp,
                ),
            )

    def save_execution(self, event: TradingEvent, exec_type: str | None = None) -> bool:
        """Insert an execution once; return False when its ExecID already exists."""
        if event.exec_id is None:
            raise ValueError("execution event requires exec_id")
        with self.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO executions
                    (exec_id, cl_ord_id, order_id, symbol, side, last_qty,
                     last_price, exec_type, order_status, received_at, is_duplicate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    event.exec_id,
                    event.cl_ord_id,
                    event.order_id,
                    event.symbol,
                    event.side.value,
                    event.last_qty or 0,
                    float(event.last_px) if event.last_px is not None else None,
                    exec_type,
                    event.order_status.value if event.order_status else None,
                    event.timestamp.isoformat(),
                ),
            )
            return cursor.rowcount == 1

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM stream_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    def list_orders(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM orders ORDER BY updated_at, cl_ord_id"
        ).fetchall()
        return [dict(row) for row in rows]

    def list_executions(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM executions ORDER BY received_at, exec_id"
        ).fetchall()
        return [dict(row) for row in rows]
