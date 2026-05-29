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

from core.memory_store import memory_store
from core.runtime_state import runtime_state
from core.skill_manager import skill_manager
from core.settings_store import settings
from web.pipeline import process_message

# ---------------------------------------------------------------------------
app = FastAPI(title="ADA Mobile", docs_url=None, redoc_url=None)

_STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


@app.on_event("startup")
async def _startup() -> None:
    # Ensure semantic memory DB is available for web chat sessions.
    memory_store.initialize()


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
    message: str
    history: list[dict] = []


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    Stream la réponse d'ADA en Server-Sent Events.
    Chaque event : data: {"text": "..."}\n\n
    Fin           : data: [DONE]\n\n
    """
    async def _sse():
        try:
            async for chunk in process_message(req.message, req.history):
                if chunk.startswith('\x00img\x00'):
                    img_url = chunk[5:]  # retire le préfixe \x00img\x00 (5 chars)
                    yield f"data: {json.dumps({'img_url': img_url})}\n\n"
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


@app.get("/api/memory/consolidated")
async def memory_consolidated(days: int = 5):
    return memory_store.get_consolidated(days=days)


class MemorySearchRequest(BaseModel):
    query: str


@app.post("/api/memory/search")
async def memory_search(req: MemorySearchRequest):
    from datetime import datetime
    if req.query.strip():
        items = memory_store.search(req.query, limit=50)
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
# Endpoints personnalisés (surveillance URLs custom)
# ---------------------------------------------------------------------------

class EndpointRequest(BaseModel):
    name: str
    url: str


@app.get("/api/infra/endpoints")
async def list_custom_endpoints():
    from core.runtime_state import _load_custom_endpoints
    return _load_custom_endpoints()


@app.post("/api/infra/endpoints")
async def add_custom_endpoint_api(req: EndpointRequest):
    from core.runtime_state import add_custom_endpoint
    add_custom_endpoint(req.name.strip(), req.url.strip())
    return {"ok": True}


@app.delete("/api/infra/endpoints/{name}")
async def remove_custom_endpoint_api(name: str):
    from core.runtime_state import remove_custom_endpoint
    found = remove_custom_endpoint(name)
    return {"ok": found}


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


@app.get("/api/cameras")
async def list_cameras():
    """Liste des caméras configurées dans Domoticz (sans mots de passe)."""
    try:
        cams = await _fetch_domoticz_cameras()
        return {
            "cameras": [
                {"idx": c["idx"], "name": c["Name"], "enabled": c.get("Enabled") == "true"}
                for c in cams
            ]
        }
    except Exception as exc:
        return {"cameras": [], "error": str(exc)}


@app.get("/api/cameras/{idx}/snapshot")
async def camera_snapshot(idx: str):
    """Proxy JPEG du snapshot Reolink pour la caméra Domoticz {idx}."""
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

    # 1. Récupérer la config caméra
    try:
        cams = await _fetch_domoticz_cameras()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Domoticz inaccessible : {exc}")
    cam = next((c for c in cams if str(c.get("idx")) == str(idx)), None)
    if not cam:
        raise HTTPException(status_code=404, detail=f"Caméra {idx} introuvable.")

    # 2. Snapshot
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
