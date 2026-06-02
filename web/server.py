"""
ADA Web Plugin — FastAPI Server

Non-intrusive : ne modifie aucun fichier existant.
Lancer avec : python web_server.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Assurer que la racine du projet est dans sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx
import ssl as _ssl

# Contexte SSL permissif pour caméras Reolink (vieux cipher suites TLS)
_REOLINK_SSL = _ssl.create_default_context()
_REOLINK_SSL.set_ciphers("DEFAULT:@SECLEVEL=0")
_REOLINK_SSL.check_hostname = False
_REOLINK_SSL.verify_mode = _ssl.CERT_NONE

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse as _JSONResponse
from starlette.types import ASGIApp as _ASGIApp

from core.ha_control import ha_manager
from core.memory_store import memory_store
from core.runtime_state import runtime_state
from core.skill_manager import skill_manager
from core.settings_store import settings
from web.pipeline import process_message
# MODULE_SKILLS: module de mémoire procédurale SQLite FTS5
from core.skills import (
    init_db as _skills_init_db,
    seed_from_files as _skills_seed,
    run_maintenance as _skills_maintenance,
    list_skills as _skills_list,
    get_skill as _skills_get,
    save_skill as _skills_save,
    delete_skill as _skills_delete,
    archive_skill as _skills_archive,
    restore_skill as _skills_restore,
    promote_skill as _skills_promote,
)
from web.router_auth import router as _auth_router
from web.router_profiles import router as _profiles_router
from core.routes.profiles import initialize as _profiles_init

# ---------------------------------------------------------------------------
# Routes toujours publiques (même quand l'auth est activée)
# ---------------------------------------------------------------------------
_PUBLIC_PREFIXES = (
    "/api/auth/",
    "/static/",
    "/api/webhook/",   # webhooks entrants — auth propre par token secret
)
_PUBLIC_EXACT = {
    "/",
    "/manifest.json",
    "/sw.js",
    "/api/status",   # status dot visible avant auth
}


class _AuthMiddleware(BaseHTTPMiddleware):
    """Middleware JWT — actif uniquement quand auth.enabled=True."""

    async def dispatch(self, request: Request, call_next):
        if not settings.get("auth.enabled", False):
            return await call_next(request)

        path = request.url.path
        if path in _PUBLIC_EXACT:
            return await call_next(request)
        for prefix in _PUBLIC_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # Vérification du JWT
        from web.auth import extract_token, verify_jwt
        token = extract_token(request)
        if token and verify_jwt(token):
            return await call_next(request)

        if path.startswith("/api/"):
            return _JSONResponse({"detail": "Non authentifié"}, status_code=401)
        # Page HTML → retourner quand même (le frontend affiche la vue auth)
        return await call_next(request)


# ---------------------------------------------------------------------------
app = FastAPI(title="ADA Mobile", docs_url=None, redoc_url=None)
app.add_middleware(_AuthMiddleware)
app.include_router(_auth_router)
app.include_router(_profiles_router)

# MODULE_SOCIETE: guard — router branché uniquement si module actif
from config import MODULES_ENABLED as _MODULES_ENABLED
if _MODULES_ENABLED.get("societe", False):
    from web.router_societe import router as _societe_router
    app.include_router(_societe_router)

# router_plugins : toujours actif — retourne liste vide si aucun plugin enregistré
from web.router_plugins import router as _plugins_router
app.include_router(_plugins_router)

# Webhooks entrants — Domoticz, n8n, Home Assistant, etc.
from web.router_webhook import router as _webhook_router
app.include_router(_webhook_router)

# routes_infra : Proxmox/PBS multi-instance — toujours monté, guard interne
from web.routes_infra import router as _infra_router
app.include_router(_infra_router)

# MODULE_DOCUMENTS: base documentaire RAG locale — toujours monté, guard interne
from web.router_documents import router as _documents_router
app.include_router(_documents_router)

_STATIC = Path(__file__).parent / "static"


class _NoCacheStaticFiles(StaticFiles):
    """StaticFiles avec Cache-Control: no-cache pour forcer la revalidation ETag."""
    def file_response(self, full_path, stat_result, scope, status_code=200):
        from starlette.staticfiles import NotModifiedResponse
        response = super().file_response(full_path, stat_result, scope, status_code)
        if not isinstance(response, NotModifiedResponse):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


app.mount("/static", _NoCacheStaticFiles(directory=str(_STATIC)), name="static")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

@app.on_event("startup")
async def _startup() -> None:
    # Ensure semantic memory DB is available for web chat sessions.
    memory_store.initialize()
    # Initialise la DB auth si l'auth est activée.
    if settings.get("auth.enabled", False):
        from web.auth_db import initialize as _auth_db_init
        _auth_db_init()
    # Initialise les profils d'affichage (tables + seed)
    _profiles_init()
    # MODULE_SOCIETE: enregistrement des plugins au démarrage web (tous modules)
    from core.plugin_registry import register_enabled_plugins, plugin_registry as _plugin_registry
    register_enabled_plugins()
    # Enrichir le semantic_router avec les utterances des plugins
    try:
        from core.semantic_router import inject_plugin_utterances as _inject_utt
        _inject_utt(_plugin_registry.combined_semantic_utterances())
    except Exception as _e:
        import logging as _log
        _log.getLogger(__name__).warning("[Server] inject_plugin_utterances: %s", _e)
    # Enregistrer les webhooks n8n des plugins
    try:
        from core.n8n_executor import n8n_executor as _n8n
        _n8n.register_plugin_webhooks(_plugin_registry.combined_n8n_webhooks())
    except Exception as _e:
        import logging as _log
        _log.getLogger(__name__).warning("[Server] register_plugin_webhooks: %s", _e)
    # MODULE_SKILLS: initialisation DB skills FTS5 + seed + maintenance
    try:
        _skills_init_db()
        _skills_seed()
        _skills_maintenance()
    except Exception as _e:
        import logging as _log
        _log.getLogger(__name__).warning("[Skills] Erreur init : %s", _e)
    # MODULE_DOCUMENTS: initialisation DB documentaire + indexation si activé
    try:
        from core.documents.documents_db import init_db as _docs_init_db
        _docs_init_db()
        from core.settings_store import settings as _settings_ref
        if _settings_ref.get("documents.enabled", False) and _settings_ref.get("documents.auto_index_on_startup", True):
            from core.documents.documents_indexer import index_all as _docs_index
            _docs_index(force=False)
    except Exception as _e:
        import logging as _log
        _log.getLogger(__name__).warning("[Documents] Erreur init : %s", _e)
    # Ping périodique des services infra (built-in + custom endpoints) toutes les 90s
    import asyncio as _aio
    async def _infra_poller():
        from core.runtime_state import runtime_state as _rs
        import concurrent.futures as _cf
        _pool = _cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix="infra-poll")
        while True:
            try:
                loop = _aio.get_event_loop()
                await loop.run_in_executor(_pool, _rs.refresh)
            except Exception:
                pass
            await _aio.sleep(90)
    _aio.create_task(_infra_poller())


# ---------------------------------------------------------------------------
# PWA obligatoire hors /static/
# ---------------------------------------------------------------------------

@app.get("/manifest.json")
async def manifest():
    return FileResponse(str(_STATIC / "manifest.json"), media_type="application/manifest+json")


@app.get("/sw.js")
async def service_worker():
    return FileResponse(str(_STATIC / "sw.js"), media_type="application/javascript")


# ---------------------------------------------------------------------------
# Shell HTML (SPA / PWA)
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    return (_STATIC / "index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message:         str
    history:         list[dict] = []
    company_context: str | None = None   # compat existant
    plugin_context:  str | None = None   # NOUVEAU : univers actif
    context_id:      str | None = None   # NOUVEAU : sous-contexte


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    Stream la réponse d'ADA en Server-Sent Events.
    Chaque event : data: {"text": "..."}\n\n
    Fin           : data: [DONE]\n\n
    """
    async def _sse():
        try:
            async for chunk in process_message(
                req.message,
                req.history,
                company_context=req.company_context,
                plugin_context=req.plugin_context,
                context_id=req.context_id,
            ):
                if chunk.startswith('\x00img\x00'):
                    img_url = chunk[5:]  # retire le préfixe \x00img\x00 (5 chars)
                    yield f"data: {json.dumps({'img_url': img_url})}\n\n"
                elif chunk.startswith('\x00think\x00'):
                    think_text = chunk[7:]  # \x00think\x00 = 7 chars
                    yield f"data: {json.dumps({'thinking': think_text})}\n\n"
                elif chunk.startswith('{"__type"'):
                    # Carte de confirmation — envoyer directement sans double-wrapping
                    yield f"data: {chunk}\n\n"
                else:
                    yield f"data: {json.dumps({'text': chunk})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        _sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ConfirmRequest(BaseModel):
    func:   str
    params: dict = {}


