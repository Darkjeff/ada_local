"""
core/routes/devices.py — Logique métier extension devices (profil, infos device).
"""
from __future__ import annotations
from web.auth_db import _connect


def get_device_with_profile(device_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    if d.get("profile_id"):
        from core.routes.profiles import get_profile
        d["profile"] = get_profile(d["profile_id"])
    else:
        d["profile"] = None
    return d
