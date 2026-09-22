from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from memory_ledger import repository
from memory_ledger.models import (
    MemoryConflictError,
    MemoryCreate,
    MemoryState,
)
from memory_ledger.reconciliation import correct_memory, flag_conflict, inspect_memory
from memory_ledger.repository import create_memory, get_memory


def test_explicit_correction_links_both_memories(
    database_path: Path,
    candidate_factory: Callable[..., MemoryCreate],
) -> None:
    pune = create_memory(database_path, candidate_factory()).memory
    mumbai_candidate = candidate_factory(
        message_id="message-002",
        value="Mumbai",
        text="User currently lives in Mumbai",
        excerpt="I moved to Mumbai.",
        occurred_at=datetime(2026, 2, 1, tzinfo=UTC),
    )

    result = correct_memory(database_path, pune.id, mumbai_candidate)
    old = get_memory(database_path, pune.id)

    assert result.created is True
    assert result.memory.state == MemoryState.ACTIVE
    assert result.memory.supersedes_id == pune.id
    assert old.state == MemoryState.SUPERSEDED
    assert old.superseded_by_id == result.memory.id


def test_exact_correction_retry_is_idempotent(
    database_path: Path,
    candidate_factory: Callable[..., MemoryCreate],
) -> None:
    pune = create_memory(database_path, candidate_factory()).memory
    replacement = candidate_factory(message_id="message-002", value="Mumbai")

    first = correct_memory(database_path, pune.id, replacement)
    retry = correct_memory(database_path, pune.id, replacement)

    assert first.created is True
    assert retry.created is False
    assert retry.memory == first.memory


def test_self_correction_and_self_conflict_are_rejected(
    database_path: Path,
    candidate_factory: Callable[..., MemoryCreate],
) -> None:
    candidate = candidate_factory()
    stored = create_memory(database_path, candidate).memory

    with pytest.raises(MemoryConflictError, match="correct itself"):
        correct_memory(database_path, stored.id, candidate)
    with pytest.raises(MemoryConflictError, match="conflict with itself"):
        flag_conflict(database_path, stored.id, candidate)


def test_non_active_target_cannot_be_corrected(
    database_path: Path,
    candidate_factory: Callable[..., MemoryCreate],
) -> None:
    pune = create_memory(database_path, candidate_factory()).memory
    correct_memory(
        database_path,
        pune.id,
        candidate_factory(message_id="message-002", value="Mumbai"),
    )

    with pytest.raises(MemoryConflictError, match="only an active memory"):
        correct_memory(
            database_path,
            pune.id,
            candidate_factory(message_id="message-003", value="Delhi"),
        )


def test_uncertain_conflict_preserves_current_truth(
    database_path: Path,
    candidate_factory: Callable[..., MemoryCreate],
) -> None:
    mumbai = create_memory(
        database_path,
        candidate_factory(value="Mumbai", text="User may live in Mumbai"),
    ).memory
    bangalore = candidate_factory(
        message_id="message-002",
        value="Bangalore",
        text="User might be in Bangalore",
        excerpt="I may spend more time in Bangalore next year.",
    )

    result = flag_conflict(database_path, mumbai.id, bangalore)
    retry = flag_conflict(database_path, mumbai.id, bangalore)

    assert get_memory(database_path, mumbai.id).state == MemoryState.ACTIVE
    assert result.memory.state == MemoryState.PENDING_REVIEW
    assert result.memory.conflicts_with_id == mumbai.id
    assert retry.created is False
    assert retry.memory == result.memory


def test_failed_guard_rolls_back_insert_and_target_change(
    database_path: Path,
    candidate_factory: Callable[..., MemoryCreate],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pune = create_memory(database_path, candidate_factory()).memory
    replacement = candidate_factory(message_id="message-002", value="Mumbai")

    monkeypatch.setattr(repository, "mark_memory_superseded", lambda *args, **kwargs: False)

    with pytest.raises(MemoryConflictError, match="no longer active"):
        correct_memory(database_path, pune.id, replacement)

    assert get_memory(database_path, pune.id).state == MemoryState.ACTIVE
    with pytest.raises(repository.MemoryNotFoundError):
        get_memory(
            database_path,
            repository.memory_id_for(
                replacement.source.message_id,
                replacement.fact.key,
                replacement.fact.value,
            ),
        )


def test_moving_back_creates_a_new_event_in_one_history(
    database_path: Path,
    candidate_factory: Callable[..., MemoryCreate],
) -> None:
    pune_one = create_memory(database_path, candidate_factory()).memory
    mumbai = correct_memory(
        database_path,
        pune_one.id,
        candidate_factory(
            message_id="message-002",
            value="Mumbai",
            occurred_at=datetime(2026, 2, 1, tzinfo=UTC),
        ),
    ).memory
    pune_two = correct_memory(
        database_path,
        mumbai.id,
        candidate_factory(
            message_id="message-003",
            value="Pune",
            occurred_at=datetime(2026, 3, 1, tzinfo=UTC),
        ),
    ).memory

    inspection = inspect_memory(database_path, pune_one.id)

    assert pune_one.id != pune_two.id
    assert [memory.id for memory in inspection.history] == [pune_one.id, mumbai.id, pune_two.id]
    assert get_memory(database_path, pune_one.id).state == MemoryState.SUPERSEDED
    assert get_memory(database_path, mumbai.id).state == MemoryState.SUPERSEDED
    assert get_memory(database_path, pune_two.id).state == MemoryState.ACTIVE


def test_concurrent_corrections_have_one_winner(
    database_path: Path,
    candidate_factory: Callable[..., MemoryCreate],
) -> None:
    target = create_memory(database_path, candidate_factory()).memory
    replacements = [
        candidate_factory(message_id="message-002", value="Mumbai"),
        candidate_factory(message_id="message-003", value="Delhi"),
    ]
    barrier = threading.Barrier(3)
    outcomes: queue.Queue[str] = queue.Queue()

    def worker(candidate: MemoryCreate) -> None:
        barrier.wait()
        try:
            correct_memory(database_path, target.id, candidate)
            outcomes.put("created")
        except MemoryConflictError:
            outcomes.put("conflict")

    threads = [threading.Thread(target=worker, args=(candidate,)) for candidate in replacements]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(outcomes.get_nowait() for _ in threads) == ["conflict", "created"]
