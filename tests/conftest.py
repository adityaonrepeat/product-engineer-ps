from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from memory_ledger.database import initialize_database
from memory_ledger.models import FactInput, MemoryCreate, SourceInput


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "memory-ledger.db"
    initialize_database(path)
    return path


@pytest.fixture
def candidate_factory() -> Callable[..., MemoryCreate]:
    def make_candidate(
        *,
        message_id: str = "message-001",
        key: str = "location.current_city",
        value: str = "Pune",
        text: str = "User currently lives in Pune",
        tags: list[str] | None = None,
        excerpt: str = "I live in Pune.",
        occurred_at: datetime = datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
    ) -> MemoryCreate:
        return MemoryCreate(
            source=SourceInput(
                message_id=message_id,
                conversation_id="conversation-001",
                excerpt=excerpt,
                occurred_at=occurred_at,
            ),
            fact=FactInput(
                key=key,
                value=value,
                text=text,
                tags=tags or ["city", "home", "location", "live"],
            ),
        )

    return make_candidate