@app.post("/api/plugins/confirm")
async def plugins_confirm(req: ConfirmRequest, request: Request):
    """Exécute une action Proxmox après confirmation de l'utilisateur."""
    from core.plugin_registry import plugin_registry as _pr
    from core.async_runner import run_async
    # Sécurité : seules les fonctions à confirmation sont exécutables ici
    _ALLOWED = {
        "vm_backup", "vm_power", "vm_snapshot", "vm_restore",
        "node_reboot", "pbs_backup_run", "pbs_restore",
    }
    if req.func not in _ALLOWED:
        return {"success": False, "message": f"Action '{req.func}' non autorisée via cet endpoint."}
    try:
        result = _pr.dispatch_action(req.func, req.params)
        if result is None:
            return {"success": False, "message": "Plugin introuvable pour cette action."}
        return result
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/api/status")
async def status():
    """Vérifie la connexion Ollama."""
    import httpx
    from config import OLLAMA_URL
    base = OLLAMA_URL.rstrip("/")
    if base.endswith("/api"):
        base = base[:-4]
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{base}/api/tags")
            ollama_ok = r.status_code == 200
    except Exception:
        ollama_ok = False
    return {"ada": "online", "ollama": "online" if ollama_ok else "offline"}


@app.get("/api/dashboard")
async def dashboard():
    """Données du tableau de bord : système + Ollama + infos ADA."""
    import httpx
    import psutil
    from config import OLLAMA_URL, RESPONDER_MODEL

    base = OLLAMA_URL.rstrip("/")
    if base.endswith("/api"):
        base = base[:-4]

    # Ollama status + modèles chargés
    ollama_ok = False
    loaded_models: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{base}/api/tags")
            if r.status_code == 200:
                ollama_ok = True
            # Modèles en mémoire
            rr = await client.get(f"{base}/api/ps")
            if rr.status_code == 200:
                loaded_models = [m["name"] for m in rr.json().get("models", [])]
    except Exception:
        pass

    # Ressources système
    cpu = psutil.cpu_percent(interval=0.3)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    # GPU VRAM (optionnel)
    vram: dict | None = None
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        vram = {
            "used_gb": round(mem.used / 1024**3, 1),
            "total_gb": round(mem.total / 1024**3, 1),
        }
    except Exception:
        pass

    return {
        "ollama": "online" if ollama_ok else "offline",
        "model": RESPONDER_MODEL,
        "loaded_models": loaded_models,
        "cpu_pct": round(cpu, 1),
        "ram": {
            "used_gb": round(ram.used / 1024**3, 1),
            "total_gb": round(ram.total / 1024**3, 1),
            "pct": ram.percent,
        },
        "disk": {
            "used_gb": round(disk.used / 1024**3, 1),
            "total_gb": round(disk.total / 1024**3, 1),
            "pct": round(disk.percent, 1),
        },
        "vram": vram,
    }


def _wmo_desc(code: int) -> str:
    """Convertit un code WMO en description météo française."""
    if code == 0:   return "Ciel dégagé"
    if code <= 2:   return "Partiellement nuageux"
    if code <= 3:   return "Nuageux"
    if code <= 48:  return "Brouillard"
    if code <= 55:  return "Bruine"
    if code <= 67:  return "Pluie"
    if code <= 77:  return "Neige"
    if code <= 82:  return "Averses"
    return "Orage"


@app.get("/api/dashboard/home")
async def dashboard_home():
    """Données enrichies pour la vue accueil : météo, tâches, appareils, news."""
    import asyncio

    user_name = settings.get("user.name", "User")
    lat = settings.get("weather.latitude", 48.8566)
    lon = settings.get("weather.longitude", 2.3522)
    city = settings.get("weather.city", "Paris")

    # --- Météo OpenMeteo (gratuit, sans clé) ---
    weather_data: dict = {"temp": None, "unit": "°C", "desc": "—", "code": 0, "city": city}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,weathercode"
            )
            if r.status_code == 200:
                cur = r.json().get("current", {})
                code = int(cur.get("weathercode", 0))
                temp = cur.get("temperature_2m")
                weather_data.update({
                    "temp": round(temp) if temp is not None else None,
                    "code": code,
                    "desc": _wmo_desc(code),
                })
    except Exception:
        pass

    # --- Tâches ---
    tasks_data: dict = {"pending": 0, "next": None}
    try:
        from core.tasks import TaskManager
        tm = TaskManager()
        all_tasks = tm.get_tasks()
        pending = [t for t in all_tasks if not t.get("completed")]
        tasks_data = {"pending": len(pending), "next": pending[0]["text"] if pending else None}
    except Exception:
        pass

    # --- Derniers capteurs Domoticz modifiés ---
    active_devices = 0
    kasa_status = "Domoticz non configuré"
    recent_devices: list = []
    try:
        domo_url = settings.get("domoticz.url", "").rstrip("/")
        domo_user = settings.get("domoticz.username", "")
        domo_pass = settings.get("domoticz.password", "")
        if domo_url:
            auth = (domo_user, domo_pass) if domo_user else None
            async with httpx.AsyncClient(timeout=4.0) as client:
                r = await client.get(
                    f"{domo_url}/json.htm",
                    params={"type": "devices", "filter": "all", "used": "true", "order": "LastUpdate"},
                    auth=auth,
                )
                if r.status_code == 200:
                    devs = r.json().get("result", [])
                    active_devices = len(devs)
                    kasa_status = f"{active_devices} appareil(s) Domoticz"
                    recent_devices = [
                        {
                            "name": d.get("Name", "?"),
                            "value": d.get("Data", d.get("Status", "?")),
                            "last_update": d.get("LastUpdate", "")[:16],
                        }
                        for d in devs[:4]
                    ]
    except Exception:
        pass

    # --- Dernière news (titre seulement, depuis cache ou RSS rapide) ---
    latest_news: dict | None = None
    news_count = 0
    try:
        import feedparser
        feed = feedparser.parse("https://www.lemonde.fr/rss/une.xml")
        entries = feed.entries
        news_count = len(entries)
        if entries:
            latest_news = {
                "title": entries[0].get("title", ""),
                "source": feed.feed.get("title", "Le Monde"),
            }
    except Exception:
        pass

    return {
        "user_name": user_name,
        "weather": weather_data,
        "tasks": tasks_data,
        "active_devices": active_devices,
        "kasa_status": kasa_status,
        "news_count": news_count,
        "latest_news": latest_news,
        "recent_devices": recent_devices,
    }


