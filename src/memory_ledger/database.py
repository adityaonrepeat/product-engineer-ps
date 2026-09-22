"""Small SQLite connection and transaction helpers."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DatabasePath = str | Path

BUSY_TIMEOUT_MS = 2_000


def _migration_path() -> Path:
    return Path(__file__).resolve().parents[2] / "migrations" / "001_initial.sql"


def connect(database: DatabasePath) -> sqlite3.Connection:
    """Open one configured connection for a single operation."""
    connection = sqlite3.connect(
        str(database),
        timeout=BUSY_TIMEOUT_MS / 1_000,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    return connection


def initialize_database(database: DatabasePath) -> None:
    """Create the database and apply the single idempotent schema migration."""
    if str(database) != ":memory:":
        Path(database).parent.mkdir(parents=True, exist_ok=True)

    connection = connect(database)
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(_migration_path().read_text(encoding="utf-8"))
    finally:
        connection.close()


@contextmanager
def read_connection(database: DatabasePath) -> Iterator[sqlite3.Connection]:
    connection = connect(database)
    try:
        yield connection
    finally:
        connection.close()


@contextmanager
def write_transaction(database: DatabasePath) -> Iterator[sqlite3.Connection]:
    """Acquire the SQLite write lock before any lifecycle validation."""
    connection = connect(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
