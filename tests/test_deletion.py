from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from memory_ledger.models import MemoryCreate, MemoryState
from memory_ledger.reconciliation import correct_memory, delete_memory
from memory_ledger.repository import create_memory, get_memory


def test_deletion_erases_content_and_preserves_tombstone_identity(
    database_path: Path,
    candidate_factory: Callable[..., MemoryCreate],
) -> None:
    candidate = candidate_factory()
    stored = create_memory(database_path, candidate).memory
    original_hash = stored.source_hash

    deleted = delete_memory(
        database_path,
        stored.id,
        now=datetime(2026, 5, 1, tzinfo=UTC),
    )
    retry = delete_memory(database_path, stored.id)
    duplicate = create_memory(database_path, candidate)

    assert deleted.id == stored.id
    assert deleted.state == MemoryState.DELETED
    assert deleted.key is None
    assert deleted.value is None
    assert deleted.text is None
    assert deleted.tags is None
    assert deleted.source_excerpt is None
    assert deleted.source_hash == original_hash
    assert deleted.deleted_at == datetime(2026, 5, 1, tzinfo=UTC)
    assert retry == deleted
    assert duplicate.created is False
    assert duplicate.memory == deleted


def test_deleting_current_memory_does_not_reactivate_history(
    database_path: Path,
    candidate_factory: Callable[..., MemoryCreate],
) -> None:
    pune = create_memory(database_path, candidate_factory()).memory
    mumbai = correct_memory(
        database_path,
        pune.id,
        candidate_factory(message_id="message-002", value="Mumbai"),
    ).memory

    delete_memory(database_path, mumbai.id)

    assert get_memory(database_path, pune.id).state == MemoryState.SUPERSEDED
    assert get_memory(database_path, mumbai.id).state == MemoryState.DELETED