# ---------------------------------------------------------------------------
# Planificateur — Tâches, Alarmes, Timers
# ---------------------------------------------------------------------------
from core.tasks import task_manager as _tm

class _TaskBody(BaseModel):
    text: str

class _TaskToggle(BaseModel):
    completed: bool

class _AlarmBody(BaseModel):
    time: str
    label: str = ""

class _TimerBody(BaseModel):
    label: str
    duration: str  # ex: "10 minutes", "1 hour 30 minutes"

@app.get("/api/tasks")
async def tasks_list():
    return _tm.get_tasks()

@app.post("/api/tasks")
async def tasks_add(body: _TaskBody):
    t = _tm.add_task(body.text)
    if t:
        return t
    from fastapi import HTTPException
    raise HTTPException(500, "Erreur création tâche")

@app.patch("/api/tasks/{task_id}")
async def tasks_toggle(task_id: str, body: _TaskToggle):
    _tm.toggle_task(task_id, body.completed)
    return {"ok": True}

@app.delete("/api/tasks/{task_id}")
async def tasks_delete(task_id: str):
    _tm.delete_task(task_id)
    return {"ok": True}

@app.get("/api/planner/alarms")
async def alarms_list():
    return _tm.get_alarms()

@app.post("/api/planner/alarms")
async def alarms_add(body: _AlarmBody):
    alarm_id = _tm.add_alarm(body.time, body.label)
    if alarm_id:
        return {"id": alarm_id, "time": body.time, "label": body.label}
    from fastapi import HTTPException
    raise HTTPException(500, "Erreur création alarme")

@app.delete("/api/planner/alarms/{alarm_id}")
async def alarms_delete(alarm_id: str):
    _tm.delete_alarm(alarm_id)
    return {"ok": True}

@app.get("/api/planner/timers")
async def timers_list():
    try:
        from core.function_executor import executor as _exec
        result = []
        with _exec._timer_lock:
            for label, t in list(_exec.active_timers.items()):
                result.append({
                    "label": label,
                    "duration_seconds": t.duration_seconds,
                    "remaining_seconds": t.remaining_seconds,
                    "is_expired": t.is_expired,
                    "start_time": t.start_time,
                })
        return result
    except Exception:
        return []

@app.post("/api/planner/timers")
async def timers_add(body: _TimerBody):
    from fastapi import HTTPException
    try:
        from core.function_executor import executor as _exec
        result = _exec.execute("set_timer", {"duration": body.duration, "label": body.label})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Durée invalide"))
    return {"ok": True, "message": result["message"]}

@app.delete("/api/planner/timers/{label}")
async def timers_delete(label: str):
    try:
        from core.function_executor import executor as _exec
        with _exec._timer_lock:
            _exec.active_timers.pop(label, None)
        return {"ok": True}
    except Exception:
        return {"ok": True}

# ---------------------------------------------------------------------------
# Mémoire sémantique
# ---------------------------------------------------------------------------

@app.get("/api/memory/stats")
async def memory_stats():
    return memory_store.stats()


@app.get("/api/memory/recent")
async def memory_recent(limit: int = 50):
    from datetime import datetime
    items = memory_store.recent(limit=limit)
    for m in items:
        m["ts_fmt"] = datetime.fromtimestamp(m["timestamp"]).strftime("%d/%m %H:%M")
    return items


# ---------------------------------------------------------------------------
# Briefing — sources RSS configurables + mots-clés
# ---------------------------------------------------------------------------
_BRIEFING_DEFAULT_SOURCES = [
    {"url": "https://news.google.com/rss?hl=fr&gl=FR&ceid=FR:fr",                          "name": "Top Stories",  "category": "Top Stories"},
    {"url": "https://news.google.com/rss/search?q=technology&hl=fr&gl=FR&ceid=FR:fr",      "name": "Technology",   "category": "Technology"},
    {"url": "https://news.google.com/rss/search?q=science&hl=fr&gl=FR&ceid=FR:fr",         "name": "Science",      "category": "Science"},
    {"url": "https://news.google.com/rss/search?q=marchés+bourse&hl=fr&gl=FR&ceid=FR:fr",  "name": "Markets",      "category": "Markets"},
    {"url": "https://news.google.com/rss/search?q=culture+cinéma&hl=fr&gl=FR&ceid=FR:fr",  "name": "Culture",      "category": "Culture"},
]
_briefing_cache: dict = {}   # {cache_key: {"ts": float, "data": list}}
_BRIEFING_TTL = 900          # 15 min

def _briefing_fetch(sources: list, keywords: list[str]) -> list:
    """Lit les flux RSS et filtre par mots-clés (léger, sans IA)."""
    import time, feedparser as _fp
    articles = []
    seen: set = set()
    kw_low = [k.lower() for k in keywords if k.strip()]
    for src in sources:
        try:
            feed = _fp.parse(src["url"])
            for entry in feed.entries[:10]:
                title = entry.get("title", "").strip()
                if not title or title in seen:
                    continue
                summary = entry.get("summary", "")
                # Filtre mots-clés
                if kw_low:
                    haystack = (title + " " + summary).lower()
                    if not any(k in haystack for k in kw_low):
                        continue
                seen.add(title)
                # Nom de source précis (Google News encapsule la source réelle)
                src_name = src["name"]
                if hasattr(entry, "source") and hasattr(entry.source, "title"):
                    src_name = entry.source.title
                articles.append({
                    "title":    title,
                    "source":   src_name,
                    "date":     entry.get("published", ""),
                    "url":      entry.get("link", ""),
                    "category": src.get("category", "Général"),
                    "image":    "",
                })
        except Exception:
            pass
    return articles


