"""web/radar/events.py — emit_event() : émission d'événements Radar pour ADA.

Cette fonction est le seul point d'entrée pour émettre un événement Radar.
Elle ne lève JAMAIS d'exception vers l'appelant.
Si RADAR_ENABLED = False, elle est un no-op immédiat.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import os
import sys
import traceback
import uuid
from pathlib import Path
from typing import Any

# ─── File SSE pour le temps réel ──────────────────────────────────────────────
# Les abonnés SSE s'enregistrent ici (set d'asyncio.Queue)
_sse_subscribers: set = set()


def _is_enabled() -> bool:
    try:
        from config import RADAR_ENABLED
        return bool(RADAR_ENABLED)
    except Exception:
        return True


def _get_sensitive_fields() -> frozenset[str]:
    try:
        from config import RADAR_SENSITIVE_FIELDS
        return frozenset(f.lower() for f in RADAR_SENSITIVE_FIELDS)
    except Exception:
        from web.radar.sanitize import _DEFAULT_SENSITIVE
        return _DEFAULT_SENSITIVE


def _get_text_preview_max() -> int:
    try:
        from config import RADAR_TEXT_PREVIEW_MAX
        return int(RADAR_TEXT_PREVIEW_MAX)
    except Exception:
        return 300


def _fallback_log(msg: str) -> None:
    """Écrit dans data/radar/fallback.log en cas d'erreur Radar interne."""
    try:
        p = Path("data/radar/fallback.log")
        p.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with p.open("a", encoding="utf-8") as f:
            f.write(f"{ts} {msg}\n")
    except Exception:
        pass


def _truncate_strings(data: Any, max_chars: int) -> Any:
    """Tronque les chaînes trop longues dans un dict/list."""
    if isinstance(data, str):
        return data[:max_chars] + "…" if len(data) > max_chars else data
    if isinstance(data, dict):
        return {k: _truncate_strings(v, max_chars) for k, v in data.items()}
    if isinstance(data, list):
        return [_truncate_strings(v, max_chars) for v in data]
    return data


def _notify_sse(evt: dict) -> None:
    """Pousse l'événement dans toutes les files SSE actives (sans bloquer)."""
    dead: set = set()
    for q in _sse_subscribers:
        try:
            q.put_nowait(evt)
        except Exception:
            dead.add(q)
    _sse_subscribers.difference_update(dead)


def subscribe_sse():
    """Crée et enregistre une asyncio.Queue pour les SSE. Retourne la queue."""
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _sse_subscribers.add(q)
    return q


def unsubscribe_sse(q) -> None:
    _sse_subscribers.discard(q)


# ─── emit_event ───────────────────────────────────────────────────────────────

def emit_event(
    type: str,
    level: str = "info",
    message: str = "",
    module: str | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    job_id: str | None = None,
    document_id: str | None = None,
    user_id: str | None = None,
    metadata: dict | None = None,
    duration_ms: int | None = None,
    error_code: str | None = None,
    exception: BaseException | None = None,
) -> None:
    """
    Émet un événement structuré vers le store Radar.
    Ne lève jamais d'exception — ADA ne doit jamais être bloqué par Radar.
    """
    try:
        if not _is_enabled():
            return

        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        evt_id = f"evt_{uuid.uuid4().hex[:20]}"

        from web.radar.sanitize import redact_sensitive_fields, safe_serialize
        sensitive = _get_sensitive_fields()
        max_chars = _get_text_preview_max()

        # Sanitize + troncature des métadonnées
        safe_meta: dict = {}
        if metadata:
            safe_meta = redact_sensitive_fields(safe_serialize(metadata), sensitive)
            safe_meta = _truncate_strings(safe_meta, max_chars)

        # Info exception (tronquée)
        exc_info: dict = {}
        if exception is not None:
            exc_info = {
                "type": type(exception).__name__,
                "message": str(exception)[:500],
                "traceback": traceback.format_exc()[:1000],
            }

        evt: dict = {
            "id": evt_id,
            "timestamp": ts,
            "level": level,
            "type": type,
            "module": module,
            "message": message,
            "session_id": session_id,
            "request_id": request_id,
            "job_id": job_id,
            "document_id": document_id,
            "user_id": user_id,
            "duration_ms": duration_ms,
            "error_code": error_code,
            "metadata": safe_meta,
            "exception_info": exc_info,
        }

        # Persistance SQLite
        from web.radar.store import init_db, insert_event
        init_db()
        insert_event(evt)

        # Notification SSE (temps réel)
        _notify_sse(evt)

    except Exception as exc_radar:  # noqa: BLE001
        try:
            _fallback_log(f"[Radar] emit_event error for type={type!r}: {exc_radar}")
        except Exception:
            pass
