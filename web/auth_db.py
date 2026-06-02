"""
ADA Auth — couche SQLite : users, devices, QR sessions, recovery codes.
DB : data/auth.db (fichier séparé des autres BDs du projet).
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional

_DB_PATH = Path(__file__).parent.parent / "data" / "auth.db"


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def initialize() -> None:
    """Crée les tables si elles n'existent pas."""
    conn = _connect()
    with conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id           TEXT PRIMARY KEY,
            username     TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            created_at   REAL NOT NULL,
            is_active    INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS user_groups (
            user_id    TEXT NOT NULL,
            group_name TEXT NOT NULL,
            PRIMARY KEY (user_id, group_name),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS devices (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            device_name TEXT NOT NULL,
            created_at  REAL NOT NULL,
            last_seen   REAL,
            is_active   INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS pending_qr (
            code           TEXT PRIMARY KEY,
            session_token  TEXT UNIQUE NOT NULL,
            type           TEXT NOT NULL DEFAULT 'qr',
            target_user_id TEXT,
            device_name    TEXT NOT NULL DEFAULT 'Nouvel appareil',
            created_at     REAL NOT NULL,
            expires_at     REAL NOT NULL,
            confirmed_at   REAL,
            jwt            TEXT
        );

        CREATE TABLE IF NOT EXISTS recovery_codes (
            id         TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL,
            code_hash  TEXT NOT NULL,
            salt       TEXT NOT NULL,
            created_at REAL NOT NULL,
            used_at    REAL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)
    conn.close()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _user_with_groups(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    user_id = row["id"]
    groups = [
        r[0] for r in conn.execute(
            "SELECT group_name FROM user_groups WHERE user_id = ?", (user_id,)
        ).fetchall()
    ]
    return {**dict(row), "groups": groups}


# ── Users ─────────────────────────────────────────────────────────────────────

def count_users() -> int:
    conn = _connect()
    n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return n


def create_user(username: str, display_name: str, groups: list[str]) -> dict:
    user_id = str(uuid.uuid4())
    now = time.time()
    conn = _connect()
    with conn:
        conn.execute(
            "INSERT INTO users (id, username, display_name, created_at) VALUES (?, ?, ?, ?)",
            (user_id, username, display_name, now),
        )
        for g in groups:
            conn.execute(
                "INSERT INTO user_groups (user_id, group_name) VALUES (?, ?)",
                (user_id, g),
            )
    conn.close()
    return {"id": user_id, "username": username, "display_name": display_name, "groups": groups}


def get_user(user_id: str) -> Optional[dict]:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,)
    ).fetchone()
    result = _user_with_groups(conn, row) if row else None
    conn.close()
    return result


def get_user_by_username(username: str) -> Optional[dict]:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)
    ).fetchone()
    result = _user_with_groups(conn, row) if row else None
    conn.close()
    return result


def list_users() -> list[dict]:
    conn = _connect()
    rows = conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()
    result = []
    for row in rows:
        d = _user_with_groups(conn, row)
        d["device_count"] = conn.execute(
            "SELECT COUNT(*) FROM devices WHERE user_id = ? AND is_active = 1", (row["id"],)
        ).fetchone()[0]
        result.append(d)
    conn.close()
    return result


def update_user_groups(user_id: str, groups: list[str]) -> None:
    conn = _connect()
    with conn:
        conn.execute("DELETE FROM user_groups WHERE user_id = ?", (user_id,))
        for g in groups:
            conn.execute(
                "INSERT INTO user_groups (user_id, group_name) VALUES (?, ?)", (user_id, g)
            )
    conn.close()


def deactivate_user(user_id: str) -> None:
    conn = _connect()
    with conn:
        conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
        conn.execute("UPDATE devices SET is_active = 0 WHERE user_id = ?", (user_id,))
    conn.close()


# ── Devices ───────────────────────────────────────────────────────────────────

def register_device(user_id: str, device_name: str) -> str:
    device_id = str(uuid.uuid4())
    conn = _connect()
    with conn:
        conn.execute(
            "INSERT INTO devices (id, user_id, device_name, created_at) VALUES (?, ?, ?, ?)",
            (device_id, user_id, device_name, time.time()),
        )
    conn.close()
    return device_id


