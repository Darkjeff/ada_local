"""
router_webhook.py — Support webhook entrant pour ADA.

POST /api/webhook/{source}?token=<secret>
  Permet à Domoticz, n8n, Home Assistant et tout autre service externe
  d'envoyer des commandes / événements à ADA.

Authentification :
  Token secret (query param `token`, header `X-Webhook-Token` ou `Authorization: Bearer ...`).
  Stocké dans settings["webhook.secret"] — auto-généré UUID si absent.
  Rotation : POST /api/webhook/config/rotate  (requiert JWT)
  Lecture   : GET  /api/webhook/config         (requiert JWT)

Modes de traitement selon le payload :
  { "text" | "message" | "query": "..." }   → intent texte → pipeline ADA → reply
  { "action": "...", "params": {...} }        → exécution directe FunctionExecutor
  { "event": "...", ... }                     → événement Radar (fire & forget)
"""
from __future__ import annotations

import hmac
import logging
import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from core.settings_store import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhook", tags=["webhook"])


# ---------------------------------------------------------------------------
# Helpers token
# ---------------------------------------------------------------------------

def _get_or_create_token() -> str:
    """Retourne le token webhook existant, le génère si absent."""
    token = settings.get("webhook.secret", "")
    if not token:
        token = secrets.token_urlsafe(32)
        settings.set("webhook.secret", token)
        logger.info("[Webhook] Token webhook auto-généré")
    return token


def _verify_token(provided: str) -> bool:
    """Comparaison sécurisée (résistante aux timing attacks)."""
    if not provided:
        return False
    expected = _get_or_create_token()
    try:
        return hmac.compare_digest(
            provided.encode("utf-8"),
            expected.encode("utf-8"),
        )
    except Exception:
        return False


def _extract_token(request: Request) -> str:
    """Extrait le token depuis query param, header ou Authorization Bearer."""
    t = request.query_params.get("token", "")
    if not t:
        t = request.headers.get("X-Webhook-Token", "")
    if not t:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            t = auth[7:]
    return t


# ---------------------------------------------------------------------------
# Routes de configuration (protégées par le middleware JWT)
# ---------------------------------------------------------------------------

@router.get("/config")
async def webhook_config():
    """Retourne le token webhook actuel et l'URL du point d'entrée."""
    return {
        "token": _get_or_create_token(),
        "endpoint": "/api/webhook/{source}",
        "auth": "query ?token=<secret>  |  header X-Webhook-Token  |  Authorization: Bearer <secret>",
        "sources_examples": ["domoticz", "n8n", "home_assistant", "alexa", "generic"],
        "payload_modes": {
            "intent": {"text": "Allume la lumière"},
            "action": {"action": "control_light", "params": {"room": "salon", "state": "on"}},
            "event":  {"event": "device_changed", "device": "lumiere_salon", "value": 1},
        },
    }


@router.post("/config/rotate")
async def webhook_rotate():
    """Régénère le token webhook (invalide l'ancien instantanément)."""
    new_token = secrets.token_urlsafe(32)
    settings.set("webhook.secret", new_token)
    logger.info("[Webhook] Token webhook régénéré")
    return {"ok": True, "token": new_token}


# ---------------------------------------------------------------------------
# Point d'entrée principal
# ---------------------------------------------------------------------------

