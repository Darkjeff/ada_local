"""
Runtime State Engine — collecte l'état factuel des services sans passer par le LLM.

Usage:
    from core.runtime_state import runtime_state
    runtime_state.refresh()          # lance les checks (bloquant, ~3-5 s)
    state = runtime_state.get_state()
    text  = runtime_state.format_infra_status_fr()
"""

import subprocess
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Individual check functions — each returns a dict, never raises
# ---------------------------------------------------------------------------

def _check_ollama(ollama_url: str) -> dict:
    """GET /tags — vérifie qu'Ollama répond."""
    try:
        import requests
        r = requests.get(f"{ollama_url.rstrip('/')}/tags", timeout=3)
        if r.status_code == 200:
            models = r.json().get("models", [])
            return {"status": "online", "details": f"{len(models)} modèle(s)"}
        return {"status": "offline", "details": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "offline", "details": str(e)[:80]}


def _check_n8n(n8n_url: str) -> dict:
    """GET /healthz — vérifie que n8n répond."""
    try:
        import requests
        r = requests.get(f"{n8n_url.rstrip('/')}/healthz", timeout=3)
        if r.status_code == 200:
            return {"status": "online", "details": ""}
        return {"status": "offline", "details": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "offline", "details": str(e)[:80]}


def _check_home_assistant(ha_url: str, ha_token: str) -> dict:
    """GET /api/ avec Bearer token — vérifie Home Assistant."""
    if not ha_url or not ha_token:
        return {"status": "unknown", "details": "non configuré"}
    try:
        import requests
        r = requests.get(
            f"{ha_url.rstrip('/')}/api/",
            headers={"Authorization": f"Bearer {ha_token}"},
            timeout=3,
        )
        if r.status_code == 200:
            return {"status": "online", "details": ""}
        return {"status": "offline", "details": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "offline", "details": str(e)[:80]}


def _check_navidrome(nav_url: str, user: str, password: str) -> dict:
    """Subsonic ping.view — vérifie Navidrome."""
    if not nav_url:
        return {"status": "unknown", "details": "non configuré"}
    try:
        import requests
        r = requests.get(
            f"{nav_url.rstrip('/')}/rest/ping.view",
            params={"u": user, "p": password, "v": "1.16.0", "c": "ada", "f": "json"},
            timeout=3,
        )
        if r.status_code == 200:
            body = r.json()
            if body.get("subsonic-response", {}).get("status") == "ok":
                return {"status": "online", "details": ""}
        return {"status": "offline", "details": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "offline", "details": str(e)[:80]}


def _check_docker() -> dict:
    """docker ps — liste les containers actifs."""
    try:
        out = subprocess.check_output(
            ["docker", "ps", "--format", "{{.Names}}|{{.Status}}|{{.Image}}"],
            timeout=5,
            stderr=subprocess.DEVNULL,
        )
        containers = []
        for line in out.decode().strip().splitlines():
            if line:
                parts = line.split("|")
                containers.append({
                    "name":   parts[0] if len(parts) > 0 else "",
                    "status": parts[1] if len(parts) > 1 else "",
                    "image":  parts[2] if len(parts) > 2 else "",
                })
        return {"status": "online", "containers": containers}
    except FileNotFoundError:
        return {"status": "unknown", "containers": []}
    except Exception:
        return {"status": "offline", "containers": []}


def _check_cuda() -> bool | None:
    """Détecte CUDA sans planter si torch n'est pas installé."""
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return None


def _check_voice() -> dict:
    """Détecte la disponibilité des modules STT/TTS."""
    stt = tts = None
    try:
        import core.stt  # noqa: F401
        stt = True
    except Exception:
        stt = False
    try:
        import core.tts  # noqa: F401
        tts = True
    except Exception:
        tts = False
    return {"stt": stt, "tts": tts, "wake_word": None}


# ---------------------------------------------------------------------------
# RuntimeStateManager
# ---------------------------------------------------------------------------