@app.get("/api/briefing/feed")
async def briefing_feed(refresh: bool = False):
    import time, asyncio
    sources  = settings.get("briefing.sources",  None) or _BRIEFING_DEFAULT_SOURCES
    keywords = settings.get("briefing.keywords", [])
    cache_key = "feed"
    cached = _briefing_cache.get(cache_key)
    if not refresh and cached and (time.time() - cached["ts"]) < _BRIEFING_TTL:
        return cached["data"]
    loop = asyncio.get_event_loop()
    articles = await loop.run_in_executor(None, _briefing_fetch, sources, keywords)
    _briefing_cache[cache_key] = {"ts": time.time(), "data": articles}
    return articles


@app.get("/api/briefing/config")
async def briefing_config():
    return {
        "sources":  settings.get("briefing.sources",  None) or _BRIEFING_DEFAULT_SOURCES,
        "keywords": settings.get("briefing.keywords", []),
    }


class _BriefingConfigBody(BaseModel):
    sources:  list | None = None
    keywords: list | None = None


@app.put("/api/briefing/config")
async def briefing_save_config(body: _BriefingConfigBody):
    if body.sources  is not None: settings.set("briefing.sources",  body.sources)
    if body.keywords is not None: settings.set("briefing.keywords", body.keywords)
    _briefing_cache.clear()   # invalide le cache
    return {"ok": True}


@app.get("/api/memory/consolidated")
async def memory_consolidated(days: int = 5):
    return memory_store.get_consolidated(days=days)


class MemorySearchRequest(BaseModel):
    query: str


@app.post("/api/memory/search")
async def memory_search(req: MemorySearchRequest):
    from datetime import datetime
    if req.query.strip():
        items = memory_store.search(req.query, limit=50, min_words=1)
    else:
        items = memory_store.recent(limit=50)
    for m in items:
        m["ts_fmt"] = datetime.fromtimestamp(m["timestamp"]).strftime("%d/%m %H:%M")
    return items


@app.delete("/api/memory/{memory_id}")
async def memory_delete(memory_id: int):
    memory_store.delete(memory_id)
    return {"ok": True}


@app.post("/api/memory/consolidate")
async def memory_consolidate():
    """Lance la consolidation mémorielle en tâche de fond."""
    import asyncio
    from datetime import date

    async def _run():
        from core.memory_consolidator import consolidate_today
        try:
            consolidate_today(force=True)
        except Exception as exc:
            print(f"[Web] Consolidation error: {exc}")

    asyncio.create_task(_run())
    return {"status": "running"}


@app.post("/api/admin/restart")
async def admin_restart():
    """Redémarre le serveur web ADA (re-exec du process)."""
    import asyncio, os, sys

    async def _do():
        await asyncio.sleep(0.6)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    asyncio.create_task(_do())
    return {"status": "restarting"}


@app.get("/api/page/home")
async def page_home():
    """Entités domotiques unifiées (Kasa, HA, Domoticz) pour la page Domotique."""
    import asyncio
    from core.unified_entities import unified_entity_service
    from core.runtime_state import runtime_state

    loop = asyncio.get_event_loop()
    entities = await loop.run_in_executor(
        None,
        lambda: unified_entity_service.get_unified_entities(force_refresh=True),
    )

    serialized = [
        {
            "id":       e.id,
            "name":     e.name,
            "type":     e.type,
            "zone":     e.zone,
            "state":    e.state,
            "provider": e.provider,
            "attributes": {
                k: v for k, v in (e.attributes or {}).items()
                if k in ("brightness", "temperature", "humidity", "battery",
                         "device_class", "unit_of_measurement", "volume_level")
            },
        }
        for e in entities
    ]

    # Statuts providers : cross-référencer avec runtime_state (HA, Domoticz)
    # et dériver Kasa depuis le nombre d'entités récupérées.
    # Si les données infra sont périmées (>120s), on relance un refresh.
    from datetime import datetime, timezone as _tz
    state_snapshot = runtime_state.get_state()
    updated_at = state_snapshot.get("updated_at", "")
    try:
        age_s = (datetime.now(_tz.utc) - datetime.fromisoformat(updated_at)).total_seconds()
    except Exception:
        age_s = 9999
    if age_s > 120:
        await loop.run_in_executor(None, runtime_state.refresh)

    infra_services = runtime_state.get_infra_summary().get("services", {})

    _PROVIDER_TO_INFRA = {
        "home_assistant": "home_assistant",
        "domoticz":       "domoticz",
    }
    _PROVIDER_LABELS = {
        "kasa":           "Kasa",
        "home_assistant": "Home Assistant",
        "domoticz":       "Domoticz",
    }

    raw_providers = {p.id: p for p in unified_entity_service.get_providers()}
    kasa_entity_count = sum(1 for e in entities if e.provider == "kasa")

    providers = []
    for pid, label in _PROVIDER_LABELS.items():
        if pid in _PROVIDER_TO_INFRA:
            svc = infra_services.get(_PROVIDER_TO_INFRA[pid], {})
            status = svc.get("status", "unknown")
        elif pid == "kasa":
            status = "online" if kasa_entity_count > 0 else "unknown"
        else:
            status = getattr(raw_providers.get(pid), "status", "unknown")
        providers.append({"id": pid, "name": label, "status": status})

    return {"entities": serialized, "count": len(serialized), "providers": providers}


@app.get("/api/page/infrastructure")
async def page_infrastructure():
    """État infrastructure pour la page desktop dédiée."""
    runtime_state.refresh()
    return runtime_state.get_infra_summary()


# ---------------------------------------------------------------------------
# Contrôle direct des entités domotiques
# ---------------------------------------------------------------------------

class _EntityToggle(BaseModel):
    on: Optional[bool] = None   # None = toggle, True = allume, False = éteint

@app.post("/api/entity/{entity_id}/toggle")
async def entity_toggle(entity_id: str, body: _EntityToggle):
    """Allume / éteint une entité domotique via le service unifié."""
    import asyncio
    from core.unified_entities import unified_entity_service
    loop = asyncio.get_event_loop()
    ok = await loop.run_in_executor(
        None,
        lambda: unified_entity_service.toggle_entity(entity_id, body.on)
    )
    return {"ok": ok, "entity_id": entity_id, "on": body.on}

@app.post("/api/scene/{scene_name}")
async def scene_activate(scene_name: str):
    """Active une scène HA (scene.<scene_name>) ou tombe en silence si absente."""
    import asyncio
    loop = asyncio.get_event_loop()
    ok = False
    try:
        from core.ha_control import ha_manager
        ha_entity = f"scene.{scene_name}"
        ok = await loop.run_in_executor(
            None,
            lambda: ha_manager.call_service("scene", "turn_on", ha_entity)
        )
    except Exception as e:
        print(f"[scene_activate] {scene_name}: {e}")
    return {"ok": ok, "scene": scene_name}


