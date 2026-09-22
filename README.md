# Memory Ledger

Memory Ledger is a deterministic long-term memory engine that preserves provenance and history, handles corrections and uncertain contradictions conservatively, supports content-erasing deletion, and retrieves only currently active facts with fully explainable scoring.

It is intentionally small: structured fact candidates, SQLite, a FastAPI transport, and no model, embedding service, or paid dependency.

## Quick start

Requirements: Python 3.12 and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync --locked
uv run pytest
uv run memory-ledger benchmark
uv run memory-ledger serve
```

The API is available at `http://127.0.0.1:8000`; interactive OpenAPI documentation is at `http://127.0.0.1:8000/docs`.

## Memory contract

Every memory has:

- A stable UUIDv5 identity.
- An atomic string fact: `key`, `value`, display `text`, and string `tags`.
- Source message ID, optional conversation ID, original excerpt, SHA-256 source digest, and required occurrence time.
- Creation, update, and optional deletion times.
- An explicit lifecycle state.
- Correction or conflict relationships where applicable.

A memory is a durable user fact or preference that is useful in a later conversation. Extraction from free-form text is deliberately out of scope; callers submit structured candidates so storage and lifecycle behavior remain deterministic.

### Identity and duplicates

Identity is derived only from immutable provenance and fact content:

```text
UUIDv5(
  fixed namespace,
  canonical(source_message_id) + "\n" + canonical(key) + "\n" + canonical(value)
)
```

Canonicalization applies Unicode NFKC normalization, case-folding, trimming, and whitespace collapsing. Replaying the same source, key, and value returns the original memory without mutating its text, tags, excerpt, timestamps, or lifecycle. A deleted identity remains a tombstone and cannot silently reappear.

### Lifecycle

```text
active         → superseded | deleted
pending_review → deleted
superseded     → deleted
deleted        → terminal
```

An explicit correction creates a newly sourced active memory and atomically marks the old memory as superseded:

```text
Pune #1 (superseded) → Mumbai (superseded) → Pune #2 (active)
```

The two Pune memories have different identities because they represent assertions from different source messages at different points in time. Deleting Pune #2 would not reactivate either historical fact.

An uncertain contradiction creates a `pending_review` memory linked to the active fact. It does not change current truth and is excluded from normal retrieval.

Correction uses `BEGIN IMMEDIATE`, validates state after acquiring SQLite's write lock, inserts the replacement, performs a guarded state update, links both records, and commits. Competing corrections serialize: one wins and the other receives a domain conflict. Exact retries are idempotent.

### Deletion

Deletion clears `key`, `value`, `text`, `tags`, and the source excerpt. It retains the stable ID, relationship graph, timestamps, source identifiers, and a cryptographic source digest used for provenance and integrity checks.

This is application-level content erasure for the exercise. It is not a claim of cryptographic erasure or GDPR compliance; low-entropy source text could potentially be guessed and re-hashed.

## Deterministic retrieval

Queries and fields are normalized using:

```text
NFKC → casefold → punctuation/underscore/separators to spaces
→ collapse whitespace → split → remove stopwords → unique token set
```

Scores are intersections of token sets:

| Field | Points per matched token |
| --- | ---: |
| key | 4 |
| tags | 3 |
| value | 2 |
| text | 1 |

Repeated words never increase a score. Evidence is returned in `key → tags → value → text` order with tokens sorted inside each field. Results contain only active memories with positive scores and are ordered by descending score, then UUID. The default limit is 5 and the maximum is 20.

This deliberately favors reproducibility and inspectability over semantic recall. Embeddings could later generate candidates, but lifecycle filtering and final evidence should remain independently testable.

## API walkthrough

Store a memory:

```bash
curl -X POST http://127.0.0.1:8000/v1/memories \
  -H "content-type: application/json" \
  -d '{
    "source": {
      "message_id": "message-001",
      "conversation_id": "demo",
      "excerpt": "I live in Pune.",
      "occurred_at": "2026-01-01T09:00:00Z"
    },
    "fact": {
      "key": "location.current_city",
      "value": "Pune",
      "text": "User currently lives in Pune",
      "tags": ["city", "home", "live", "location"]
    }
  }'
```

Use the returned memory ID to inspect its provenance and connected history:

```bash
curl http://127.0.0.1:8000/v1/memories/MEMORY_ID
```

Correct it with a new sourced assertion:

```bash
curl -X POST http://127.0.0.1:8000/v1/memories/MEMORY_ID/corrections \
  -H "content-type: application/json" \
  -d '{
    "source": {
      "message_id": "message-002",
      "conversation_id": "demo",
      "excerpt": "I moved to Mumbai.",
      "occurred_at": "2026-02-01T09:00:00Z"
    },
    "fact": {
      "key": "location.current_city",
      "value": "Mumbai",
      "text": "User currently lives in Mumbai",
      "tags": ["city", "home", "live", "location"]
    }
  }'
```

Retrieve current context with evidence:

```bash
curl -X POST http://127.0.0.1:8000/v1/retrievals \
  -H "content-type: application/json" \
  -d '{"query":"What is my current home city?","limit":5}'
```

Create an uncertain candidate with `POST /v1/memories/{id}/conflicts`, and erase a memory with `DELETE /v1/memories/{id}`. Both operations are also available in the OpenAPI interface.

## Verification benchmark

```bash
uv run memory-ledger benchmark
```

The version-controlled fixture contains:

- 32 resulting memory rows across multiple topics.
- Five correction chains.
- Two ambiguous conflict candidates.
- One content-erased tombstone.
- 20 fixed retrieval queries with expected inclusions and exclusions.

The command creates an isolated temporary database, prints every query result, reports an overall pass count, and exits nonzero if an inclusion is missing, an exclusion appears, a non-active memory is returned, or the fixture count changes. Tests run the benchmark twice and compare structured results for semantic determinism.

## Project structure

```text
src/memory_ledger/
├── models.py          # contracts, identity, and domain errors
├── database.py        # SQLite connection and transaction helpers
├── repository.py      # persistence
├── reconciliation.py  # lifecycle rules and history traversal
├── retrieval.py       # deterministic scoring and evidence
├── api.py             # HTTP transport
├── benchmark.py       # fixed evaluation runner
└── cli.py             # serve and benchmark entry points
```

The API is intentionally boring: validation, one domain call, and serialization. Lifecycle correctness is tested below the HTTP layer.

## Production considerations

Sensitive or high-risk memories would need explicit collection policy, user consent, encryption at rest, tenant isolation, authorization, retention controls, redacted logs, audit trails, and a genuine purge workflow. Inferred sensitive attributes should not be stored automatically.

At larger volume, active-state and tenant indexes would come first. SQLite lexical scanning could then be replaced by FTS or an external candidate index. A semantic retriever could improve recall, but the relational lifecycle store would remain authoritative and would filter superseded, pending, and deleted records before context is returned.

Current limitations are intentional: single-user storage, atomic string values, exact lexical matching, one direct successor per correction, no pending-candidate approval workflow, and no authentication or model-based extraction.

## Development

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv run memory-ledger benchmark
```

The tests cover stable identity, immutable duplicates, provenance, atomic correction and rollback, concurrent corrections, uncertain conflicts, tombstone deletion, history traversal, active-only retrieval, score evidence, HTTP behavior, and benchmark failure modes.
