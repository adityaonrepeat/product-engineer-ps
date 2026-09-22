"""Lifecycle rules for corrections, uncertain conflicts, deletion, and history."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from uuid import UUID

from memory_ledger import repository
from memory_ledger.database import DatabasePath, read_connection, write_transaction
from memory_ledger.models import (
    CreateResult,
    MemoryConflictError,
    MemoryCreate,
    MemoryInspection,
    MemoryNotFoundError,
    MemoryRecord,
    MemoryState,
    as_utc,
    memory_id_for,
)


def _candidate_id(candidate: MemoryCreate) -> UUID:
    return memory_id_for(
        candidate.source.message_id,
        candidate.fact.key,
        candidate.fact.value,
    )


def correct_memory(
    database: DatabasePath,
    target_id: UUID,
    replacement: MemoryCreate,
    *,
    now: datetime | None = None,
) -> CreateResult:
    replacement_id = _candidate_id(replacement)
    if replacement_id == target_id:
        raise MemoryConflictError("a memory cannot correct itself")

    timestamp = as_utc(now or repository.utc_now())
    with write_transaction(database) as connection:
        existing = repository.get_memory_from_connection(connection, replacement_id)
        if existing is not None:
            target = repository.get_memory_from_connection(connection, target_id)
            if (
                target is not None
                and existing.supersedes_id == target_id
                and target.superseded_by_id == replacement_id
            ):
                return CreateResult(memory=existing, created=False)
            raise MemoryConflictError("replacement identity is already in use")

        target = repository.get_memory_from_connection(connection, target_id)
        if target is None:
            raise MemoryNotFoundError(f"memory {target_id} was not found")
        if target.state != MemoryState.ACTIVE:
            raise MemoryConflictError("only an active memory can be corrected")

        inserted = repository.insert_candidate(
            connection,
            replacement,
            state=MemoryState.ACTIVE,
            now=timestamp,
            supersedes_id=target_id,
        )
        if not repository.mark_memory_superseded(
            connection,
            target_id,
            inserted.id,
            now=timestamp,
        ):
            raise MemoryConflictError("target is no longer active")
        return CreateResult(memory=inserted, created=True)


def flag_conflict(
    database: DatabasePath,
    target_id: UUID,
    candidate: MemoryCreate,
    *,
    now: datetime | None = None,
) -> CreateResult:
    candidate_id = _candidate_id(candidate)
    if candidate_id == target_id:
        raise MemoryConflictError("a memory cannot conflict with itself")

    timestamp = as_utc(now or repository.utc_now())
    with write_transaction(database) as connection:
        existing = repository.get_memory_from_connection(connection, candidate_id)
        if existing is not None:
            if (
                existing.state == MemoryState.PENDING_REVIEW
                and existing.conflicts_with_id == target_id
            ):
                return CreateResult(memory=existing, created=False)
            raise MemoryConflictError("candidate identity is already in use")

        target = repository.get_memory_from_connection(connection, target_id)
        if target is None:
            raise MemoryNotFoundError(f"memory {target_id} was not found")
        if target.state != MemoryState.ACTIVE:
            raise MemoryConflictError("only an active memory can receive a conflict candidate")

        inserted = repository.insert_candidate(
            connection,
            candidate,
            state=MemoryState.PENDING_REVIEW,
            now=timestamp,
            conflicts_with_id=target_id,
        )
        return CreateResult(memory=inserted, created=True)


def delete_memory(
    database: DatabasePath,
    memory_id: UUID,
    *,
    now: datetime | None = None,
) -> MemoryRecord:
    timestamp = as_utc(now or repository.utc_now())
    with write_transaction(database) as connection:
        memory = repository.get_memory_from_connection(connection, memory_id)
        if memory is None:
            raise MemoryNotFoundError(f"memory {memory_id} was not found")
        if memory.state == MemoryState.DELETED:
            return memory
        return repository.erase_memory_content(connection, memory_id, now=timestamp)


def inspect_memory(database: DatabasePath, memory_id: UUID) -> MemoryInspection:
    with read_connection(database) as connection:
        root = repository.get_memory_from_connection(connection, memory_id)
        if root is None:
            raise MemoryNotFoundError(f"memory {memory_id} was not found")

        visited: set[UUID] = set()
        queue: deque[UUID] = deque([memory_id])
        records: list[MemoryRecord] = []
        while queue:
            current_id = queue.popleft()
            if current_id in visited:
                continue
            visited.add(current_id)
            current = repository.get_memory_from_connection(connection, current_id)
            if current is None:
                continue
            records.append(current)
            queue.extend(repository.related_memory_ids(connection, current_id) - visited)

    records.sort(key=lambda memory: (memory.source_occurred_at, str(memory.id)))
    return MemoryInspection(memory=root, history=records)
