"""
core/documents/documents_db.py
Schéma SQLite + FTS5 pour la base documentaire RAG locale d'ADA Web.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

_DB_PATH: Path | None = None


def _get_db_path() -> Path:
    global _DB_PATH
    if _DB_PATH:
        return _DB_PATH
    from core.settings_store import settings
    custom = (settings.get("documents.index_path") or "").strip()
    if custom:
        p = Path(custom)
        p.parent.mkdir(parents=True, exist_ok=True)
        _DB_PATH = p
    else:
        data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        _DB_PATH = data_dir / "documents.db"
    return _DB_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_get_db_path()), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Crée les tables, la table virtuelle FTS5 et les triggers si nécessaires."""
    conn = get_connection()
    with conn:
        conn.executescript("""
CREATE TABLE IF NOT EXISTS documents (
    id              TEXT PRIMARY KEY,
    path            TEXT NOT NULL UNIQUE,
    rel_path        TEXT NOT NULL,
    title           TEXT NOT NULL,
    hash            TEXT NOT NULL,
    size_bytes      INTEGER NOT NULL DEFAULT 0,
    mtime           REAL NOT NULL DEFAULT 0,
    extension       TEXT NOT NULL DEFAULT '.md',
    tags            TEXT NOT NULL DEFAULT '[]',
    frontmatter     TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id              TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    heading         TEXT NOT NULL DEFAULT '',
    content         TEXT NOT NULL,
    token_estimate  INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts USING fts5(
    id UNINDEXED,
    document_id UNINDEXED,
    heading,
    content,
    tokenize = "unicode61"
);

CREATE TABLE IF NOT EXISTS document_index_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    level       TEXT NOT NULL,
    message     TEXT NOT NULL,
    path        TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_documents_path     ON documents(path);
CREATE INDEX IF NOT EXISTS idx_documents_rel_path ON documents(rel_path);
CREATE INDEX IF NOT EXISTS idx_chunks_document    ON document_chunks(document_id);

CREATE TRIGGER IF NOT EXISTS document_chunks_ai AFTER INSERT ON document_chunks BEGIN
    INSERT INTO document_chunks_fts(id, document_id, heading, content)
    VALUES (new.id, new.document_id, new.heading, new.content);
END;

CREATE TRIGGER IF NOT EXISTS document_chunks_au AFTER UPDATE ON document_chunks BEGIN
    DELETE FROM document_chunks_fts WHERE id = old.id;
    INSERT INTO document_chunks_fts(id, document_id, heading, content)
    VALUES (new.id, new.document_id, new.heading, new.content);
END;

CREATE TRIGGER IF NOT EXISTS document_chunks_ad AFTER DELETE ON document_chunks BEGIN
    DELETE FROM document_chunks_fts WHERE id = old.id;
END;
        """)
    conn.close()
    print("[Documents] ✓ Base documentaire initialisée")


def _log(conn: sqlite3.Connection, level: str, message: str, path: str | None = None) -> None:
    conn.execute(
        "INSERT INTO document_index_log(level, message, path) VALUES (?,?,?)",
        (level, message, path),
    )