@router.post("/{source}")
async def receive_webhook(source: str, request: Request):
    """
    Point d'entrée webhook universel.

    Sources reconnues : domoticz, n8n, home_assistant, alexa, google_home
    Sources libres    : tout nom de chaîne (ex: "zigbee2mqtt", "custom")
    """
    # ── Authentification ──────────────────────────────────────────────────
    token = _extract_token(request)
    if not _verify_token(token):
        logger.warning(
            "[Webhook] Tentative non authentifiée — IP=%s source=%s",
            getattr(request.client, "host", "?"),
            source,
        )
        raise HTTPException(status_code=401, detail="Token webhook invalide ou manquant")

    # ── Décodage payload ─────────────────────────────────────────────────
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    if not isinstance(payload, dict):
        payload = {"text": str(payload)}

    # Log sans exposer le token s'il est dans le body
    safe_log = {k: v for k, v in payload.items() if k not in ("token", "secret")}
    logger.info("[Webhook] Reçu — source=%s payload=%s", source, safe_log)

    # ── Routage selon le mode ─────────────────────────────────────────────

    # Mode action directe
    if "action" in payload:
        return await _handle_action(source, payload)

    # Mode événement pur (pas de champ texte)
    _text_keys = {"text", "message", "query", "queryText"}
    if "event" in payload and not _text_keys.intersection(payload):
        return await _handle_event(source, payload)

    # Mode intent texte → pipeline ADA
    text = _normalize_text(source, payload)
    if text:
        return await _handle_intent(source, text, payload)

    return JSONResponse(
        {"ok": False, "detail": "Payload non reconnu — champs attendus: text/message/query, action ou event"},
        status_code=422,
    )


# ---------------------------------------------------------------------------
# Normalisation du texte par source (réutilise IntentBridge)
# ---------------------------------------------------------------------------

def _normalize_text(source: str, payload: dict) -> str | None:
    """Extrait le texte d'intention depuis le payload."""
    try:
        from core.intent_bridge import intent_bridge
        return intent_bridge.normalize_intent(source, payload)
    except Exception:
        pass
    # Fallback générique
    for key in ("text", "message", "query", "queryText", "input"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def _handle_intent(source: str, text: str, payload: dict) -> JSONResponse:
    """Route l'intent texte vers le pipeline ADA et retourne la réponse complète."""
    from web.pipeline import process_message

    history        = payload.get("history", [])
    plugin_context = payload.get("universe") or payload.get("plugin_context") or None

    chunks: list[str] = []
    try:
        async for chunk in process_message(text, history, plugin_context=plugin_context):
            # Filtrer les chunks spéciaux (images, thinking, cartes de confirmation)
            if not chunk:
                continue
            if chunk.startswith("\x00img\x00") or chunk.startswith("\x00think\x00"):
                continue
            if chunk.startswith('{"__type"'):
                continue
            chunks.append(chunk)
    except Exception as exc:
        logger.error("[Webhook] Erreur pipeline : %s", exc, exc_info=True)
        return JSONResponse({"ok": False, "detail": str(exc)}, status_code=500)

    reply = "".join(chunks).strip()
    logger.info("[Webhook] Réponse ADA → source=%s len=%d", source, len(reply))
    return JSONResponse({"ok": True, "source": source, "text": text, "reply": reply})


async def _handle_action(source: str, payload: dict) -> JSONResponse:
    """Exécute directement une action via FunctionExecutor."""
    action = str(payload.get("action", "")).strip()
    params = payload.get("params") or {}
    if not action:
        return JSONResponse({"ok": False, "detail": "Champ 'action' vide"}, status_code=422)
    try:
        from core.function_executor import FunctionExecutor
        result = FunctionExecutor().execute(action, params)
        return JSONResponse({"ok": True, "source": source, "action": action, "result": result})
    except Exception as exc:
        logger.error("[Webhook] Erreur action %s : %s", action, exc, exc_info=True)
        return JSONResponse({"ok": False, "detail": str(exc)}, status_code=500)


async def _handle_event(source: str, payload: dict) -> JSONResponse:
    """Enregistre un événement entrant dans le Radar (fire & forget)."""
    event_type = str(payload.get("event", "webhook.event"))
    try:
        from web.radar.events import emit_event
        emit_event(
            type=f"webhook.{event_type}",
            level="info",
            module=f"webhook.{source}",
            metadata={k: v for k, v in payload.items() if k not in ("event", "token", "secret")},
        )
    except Exception:
        pass  # emit_event ne doit jamais planter l'appelant
    return JSONResponse({"ok": True, "source": source, "event": event_type, "queued": True})
