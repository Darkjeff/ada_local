"""web/radar/sanitize.py — Masquage des champs sensibles pour Radar."""
from __future__ import annotations

from typing import Any

_REDACTED = "[REDACTED]"

_DEFAULT_SENSITIVE: frozenset[str] = frozenset({
    "api_key", "token", "access_token", "refresh_token",
    "authorization", "password", "secret", "cookie",
    "session_cookie", "private_key", "x-api-key", "x_api_key",
})


def redact_sensitive_fields(
    data: Any,
    sensitive_fields: frozenset[str] | None = None,
) -> Any:
    """Parcourt récursivement dict/list et remplace les champs sensibles par [REDACTED]."""
    if sensitive_fields is None:
        try:
            from config import RADAR_SENSITIVE_FIELDS
            sensitive_fields = frozenset(f.lower() for f in RADAR_SENSITIVE_FIELDS)
        except Exception:
            sensitive_fields = _DEFAULT_SENSITIVE

    if isinstance(data, dict):
        return {
            k: _REDACTED if k.lower() in sensitive_fields
            else redact_sensitive_fields(v, sensitive_fields)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [redact_sensitive_fields(item, sensitive_fields) for item in data]
    return data


def safe_serialize(obj: Any) -> Any:
    """Rend n'importe quel objet sérialisable en JSON (sans lever d'erreur)."""
    if isinstance(obj, dict):
        return {k: safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [safe_serialize(v) for v in obj]
    try:
        import json
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)