# ---------------------------------------------------------------------------
# Endpoints personnalisés (surveillance URLs custom)
# ---------------------------------------------------------------------------

class EndpointRequest(BaseModel):
    name: str
    url: str
    tags: list[str] = ["local"]


class EndpointTagsUpdate(BaseModel):
    tags: list[str]


# ---------------------------------------------------------------------------
# Paramètres ADA — CRUD complet
# ---------------------------------------------------------------------------

class SettingUpdate(BaseModel):
    key: str
    value: Any


@app.get("/api/settings")
async def get_settings_api():
    """Renvoie tous les paramètres courants."""
    from core.settings_store import settings as _s
    return _s._settings


@app.post("/api/settings")
async def update_setting(req: SettingUpdate):
    """Met à jour un paramètre par chemin pointé (ex: 'home_assistant.url')."""
    from core.settings_store import settings as _s
    _s.set(req.key, req.value)
    return {"ok": True}


@app.get("/api/ollama/models")
async def get_ollama_models():
    """Renvoie la liste des modèles Ollama installés."""
    from core.settings_store import settings as _s
    base = _s.get("ollama_url", "http://localhost:11434").rstrip("/")
    if base.endswith("/api"):
        base = base[:-4]
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{base}/api/tags")
            if r.status_code == 200:
                return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return []


class OllamaPullRequest(BaseModel):
    name: str


@app.post("/api/ollama/pull")
async def ollama_pull(body: OllamaPullRequest):
    """Pull un modèle Ollama. Retourne un SSE avec la progression."""
    from core.settings_store import settings as _s
    base = _s.get("ollama_url", "http://localhost:11434").rstrip("/")
    if base.endswith("/api"):
        base = base[:-4]
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nom du modèle requis")

    async def _stream():
        try:
            async with httpx.AsyncClient(timeout=600.0) as client:
                async with client.stream(
                    "POST", f"{base}/api/pull",
                    json={"name": name, "stream": True}
                ) as resp:
                    async for line in resp.aiter_lines():
                        if line:
                            yield f"data: {line}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")


@app.delete("/api/ollama/models/{model_name:path}")
async def ollama_delete_model(model_name: str):
    """Supprime un modèle Ollama installé."""
    from core.settings_store import settings as _s
    base = _s.get("ollama_url", "http://localhost:11434").rstrip("/")
    if base.endswith("/api"):
        base = base[:-4]
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.request("DELETE", f"{base}/api/delete", json={"name": model_name})
            if r.status_code in (200, 204):
                return {"ok": True}
            return {"ok": False, "detail": r.text}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/infra/endpoints")
async def list_custom_endpoints():
    from core.runtime_state import _load_custom_endpoints
    return _load_custom_endpoints()


@app.post("/api/infra/endpoints")
async def add_custom_endpoint_api(req: EndpointRequest):
    from core.runtime_state import add_custom_endpoint
    add_custom_endpoint(req.name.strip(), req.url.strip(), req.tags)
    return {"ok": True}


@app.patch("/api/infra/endpoints/{name}/tags")
async def update_endpoint_tags_api(name: str, req: EndpointTagsUpdate):
    from core.runtime_state import update_endpoint_tags
    ok = update_endpoint_tags(name, req.tags)
    return {"ok": ok}


@app.delete("/api/infra/endpoints/{name}")
async def remove_custom_endpoint_api(name: str):
    from core.runtime_state import remove_custom_endpoint
    found = remove_custom_endpoint(name)
    return {"ok": found}


class _ServiceHiddenBody(BaseModel):
    hidden: bool


class _ServiceTagsBody(BaseModel):
    tags: list[str]


class _UniverseBody(BaseModel):
    universe: str = ''


@app.get("/api/infra/services")
async def list_infra_services():
    """Retourne les services built-in avec statut, tags, hidden et universe."""
    from core.runtime_state import runtime_state, _BUILTIN_SERVICES, _load_service_overrides
    state = runtime_state.get_infra_summary()
    svcs = state.get("services", {})
    overrides = _load_service_overrides()
    result = []
    for name in _BUILTIN_SERVICES:
        svc = svcs.get(name, {"status": "unknown", "details": ""})
        ov = overrides.get(name, {})
        result.append({
            "name": name,
            "status": svc.get("status", "unknown"),
            "details": svc.get("details", ""),
            "tags": ov.get("tags", ["local"]),
            "hidden": ov.get("hidden", False),
            "universe": ov.get("universe", ""),
            "builtin": True,
        })
    return result


@app.patch("/api/infra/services/{name}/hidden")
async def update_service_hidden_api(name: str, body: _ServiceHiddenBody):
    from core.runtime_state import update_service_hidden
    update_service_hidden(name, body.hidden)
    return {"ok": True}


@app.patch("/api/infra/services/{name}/tags")
async def update_service_tags_api(name: str, body: _ServiceTagsBody):
    from core.runtime_state import update_service_tags
    update_service_tags(name, body.tags)
    return {"ok": True}


@app.patch("/api/infra/services/{name}/universe")
async def update_service_universe_api(name: str, body: _UniverseBody):
    from core.runtime_state import update_service_universe
    update_service_universe(name, body.universe)
    return {"ok": True}


@app.patch("/api/infra/endpoints/{name}/universe")
async def update_endpoint_universe_api(name: str, body: _UniverseBody):
    from core.runtime_state import update_endpoint_universe
    ok = update_endpoint_universe(name, body.universe)
    return {"ok": ok}


@app.get("/api/infra/docker/universes")
async def get_docker_universes():
    """Retourne la map container_name → universe."""
    from core.runtime_state import _load_docker_universe
    return _load_docker_universe()


@app.patch("/api/infra/docker/{name}/universe")
async def update_docker_universe_api(name: str, body: _UniverseBody):
    from core.runtime_state import update_docker_universe
    update_docker_universe(name, body.universe)
    return {"ok": True}


@app.get("/api/page/memory")
async def page_memory(limit: int = 30):
    """Récents souvenirs + stats pour la page Mémoire desktop."""
    safe_limit = max(5, min(limit, 100))
    return {
        "stats": memory_store.stats(),
        "recent": memory_store.recent(limit=safe_limit),
    }


@app.get("/api/page/skills")
async def page_skills():
    """Liste des skills chargées pour la page Compétences web."""
    skills = []
    for s in skill_manager.skills:
        skills.append(
            {
                "name": s.name,
                "description": s.description,
                "triggers": s.triggers,
                "always": bool(s.always),
                "body": s.body,
            }
        )
    return {"count": len(skills), "skills": skills}


# ---------------------------------------------------------------------------
# Caméras — proxy Reolink via config Domoticz
# ---------------------------------------------------------------------------

