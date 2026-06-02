"""
core/routes/profiles.py — Logique métier profils & univers.
Appelé par web/router_profiles.py.
"""
from __future__ import annotations

import time
import uuid
from typing import Optional

from web.auth_db import _connect          # réutilise la connexion SQLite existante
from core.views import ALL_MODULES, MODULE_BY_ID, available_modules
from config import MODULES_ENABLED


# ── Initialisation ─────────────────────────────────────────────────────────

def initialize() -> None:
    """Crée les tables, seed modules et profils par défaut."""
    conn = _connect()
    with conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS modules (
            id               TEXT PRIMARY KEY,
            label            TEXT NOT NULL,
            icon             TEXT NOT NULL,
            category         TEXT NOT NULL,
            requires_module  TEXT
        );

        CREATE TABLE IF NOT EXISTS universes (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            icon        TEXT NOT NULL DEFAULT '◈',
            color       TEXT NOT NULL DEFAULT '#00c8f0',
            position    INTEGER NOT NULL DEFAULT 0,
            created_at  REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS universe_modules (
            universe_id TEXT NOT NULL,
            module_id   TEXT NOT NULL,
            position    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (universe_id, module_id),
            FOREIGN KEY (universe_id) REFERENCES universes(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS display_profiles (
            id                  TEXT PRIMARY KEY,
            name                TEXT NOT NULL,
            theme               TEXT NOT NULL DEFAULT 'dark',
            density             TEXT NOT NULL DEFAULT 'normal',
            default_universe_id TEXT,
            created_at          REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS profile_universes (
            profile_id  TEXT NOT NULL,
            universe_id TEXT NOT NULL,
            position    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (profile_id, universe_id),
            FOREIGN KEY (profile_id)  REFERENCES display_profiles(id) ON DELETE CASCADE,
            FOREIGN KEY (universe_id) REFERENCES universes(id)        ON DELETE CASCADE
        );
        """)

        # Migration devices si table et colonne absentes
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if "devices" in tables:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(devices)").fetchall()]
            if "profile_id" not in cols:
                conn.execute("ALTER TABLE devices ADD COLUMN profile_id TEXT")

    conn.close()
    _seed_modules()
    _seed_default_profiles()


def _seed_modules() -> None:
    conn = _connect()
    count = conn.execute("SELECT COUNT(*) FROM modules").fetchone()[0]
    if count == 0:
        with conn:
            for m in ALL_MODULES:
                conn.execute(
                    "INSERT OR IGNORE INTO modules (id, label, icon, category, requires_module) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (m.id, m.label, m.icon, m.category, m.requires_module),
                )
    conn.close()


def _seed_default_profiles() -> None:
    conn = _connect()
    count = conn.execute("SELECT COUNT(*) FROM display_profiles").fetchone()[0]
    if count > 0:
        conn.close()
        return

    now = time.time()

    def _make_universe(conn, name, icon, color, position, module_ids):
        uid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO universes (id, name, icon, color, position, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (uid, name, icon, color, position, now),
        )
        for pos, mid in enumerate(module_ids):
            conn.execute(
                "INSERT INTO universe_modules (universe_id, module_id, position) VALUES (?, ?, ?)",
                (uid, mid, pos),
            )
        return uid

    def _make_profile(conn, name, theme, density, universe_ids, default_uid):
        pid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO display_profiles (id, name, theme, density, default_universe_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (pid, name, theme, density, default_uid, now),
        )
        for pos, uid in enumerate(universe_ids):
            conn.execute(
                "INSERT INTO profile_universes (profile_id, universe_id, position) VALUES (?, ?, ?)",
                (pid, uid, pos),
            )
        return pid

    with conn:
        # Profil Complet
        u_dash   = _make_universe(conn, "Dashboard",    "◈",  "#00c8f0", 0,
                                  ["dashboard", "chat"])
        u_maison = _make_universe(conn, "Maison",       "🏠", "#8870ff", 1,
                                  ["home", "cameras", "senses", "music"])
        u_societe= _make_universe(conn, "Société",      "◈",  "#00e898", 2,
                                  ["infrastructure", "societe", "marketing"])
        u_plan   = _make_universe(conn, "Planification","📅", "#ff9a00", 3,
                                  ["planner", "briefing"])
        u_tools  = _make_universe(conn, "Outils",       "⚙",  "#ff6b35", 4,
                                  ["webagent", "cad", "printers", "skills",
                                   "memory", "library", "settings"])
        _make_profile(conn, "Complet", "dark", "normal",
                      [u_dash, u_maison, u_societe, u_plan, u_tools], u_dash)

        # Profil Mobile
        u_mobile = _make_universe(conn, "Dashboard",   "◈",  "#00c8f0", 0,
                                  ["dashboard", "chat", "planner", "briefing"])
        _make_profile(conn, "Mobile", "dark", "compact", [u_mobile], u_mobile)

        # Profil Maison
        u_mh_dash = _make_universe(conn, "Dashboard", "◈",  "#00c8f0", 0,
                                   ["dashboard", "chat"])
        u_mh_home = _make_universe(conn, "Maison",    "🏠", "#8870ff", 1,
                                   ["home", "cameras", "senses", "music"])
        _make_profile(conn, "Maison", "light", "comfortable",
                      [u_mh_dash, u_mh_home], u_mh_home)

    conn.close()


# ── Modules ────────────────────────────────────────────────────────────────

def list_modules() -> list[dict]:
    """Retourne les modules disponibles (filtrés par feature flags actifs)."""
    avail = {m.id for m in available_modules(MODULES_ENABLED)}
    conn = _connect()
    rows = conn.execute("SELECT * FROM modules ORDER BY category, id").fetchall()
    conn.close()
    return [dict(r) for r in rows if r["id"] in avail]


# ── Univers ────────────────────────────────────────────────────────────────

def list_universes() -> list[dict]:
    conn = _connect()
    rows = conn.execute("SELECT * FROM universes ORDER BY position").fetchall()
    result = []
    for row in rows:
        modules = conn.execute(
            "SELECT module_id, position FROM universe_modules "
            "WHERE universe_id = ? ORDER BY position",
            (row["id"],),
        ).fetchall()
        result.append({**dict(row), "modules": [r["module_id"] for r in modules]})
    conn.close()
    return result


def get_universe(universe_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM universes WHERE id = ?", (universe_id,)).fetchone()
    if not row:
        conn.close()
        return None
    modules = conn.execute(
        "SELECT module_id FROM universe_modules WHERE universe_id = ? ORDER BY position",
        (universe_id,),
    ).fetchall()
    avail_ids = {m.id for m in available_modules(MODULES_ENABLED)}
    result = {**dict(row), "modules": [r["module_id"] for r in modules if r["module_id"] in avail_ids]}
    conn.close()
    return result


def create_universe(name: str, icon: str, color: str, module_ids: list[str]) -> dict:
    uid = str(uuid.uuid4())
    now = time.time()
    conn = _connect()
    max_pos = conn.execute("SELECT COALESCE(MAX(position),0) FROM universes").fetchone()[0]
    with conn:
        conn.execute(
            "INSERT INTO universes (id, name, icon, color, position, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (uid, name, icon, color, max_pos + 1, now),
        )
        for pos, mid in enumerate(module_ids):
            conn.execute(
                "INSERT INTO universe_modules (universe_id, module_id, position) "
                "VALUES (?, ?, ?)", (uid, mid, pos),
            )
    conn.close()
    return get_universe(uid)


def update_universe(universe_id: str, name: str, icon: str, color: str,
                    module_ids: list[str]) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT id FROM universes WHERE id = ?", (universe_id,)).fetchone()
    if not row:
        conn.close()
        return None
    with conn:
        conn.execute(
            "UPDATE universes SET name=?, icon=?, color=? WHERE id=?",
            (name, icon, color, universe_id),
        )
        conn.execute("DELETE FROM universe_modules WHERE universe_id=?", (universe_id,))
        for pos, mid in enumerate(module_ids):
            conn.execute(
                "INSERT INTO universe_modules (universe_id, module_id, position) "
                "VALUES (?, ?, ?)", (universe_id, mid, pos),
            )
    conn.close()
    return get_universe(universe_id)


def delete_universe(universe_id: str) -> bool:
    conn = _connect()
    row = conn.execute("SELECT id FROM universes WHERE id=?", (universe_id,)).fetchone()
    if not row:
        conn.close()
        return False
    with conn:
        conn.execute("DELETE FROM universes WHERE id=?", (universe_id,))
    conn.close()
    return True


# ── Profils ────────────────────────────────────────────────────────────────

def list_profiles() -> list[dict]:
    conn = _connect()
    rows = conn.execute("SELECT * FROM display_profiles ORDER BY created_at").fetchall()
    result = []
    for row in rows:
        universes = conn.execute(
            "SELECT universe_id, position FROM profile_universes "
            "WHERE profile_id=? ORDER BY position",
            (row["id"],),
        ).fetchall()
        result.append({
            **dict(row),
            "universe_ids": [r["universe_id"] for r in universes],
        })
    conn.close()
    return result


def get_profile(profile_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM display_profiles WHERE id=?", (profile_id,)
    ).fetchone()
    if not row:
        conn.close()
        return None
    universes = conn.execute(
        "SELECT universe_id FROM profile_universes WHERE profile_id=? ORDER BY position",
        (profile_id,),
    ).fetchall()
    # Hydrate chaque univers
    universe_list = []
    for u in universes:
        uni = get_universe(u["universe_id"])
        if uni:
            universe_list.append(uni)
    result = {
        **dict(row),
        "universes": universe_list,
    }
    conn.close()
    return result


def create_profile(name: str, theme: str, density: str,
                   universe_ids: list[str], default_universe_id: str | None) -> dict:
    pid = str(uuid.uuid4())
    conn = _connect()
    with conn:
        conn.execute(
            "INSERT INTO display_profiles "
            "(id, name, theme, density, default_universe_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (pid, name, theme, density, default_universe_id, time.time()),
        )
        for pos, uid in enumerate(universe_ids):
            conn.execute(
                "INSERT INTO profile_universes (profile_id, universe_id, position) "
                "VALUES (?, ?, ?)", (pid, uid, pos),
            )
    conn.close()
    return get_profile(pid)


def update_profile(profile_id: str, name: str, theme: str, density: str,
                   universe_ids: list[str], default_universe_id: str | None) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT id FROM display_profiles WHERE id=?", (profile_id,)
    ).fetchone()
    if not row:
        conn.close()
        return None
    with conn:
        conn.execute(
            "UPDATE display_profiles SET name=?, theme=?, density=?, "
            "default_universe_id=? WHERE id=?",
            (name, theme, density, default_universe_id, profile_id),
        )
        conn.execute("DELETE FROM profile_universes WHERE profile_id=?", (profile_id,))
        for pos, uid in enumerate(universe_ids):
            conn.execute(
                "INSERT INTO profile_universes (profile_id, universe_id, position) "
                "VALUES (?, ?, ?)", (profile_id, uid, pos),
            )
    conn.close()
    return get_profile(profile_id)


def delete_profile(profile_id: str) -> bool:
    conn = _connect()
    row = conn.execute("SELECT id FROM display_profiles WHERE id=?", (profile_id,)).fetchone()
    if not row:
        conn.close()
        return False
    with conn:
        conn.execute("DELETE FROM display_profiles WHERE id=?", (profile_id,))
        conn.execute(
            "UPDATE devices SET profile_id=NULL WHERE profile_id=?", (profile_id,)
        )
    conn.close()
    return True


# ── Device → Profile ────────────────────────────────────────────────────────

def assign_profile_to_device(device_id: str, profile_id: str | None) -> bool:
    conn = _connect()
    row = conn.execute("SELECT id FROM devices WHERE id=?", (device_id,)).fetchone()
    if not row:
        conn.close()
        return False
    with conn:
        conn.execute(
            "UPDATE devices SET profile_id=? WHERE id=?", (profile_id, device_id)
        )
    conn.close()
    return True


def get_device_profile(device_id: str) -> dict | None:
    """Retourne le profil hydraté du device, ou le profil 'Complet' par défaut."""
    conn = _connect()
    row = conn.execute(
        "SELECT profile_id FROM devices WHERE id=?", (device_id,)
    ).fetchone()
    conn.close()
    if row and row["profile_id"]:
        return get_profile(row["profile_id"])
    # Fallback : premier profil (seed "Complet")
    conn = _connect()
    first = conn.execute(
        "SELECT id FROM display_profiles ORDER BY created_at LIMIT 1"
    ).fetchone()
    conn.close()
    return get_profile(first["id"]) if first else None
