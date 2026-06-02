"""
ADA Auth — router FastAPI (/api/auth/*)
"""
from __future__ import annotations

import base64
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from core.settings_store import settings
from web.auth import (
    bootstrap_setup,
    create_jwt,
    extract_token,
    generate_qr_png,
    verify_jwt,
)
from web.auth_db import (
    cleanup_expired_qr,
    confirm_pending_qr,
    count_users,
    create_pending_qr,
    create_recovery_codes,
    create_user,
    deactivate_device,
    deactivate_user,
    get_pending_qr_by_code,
    get_pending_qr_by_session,
    get_user,
    get_user_by_username,
    initialize as db_init,
    list_devices,
    list_users,
    register_device,
    update_user_groups,
    use_recovery_code,
)
from web.auth_permissions import (
    GROUP_DESCRIPTIONS,
    PERMISSION_GROUPS,
    groups_to_tags,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_verified(request: Request) -> Optional[dict]:
    token = extract_token(request)
    return verify_jwt(token) if token else None


def _require_auth(request: Request) -> dict:
    payload = _get_verified(request)
    if not payload:
        raise HTTPException(status_code=401, detail="Non authentifié")
    return payload


def _require_admin(request: Request) -> dict:
    # Si l'auth est désactivée, accès admin libre (réseau local de confiance)
    if not settings.get("auth.enabled", False):
        return {"groups": ["admin"], "sub": "local"}
    payload = _require_auth(request)
    if "admin" not in payload.get("groups", []):
        raise HTTPException(status_code=403, detail="Accès admin requis")
    return payload


def _server_url(request: Request) -> str:
    scheme = request.url.scheme
    host = request.headers.get("host", request.url.netloc)
    return f"{scheme}://{host}"


# ── Config globale (publique) ─────────────────────────────────────────────────


@router.get("/config")
async def auth_config():
    """Retourne l'état de l'auth : activé ? bootstrap requis ?"""
    enabled = settings.get("auth.enabled", False)
    if not enabled:
        return {"enabled": False}
    db_init()
    return {
        "enabled": True,
        "bootstrap_required": count_users() == 0,
        "groups": {k: v for k, v in GROUP_DESCRIPTIONS.items()},
    }


# ── QR — Nouvelle session (appareil non authentifié) ──────────────────────────


@router.get("/qr")
async def get_qr(request: Request, device_name: str = "Nouvel appareil"):
    """
    Crée une session QR pour un nouvel appareil.
    En bootstrap : retourne un QR vers la page d'inscription admin.
    Sinon : retourne un QR pour confirmation par un appareil existant.
    """
    if not settings.get("auth.enabled", False):
        raise HTTPException(status_code=404, detail="Auth désactivée")

    db_init()
    cleanup_expired_qr()
    server_url = _server_url(request)

    if count_users() == 0:
        data = bootstrap_setup(server_url)
        png = generate_qr_png(data["enroll_url"])
        return {
            "bootstrap_required": True,
            "session_token": data["session_token"],
            "qr_url": data["enroll_url"],
            "qr_png_b64": base64.b64encode(png).decode() if png else None,
            "expires_at": data["expires_at"],
        }

    pending = create_pending_qr(qr_type="qr", device_name=device_name[:80])
    confirm_url = f"{server_url}/?confirm={pending['code']}"
    png = generate_qr_png(confirm_url)
    return {
        "bootstrap_required": False,
        "session_token": pending["session_token"],
        "qr_url": confirm_url,
        "qr_png_b64": base64.b64encode(png).decode() if png else None,
        "expires_at": pending["expires_at"],
    }


# ── QR — Polling statut ───────────────────────────────────────────────────────


@router.get("/qr/status")
async def qr_status(session_token: str):
    """Polling : retourne le JWT quand la session QR est confirmée."""
    if not settings.get("auth.enabled", False):
        raise HTTPException(status_code=404)

    db_init()
    pending = get_pending_qr_by_session(session_token)
    if not pending:
        raise HTTPException(status_code=404, detail="Session inconnue")

    if time.time() > pending["expires_at"]:
        return {"status": "expired"}

    if pending.get("confirmed_at") and pending.get("jwt"):
        return {"status": "confirmed", "token": pending["jwt"]}

    return {"status": "pending"}


# ── QR — Confirmation (appareil authentifié approuve) ─────────────────────────


@router.post("/confirm")
async def confirm_qr(request: Request):
    """
    L'appareil authentifié confirme l'enrollment du nouvel appareil.
    Body JSON : {code, device_name?}
    """
    body = await request.json()
    code = str(body.get("code", "")).strip()
    confirmer = _get_verified(request)
    if not confirmer:
        raise HTTPException(status_code=401, detail="Non authentifié")
    if not code:
        raise HTTPException(status_code=400, detail="Code manquant")

    db_init()
    pending = get_pending_qr_by_code(code)
    if not pending:
        raise HTTPException(status_code=404, detail="Code invalide")
    if time.time() > pending["expires_at"]:
        raise HTTPException(status_code=410, detail="QR code expiré")
    if pending.get("confirmed_at"):
        raise HTTPException(status_code=409, detail="Déjà confirmé")
    if pending.get("type") != "qr":
        raise HTTPException(status_code=400, detail="Type de code incompatible")

    # L'appareil est enrôlé sous l'utilisateur du confirmant
    target_uid = pending.get("target_user_id") or confirmer["sub"]
    user = get_user(target_uid)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur cible introuvable")

    device_name = str(body.get("device_name", pending.get("device_name", "Appareil")))[:80]
    device_id = register_device(target_uid, device_name)
    token = create_jwt(target_uid, device_id, user["groups"])
    confirm_pending_qr(code, token)
    return {"ok": True, "message": f"Appareil '{device_name}' enrôlé pour {user['display_name']}"}


# ── Enrollment auto-guidé (invite admin ou bootstrap) ────────────────────────


@router.get("/enroll")
async def enroll_page(code: str, request: Request):
    """Sert la page HTML d'enrollment (création compte ou ajout appareil)."""
    db_init()
    pending = get_pending_qr_by_code(code)
    if not pending:
        raise HTTPException(status_code=404, detail="Lien invalide")
    if time.time() > pending["expires_at"]:
        raise HTTPException(status_code=410, detail="Lien expiré — demandez un nouveau QR")
    if pending.get("confirmed_at"):
        raise HTTPException(status_code=409, detail="Lien déjà utilisé")
    if pending.get("type") != "invite":
        raise HTTPException(status_code=400, detail="Type de QR incompatible")

    is_bootstrap = count_users() == 0 and pending.get("target_user_id") is None
    target_user: dict | None = None
    if pending.get("target_user_id"):
        target_user = get_user(pending["target_user_id"])

    if is_bootstrap:
        form_title = "Créer le compte administrateur"
        form_subtitle = "Premier lancement d'ADA — définissez le compte admin."
        show_username = True
    elif target_user:
        form_title = f"Bienvenue, {target_user['display_name']} !"
        form_subtitle = "Donnez un nom à cet appareil pour l'enregistrer."
        show_username = False
    else:
        raise HTTPException(status_code=400, detail="Lien invalide")

    username_row = """
    <label>Nom d'utilisateur (login)</label>
    <input id="username" type="text" placeholder="ex: alice" autocomplete="username" />
    <label>Prénom / nom affiché</label>
    <input id="display_name" type="text" placeholder="ex: Alice" />
    """ if show_username else ""

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ADA — Enrollment</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: #0f1117; color: #e2e8f0; font-family: system-ui, sans-serif;
            display: flex; align-items: center; justify-content: center;
            min-height: 100vh; padding: 1rem; }}
    .card {{ background: #1e2330; border-radius: 16px; padding: 2rem;
             max-width: 420px; width: 100%; }}
    .logo {{ width: 48px; height: 48px; background: #7b68ee; border-radius: 12px;
             display: flex; align-items: center; justify-content: center;
             font-size: 1.5rem; font-weight: 900; color: #fff; margin-bottom: 1rem; }}
    h1 {{ color: #c7d2fe; font-size: 1.2rem; margin-bottom: .3rem; }}
    p  {{ color: #64748b; font-size: .875rem; margin-bottom: 1.5rem; }}
    label {{ display: block; color: #94a3b8; font-size: .8rem;
             margin-bottom: .25rem; margin-top: .75rem; }}
    input {{ display: block; width: 100%; background: #252b3b;
             border: 1px solid #374151; border-radius: 8px; color: #e2e8f0;
             padding: .6rem .8rem; font-size: 1rem; }}
    input:focus {{ outline: none; border-color: #7b68ee; }}
    button {{ margin-top: 1.5rem; width: 100%; padding: .75rem; border: none;
              border-radius: 8px; background: #7b68ee; color: #fff;
              font-size: 1rem; cursor: pointer; transition: background .15s; }}
    button:hover {{ background: #6b58de; }}
    button:disabled {{ background: #374151; cursor: not-allowed; }}
    .msg {{ margin-top: 1rem; padding: .75rem; border-radius: 8px;
            font-size: .875rem; display: none; }}
    .msg.ok  {{ background: #14532d; color: #86efac; display: block; }}
    .msg.err {{ background: #7f1d1d; color: #fca5a5; display: block; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">A</div>
    <h1>{form_title}</h1>
    <p>{form_subtitle}</p>
    {username_row}
    <label>Nom de cet appareil</label>
    <input id="device_name" type="text"
           placeholder="ex: iPhone Alice, PC Bureau…"
           value="{pending.get('device_name', 'Nouvel appareil')}" />
    <button id="btn" onclick="enroll()">Enregistrer</button>
    <div id="msg" class="msg"></div>
  </div>
  <script>
    const CODE = {repr(code)};
    const IS_BOOTSTRAP = {"true" if is_bootstrap else "false"};
    async function enroll() {{
      const btn = document.getElementById('btn');
      btn.disabled = true;
      const device_name = document.getElementById('device_name').value.trim() || 'Appareil';
      const body = {{ code: CODE, device_name }};
      if (IS_BOOTSTRAP) {{
        const username = (document.getElementById('username')?.value || '').trim();
        const display_name = (document.getElementById('display_name')?.value || username).trim();
        if (!username) {{ showMsg('Nom d\\'utilisateur requis', 'err'); btn.disabled=false; return; }}
        Object.assign(body, {{ username, display_name }});
      }}
      const r = await fetch('/api/auth/enroll/finalize', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(body),
      }});
      const data = await r.json();
      if (r.ok) {{
        localStorage.setItem('ada_token', data.token);
        document.cookie = `ada_token=${{data.token}}; path=/; SameSite=Strict; Max-Age=${{30*86400}}`;
        showMsg('Compte enregistré ! Redirection…', 'ok');
        setTimeout(() => {{ window.location.href = '/'; }}, 1500);
      }} else {{
        showMsg(data.detail || 'Erreur', 'err');
        btn.disabled = false;
      }}
    }}
    function showMsg(text, type) {{
      const el = document.getElementById('msg');
      el.textContent = text;
      el.className = 'msg ' + type;
    }}
  </script>
</body>
</html>"""
    return HTMLResponse(html)


@router.post("/enroll/finalize")
async def enroll_finalize(request: Request):
    """Finalise l'enrollment (bootstrap admin ou nouvel appareil pour user invité)."""
    body = await request.json()
    code = str(body.get("code", "")).strip()
    device_name = str(body.get("device_name", "Appareil")).strip()[:80]

    if not code:
        raise HTTPException(status_code=400, detail="Code manquant")

    db_init()
    pending = get_pending_qr_by_code(code)
    if not pending:
        raise HTTPException(status_code=404, detail="Code invalide")
    if time.time() > pending["expires_at"]:
        raise HTTPException(status_code=410, detail="Lien expiré")
    if pending.get("confirmed_at"):
        raise HTTPException(status_code=409, detail="Déjà utilisé")
    if pending.get("type") != "invite":
        raise HTTPException(status_code=400, detail="Type de code incompatible")

    # Bootstrap : créer le premier admin
    if pending.get("target_user_id") is None:
        if count_users() > 0:
            raise HTTPException(status_code=400, detail="Bootstrap déjà effectué")
        username = str(body.get("username", "")).strip()
        display_name = str(body.get("display_name", username)).strip() or username
        if not username:
            raise HTTPException(status_code=400, detail="Nom d'utilisateur requis")
        user = create_user(username, display_name, ["admin"])
    else:
        user = get_user(pending["target_user_id"])
        if not user:
            raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    device_id = register_device(user["id"], device_name)
    token = create_jwt(user["id"], device_id, user["groups"])
    confirm_pending_qr(code, token)
    return {"ok": True, "token": token}


# ── Profil courant ────────────────────────────────────────────────────────────


@router.get("/me")
async def me(request: Request):
    payload = _get_verified(request)
    if not payload:
        raise HTTPException(status_code=401)
    user = get_user(payload["sub"])
    if not user:
        raise HTTPException(status_code=401)
    return {
        "user_id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "groups": user["groups"],
        "accessible_tags": groups_to_tags(user["groups"]),
    }


# ── Déconnexion ───────────────────────────────────────────────────────────────


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("ada_token", path="/")
    return {"ok": True}


# ── Appareils (vue utilisateur) ───────────────────────────────────────────────


@router.get("/devices")
async def my_devices(request: Request):
    payload = _require_auth(request)
    db_init()
    return list_devices(payload["sub"])


@router.delete("/devices/{device_id}")
async def revoke_device(device_id: str, request: Request):
    payload = _require_auth(request)
    db_init()
    devices = list_devices(payload["sub"])
    is_own = any(d["id"] == device_id for d in devices)
    if not is_own and "admin" not in payload.get("groups", []):
        raise HTTPException(status_code=403, detail="Accès refusé")
    deactivate_device(device_id)
    return {"ok": True}


# ── Codes de récupération ─────────────────────────────────────────────────────


@router.post("/recovery/generate")
async def generate_recovery(request: Request):
    payload = _require_auth(request)
    db_init()
    codes = create_recovery_codes(payload["sub"])
    return {"codes": codes}


class _RecoveryLoginBody(BaseModel):
    username: str
    code: str
    device_name: str = "Récupération"


@router.post("/recovery/login")
async def recovery_login(body: _RecoveryLoginBody):
    if not settings.get("auth.enabled", False):
        raise HTTPException(status_code=404)
    db_init()
    user = get_user_by_username(body.username)
    if not user:
        raise HTTPException(status_code=401, detail="Identifiants invalides")
    if not use_recovery_code(user["id"], body.code):
        raise HTTPException(status_code=401, detail="Code invalide ou déjà utilisé")
    device_id = register_device(user["id"], body.device_name[:80])
    token = create_jwt(user["id"], device_id, user["groups"])
    return {"token": token}


# ── Admin — gestion des utilisateurs ─────────────────────────────────────────


@router.get("/admin/users")
async def admin_list_users(request: Request):
    _require_admin(request)
    db_init()
    return list_users()


@router.post("/admin/users")
async def admin_create_user(request: Request):
    _require_admin(request)
    body = await request.json()
    username = str(body.get("username", "")).strip()
    display_name = str(body.get("display_name", username)).strip() or username
    groups = list(body.get("groups", ["assistant"]))
    if not username:
        raise HTTPException(status_code=400, detail="Nom d'utilisateur requis")
    db_init()
    return create_user(username, display_name, groups)


@router.patch("/admin/users/{user_id}")
async def admin_update_user(user_id: str, request: Request):
    _require_admin(request)
    body = await request.json()
    groups = body.get("groups")
    if groups is not None:
        db_init()
        update_user_groups(user_id, list(groups))
    return {"ok": True}


@router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, request: Request):
    _require_admin(request)
    db_init()
    deactivate_user(user_id)
    return {"ok": True}


# ── Admin — invitation (QR d'enrollment pour un utilisateur existant) ─────────


@router.post("/admin/invite")
async def admin_invite(request: Request):
    """Génère un QR d'invitation pour enrôler un appareil pour un utilisateur existant."""
    _require_admin(request)
    body = await request.json()
    target_user_id = str(body.get("user_id", "")).strip()
    device_name = str(body.get("device_name", "Nouvel appareil")).strip()[:80]
    if not target_user_id:
        raise HTTPException(status_code=400, detail="user_id requis")

    db_init()
    cleanup_expired_qr()
    server_url = _server_url(request)
    pending = create_pending_qr(
        qr_type="invite", target_user_id=target_user_id, device_name=device_name, ttl=3600
    )
    enroll_url = f"{server_url}/api/auth/enroll?code={pending['code']}"
    png = generate_qr_png(enroll_url)
    return {
        "session_token": pending["session_token"],
        "enroll_url": enroll_url,
        "qr_png_b64": base64.b64encode(png).decode() if png else None,
        "expires_at": pending["expires_at"],
    }
