# Product Engineering Challenge Submission

## Candidate

- **Name:** Aditya Kumar Singh
- **Email:** adityasinghstuff@gmail.com
- **GitHub:** https://github.com/adityaonrepeat
- **LinkedIn:** https://linkedin.com/in/adityaonrepeat
- **Resume:** [RESUME.pdf](RESUME.pdf)
- **Portfolio:** https://adityaonrepeat.vercel.app
- **Selected problem:** Problem 4 — Trustworthy long-term memory
- **Demo video:** PENDING — add the public 3–5 minute video URL before submission

## Run the project

Prerequisites: Python 3.12 and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/adityaonrepeat/product-engineer-ps.git
cd product-engineer-ps
uv sync --locked
uv run memory-ledger serve
```

The API is available at `http://127.0.0.1:8000`, and its interactive OpenAPI documentation is at `http://127.0.0.1:8000/docs`. No environment variables or paid external services are required.

For the successful scenario, use the OpenAPI interface to store a sourced memory, inspect it, correct it with a later sourced assertion, inspect the linked history, and retrieve current context. The exact request bodies are also provided in the root `README.md`.

For a conservative failure/recovery scenario, create an uncertain conflict with `POST /v1/memories/{id}/conflicts`. The candidate is retained as `pending_review`, the active memory remains current, and normal retrieval excludes the pending candidate. Transaction rollback and concurrent correction behavior can be reproduced with:

```bash
uv run pytest tests/test_reconciliation.py::test_failed_guard_rolls_back_insert_and_target_change -vv
uv run pytest tests/test_reconciliation.py::test_concurrent_corrections_have_one_winner -vv
```

## Run the tests

```bash
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

The submitted suite contains 24 deterministic tests covering storage, provenance, immutable retries, lifecycle transitions, rollback, contention, deletion, retrieval evidence, HTTP behavior, and benchmark failure detection.

## Acceptance scenarios and verification

- **AC1 — Store with provenance:** Completed. UUIDv5 provides stable identity; source message, conversation, excerpt, occurrence time, and source digest are inspectable.
- **AC2 — Relevant retrieval:** Completed. Retrieval is bounded, active-only, deterministic, and returns field-level matched-token evidence with its score.
- **AC3 — Explicit correction:** Completed. A new sourced memory becomes active while the previous fact becomes visibly `superseded`; normal retrieval excludes the old fact.
- **AC4 — Uncertain contradiction:** Completed. Ambiguous candidates become `pending_review` without replacing or destroying current truth.
- **AC5 — Deletion:** Completed. Content fields are erased, a relationship-preserving tombstone remains, and the memory cannot appear in current retrieval.
- **AC6 — Stable evaluation:** Completed. The fixed fixture and query expectations are version-controlled and run without a model or paid service.

Run the problem-specific verification benchmark with:

```bash
uv run memory-ledger benchmark
```

Observed on 22 September 2026 using the committed lockfile:

```text
Overall: 20/20 queries passed; 32/32 memories loaded
```

The fixture includes 32 resulting memory rows across multiple topics, five correction chains, two ambiguous conflict candidates, one content-erased tombstone, and 20 queries with expected inclusions and exclusions. Each query reports returned IDs, missing expectations, forbidden results, and invalid lifecycle states. The command exits nonzero for a missing required result, a forbidden result, a non-active result, or an unexpected fixture count.

The demo's failure/recovery scenario uses an uncertain contradiction: the candidate is preserved for review while the existing active fact remains authoritative. Reviewers can reproduce it through the `/conflicts` endpoint or `test_uncertain_conflict_preserves_current_truth`.

## Architecture and data flow

```text
HTTP / CLI
    |
    v
Pydantic contracts and deterministic UUID identity
    |
    v
Reconciliation service ----> Retrieval scorer
    |                             |
    v                             v
Repository ----------------> active-only results + evidence
    |
    v
