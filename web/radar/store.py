"""web/radar/store.py — SQLiteStore pour les événements Radar."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

_lock = threading.Lock()
_db_path: Path | None = None


def _get_db_path() -> Path:
    global _db_path
    if _db_path is not None:
        return _db_path
    try:
        from config import RADAR_DB_PATH
        _db_path = Path(RADAR_DB_PATH)
    except Exception:
        _db_path = Path("data/radar/events.sqlite")
    return _db_path


def _connect() -> sqlite3.Connection:
    p = _get_db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=5, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    """Crée le schéma si nécessaire."""
    with _lock:
        conn = _connect()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS radar_events (
                    id          TEXT PRIMARY KEY,
                    timestamp   TEXT NOT NULL,
                    level       TEXT NOT NULL,
                    type        TEXT NOT NULL,
                    module      TEXT,
                    message     TEXT,
                    session_id  TEXT,
                    request_id  TEXT,
                    job_id      TEXT,
                    document_id TEXT,
                    user_id     TEXT,
                    duration_ms INTEGER,
                    error_code  TEXT,
                    metadata_json    TEXT,
                    exception_json   TEXT,
                    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_re_timestamp   ON radar_events(timestamp);
                CREATE INDEX IF NOT EXISTS idx_re_level       ON radar_events(level);
                CREATE INDEX IF NOT EXISTS idx_re_type        ON radar_events(type);
                CREATE INDEX IF NOT EXISTS idx_re_request_id  ON radar_events(request_id);
                CREATE INDEX IF NOT EXISTS idx_re_document_id ON radar_events(document_id);
                CREATE INDEX IF NOT EXISTS idx_re_job_id      ON radar_events(job_id);
                CREATE INDEX IF NOT EXISTS idx_re_session_id  ON radar_events(session_id);
            """)
            conn.commit()
        finally:
            conn.close()


def insert_event(evt: dict) -> None:
    """Insère un événement dans la base (sans lever d'exception)."""
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO radar_events
                   (id, timestamp, level, type, module, message,
                    session_id, request_id, job_id, document_id, user_id,
                    duration_ms, error_code, metadata_json, exception_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
                (
                    evt.get("id"),
                    evt.get("timestamp"),
                    evt.get("level", "info"),
                    evt.get("type", "unknown"),
                    evt.get("module"),
                    evt.get("message"),
                    evt.get("session_id"),
                    evt.get("request_id"),
                    evt.get("job_id"),
                    evt.get("document_id"),
                    evt.get("user_id"),
                    evt.get("duration_ms"),
                    evt.get("error_code"),
                    json.dumps(evt.get("metadata") or {}),
                    json.dumps(evt.get("exception_info") or {}),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def query_events(
    level: str | None = None,
    type_: str | None = None,
    module: str | None = None,
    request_id: str | None = None,
    document_id: str | None = None,
    job_id: str | None = None,
    session_id: str | None = None,
    from_ts: str | None = None,
    to_ts: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Retourne des événements filtrés, triés par timestamp desc."""
    conn = _connect()
    try:
        clauses = []
        params: list[Any] = []
        if level:
            clauses.append("level = ?")
            params.append(level)
        if type_:
            clauses.append("type = ?")
            params.append(type_)
        if module:
            clauses.append("module = ?")
            params.append(module)
        if request_id:
            clauses.append("request_id = ?")
            params.append(request_id)
        if document_id:
            clauses.append("document_id = ?")
            params.append(document_id)
        if job_id:
            clauses.append("job_id = ?")
            params.append(job_id)
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if from_ts:
            clauses.append("timestamp >= ?")
            params.append(from_ts)
        if to_ts:
            clauses.append("timestamp <= ?")
            params.append(to_ts)
        if q:
            clauses.append("(message LIKE ? OR metadata_json LIKE ?)")
            params.extend([f"%{q}%", f"%{q}%"])

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.extend([limit, offset])
        rows = conn.execute(
            f"SELECT * FROM radar_events {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_event(event_id: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM radar_events WHERE id = ?", (event_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def timeline(
    field: str,
    value: str,
) -> list[dict]:
    """Timeline par request_id, document_id ou job_id."""
    assert field in ("request_id", "document_id", "job_id", "session_id")
    conn = _connect()
    try:
        rows = conn.execute(
            f"SELECT * FROM radar_events WHERE {field} = ? ORDER BY timestamp ASC",
            (value,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def count_events(level: str | None = None) -> int:
    conn = _connect()
    try:
        if level:
            return conn.execute(
                "SELECT COUNT(*) FROM radar_events WHERE level=?", (level,)
            ).fetchone()[0]
        return conn.execute("SELECT COUNT(*) FROM radar_events").fetchone()[0]
    finally:
        conn.close()


def stats() -> dict:
    conn = _connect()
    try:
        total = conn.execute("SELECT COUNT(*) FROM radar_events").fetchone()[0]
        errors = conn.execute(
            "SELECT COUNT(*) FROM radar_events WHERE level IN ('error','critical')"
        ).fetchone()[0]
        last_row = conn.execute(
            "SELECT timestamp FROM radar_events ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        return {
            "total": total,
            "errors": errors,
            "last_event": last_row[0] if last_row else None,
        }
    finally:
        conn.close()


def purge_old(retention_days: int = 30, max_events: int = 100_000) -> int:
    """Supprime les événements trop anciens ou au-delà du seuil max."""
    with _lock:
        conn = _connect()
        removed = 0
        try:
            # Par ancienneté
            conn.execute(
                "DELETE FROM radar_events WHERE timestamp < datetime('now', ?)",
                (f"-{retention_days} days",),
            )
            # Par volume (on garde les N plus récents)
            conn.execute(
                """DELETE FROM radar_events WHERE id NOT IN (
                    SELECT id FROM radar_events ORDER BY timestamp DESC LIMIT ?
                )""",
                (max_events,),
            )
            removed = conn.total_changes
            conn.commit()
        finally:
            conn.close()
        return removed


def query_events_after(after_ts: str, limit: int = 100) -> list[dict]:
    """Retourne les événements dont le timestamp est strictement > after_ts, triés ASC."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM radar_events WHERE timestamp > ? ORDER BY timestamp ASC LIMIT ?",
            (after_ts, limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def latest_timestamp() -> str:
    """Retourne le timestamp du dernier événement (ou epoch si vide)."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT timestamp FROM radar_events ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else "1970-01-01T00:00:00.000Z"
    finally:
        conn.close()


def export_ndjson(
    limit: int = 10_000,
    level: str | None = None,
) -> str:
    """Retourne les événements au format NDJSON."""
    rows = query_events(level=level, limit=limit, offset=0)
    lines = []
    for r in rows:
        lines.append(json.dumps(r, ensure_ascii=False))
    return "\n".join(lines)


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key in ("metadata_json", "exception_json"):
        raw = d.pop(key, None)
        short_key = key.replace("_json", "")
        try:
            d[short_key] = json.loads(raw) if raw else {}
        except Exception:
            d[short_key] = {}
    return d
