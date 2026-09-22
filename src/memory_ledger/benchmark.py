"""Version-controlled deterministic verification benchmark."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from memory_ledger.database import initialize_database, read_connection
from memory_ledger.models import MemoryCreate, MemoryState, RetrievalRequest
from memory_ledger.reconciliation import correct_memory, delete_memory, flag_conflict
from memory_ledger.repository import create_memory
from memory_ledger.retrieval import retrieve_memories

DEFAULT_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures"


@dataclass(frozen=True)
class BenchmarkQueryResult:
    query_id: str
    passed: bool
    returned: tuple[str, ...]
    missing: tuple[str, ...]
    forbidden: tuple[str, ...]
    invalid_states: tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkResult:
    query_results: tuple[BenchmarkQueryResult, ...]
    memory_count: int
    expected_memory_count: int

    @property
    def pass_count(self) -> int:
        return sum(result.passed for result in self.query_results)

    @property
    def query_count(self) -> int:
        return len(self.query_results)

    @property
    def passed(self) -> bool:
        return self.memory_count == self.expected_memory_count and all(
            result.passed for result in self.query_results
        )


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def _fixture_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def run_benchmark(fixture_dir: Path = DEFAULT_FIXTURE_DIR) -> BenchmarkResult:
    memory_fixture = _load_json(fixture_dir / "memories.json")
    query_fixture = _load_json(fixture_dir / "queries.json")

    with TemporaryDirectory(prefix="memory-ledger-benchmark-") as temp_directory:
        database = Path(temp_directory) / "benchmark.db"
        initialize_database(database)
        aliases: dict[str, UUID] = {}

        for raw_event in memory_fixture["events"]:
            event = dict(raw_event)
            alias = str(event["alias"])
            operation = str(event["operation"])
            candidate = MemoryCreate.model_validate(
                {"source": event["source"], "fact": event["fact"]}
            )
            recorded_at = _fixture_datetime(str(event["recorded_at"]))

            if operation == "store":
                result = create_memory(database, candidate, now=recorded_at)
            elif operation == "correct":
                result = correct_memory(
                    database,
                    aliases[str(event["target"])],
                    candidate,
                    now=recorded_at,
                )
            elif operation == "conflict":
                result = flag_conflict(
                    database,
                    aliases[str(event["target"])],
                    candidate,
                    now=recorded_at,
                )
            else:
                raise ValueError(f"unsupported fixture operation: {operation}")
            aliases[alias] = result.memory.id

        for raw_deletion in memory_fixture.get("deletions", []):
            deletion = dict(raw_deletion)
            delete_memory(
                database,
                aliases[str(deletion["target"])],
                now=_fixture_datetime(str(deletion["recorded_at"])),
            )

        with read_connection(database) as connection:
            memory_count = int(connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0])

        aliases_by_id = {memory_id: alias for alias, memory_id in aliases.items()}
        query_results: list[BenchmarkQueryResult] = []
        for raw_query in query_fixture["queries"]:
            query = dict(raw_query)
            response = retrieve_memories(
                database,
                RetrievalRequest(query=str(query["query"]), limit=int(query.get("limit", 5))),
            )
            returned = tuple(
                aliases_by_id.get(item.memory.id, str(item.memory.id)) for item in response.results
            )
            returned_set = set(returned)
            expected_inclusions = {str(alias) for alias in query.get("include", [])}
            expected_exclusions = {str(alias) for alias in query.get("exclude", [])}
            missing = tuple(sorted(expected_inclusions - returned_set))
            forbidden = tuple(sorted(expected_exclusions & returned_set))
            invalid_states = tuple(
                sorted(
                    aliases_by_id.get(item.memory.id, str(item.memory.id))
                    for item in response.results
                    if item.memory.state != MemoryState.ACTIVE
                )
            )
            query_results.append(
                BenchmarkQueryResult(
                    query_id=str(query["id"]),
                    passed=not missing and not forbidden and not invalid_states,
                    returned=returned,
                    missing=missing,
                    forbidden=forbidden,
                    invalid_states=invalid_states,
                )
            )

    return BenchmarkResult(
        query_results=tuple(query_results),
        memory_count=memory_count,
        expected_memory_count=int(memory_fixture["expected_memory_count"]),
    )


def print_benchmark(fixture_dir: Path = DEFAULT_FIXTURE_DIR) -> BenchmarkResult:
    result = run_benchmark(fixture_dir)
    for query in result.query_results:
        label = "PASS" if query.passed else "FAIL"
        print(
            f"{label} {query.query_id}: returned={list(query.returned)} "
            f"missing={list(query.missing)} forbidden={list(query.forbidden)} "
            f"invalid_states={list(query.invalid_states)}"
        )
    print(
        f"Overall: {result.pass_count}/{result.query_count} queries passed; "
        f"{result.memory_count}/{result.expected_memory_count} memories loaded"
    )
    return result
