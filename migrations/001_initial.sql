CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    key TEXT NULL,
    value TEXT NULL,
    text TEXT NULL,
    tags_json TEXT NULL,

    source_message_id TEXT NOT NULL,
    source_conversation_id TEXT NULL,
    source_excerpt TEXT NULL,
    source_hash TEXT NOT NULL,
    source_occurred_at TEXT NOT NULL,

    state TEXT NOT NULL CHECK (
        state IN ('active', 'superseded', 'pending_review', 'deleted')
    ),

    supersedes_id TEXT NULL UNIQUE,
    superseded_by_id TEXT NULL UNIQUE,
    conflicts_with_id TEXT NULL,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NULL,

    FOREIGN KEY (supersedes_id) REFERENCES memories(id),
    FOREIGN KEY (superseded_by_id) REFERENCES memories(id),
    FOREIGN KEY (conflicts_with_id) REFERENCES memories(id)
);

CREATE INDEX IF NOT EXISTS idx_memories_state ON memories(state);
CREATE INDEX IF NOT EXISTS idx_memories_conflicts_with_id
    ON memories(conflicts_with_id);

