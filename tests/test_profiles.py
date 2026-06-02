"""
tests/test_profiles.py — Tests unitaires pour le système profils/univers/devices.
"""
from __future__ import annotations

import os
import sys
import tempfile
import pytest

# Assure que la racine du projet est dans sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _tmp_db(tmp_path, monkeypatch):
    """Redirige auth_db vers une DB temporaire pour les tests."""
    db_path = tmp_path / "test_auth.db"
    import web.auth_db as adb
    monkeypatch.setattr(adb, "_DB_PATH", db_path)
    # Initialise les tables auth (users, devices…)
    adb.initialize()
    yield db_path


@pytest.fixture()
def _init_profiles():
    """Initialise les tables profils + seed."""
    from core.routes.profiles import initialize
    initialize()


@pytest.fixture()
def _device_id(_tmp_db):
    """Crée un device de test et retourne son id."""
    from web.auth_db import _connect
    import uuid, time
    uid = str(uuid.uuid4())
    did = str(uuid.uuid4())
    conn = _connect()
    with conn:
        conn.execute(
            "INSERT INTO users (id, username, display_name, created_at) VALUES (?,?,?,?)",
            (uid, "testuser", "Test User", time.time()),
        )
        conn.execute(
            "INSERT INTO devices (id, user_id, device_name, created_at) VALUES (?,?,?,?)",
            (did, uid, "Test Device", time.time()),
        )
    conn.close()
    return did


# ── Tests initialize ──────────────────────────────────────────────────────────

def test_initialize_creates_tables(_init_profiles):
    from web.auth_db import _connect
    conn = _connect()
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()
    assert "modules" in tables
    assert "universes" in tables
    assert "universe_modules" in tables
    assert "display_profiles" in tables
    assert "profile_universes" in tables


def test_initialize_adds_profile_id_column(_init_profiles):
    from web.auth_db import _connect
    conn = _connect()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(devices)").fetchall()]
    conn.close()
    assert "profile_id" in cols


def test_initialize_idempotent(_init_profiles):
    """Appeler initialize() deux fois ne doit pas lever d'erreur."""
    from core.routes.profiles import initialize
    initialize()


# ── Tests modules ─────────────────────────────────────────────────────────────

def test_list_modules_returns_all(_init_profiles):
    from core.routes.profiles import list_modules
    mods = list_modules()
    assert len(mods) > 0
    ids = [m["id"] for m in mods]
    assert "dashboard" in ids
    assert "chat" in ids


def test_list_modules_respects_feature_flags(_init_profiles, monkeypatch):
    import core.routes.profiles as rp
    monkeypatch.setattr(rp, "MODULES_ENABLED", {"societe": False})
    mods = rp.list_modules()
    ids = [m["id"] for m in mods]
    assert "societe" not in ids


# ── Tests univers ─────────────────────────────────────────────────────────────

def test_list_universes_after_seed(_init_profiles):
    from core.routes.profiles import list_universes
    univs = list_universes()
    assert len(univs) >= 3  # seed crée au moins 3 univers (via les 3 profils)


def test_create_and_get_universe(_init_profiles):
    from core.routes.profiles import create_universe, get_universe
    u = create_universe("Test", "🔧", "#ff0000", ["dashboard", "chat"])
    assert u["name"] == "Test"
    assert u["icon"] == "🔧"
    assert u["color"] == "#ff0000"
    assert "dashboard" in u["modules"]

    fetched = get_universe(u["id"])
    assert fetched is not None
    assert fetched["id"] == u["id"]


def test_update_universe(_init_profiles):
    from core.routes.profiles import create_universe, update_universe
    u = create_universe("Avant", "◈", "#aaa", ["dashboard"])
    updated = update_universe(u["id"], "Après", "🏠", "#bbb", ["chat"])
    assert updated["name"] == "Après"
    assert updated["modules"] == ["chat"]


def test_delete_universe(_init_profiles):
    from core.routes.profiles import create_universe, delete_universe, get_universe
    u = create_universe("Temp", "◈", "#ccc", [])
    assert delete_universe(u["id"]) is True
    assert get_universe(u["id"]) is None
    assert delete_universe("inexistant-id") is False


# ── Tests profils ─────────────────────────────────────────────────────────────

def test_list_profiles_after_seed(_init_profiles):
    from core.routes.profiles import list_profiles
    profiles = list_profiles()
    assert len(profiles) == 3
    names = [p["name"] for p in profiles]
    assert "Complet" in names
    assert "Mobile" in names
    assert "Maison" in names


def test_create_and_get_profile(_init_profiles):
    from core.routes.profiles import create_universe, create_profile, get_profile
    u = create_universe("Dash", "◈", "#00c8f0", ["dashboard"])
    p = create_profile("TestProfil", "dark", "normal", [u["id"]], u["id"])
    assert p["name"] == "TestProfil"
    assert len(p["universes"]) == 1

    fetched = get_profile(p["id"])
    assert fetched is not None
    assert fetched["id"] == p["id"]


def test_update_profile(_init_profiles):
    from core.routes.profiles import create_universe, create_profile, update_profile
    u = create_universe("U1", "◈", "#aaa", ["dashboard"])
    p = create_profile("Avant", "dark", "normal", [u["id"]], u["id"])
    updated = update_profile(p["id"], "Après", "light", "compact", [], None)
    assert updated["name"] == "Après"
    assert updated["theme"] == "light"
    assert updated["universes"] == []


def test_delete_profile(_init_profiles):
    from core.routes.profiles import create_universe, create_profile, delete_profile, get_profile
    u = create_universe("U2", "◈", "#bbb", [])
    p = create_profile("ToDelete", "dark", "normal", [u["id"]], None)
    assert delete_profile(p["id"]) is True
    assert get_profile(p["id"]) is None
    assert delete_profile("inexistant") is False


# ── Tests device → profil ─────────────────────────────────────────────────────

def test_assign_profile_to_device(_init_profiles, _device_id):
    from core.routes.profiles import (
        create_universe, create_profile,
        assign_profile_to_device, get_device_profile,
    )
    u = create_universe("D", "◈", "#111", ["dashboard"])
    p = create_profile("DevProfil", "dark", "normal", [u["id"]], u["id"])

    ok = assign_profile_to_device(_device_id, p["id"])
    assert ok is True

    profile = get_device_profile(_device_id)
    assert profile is not None
    assert profile["name"] == "DevProfil"


def test_assign_profile_invalid_device(_init_profiles):
    from core.routes.profiles import assign_profile_to_device
    assert assign_profile_to_device("inexistant-device", None) is False


def test_get_device_profile_fallback(_init_profiles, _device_id):
    """Device sans profil assigné → fallback sur profil 'Complet'."""
    from core.routes.profiles import get_device_profile
    profile = get_device_profile(_device_id)
    assert profile is not None
    assert profile["name"] == "Complet"
