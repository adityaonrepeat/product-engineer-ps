"""SQLite persistence for memories."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from uuid import UUID

from memory_ledger.database import DatabasePath, read_connection, write_transaction
from memory_ledger.models import (
    CreateResult,
    MemoryCreate,
    MemoryNotFoundError,
    MemoryRecord,
    MemoryState,
    as_utc,
    memory_id_for,
    source_digest,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_db_datetime(value: datetime) -> str:
    return as_utc(value).isoformat().replace("+00:00", "Z")


def from_db_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def memory_from_row(row: sqlite3.Row) -> MemoryRecord:
    tags = json.loads(row["tags_json"]) if row["tags_json"] is not None else None
    return MemoryRecord(
        id=UUID(row["id"]),
        key=row["key"],
        value=row["value"],
        text=row["text"],
        tags=tags,
        source_message_id=row["source_message_id"],
        source_conversation_id=row["source_conversation_id"],
        source_excerpt=row["source_excerpt"],
        source_hash=row["source_hash"],
        source_occurred_at=from_db_datetime(row["source_occurred_at"]),
        state=MemoryState(row["state"]),
        supersedes_id=UUID(row["supersedes_id"]) if row["supersedes_id"] else None,
        superseded_by_id=(UUID(row["superseded_by_id"]) if row["superseded_by_id"] else None),
        conflicts_with_id=(UUID(row["conflicts_with_id"]) if row["conflicts_with_id"] else None),
        created_at=from_db_datetime(row["created_at"]),
        updated_at=from_db_datetime(row["updated_at"]),
        deleted_at=from_db_datetime(row["deleted_at"]),
    )


def get_memory_from_connection(
    connection: sqlite3.Connection, memory_id: UUID
) -> MemoryRecord | None:
    row = connection.execute("SELECT * FROM memories WHERE id = ?", (str(memory_id),)).fetchone()
    return memory_from_row(row) if row else None


def create_memory(
    database: DatabasePath,
    candidate: MemoryCreate,
    *,
    now: datetime | None = None,
) -> CreateResult:
    """Create once; duplicates return the immutable original row."""
    memory_id = memory_id_for(
        candidate.source.message_id,
        candidate.fact.key,
        candidate.fact.value,
    )
    timestamp = as_utc(now or utc_now())

    with write_transaction(database) as connection:
        existing = get_memory_from_connection(connection, memory_id)
        if existing is not None:
            return CreateResult(memory=existing, created=False)

        connection.execute(
            """
            INSERT INTO memories (
                id, key, value, text, tags_json,
                source_message_id, source_conversation_id, source_excerpt,
                source_hash, source_occurred_at, state,
                supersedes_id, superseded_by_id, conflicts_with_id,
                created_at, updated_at, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, NULL)
            """,
            (
                str(memory_id),
                candidate.fact.key,
                candidate.fact.value,
                candidate.fact.text,
                json.dumps(candidate.fact.tags, ensure_ascii=False, separators=(",", ":")),
                candidate.source.message_id,
                candidate.source.conversation_id,
                candidate.source.excerpt,
                source_digest(candidate.source.excerpt),
                to_db_datetime(candidate.source.occurred_at),
                MemoryState.ACTIVE.value,
                to_db_datetime(timestamp),
                to_db_datetime(timestamp),
            ),
        )
        created = get_memory_from_connection(connection, memory_id)
        assert created is not None
        return CreateResult(memory=created, created=True)


def get_memory(database: DatabasePath, memory_id: UUID) -> MemoryRecord:
    with read_connection(database) as connection:
        memory = get_memory_from_connection(connection, memory_id)
    if memory is None:
        raise MemoryNotFoundError(f"memory {memory_id} was not found")
    return memory
