"""Deterministic set-based lexical retrieval with inspectable evidence."""

from __future__ import annotations

import re
import unicodedata

from memory_ledger.database import DatabasePath
from memory_ledger.models import (
    EvidenceContribution,
    MemoryRecord,
    RetrievalEvidence,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalResult,
)
from memory_ledger.repository import list_active_memories

STOPWORDS = frozenset(
    {
        "a",
        "about",
        "an",
        "and",
        "are",
        "at",
        "did",
        "do",
        "does",
        "for",
        "how",
        "i",
        "in",
        "is",
        "me",
        "my",
        "of",
        "on",
        "or",
        "please",
        "tell",
        "the",
        "to",
        "was",
        "were",
        "what",
        "when",
        "where",
        "who",
        "you",
        "your",
    }
)

FIELD_WEIGHTS = (("key", 4), ("tags", 3), ("value", 2), ("text", 1))
_WHITESPACE = re.compile(r"\s+")


def tokenize(value: str) -> set[str]:
    """Normalize text into unique tokens without stemming or fuzzy matching."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    separated = "".join(
        " " if character == "_" or unicodedata.category(character)[0] in {"P", "Z"} else character
        for character in normalized
    )
    collapsed = _WHITESPACE.sub(" ", separated).strip()
    if not collapsed:
        return set()
    return {token for token in collapsed.split(" ") if token and token not in STOPWORDS}


def _field_value(memory: MemoryRecord, field: str) -> str:
    if field == "tags":
        return " ".join(memory.tags or [])
    value = getattr(memory, field)
    return value or ""


def score_memory(memory: MemoryRecord, query_tokens: set[str]) -> RetrievalEvidence:
    contributions: list[EvidenceContribution] = []
    matched_tokens: set[str] = set()

    for field, weight in FIELD_WEIGHTS:
        matches = query_tokens & tokenize(_field_value(memory, field))
        matched_tokens.update(matches)
        contributions.extend(
            EvidenceContribution(field=field, token=token, weight=weight)
            for token in sorted(matches)
        )

    return RetrievalEvidence(
        query_tokens=sorted(query_tokens),
        matched_tokens=sorted(matched_tokens),
        contributions=contributions,
        score=sum(contribution.weight for contribution in contributions),
    )


def retrieve_memories(database: DatabasePath, request: RetrievalRequest) -> RetrievalResponse:
    query_tokens = tokenize(request.query)
    ranked: list[RetrievalResult] = []
    for memory in list_active_memories(database):
        evidence = score_memory(memory, query_tokens)
        if evidence.score > 0:
            ranked.append(RetrievalResult(memory=memory, evidence=evidence))

    ranked.sort(key=lambda result: (-result.evidence.score, str(result.memory.id)))
    return RetrievalResponse(
        query=request.query,
        limit=request.limit,
        results=ranked[: request.limit],
    )
