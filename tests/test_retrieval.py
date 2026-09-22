from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from memory_ledger.models import MemoryCreate, RetrievalRequest
from memory_ledger.reconciliation import correct_memory, delete_memory, flag_conflict
from memory_ledger.repository import create_memory
from memory_ledger.retrieval import retrieve_memories, score_memory, tokenize


def test_tokenization_replaces_separators_and_deduplicates() -> None:
    assert tokenize("  LOCATION.current_city / City—CITY  ") == {
        "location",
        "current",
        "city",
    }


def test_score_is_set_based_and_evidence_order_is_fixed(
    database_path: Path,
    candidate_factory: Callable[..., MemoryCreate],
) -> None:
    memory = create_memory(
        database_path,
        candidate_factory(
            key="location.current_city",
            value="Mumbai",
            text="Current home city is Mumbai",
            tags=["home", "city"],
        ),
    ).memory

    evidence = score_memory(memory, tokenize("current home city city CITY"))

    assert evidence.score == 17
    assert [(item.field, item.token, item.weight) for item in evidence.contributions] == [
        ("key", "city", 4),
        ("key", "current", 4),
        ("tags", "city", 3),
        ("tags", "home", 3),
        ("text", "city", 1),
        ("text", "current", 1),
        ("text", "home", 1),
    ]
    assert evidence.matched_tokens == ["city", "current", "home"]


def test_retrieval_excludes_every_non_active_state(
    database_path: Path,
    candidate_factory: Callable[..., MemoryCreate],
) -> None:
    pune = create_memory(database_path, candidate_factory()).memory
    mumbai = correct_memory(
        database_path,
        pune.id,
        candidate_factory(message_id="message-002", value="Mumbai"),
    ).memory
    flag_conflict(
        database_path,
        mumbai.id,
        candidate_factory(message_id="message-003", value="Bangalore"),
    )
    deleted = create_memory(
        database_path,
        candidate_factory(message_id="message-004", value="Delhi"),
    ).memory
    delete_memory(database_path, deleted.id)

    response = retrieve_memories(
        database_path,
        RetrievalRequest(query="location city home", limit=20),
    )

    assert [result.memory.id for result in response.results] == [mumbai.id]


def test_limit_and_uuid_tie_break_are_deterministic(
    database_path: Path,
    candidate_factory: Callable[..., MemoryCreate],
) -> None:
    memories = [
        create_memory(
            database_path,
            candidate_factory(
                message_id=f"message-{number}",
                key=f"preference.topic_{number}",
                value=f"Value {number}",
                text=f"User likes topic {number}",
                tags=["shared"],
            ),
        ).memory
        for number in range(3)
    ]

    first = retrieve_memories(database_path, RetrievalRequest(query="shared", limit=2))
    second = retrieve_memories(database_path, RetrievalRequest(query="shared", limit=2))

    expected_ids = sorted((memory.id for memory in memories), key=str)[:2]
    assert [result.memory.id for result in first.results] == expected_ids
    assert first == second