from fastapi import HTTPException  # noqa: E402


async def _fetch_domoticz_cameras() -> list[dict]:
    """Récupère la liste des caméras depuis Domoticz."""
    domo_url = settings.get("domoticz.url", "").rstrip("/")
    if not domo_url:
        return []
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get(f"{domo_url}/json.htm?type=cameras")
        data = r.json()
    return data.get("result", [])


def _ha_cameras_as_list() -> list[dict]:
    """Retourne les caméras HA sous le même format que Domoticz."""
    from core.camera_manager import camera_manager
    camera_manager.refresh()
    return [
        {"idx": ep.entity_id, "name": ep.friendly_name, "enabled": True}
        for ep in camera_manager.list_endpoints()
    ]


@app.get("/api/cameras")
async def list_cameras():
    """Liste des caméras : Domoticz en priorité, HA en fallback."""
    try:
        cams = await _fetch_domoticz_cameras()
        if cams:
            return {
                "cameras": [
                    {"idx": c["idx"], "name": c["Name"], "enabled": c.get("Enabled") == "true"}
                    for c in cams
                ]
            }
    except Exception:
        pass
    # Fallback Home Assistant
    try:
        return {"cameras": _ha_cameras_as_list(), "source": "ha"}
    except Exception as exc:
        return {"cameras": [], "error": str(exc)}