SQLite lifecycle source of truth
```

- `models.py` defines contracts, lifecycle states, identity, normalization, and domain errors.
- `database.py` owns SQLite connections, WAL configuration, busy timeout, and transaction boundaries.
- `repository.py` contains persistence and row-mapping primitives.
- `reconciliation.py` implements correction, conservative conflict handling, deletion, and connected history.
- `retrieval.py` performs deterministic tokenization, scoring, filtering, evidence generation, and tie-breaking.
- `api.py` is a thin HTTP transport; `cli.py` exposes serving and benchmark commands.
- `benchmark.py` loads an isolated fixture and evaluates semantic expectations.

Structured candidates enter through the transport, receive a provenance-derived stable identity, and are persisted transactionally. Explicit corrections create a new active row and supersede the previous row atomically. Ambiguous candidates remain pending. Deletion clears content while retaining a tombstone and relationship graph. Retrieval reads only active rows and returns observable field-level evidence.

## Technology choices

- **Python 3.12:** concise domain code and a strong testing ecosystem.
- **FastAPI and Pydantic:** explicit request/response contracts, validation, and an immediately usable OpenAPI demo surface.
- **SQLite:** transactional lifecycle correctness with no external setup; WAL, busy timeout, and `BEGIN IMMEDIATE` make concurrency behavior explicit.
- **pytest:** deterministic domain, transport, contention, rollback, and benchmark tests.
- **`uv`:** fast, reproducible installation through a committed lockfile.

SQLite was chosen over PostgreSQL to keep reviewer setup under ten minutes and make the benchmark fully isolated. Exact lexical retrieval was chosen over embeddings because the challenge prioritizes inspectability and determinism. At production scale, PostgreSQL plus an FTS/vector candidate index would improve concurrency and recall while the relational lifecycle store remained authoritative.

## Important decisions

1. **Identity represents an assertion event, not only its current value.** UUIDv5 is derived from canonical source identity and fact content. Replaying the same assertion is idempotent, while moving back to a prior city creates a new historical event rather than reviving an old row.
2. **Explicit corrections and uncertain contradictions are different operations.** Explicit correction atomically supersedes current truth. Ambiguity creates a linked `pending_review` candidate and preserves the active fact.
3. **Lifecycle filtering is authoritative and independent of relevance.** Retrieval candidates must be active before scoring. This prevents superseded, pending, or deleted content from leaking into context even if a future semantic retriever ranks it highly.

Deletion performs application-level content erasure: key, value, display text, tags, and source excerpt are cleared, while stable identity, source identifiers, relationships, timestamps, and a source digest remain for integrity and history. This is deliberately not described as cryptographic erasure or complete regulatory compliance.

## Assumptions and limitations

- Callers provide structured fact candidates; free-form model extraction is out of scope.
- The prototype is single-user and has no authentication, authorization, or tenant isolation.
- Facts use atomic string keys and values rather than a general ontology.
- Retrieval is exact lexical matching, so it favors explainability over semantic recall.
- One direct successor is allowed per correction target; competing corrections serialize and one receives a domain conflict.
- Pending candidates can be inspected and deleted, but an approval workflow is deliberately omitted.
- SQLite content erasure does not guarantee removal from backups, pages, logs, or storage media.

## Production and scale

The submitted implementation is a local single-user prototype. For production, the first changes would be tenant-scoped authorization, explicit consent and retention policy, encryption at rest, redacted logs, audited access, and a genuine purge workflow covering replicas and backups. Sensitive or inferred high-risk memories should require stricter collection rules and should not be stored automatically.

At larger volume, I would move the lifecycle store to PostgreSQL, add tenant/state indexes, use optimistic versioning or guarded row locks for transitions, and introduce an outbox for reliable downstream indexing. FTS or a vector service could generate retrieval candidates, but authoritative lifecycle filtering and observable final evidence would remain in the relational layer. Metrics would cover transition conflicts, pending-review age, deletion completion, retrieval latency, excluded-state leaks, and benchmark regressions.

## AI usage

I used OpenAI Codex while implementing and reviewing this challenge. It assisted with code generation, test-case enumeration, documentation structure, and repository verification. I reviewed the resulting domain model and lifecycle rules, inspected every submitted change, and validated the result through 24 deterministic tests, repeated benchmark execution, formatting/lint checks, and manual review of the Git history and committed files. I remain responsible for the submitted design and can explain or modify each component.

## Credibility note

I built [Bloom](https://bloom-net.vercel.app/), a mental-wellness product that matches users into anonymous, emotion-based peer video conversations and also provides an AI therapist, journaling, and mood tracking. The public source is available at [github.com/adityaonrepeat/bloom-v2](https://github.com/adityaonrepeat/bloom-v2).

My contribution included the full-stack application and a separate Socket.IO realtime service, emotion-based matchmaking queues, skip/rematch cooldowns, atomic re-queueing, persisted conversation history, authenticated API routes, Redis-backed rate limiting, and streaming AI responses. The product has served more than 100 users, and the realtime path was load-tested with more than 50 concurrent sockets.

An important decision was separating the realtime service from the Next.js application. That added deployment and operational complexity, but it kept long-lived socket state and matchmaking behavior independent from serverless request lifecycles. Redis-backed coordination provided a path beyond single-process in-memory queues while retaining fast matching and explicit cooldown behavior.

Additional shipped work and project links are available in my [portfolio](https://adityaonrepeat.vercel.app/) and [GitHub profile](https://github.com/adityaonrepeat).
