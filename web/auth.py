"""
ADA Auth — logique JWT, QR et bootstrap.
"""
from __future__ import annotations

import io
import secrets
import time
from pathlib import Path
from typing import Optional

from jose import JWTError, jwt

from web.auth_db import (
    count_users,
    create_pending_qr,
    is_device_active,
    touch_device,
)

# ── Secret JWT ────────────────────────────────────────────────────────────────

_SECRET_FILE = Path(__file__).parent.parent / "data" / ".jwt_secret"
_ALGORITHM = "HS256"
_TOKEN_EXPIRE_DAYS = 30


def _get_secret() -> str:
    if _SECRET_FILE.exists():
        return _SECRET_FILE.read_text().strip()
    secret = secrets.token_urlsafe(64)
    _SECRET_FILE.write_text(secret)
    _SECRET_FILE.chmod(0o600)
    return secret


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_jwt(user_id: str, device_id: str, groups: list[str]) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "device_id": device_id,
        "groups": groups,
        "iat": now,
        "exp": now + _TOKEN_EXPIRE_DAYS * 86_400,
    }
    return jwt.encode(payload, _get_secret(), algorithm=_ALGORITHM)


def verify_jwt(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, _get_secret(), algorithms=[_ALGORITHM])
        device_id = payload.get("device_id", "")
        if not is_device_active(device_id):
            return None
        touch_device(device_id)
        return payload
    except JWTError:
        return None


def extract_token(request) -> Optional[str]:
    """Extrait le Bearer token du header Authorization ou du cookie ada_token."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.cookies.get("ada_token")


# ── QR Code PNG ───────────────────────────────────────────────────────────────

def generate_qr_png(url: str) -> bytes:
    """Génère un QR code PNG et retourne les bytes bruts."""
    try:
        import qrcode  # type: ignore

        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return b""


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def bootstrap_setup(server_url: str) -> dict:
    """
    Appelé lorsque l'auth est activée mais qu'aucun utilisateur n'existe.
    Crée une session QR de type 'invite' (sans target_user_id → création admin).
    Affiche le lien dans le terminal.
    """
    from web.auth_db import cleanup_expired_qr

    cleanup_expired_qr()
    pending = create_pending_qr(qr_type="invite", target_user_id=None, device_name="Admin principal", ttl=600)
    enroll_url = f"{server_url}/api/auth/enroll?code={pending['code']}"

    banner = "\n" + "=" * 62
    banner += "\n  ADA Auth — BOOTSTRAP ADMIN"
    banner += "\n  Scannez le QR ou visitez ce lien dans un navigateur"
    banner += f"\n  de confiance (valable 10 min) :\n\n  {enroll_url}"
    banner += "\n" + "=" * 62 + "\n"
    print(banner, flush=True)

    return {
        "session_token": pending["session_token"],
        "enroll_url": enroll_url,
        "expires_at": pending["expires_at"],
    }