@app.get("/api/cameras/{idx}/snapshot")
async def camera_snapshot(idx: str):
    """Proxy JPEG du snapshot — Domoticz/Reolink ou HA selon la source."""
    # Caméra HA (entity_id commence par "camera.")
    if str(idx).startswith("camera."):
        jpg = ha_manager.get_camera_snapshot(idx)
        if jpg is None:
            raise HTTPException(status_code=502, detail="Snapshot HA indisponible.")
        return Response(content=jpg, media_type="image/jpeg",
                        headers={"Cache-Control": "no-store, no-cache"})

    # Caméra Domoticz
    try:
        cams = await _fetch_domoticz_cameras()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Domoticz inaccessible : {exc}")
    cam = next((c for c in cams if str(c.get("idx")) == str(idx)), None)
    if not cam:
        raise HTTPException(status_code=404, detail=f"Caméra {idx} introuvable.")
    protocol = "https" if cam.get("Protocol", 0) == 1 else "http"
    snap_url = f"{protocol}://{cam['Address']}:{cam['Port']}/{cam['ImageURL']}"
    try:
        async with httpx.AsyncClient(timeout=10, verify=_REOLINK_SSL) as client:
            snap = await client.get(snap_url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Caméra injoignable : {exc}")
    if snap.status_code != 200:
        raise HTTPException(status_code=502, detail="Snapshot indisponible.")
    return Response(
        content=snap.content,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store, no-cache"},
    )


class CameraAnalyzeRequest(BaseModel):
    question: str = "Décris ce que tu vois. Compte les véhicules et personnes visibles."


@app.post("/api/cameras/{idx}/analyze")
async def camera_analyze(idx: str, req: CameraAnalyzeRequest):
    """Analyse le snapshot de la caméra via gemma4 (vision LLM). SSE stream."""
    import base64
    from config import OLLAMA_URL

    # 1. Récupérer le snapshot (HA ou Domoticz)
    if str(idx).startswith("camera."):
        jpg = ha_manager.get_camera_snapshot(idx)
        if jpg is None:
            raise HTTPException(status_code=502, detail="Snapshot HA indisponible.")
        img_b64 = base64.b64encode(jpg).decode()
    else:
        try:
            cams = await _fetch_domoticz_cameras()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Domoticz inaccessible : {exc}")
        cam = next((c for c in cams if str(c.get("idx")) == str(idx)), None)
        if not cam:
            raise HTTPException(status_code=404, detail=f"Caméra {idx} introuvable.")
        protocol = "https" if cam.get("Protocol", 0) == 1 else "http"
        snap_url = f"{protocol}://{cam['Address']}:{cam['Port']}/{cam['ImageURL']}"
        try:
            async with httpx.AsyncClient(timeout=12, verify=_REOLINK_SSL) as client:
                snap = await client.get(snap_url)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Caméra injoignable : {exc}")
        if snap.status_code != 200:
            raise HTTPException(status_code=502, detail="Snapshot indisponible.")
        img_b64 = base64.b64encode(snap.content).decode()

    # 3. Stream gemma4 vision
    vision_model = settings.get("models.vision", "gemma4:latest") or "gemma4:latest"
    payload = {
        "model": vision_model,
        "messages": [{
            "role": "user",
            "content": req.question + " Réponds en français, sois précis et concis.",
            "images": [img_b64],
        }],
        "stream": True,
    }

    async def _gen():
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                async with client.stream("POST", f"{OLLAMA_URL}/chat", json=payload) as resp:
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                            token = chunk.get("message", {}).get("content", "")
                            if token:
                                yield f"data: {json.dumps({'token': token})}\n\n"
                            if chunk.get("done"):
                                yield "data: [DONE]\n\n"
                                return
                        except Exception:
                            continue
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------------------
# Skills CRUD
# ---------------------------------------------------------------------------


def _build_skill_content(name: str, description: str, triggers: list, body: str, always: bool = False) -> str:
    trigger_lines = "\n".join(f"  - {t}" for t in triggers) if triggers else "  []"
    always_line = "\nalways: true" if always else ""
    return (
        f"---\nname: {name}\ndescription: {description}\ntriggers:\n{trigger_lines}"
        f"{always_line}\n---\n{body}\n"
    )


class SkillPayload(BaseModel):
    description: str = ""
    triggers: list = []
    body: str = ""


class SkillCreatePayload(SkillPayload):
    name: str


@app.put("/api/skills/{name}")
async def update_skill(name: str, req: SkillPayload):
    """Met à jour description, triggers et body d'une skill existante."""
    skill = skill_manager.get(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' introuvable.")
    content = _build_skill_content(
        name=skill.name,
        description=req.description,
        triggers=req.triggers,
        body=req.body,
        always=skill.always,
    )
    skill.path.write_text(content, encoding="utf-8")
    skill_manager.reload()
    return {"ok": True}


@app.post("/api/skills")
async def create_skill(req: SkillCreatePayload):
    """Crée une nouvelle skill (dossier + SKILL.md)."""
    name = req.name.strip().lower().replace(" ", "_")
    if not name:
        raise HTTPException(status_code=400, detail="Nom invalide.")
    skills_dir = Path(__file__).resolve().parent.parent / "skills" / name
    if skills_dir.exists():
        raise HTTPException(status_code=409, detail=f"Skill '{name}' existe déjà.")
    skills_dir.mkdir(parents=True)
    skill_path = skills_dir / "SKILL.md"
    content = _build_skill_content(
        name=name,
        description=req.description,
        triggers=req.triggers,
        body=req.body,
    )
    skill_path.write_text(content, encoding="utf-8")
    skill_manager.reload()
    return {"ok": True, "name": name}


# ---------------------------------------------------------------------------
# Agent Web (Playwright + Ollama)
# ---------------------------------------------------------------------------

class WebAgentRequest(BaseModel):
    instruction: str


@app.post("/api/agent/web")
async def agent_web(request: Request, req: WebAgentRequest):
    """
    Lance l'agent web (Playwright headless + Ollama) et streame les étapes.
    Events SSE : {"type": "step"|"result"|"error", "text": "..."}
    Fin         : [DONE]
    """
    import re
    import httpx
    from playwright.async_api import async_playwright
    from config import OLLAMA_URL, RESPONDER_MODEL
    from core.settings_store import settings as app_settings
    from core.agent.text_agent import _SYSTEM_PROMPT

    MAX_STEPS = 12
    MAX_PAGE_CHARS = 4000

    def _evt(type_: str, text: str) -> str:
        return f"data: {json.dumps({'type': type_, 'text': text})}\n\n"

    async def _sse():
        goal = req.instruction.strip()
        if not goal:
            yield _evt("error", "Instruction vide.")
            yield "data: [DONE]\n\n"
            return

        ollama_url = app_settings.get("ollama_url", OLLAMA_URL)
        base = ollama_url.rstrip("/")
        if base.endswith("/api"):
            base = base[:-4]
        chat_url = f"{base}/api/chat"
        model = app_settings.get("models.chat", RESPONDER_MODEL)

        yield _evt("step", f"Démarrage : {goal}")

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                ctx = await browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
                page = await ctx.new_page()
                history: list[dict] = []

                for step in range(1, MAX_STEPS + 1):
                    if await request.is_disconnected():
                        yield _evt("step", "Arrêté par l'utilisateur.")
                        await browser.close()
                        return

                    # Résumé de la page courante
                    try:
                        url   = page.url
                        title = await page.title()
                        body  = await page.eval_on_selector("body", "el => el.innerText") or ""
                        body  = re.sub(r"\s{3,}", "\n", body)[:MAX_PAGE_CHARS]
                        links = await page.eval_on_selector_all(
                            "a[href]",
                            "els => els.slice(0,30).map(e => ({t:e.innerText.trim(), h:e.href})).filter(l=>l.t)",
                        )
                        links_str = "\n".join(
                            f"  [{l['t'][:60]}] {l['h'][:80]}" for l in links[:20]
                        )
                        page_summary = (
                            f"URL: {url}\nTitle: {title}\n"
                            f"Links:\n{links_str}\nBody:\n{body}"
                        )
                    except Exception as e:
                        page_summary = f"(erreur lecture page: {e})"

                    user_msg = (
                        f"Goal: {goal}\n\nStep {step}/{MAX_STEPS}\n\n"
                        f"Current page:\n{page_summary[:MAX_PAGE_CHARS + 500]}\n\n"
                        "Output the next JSON action:"
                    )
                    messages = [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        *history,
                        {"role": "user", "content": user_msg},
                    ]

                    yield _evt("step", f"[Étape {step}/{MAX_STEPS}] Réflexion…")

                    try:
                        async with httpx.AsyncClient(timeout=120.0) as client:
                            r = await client.post(
                                chat_url,
                                json={
                                    "model": model,
                                    "messages": messages,
                                    "stream": False,
                                    "think": False,
                                },
                            )
                            r.raise_for_status()
                            reply = r.json().get("message", {}).get("content", "").strip()
                    except Exception as e:
                        yield _evt("error", f"Erreur LLM : {e}")
                        await browser.close()
                        return

                    # Parse action JSON (cherche le premier objet JSON dans la réponse)
                    action = None
                    m = re.search(r"\{[^{}]+\}", reply, re.DOTALL)
                    if m:
                        try:
                            action = json.loads(m.group())
                        except Exception:
                            pass

                    if not action:
                        history.append({"role": "assistant", "content": reply})
                        history.append({"role": "user", "content": "Output a valid JSON action."})
                        yield _evt("step", f"[Étape {step}] Action invalide, nouvelle tentative…")
                        continue

                    history.append({"role": "assistant", "content": json.dumps(action)})
                    action_name = action.get("action", "")
                    yield _evt("step", f"[Étape {step}] → {action_name}: {json.dumps(action)[:120]}")

                    # Actions terminales
                    if action_name in ("done", "extract"):
                        result = action.get("result", reply)
                        yield _evt("result", result)
                        await browser.close()
                        return

                    # Exécution de l'action navigateur
                    try:
                        if action_name == "navigate":
                            await page.goto(
                                action.get("url", ""),
                                wait_until="domcontentloaded",
                                timeout=15_000,
                            )
                            # Fermer les dialogues de consentement
                            for sel in [
                                "button:has-text('Tout accepter')",
                                "button:has-text('Accept all')",
                                "button:has-text('J\\'accepte')",
                            ]:
                                try:
                                    btn = page.locator(sel).first
                                    if await btn.is_visible(timeout=800):
                                        await btn.click(timeout=2000)
                                        break
                                except Exception:
                                    pass

                        elif action_name == "click":
                            link_text = action.get("link_text", "")
                            await page.get_by_text(link_text, exact=False).first.click(timeout=5_000)
                            try:
                                await page.wait_for_load_state("domcontentloaded", timeout=10_000)
                            except Exception:
                                pass

                        elif action_name == "scroll_down":
                            await page.evaluate("window.scrollBy(0, window.innerHeight)")

                    except Exception as e:
                        yield _evt("step", f"  ✗ Erreur action : {e}")

                yield _evt("step", "Nombre maximum d'étapes atteint.")
                yield _evt("result", "L'agent n'a pas pu terminer la tâche dans la limite d'étapes.")
                await browser.close()

        except Exception as e:
            yield _evt("error", str(e))
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        _sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Marketing
# ---------------------------------------------------------------------------

class MarketingRequest(BaseModel):
    skill_name: str = "margepro"
    content_type: str
    reseau: str
    secteur: str
    ton: str
    brief: str = ""
    model: str = ""


@app.get("/api/marketing/skills")
async def marketing_skills():
    from core.marketing_executor import list_marketing_skills
    return list_marketing_skills()


@app.get("/api/marketing/models")
async def marketing_models():
    import httpx
    from config import OLLAMA_URL
    base = OLLAMA_URL.rstrip("/")
    if base.endswith("/api"):
        base = base[:-4]
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{base}/api/tags")
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


@app.get("/api/marketing/meta")
async def marketing_meta():
    from core.marketing_executor import CONTENT_TYPES, RESEAUX, SECTEURS, TONS
    return {
        "content_types": list(CONTENT_TYPES.keys()),
        "reseaux": RESEAUX,
        "secteurs": SECTEURS,
        "tons": TONS,
    }


@app.post("/api/marketing/generate")
async def marketing_generate(req: MarketingRequest):
    import asyncio
    from core.marketing_executor import generate_stream

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _run():
        generate_stream(
            content_type=req.content_type,
            reseau=req.reseau,
            secteur=req.secteur,
            ton=req.ton,
            brief=req.brief,
            skill_name=req.skill_name,
            model=req.model,
            on_token=lambda t: loop.call_soon_threadsafe(queue.put_nowait, ("token", t)),
            on_done=lambda _: loop.call_soon_threadsafe(queue.put_nowait, ("done", None)),
            on_error=lambda e: loop.call_soon_threadsafe(queue.put_nowait, ("error", e)),
        )

    loop.run_in_executor(None, _run)

    async def _sse():
        while True:
            kind, data = await queue.get()
            if kind == "token":
                yield f"data: {json.dumps({'text': data})}\n\n"
            elif kind == "done":
                yield "data: [DONE]\n\n"
                break
            else:
                yield f"data: {json.dumps({'error': data})}\n\n"
                yield "data: [DONE]\n\n"
                break

    return StreamingResponse(
        _sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/marketing/history")
async def marketing_history():
    from core.marketing_executor import get_history
    return get_history(limit=50)


@app.delete("/api/marketing/history/{entry_id}")
async def marketing_history_delete(entry_id: int):
    from core.marketing_executor import delete_history_entry
    delete_history_entry(entry_id)
    return {"ok": True}


class _TagsBody(BaseModel):
    tags: list[str]


@app.patch("/api/marketing/history/{entry_id}/tags")
async def marketing_history_tags(entry_id: int, req: _TagsBody):
    from core.marketing_executor import update_history_tags
    ok = update_history_tags(entry_id, req.tags)
    return {"ok": ok}


@app.get("/api/tags/available")
async def get_available_tags():
    """Retourne les tags disponibles : local + noms des societes."""
    tags = ["local"]
    try:
        from core.societe.company_model import company_model
        companies = company_model.list_companies()
        tags += [c["id"] for c in companies if c.get("id")]
    except Exception:
        pass
    return tags


@app.get("/api/societe/companies/{company_id}/tagged-items")
async def get_tagged_items(company_id: str):
    """Retourne les endpoints infra + contenus marketing taggés avec company_id,
    avec statut live depuis runtime_state."""
    from core.runtime_state import _load_custom_endpoints, runtime_state
    from core.marketing_executor import get_history
    live_services = runtime_state.get_infra_summary().get("services", {})
    raw_eps = [ep for ep in _load_custom_endpoints() if company_id in ep.get("tags", [])]
    endpoints = [{**ep, "status": live_services.get(ep["name"], {}).get("status", "unknown"),
                  "details": live_services.get(ep["name"], {}).get("details", "")} for ep in raw_eps]
    marketing = [h for h in get_history(limit=200) if company_id in h.get("tags", [])]
    return {"endpoints": endpoints, "marketing": marketing}


# ---------------------------------------------------------------------------
# MODULE_SKILLS: API AutoSkills (SQLite FTS5)
# Préfixe /api/autoskills/ pour éviter le conflit avec /api/skills (SKILL.md)
# ---------------------------------------------------------------------------

@app.get("/api/autoskills")
async def api_skills_list(status: str = "active", domain: str | None = None):
    """Liste les autoskills selon status (active|archived) et domaine optionnel."""
    return {"skills": _skills_list(status=status, domain=domain)}


@app.get("/api/autoskills/{skill_id}")
async def api_skills_get(skill_id: str):
    """Récupère une autoskill par ID."""
    skill = _skills_get(skill_id)
    if skill is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Skill introuvable")
    return skill


@app.post("/api/autoskills")
async def api_skills_create(body: dict):
    """Crée ou met à jour une autoskill."""
    name = body.get("name", "").strip()
    content = body.get("content", "").strip()
    if not name or not content:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="name et content requis")
    skill_id = _skills_save(
        name=name,
        content=content,
        domain=body.get("domain", "core"),
        source=body.get("source", "manual"),
        summary=body.get("summary", ""),
        priority=int(body.get("priority", 5)),
        skill_id=body.get("id"),
    )
    return {"id": skill_id, "ok": True}


@app.patch("/api/autoskills/{skill_id}/archive")
async def api_skills_archive(skill_id: str):
    """Archive une autoskill."""
    ok = _skills_archive(skill_id)
    return {"ok": ok}


@app.patch("/api/autoskills/{skill_id}/restore")
async def api_skills_restore(skill_id: str):
    """Restaure une autoskill archivée."""
    ok = _skills_restore(skill_id)
    return {"ok": ok}


@app.patch("/api/autoskills/{skill_id}/promote")
async def api_skills_promote(skill_id: str, body: dict | None = None):
    """Monte la priorité d'une autoskill."""
    new_priority = (body or {}).get("priority")
    ok = _skills_promote(skill_id, new_priority=new_priority)
    return {"ok": ok}


@app.delete("/api/autoskills/{skill_id}")
async def api_skills_delete(skill_id: str):
    """Supprime une autoskill (refusé si protégée)."""
    ok = _skills_delete(skill_id)
    if not ok:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Skill protégée ou introuvable")
    return {"ok": True}


@app.patch("/api/autoskills/{skill_id}")
async def api_skills_update(skill_id: str, body: dict):
    """Mise à jour partielle d'une autoskill (name, summary, content, priority, domain)."""
    skill = _skills_get(skill_id)
    if skill is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Skill introuvable")
    updated_id = _skills_save(
        skill_id=skill_id,
        name=body.get("name", skill["name"]),
        content=body.get("content", skill["content"]),
        domain=body.get("domain", skill["domain"]),
        source=skill.get("source", "manual"),
        summary=body.get("summary", skill.get("summary", "")),
        priority=int(body.get("priority", skill["priority"])),
    )
    return {"id": updated_id, "ok": True}


@app.post("/api/autoskills/{skill_id}/feedback")
async def api_skills_feedback(skill_id: str, body: dict):
    """Enregistre un feedback utilisateur sur une autoskill."""
    feedback = body.get("feedback", "").strip()
    if feedback not in ("positive", "negative", "neutral"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="feedback doit être positive|negative|neutral")
    from core.skills import get_skill
    skill = get_skill(skill_id)
    if skill is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Skill introuvable")
    # Feedback positif → record_success (incrémente usage + auto-promotion)
    if feedback == "positive":
        from core.skills import record_success
        record_success(skill_id)
    # Stocker dans autoskill_feedback
    try:
        from core.skills.skills_db import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO autoskill_feedback (skill_id, session_id, request_id, feedback, reason) VALUES (?,?,?,?,?)",
            (skill_id, body.get("session_id"), body.get("request_id"), feedback, body.get("reason", "")),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    return {"ok": True, "feedback": feedback}


@app.post("/api/autoskills/maintenance")
async def api_skills_maintenance():
    """Lance la maintenance manuelle des autoskills."""
    result = _skills_maintenance()
    return result