class RuntimeStateManager:
    """
    Collecte l'état factuel de tous les services ADA.
    Thread-safe : refresh() peut être appelé depuis n'importe quel thread.
    get_state() retourne toujours un dict valide, même avant le premier refresh().
    """

    def __init__(self):
        self._state: dict[str, Any] = self._empty_state()

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Lance tous les checks et met à jour l'état interne. Ne lève jamais."""
        try:
            self._state = self._collect()
        except Exception as e:
            self._state["warnings"].append(f"refresh error: {e}")

    def get_state(self) -> dict:
        """Retourne l'état complet (dernière collecte)."""
        return self._state

    def get_infra_summary(self) -> dict:
        """Sous-ensemble services + docker, pratique pour l'UI."""
        s = self._state
        return {
            "services":   s.get("services", {}),
            "docker":     s.get("docker", {}),
            "warnings":   s.get("warnings", []),
            "updated_at": s.get("updated_at", ""),
        }

    def format_infra_status_fr(self) -> str:
        """Formate un résumé lisible en français. Ne lève jamais."""
        try:
            return self._format()
        except Exception as e:
            return f"⚠️ Impossible de récupérer l'état infra : {e}"

    # ── Internal ──────────────────────────────────────────────────────────────

    def _empty_state(self) -> dict:
        return {
            "services": {
                "ollama":         {"status": "unknown", "details": ""},
                "n8n":            {"status": "unknown", "details": ""},
                "home_assistant": {"status": "unknown", "details": ""},
                "navidrome":      {"status": "unknown", "details": ""},
            },
            "docker":     {"status": "unknown", "containers": []},
            "voice":      {"stt": None, "tts": None, "wake_word": None},
            "ai":         {"model": "", "cuda_available": None},
            "warnings":   [],
            "updated_at": "",
        }

    def _collect(self) -> dict:
        from config import OLLAMA_URL, RESPONDER_MODEL
        from core.settings_store import settings

        n8n_url  = settings.get("n8n.url", "http://localhost:5678")
        ha_url   = settings.get("home_assistant.url", "")
        ha_token = settings.get("home_assistant.token", "")

        nav_cfg  = settings.get("navidrome") or {}
        nav_url  = nav_cfg.get("url", "http://localhost:4533")
        nav_user = nav_cfg.get("user", "")
        nav_pass = nav_cfg.get("password", "")

        cuda = _check_cuda()
        warnings = []
        if cuda is False:
            warnings.append("CUDA indisponible, fallback CPU")

        return {
            "services": {
                "ollama":         _check_ollama(OLLAMA_URL),
                "n8n":            _check_n8n(n8n_url),
                "home_assistant": _check_home_assistant(ha_url, ha_token),
                "navidrome":      _check_navidrome(nav_url, nav_user, nav_pass),
            },
            "docker":     _check_docker(),
            "voice":      _check_voice(),
            "ai":         {"model": RESPONDER_MODEL, "cuda_available": cuda},
            "warnings":   warnings,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _format(self) -> str:
        s = self._state
        icons  = {"online": "🟢", "offline": "🔴", "unknown": "🟡"}
        labels = {
            "ollama":         "Ollama",
            "n8n":            "n8n",
            "home_assistant": "Home Assistant",
            "navidrome":      "Navidrome",
        }
        status_fr = {"online": "en ligne", "offline": "hors ligne", "unknown": "statut non vérifié"}

        lines = ["🖥️ *État infrastructure*\n"]

        for key, label in labels.items():
            svc    = s["services"].get(key, {})
            status = svc.get("status", "unknown")
            lines.append(f"{icons.get(status, '🟡')} {label} : {status_fr.get(status, status)}")

        docker     = s.get("docker", {})
        containers = docker.get("containers", [])
        if containers:
            lines.append("\n🐳 *Containers :*")
            for c in containers:
                lines.append(f"- {c['name']} : {c['status']}")
        elif docker.get("status") == "online":
            lines.append("\n🐳 Docker : aucun container actif")

        warnings = s.get("warnings", [])
        if warnings:
            lines.append("\n⚠️ *Alertes :*")
            for w in warnings:
                lines.append(f"- {w}")

        return "\n".join(lines)


# Module-level singleton
runtime_state = RuntimeStateManager()