def touch_device(device_id: str) -> None:
    conn = _connect()
    with conn:
        conn.execute(
            "UPDATE devices SET last_seen = ? WHERE id = ?", (time.time(), device_id)
        )
    conn.close()


def is_device_active(device_id: str) -> bool:
    conn = _connect()
    row = conn.execute(
        "SELECT is_active FROM devices WHERE id = ?", (device_id,)
    ).fetchone()
    conn.close()
    return bool(row and row[0])


def list_devices(user_id: str) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM devices WHERE user_id = ? ORDER BY created_at", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def deactivate_device(device_id: str) -> None:
    conn = _connect()
    with conn:
        conn.execute("UPDATE devices SET is_active = 0 WHERE id = ?", (device_id,))
    conn.close()


# ── Pending QR ────────────────────────────────────────────────────────────────

def create_pending_qr(
    qr_type: str = "qr",
    target_user_id: Optional[str] = None,
    device_name: str = "Nouvel appareil",
    ttl: int = 300,
) -> dict:
    code = secrets.token_urlsafe(32)
    session_token = secrets.token_urlsafe(32)
    now = time.time()
    conn = _connect()
    with conn:
        conn.execute(
            "INSERT INTO pending_qr "
            "(code, session_token, type, target_user_id, device_name, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (code, session_token, qr_type, target_user_id, device_name, now, now + ttl),
        )
    conn.close()
    return {"code": code, "session_token": session_token, "expires_at": now + ttl}


def get_pending_qr_by_code(code: str) -> Optional[dict]:
    conn = _connect()
    row = conn.execute("SELECT * FROM pending_qr WHERE code = ?", (code,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_pending_qr_by_session(session_token: str) -> Optional[dict]:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM pending_qr WHERE session_token = ?", (session_token,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def confirm_pending_qr(code: str, jwt_token: str) -> None:
    conn = _connect()
    with conn:
        conn.execute(
            "UPDATE pending_qr SET confirmed_at = ?, jwt = ? WHERE code = ?",
            (time.time(), jwt_token, code),
        )
    conn.close()


def cleanup_expired_qr() -> None:
    conn = _connect()
    with conn:
        conn.execute("DELETE FROM pending_qr WHERE expires_at < ?", (time.time(),))
    conn.close()


# ── Recovery codes ────────────────────────────────────────────────────────────

def _hash_code(code: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", code.encode(), salt.encode(), 100_000).hex()


def create_recovery_codes(user_id: str, count: int = 8) -> list[str]:
    codes = [secrets.token_hex(4).upper() + "-" + secrets.token_hex(4).upper() for _ in range(count)]
    now = time.time()
    conn = _connect()
    with conn:
        conn.execute("DELETE FROM recovery_codes WHERE user_id = ?", (user_id,))
        for code in codes:
            salt = secrets.token_hex(16)
            conn.execute(
                "INSERT INTO recovery_codes (id, user_id, code_hash, salt, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), user_id, _hash_code(code, salt), salt, now),
            )
    conn.close()
    return codes


def use_recovery_code(user_id: str, code: str) -> bool:
    normalized = code.strip().upper()
    conn = _connect()
    rows = conn.execute(
        "SELECT id, code_hash, salt FROM recovery_codes WHERE user_id = ? AND used_at IS NULL",
        (user_id,),
    ).fetchall()
    for row in rows:
        if secrets.compare_digest(_hash_code(normalized, row["salt"]), row["code_hash"]):
            with conn:
                conn.execute(
                    "UPDATE recovery_codes SET used_at = ? WHERE id = ?",
                    (time.time(), row["id"]),
                )
            conn.close()
            return True
    conn.close()
    return False


def get_device_profile_id(device_id: str) -> str | None:
    conn = _connect()
    row = conn.execute(
        "SELECT profile_id FROM devices WHERE id=?", (device_id,)
    ).fetchone()
    conn.close()
    return row["profile_id"] if row else None
