"""Public contracts and deterministic identity helpers."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid5

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

MEMORY_NAMESPACE = UUID("5e19ee72-18c7-5df1-a520-15b1d056dd60")
_WHITESPACE = re.compile(r"\s+")


class MemoryLedgerError(Exception):
    """Base class for expected domain failures."""


class MemoryNotFoundError(MemoryLedgerError):
    """Raised when a requested memory does not exist."""


class MemoryConflictError(MemoryLedgerError):
    """Raised when an operation violates a lifecycle invariant."""


class MemoryState(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    PENDING_REVIEW = "pending_review"
    DELETED = "deleted"


def canonical_identity_component(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return _WHITESPACE.sub(" ", normalized)


def memory_id_for(source_message_id: str, key: str, value: str) -> UUID:
    identity = "\n".join(
        canonical_identity_component(part) for part in (source_message_id, key, value)
    )
    return uuid5(MEMORY_NAMESPACE, identity)


def source_digest(excerpt: str) -> str:
    return hashlib.sha256(excerpt.encode("utf-8")).hexdigest()


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone")
    return value.astimezone(UTC)


class SourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str = Field(min_length=1)
    conversation_id: str | None = None
    excerpt: str = Field(min_length=1)
    occurred_at: AwareDatetime

    @field_validator("message_id", "excerpt")
    @classmethod
    def strip_required_strings(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("conversation_id")
    @classmethod
    def strip_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("occurred_at")
    @classmethod
    def normalize_occurred_at(cls, value: datetime) -> datetime:
        return as_utc(value)


class FactInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    value: str = Field(min_length=1)
    text: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)

    @field_validator("key", "value", "text")
    @classmethod
    def strip_fact_strings(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, tags: list[str]) -> list[str]:
        normalized = {tag.strip() for tag in tags if tag.strip()}
        return sorted(normalized, key=lambda tag: (tag.casefold(), tag))


class MemoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: SourceInput
    fact: FactInput


class MemoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    key: str | None
    value: str | None
    text: str | None
    tags: list[str] | None
    source_message_id: str
    source_conversation_id: str | None
    source_excerpt: str | None
    source_hash: str
    source_occurred_at: AwareDatetime
    state: MemoryState
    supersedes_id: UUID | None
    superseded_by_id: UUID | None
    conflicts_with_id: UUID | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    deleted_at: AwareDatetime | None


class CreateResult(BaseModel):
    memory: MemoryRecord
    created: bool
