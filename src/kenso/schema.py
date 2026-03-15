"""SQLite schema DDL with FTS5 full-text search."""

from __future__ import annotations

__all__ = ["get_schema"]


def get_schema() -> list[str]:
    """SQL statements to initialize the kenso schema."""
    return [
        # Main chunks table
        """\
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    title TEXT,
    section_path TEXT,
    content TEXT NOT NULL,
    searchable_content TEXT,
    category TEXT,
    audience TEXT DEFAULT 'all',
    tags TEXT,
    content_hash TEXT,
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (file_path, chunk_index)
)""",
        "CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks (file_path)",
        "CREATE INDEX IF NOT EXISTS idx_chunks_cat ON chunks (category)",
        # FTS5: title (10x), section_path (8x), tags (7x), category (5x), searchable_content (1x)
        """\
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    title,
    section_path,
    tags,
    category,
    searchable_content,
    content='chunks',
    content_rowid='id',
    tokenize='porter unicode61 remove_diacritics 2'
)""",
        # Triggers to keep FTS in sync
        """\
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, title, section_path, tags, category, searchable_content)
    VALUES (new.id, new.title, COALESCE(new.section_path, ''), COALESCE(new.tags, ''), COALESCE(new.category, ''), COALESCE(new.searchable_content, new.content));
END""",
        """\
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, title, section_path, tags, category, searchable_content)
    VALUES ('delete', old.id, old.title, COALESCE(old.section_path, ''), COALESCE(old.tags, ''), COALESCE(old.category, ''), COALESCE(old.searchable_content, old.content));
END""",
        """\
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, title, section_path, tags, category, searchable_content)
    VALUES ('delete', old.id, old.title, COALESCE(old.section_path, ''), COALESCE(old.tags, ''), COALESCE(old.category, ''), COALESCE(old.searchable_content, old.content));
    INSERT INTO chunks_fts(rowid, title, section_path, tags, category, searchable_content)
    VALUES (new.id, new.title, COALESCE(new.section_path, ''), COALESCE(new.tags, ''), COALESCE(new.category, ''), COALESCE(new.searchable_content, new.content));
END""",
        # Links table for relates_to
        """\
CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL,
    target_path TEXT NOT NULL,
    relation_type TEXT NOT NULL DEFAULT 'related',
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (source_path, target_path, relation_type)
)""",
        "CREATE INDEX IF NOT EXISTS idx_links_source ON links (source_path)",
        "CREATE INDEX IF NOT EXISTS idx_links_target ON links (target_path)",
    ]
