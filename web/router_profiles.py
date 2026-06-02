"""
web/router_profiles.py — Router FastAPI pour les profils d'affichage & univers.

Endpoints :
  GET  /api/profile                   → profil du device courant (JWT device_id)
  GET  /api/modules                   → liste des modules disponibles
  GET  /api/universes                 → liste tous les univers
  POST /api/universes                 → crée un univers (admin)
  PUT  /api/universes/{id}            → modifie un univers (admin)
  DELETE /api/universes/{id}          → supprime un univers (admin)
  GET  /api/profiles                  → liste tous les profils (admin)
  POST /api/profiles                  → crée un profil (admin)
  PUT  /api/profiles/{id}             → modifie un profil (admin)
  DELETE /api/profiles/{id}           → supprime un profil (admin)
  POST /api/devices/{id}/profile      → assigne un profil à un device (admin)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from web.router_auth import _require_auth, _require_admin
from core.routes.profiles import (
    list_modules,
    list_universes,
    get_universe,
    create_universe,
    update_universe,
    delete_universe,
    list_profiles,
    get_profile,
    create_profile,
    update_profile,
    delete_profile,
    assign_profile_to_device,
    get_device_profile,
)

router = APIRouter(tags=["profiles"])


# ── Schémas Pydantic ──────────────────────────────────────────────────────


class UniverseIn(BaseModel):
    name: str
    icon: str = "◈"
    color: str = "#00c8f0"
    module_ids: list[str] = []


class ProfileIn(BaseModel):
    name: str
    theme: str = "dark"
    density: str = "normal"
    universe_ids: list[str] = []
    default_universe_id: Optional[str] = None


class DeviceProfileIn(BaseModel):
    profile_id: Optional[str] = None


# ── Profil du device courant ──────────────────────────────────────────────


@router.get("/api/profile")
async def get_my_profile(request: Request):
    """Retourne le profil hydraté du device authentifié."""
    payload = _require_auth(request)
    device_id = payload.get("device_id")
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id absent du token")
    profile = get_device_profile(device_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Aucun profil trouvé")
    return {"profile": profile}


# ── Modules ───────────────────────────────────────────────────────────────


@router.get("/api/modules")
async def api_list_modules(request: Request):
    _require_auth(request)
    return {"modules": list_modules()}


# ── Univers ───────────────────────────────────────────────────────────────


@router.get("/api/universes")
async def api_list_universes(request: Request):
    _require_auth(request)
    return {"universes": list_universes()}


@router.post("/api/universes", status_code=201)
async def api_create_universe(body: UniverseIn, request: Request):
    _require_admin(request)
    u = create_universe(body.name, body.icon, body.color, body.module_ids)
    return {"universe": u}


@router.put("/api/universes/{universe_id}")
async def api_update_universe(universe_id: str, body: UniverseIn, request: Request):
    _require_admin(request)
    u = update_universe(universe_id, body.name, body.icon, body.color, body.module_ids)
    if not u:
        raise HTTPException(status_code=404, detail="Univers introuvable")
    return {"universe": u}


@router.delete("/api/universes/{universe_id}", status_code=204)
async def api_delete_universe(universe_id: str, request: Request):
    _require_admin(request)
    if not delete_universe(universe_id):
        raise HTTPException(status_code=404, detail="Univers introuvable")


# ── Profils ───────────────────────────────────────────────────────────────


@router.get("/api/profiles")
async def api_list_profiles(request: Request):
    _require_admin(request)
    return {"profiles": list_profiles()}


@router.post("/api/profiles", status_code=201)
async def api_create_profile(body: ProfileIn, request: Request):
    _require_admin(request)
    p = create_profile(
        body.name, body.theme, body.density,
        body.universe_ids, body.default_universe_id,
    )
    return {"profile": p}


@router.put("/api/profiles/{profile_id}")
async def api_update_profile(profile_id: str, body: ProfileIn, request: Request):
    _require_admin(request)
    p = update_profile(
        profile_id, body.name, body.theme, body.density,
        body.universe_ids, body.default_universe_id,
    )
    if not p:
        raise HTTPException(status_code=404, detail="Profil introuvable")
    return {"profile": p}


@router.delete("/api/profiles/{profile_id}", status_code=204)
async def api_delete_profile(profile_id: str, request: Request):
    _require_admin(request)
    if not delete_profile(profile_id):
        raise HTTPException(status_code=404, detail="Profil introuvable")


# ── Assignation device → profil ───────────────────────────────────────────


@router.post("/api/devices/{device_id}/profile")
async def api_assign_profile(device_id: str, body: DeviceProfileIn, request: Request):
    _require_admin(request)
    ok = assign_profile_to_device(device_id, body.profile_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Device introuvable")
    return {"ok": True}


# ── Admin : liste tous les devices avec profil ────────────────────────────────

@router.get("/api/admin/devices")
async def admin_list_all_devices(request: Request):
    """Liste tous les devices actifs avec profil courant. Requiert admin."""
    _require_admin(request)
    from web.auth_db import _connect
    conn = _connect()
    rows = conn.execute("""
        SELECT d.id, d.device_name, d.last_seen, d.is_active, d.profile_id,
               u.display_name as user_display_name,
               p.name as profile_name
        FROM devices d
        JOIN users u ON d.user_id = u.id
        LEFT JOIN display_profiles p ON d.profile_id = p.id
        WHERE d.is_active = 1
        ORDER BY d.last_seen DESC NULLS LAST
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]
