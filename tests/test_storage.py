from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from memory_ledger.models import MemoryCreate, MemoryNotFoundError, memory_id_for, source_digest
from memory_ledger.repository import create_memory, get_memory


def test_uuid_is_stable_and_canonical() -> None:
    first = memory_id_for(" Message-1 ", "Location.Current_City", " Pune ")
    second = memory_id_for("message-1", "location.current_city", "pune")

    assert first == second


def test_store_preserves_provenance(
    database_path: Path,
    candidate_factory: Callable[..., MemoryCreate],
) -> None:
    local_time = datetime(2026, 2, 1, 14, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    candidate = candidate_factory(occurred_at=local_time)

    result = create_memory(
        database_path,
        candidate,
        now=datetime(2026, 2, 1, 10, 0, tzinfo=UTC),
    )

    assert result.created is True
    assert result.memory.source_message_id == "message-001"
    assert result.memory.source_conversation_id == "conversation-001"
    assert result.memory.source_excerpt == "I live in Pune."
    assert result.memory.source_hash == source_digest("I live in Pune.")
    assert result.memory.source_occurred_at == datetime(2026, 2, 1, 9, 0, tzinfo=UTC)
    assert result.memory.created_at == datetime(2026, 2, 1, 10, 0, tzinfo=UTC)


def test_duplicate_is_immutable_even_when_non_identity_fields_change(
    database_path: Path,
    candidate_factory: Callable[..., MemoryCreate],
) -> None:
    original = candidate_factory(text="Original text", tags=["original"])
    changed = candidate_factory(
        text="Replacement text that must be ignored",
        tags=["changed"],
        excerpt="A different excerpt that must be ignored",
        occurred_at=datetime(2026, 4, 1, tzinfo=UTC),
    )

    first = create_memory(database_path, original)
    duplicate = create_memory(database_path, changed)

    assert first.created is True
    assert duplicate.created is False
    assert duplicate.memory == first.memory
    assert duplicate.memory.text == "Original text"
    assert duplicate.memory.tags == ["original"]
    assert duplicate.memory.source_excerpt == "I live in Pune."


def test_missing_memory_raises_domain_error(database_path: Path) -> None:
    missing_id = memory_id_for("missing", "profile.name", "Nobody")

    with pytest.raises(MemoryNotFoundError):
        get_memory(database_path, missing_id)
