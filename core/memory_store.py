"""
Semantic Memory Store — SQLite + FTS5 (BM25 full-text search).

Saves every conversation turn and retrieves relevant past exchanges to inject
as context before each LLM call. No external dependencies beyond sqlite3.

DB location: data/memory.db
"""

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "memory.db"

# Minimum word count to bother searching (avoids flooding results for "bonjour")
_MIN_WORDS_TO_SEARCH = 3


class MemoryStore:
    def __init__(self):
        self._db: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()

    # ── Init ─────────────────────────────────────────────────────────────────

    def initialize(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._create_tables()
        print(f"[MemoryStore] Ready — {DB_PATH}")

    def _create_tables(self):
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT    NOT NULL,
                role      TEXT    NOT NULL,
                content   TEXT    NOT NULL,
                timestamp REAL    NOT NULL
            );

            -- FTS5 virtual table for BM25 full-text search
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
            USING fts5(content, content='memories', content_rowid='id',
                       tokenize='unicode61');

            -- Keep FTS index in sync with the memories table
            CREATE TRIGGER IF NOT EXISTS memories_ai
            AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, content)
                VALUES (new.id, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_ad
            AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content)
                VALUES ('delete', old.id, old.content);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_au
            AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content)
                VALUES ('delete', old.id, old.content);
                INSERT INTO memories_fts(rowid, content)
                VALUES (new.id, new.content);
            END;

            -- Consolidated memories: nightly LLM summaries
            CREATE TABLE IF NOT EXISTS consolidated_memories (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                date       TEXT    NOT NULL UNIQUE,  -- "2026-05-11"
                summary    TEXT    NOT NULL,
                facts      TEXT    NOT NULL DEFAULT '[]',  -- JSON array
                topics     TEXT    NOT NULL DEFAULT '[]',  -- JSON array
                raw_count  INTEGER NOT NULL DEFAULT 0,
                created_at REAL    NOT NULL
            );
        """)
        self._db.commit()

    # ── Write ─────────────────────────────────────────────────────────────────

    def save(self, session_id: str, role: str, content: str):
        """Persist one conversation turn."""
        if not self._db or not content.strip():
            return
        with self._lock:
            self._db.execute(
                "INSERT INTO memories (session_id, role, content, timestamp) "
                "VALUES (?, ?, ?, ?)",
                (session_id, role, content.strip(), datetime.now().timestamp()),
            )
            self._db.commit()

    def delete(self, memory_id: int):
        with self._lock:
            self._db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            self._db.commit()

    def clear_session(self, session_id: str):
        with self._lock:
            self._db.execute(
                "DELETE FROM memories WHERE session_id = ?", (session_id,)
            )
            self._db.commit()

    def clear_all(self):
        with self._lock:
            self._db.execute("DELETE FROM memories")
            self._db.commit()

    # ── Read ──────────────────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 5,
               exclude_session: Optional[str] = None,
               min_words: int = _MIN_WORDS_TO_SEARCH) -> List[dict]:
        """
        BM25 full-text search via FTS5. Returns matching memories ordered by
        relevance. Skips short queries (greetings, single words) unless
        min_words=1 is passed (e.g. for explicit UI searches).
        """
        if not self._db:
            return []

        # Normalise: split on apostrophes/punctuation so "l'espace" → ["l", "espace"]
        import re as _re
        clean = _re.sub(r"[^\w\s]", " ", query.lower())
        words = [w for w in clean.split() if len(w) > 2]
        if len(words) < min_words:
            return []

        # Join as FTS5 OR query so ANY matching term returns results
        # (default AND would require all terms to co-occur in one short message)
        fts_terms = " OR ".join(words)
        if not fts_terms:
            return []

        try:
            params: list = [fts_terms, limit]
            session_filter = ""
            if exclude_session:
                session_filter = "AND m.session_id != ?"
                params.insert(1, exclude_session)

            rows = self._db.execute(f"""
                SELECT m.id, m.session_id, m.role, m.content, m.timestamp,
                       memories_fts.rank AS score
                FROM memories_fts
                JOIN memories m ON m.id = memories_fts.rowid
                WHERE memories_fts MATCH ?
                  {session_filter}
                ORDER BY memories_fts.rank
                LIMIT ?
            """, params).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            print(f"[MemoryStore] Search error: {e}")
            return []

    def recent(self, limit: int = 20, session_id: Optional[str] = None) -> List[dict]:
        """Return most recent memories, optionally filtered by session."""
        if not self._db:
            return []
        if session_id:
            rows = self._db.execute(
                "SELECT * FROM memories WHERE session_id = ? "
                "ORDER BY timestamp DESC LIMIT ?", (session_id, limit)
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM memories ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        if not self._db:
            return {}
        row = self._db.execute(
            "SELECT COUNT(*) as total, COUNT(DISTINCT session_id) as sessions "
            "FROM memories"
        ).fetchone()
        r2 = self._db.execute(
            "SELECT COUNT(*) as consolidated FROM consolidated_memories"
        ).fetchone()
        d = dict(row) if row else {}
        d["consolidated"] = r2["consolidated"] if r2 else 0
        return d

    # ── Consolidated memories ─────────────────────────────────────────────────

    def get_memories_for_date(self, date_str: str) -> List[dict]:
        """Get all raw memories for a given date (YYYY-MM-DD)."""
        if not self._db:
            return []
        start = datetime.strptime(date_str, "%Y-%m-%d").timestamp()
        end = start + 86400
        rows = self._db.execute(
            "SELECT * FROM memories WHERE timestamp >= ? AND timestamp < ? "
            "ORDER BY timestamp ASC",
            (start, end)
        ).fetchall()
        return [dict(r) for r in rows]

    def save_consolidated(self, date_str: str, summary: str,
                          facts: list, topics: list, raw_count: int):
        """Upsert a consolidated memory for a given date."""
        if not self._db:
            return
        import json
        with self._lock:
            self._db.execute("""
                INSERT INTO consolidated_memories
                    (date, summary, facts, topics, raw_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    summary=excluded.summary, facts=excluded.facts,
                    topics=excluded.topics, raw_count=excluded.raw_count,
                    created_at=excluded.created_at
            """, (date_str, summary, json.dumps(facts, ensure_ascii=False),
                  json.dumps(topics, ensure_ascii=False), raw_count,
                  datetime.now().timestamp()))
            self._db.commit()

    def get_consolidated(self, days: int = 7) -> List[dict]:
        """Return the most recent N consolidated memories."""
        if not self._db:
            return []
        import json
        rows = self._db.execute(
            "SELECT * FROM consolidated_memories ORDER BY date DESC LIMIT ?",
            (days,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["facts"] = json.loads(d["facts"])
            d["topics"] = json.loads(d["topics"])
            result.append(d)
        return result

    def already_consolidated(self, date_str: str) -> bool:
        if not self._db:
            return False
        row = self._db.execute(
            "SELECT 1 FROM consolidated_memories WHERE date = ?", (date_str,)
        ).fetchone()
        return row is not None

    # ── Injection helper ──────────────────────────────────────────────────────

    def build_context(self, query: str, current_session_id: Optional[str] = None,
                      limit: int = 3) -> str:
        """
        Build context block from raw BM25 matches of past sessions.
        Consolidated summaries are intentionally excluded: they are too broad
        and the LLM over-weights them, ignoring the current conversation.
        Returns empty string if nothing relevant found.
        """
        # Raw BM25 search (OR semantics — any matching term, past sessions only)
        results = self.search(query, limit=limit, exclude_session=current_session_id)
        if not results:
            return ""

        lines = ["[SOUVENIRS DE CONVERSATIONS PASSÉES — contexte de fond, la conversation ci-dessous a la priorité absolue]"]
        for r in results:
            date = datetime.fromtimestamp(r["timestamp"]).strftime("%d/%m %H:%M")
            role_label = "Toi" if r["role"] == "user" else "ADA"
            snippet = r["content"][:180].replace("\n", " ")
            if len(r["content"]) > 180:
                snippet += "…"
            lines.append(f"• [{date}] {role_label} : {snippet}")
        return "\n".join(lines)


# Global singleton — call memory_store.initialize() once at startup
memory_store = MemoryStore()
