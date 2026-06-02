"""ADA Web Plugin — Chat Pipeline aligned with ADA app behavior."""
from __future__ import annotations

import json
import os
import re
import sys
import time as _time
import uuid as _uuid
from typing import AsyncGenerator

import httpx

# Ensure project root is in sys.path when run standalone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import OLLAMA_URL, RESPONDER_MODEL, FUNCTIONS
from core.function_executor import executor as function_executor
from core.memory_store import memory_store
from core.semantic_router import get_route as semantic_route
from core.skill_manager import skill_manager

# ---------------------------------------------------------------------------
# Ollama endpoint (normalise que OLLAMA_URL finisse en /api ou non)
# ---------------------------------------------------------------------------
_base = OLLAMA_URL.rstrip("/")
if _base.endswith("/api"):
    _base = _base[:-4]
_OLLAMA_CHAT_URL = f"{_base}/api/chat"


def _chat_model() -> str:
    """Lit le modèle de chat depuis settings (dynamique, sans redémarrage)."""
    from core.settings_store import settings as _s
    return _s.get("models.chat", RESPONDER_MODEL) or RESPONDER_MODEL


def _chat_url() -> str:
    """Construit l'URL chat Ollama depuis settings (dynamique, sans redémarrage)."""
    from core.settings_store import settings as _s
    url = _s.get("ollama_url", OLLAMA_URL) or OLLAMA_URL
    b = url.rstrip("/")
    if b.endswith("/api"):
        b = b[:-4]
    return f"{b}/api/chat"

# ---------------------------------------------------------------------------
# Pattern : "ajoute l'URL https://... à l'infra" (et variantes)
_ADD_URL_RE = re.compile(
    r"(?:ajoute|surveille|monitore|vérifie|watch)\b"
    r".*?((?:https?://)?[a-zA-Z0-9][a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}(?:/[^\s<>\"\)\]]*)?)",
    re.IGNORECASE,
)
# Extraction du/des tags depuis "avec le tag X" ou "avec les tags X, Y"
_ADD_TAG_RE = re.compile(
    r"avec le(?:s)? tags?\s+([a-zA-Z0-9_,\s]+?)(?:\.|$|\s+(?:et|à|a)\b)",
    re.IGNORECASE,
)


# Triggers de recherche web → délégation à l'agent Playwright
# ---------------------------------------------------------------------------
_WEB_TRIGGERS = (
    "cherche sur le web", "cherche sur internet", "cherche en ligne",
    "recherche sur le web", "recherche sur internet", "recherche en ligne",
    "fais une recherche web", "fais une recherche sur le web",
    "fais une recherche sur internet", "trouve sur internet", "trouve sur le web",
    "google", "bing", "search the web", "search on the web",
    "dernières nouvelles", "actualités récentes", "latest news",
    "cherche l'info", "cherche des infos sur le web",
)


# ---------------------------------------------------------------------------
# Triggers déterministes: évitent un passage LLM inutile pour l'état infra.
_INFRA_TRIGGERS = frozenset(
    {
        "état infra",
        "etat infra",
        "status infra",
        "infrastructure status",
        "état de l'infra",
        "etat de l infra",
        "état de l'infrastructure",
        "etat de l infrastructure",
        "infrastructure",
    }
)

# Routing déterministe pour lister les VMs / CTs Proxmox
# Exemples : "liste les VM", "liste mes CT de ot-mutu", "affiche les containers", "montre les VMs"
_PROXMOX_VM_LIST_RE = re.compile(
    r"\b(liste[rz]?|affiche[rz]?|montre[rz]?|show|donne[rz]?|voir|quels?|combien)\b"
    r".*\b(vm|vms|ct|cts|lxc|qemu|container|conteneur|machine[s]?\s+virtuelle[s]?)\b",
    re.IGNORECASE,
)

# Routing déterministe : backup Proxmox → génère directement une carte de confirmation
# Exemples : "backup vm 112", "sauvegarde CT 105", "lance un backup de 112 sur nas-backup"
_PROXMOX_BACKUP_RE = re.compile(
    r"\b(backup|sauvegarder?|sauvegarde)\b.*\b(?:vm|ct|lxc|conteneur)?\s*(\d{2,4})\b",
    re.IGNORECASE,
)
# Routing déterministe : power VM (start/stop/reboot) → carte de confirmation
_PROXMOX_POWER_RE = re.compile(
    r"\b(start|démarre[rz]?|stop|arrête[rz]?|éteins?|reboot|redémarre[rz]?)\b"
    r".*\b(?:vm|ct|lxc|conteneur)?\s*(\d{2,4})\b",
    re.IGNORECASE,
)

# Regex de routing déterministe pour la création de timers
# "mets/ajoute/lance un timer de 10 minutes pour les pâtes", "lance un timer 30s"
_TIMER_RE = re.compile(
    r"(?:mets?|ajoute[rz]?|pose|lance[rz]?|démarre[rz]?|demarre[rz]?|start|set|crée[rz]?|créer|créé|programme[rz]?)"
    r"\s+(?:un\s+|une?\s+)?timer(?:\s+de|\s+for)?\s+(.+)",
    re.IGNORECASE,
)

# Regex de commande de contrôle domotique
_CONTROL_RE = re.compile(
    r"^(?P<action>allume|allumer|éteins|éteint|eteins|eteint|éteindre|eteindre"
    r"|ouvre|ouvrir|ferme|fermer|active|activer|désactive|desactive|désactiver|desactiver"
    r"|toggle|bascule)\s+(?P<name>.+)$",
    re.IGNORECASE,
)

# Regex de demande d'analyse caméra
# Ex : "analyse dep-parking", "caméra parking combien de voiture", "regarde la cam parking"
_CAMERA_RE = re.compile(
    r"(?:analyse[rz]?|analys[ie]|regarde[rz]?|scan[ne]*|capture|visionne[rz]?|montre|affiche|inspect)"
    r".*?(?:cam(?:éra)?|caméra|camera|parking|dep[-_\s]parking)\s*(?P<name1>[a-z0-9_\-]+)?"
    r"|(?:cam(?:éra)?|caméra|camera)\s+(?P<name2>[a-z0-9_\-]+)"
    r"|(?P<name3>[a-z0-9_\-]+(?:parking|cam)[a-z0-9_\-]*)",
    re.IGNORECASE,
)
_ACTION_TO_ON: dict[str, bool | None] = {
    "allume": True,  "allumer": True,
    "ouvre": True,   "ouvrir": True,
    "active": True,  "activer": True,
    "éteins": False, "éteint": False, "eteins": False, "eteint": False,
    "éteindre": False, "eteindre": False,
    "ferme": False,  "fermer": False,
    "désactive": False, "desactive": False, "désactiver": False, "desactiver": False,
    "toggle": None,  "bascule": None,
}


def _find_entity_by_name(name_query: str):
    """Cherche une entité dont le nom correspond à la requête (insensible à la casse, substring)."""
    try:
        from core.unified_entities import unified_entity_service
        entities = unified_entity_service.get_unified_entities(force_refresh=False)
        if not entities:
            return None
        q = name_query.strip().lower()
        # 1. Correspondance exacte
        for e in entities:
            if e.name.lower() == q:
                return e
        # 2. Correspondance partielle
        candidates = [e for e in entities if q in e.name.lower() or e.name.lower() in q]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            # Préférer la correspondance la plus courte (plus précise)
            return min(candidates, key=lambda e: len(e.name))
        # 3. Correspondance par mots communs
        words = set(q.split())
        scored = [(sum(1 for w in words if w in e.name.lower()), e) for e in entities]
        scored = [(s, e) for s, e in scored if s > 0]
        if scored:
            return max(scored, key=lambda x: x[0])[1]
    except Exception:
        pass
    return None


async def _find_camera_by_hint(hint: str) -> dict | None:
    """Cherche une caméra Domoticz dont le nom correspond au hint."""
    from core.settings_store import settings as app_settings
    domo_url = app_settings.get("domoticz.url", "").rstrip("/")
    if not domo_url:
        return None
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{domo_url}/json.htm?type=cameras")
            cams = r.json().get("result", [])
    except Exception:
        return None
    if not cams:
        return None
    hint_l = hint.strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    # Correspondance exacte
    for c in cams:
        if c["Name"].lower().replace("-", "").replace("_", "") == hint_l:
            return c
    # Substring : préférer le nom de caméra le plus long (évite "parking" de matcher avant "dep-parking")
    matches = []
    for c in cams:
        n = c["Name"].lower().replace("-", "").replace("_", "")
        if hint_l in n or n in hint_l:
            matches.append((len(n), c))
    if matches:
        matches.sort(key=lambda x: x[0], reverse=True)
        return matches[0][1]
    # Si un seul candidat, le retourner
    if len(cams) == 1:
        return cams[0]
    return None


async def _find_camera_in_text(text: str) -> dict | None:
    """Trouve la caméra dont le nom (normalisé) apparaît dans le texte.
    En cas d'ambiguïté, retourne la caméra avec le nom le plus long (plus spécifique).
    Ex : "montre dep-parking" → dep-parking gagne sur parking."""
    from core.settings_store import settings as app_settings
    domo_url = app_settings.get("domoticz.url", "").rstrip("/")
    if not domo_url:
        return None
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{domo_url}/json.htm?type=cameras")
            cams = r.json().get("result", [])
    except Exception:
        return None
    if not cams:
        return None
    text_n = text.lower().replace("-", "").replace("_", "").replace(" ", "")
    matches = []
    for c in cams:
        n = c["Name"].lower().replace("-", "").replace("_", "")
        if n and n in text_n:
            matches.append((len(n), c))
    if matches:
        matches.sort(key=lambda x: x[0], reverse=True)
        return matches[0][1]
    # Fallback : une seule caméra disponible
    if len(cams) == 1:
        return cams[0]
    return None


# Mots indiquant qu'on veut juste voir l'image (pas analyser)
_SHOW_ONLY_WORDS = ("montre", "affiche", "voit", "voir", "montre-moi", "capture")
# Mots indiquant une vraie demande d'analyse
_ANALYZE_WORDS   = ("analyse", "analyser", "décris", "decris", "compte",
                    "combien", "qu'est", "que vois", "scan", "inspecte",
                    "regarde", "regarder")


async def _analyze_camera_stream(cam: dict, question: str, show_only: bool = False):
    """Fetch snapshot + gemma4 vision, yield text tokens.
    Émet d'abord un marqueur d'image \x00img\x00<url> pour l'affichage dans le chat.
    Si show_only=True, ne lance pas le LLM vision.
    """
    import base64
    import ssl as _ssl_mod
    from config import OLLAMA_URL as _OLLAMA_URL
    from core.settings_store import settings as app_settings

    ctx = _ssl_mod.create_default_context()
    ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
    ctx.check_hostname = False
    ctx.verify_mode = _ssl_mod.CERT_NONE

    protocol = "https" if cam.get("Protocol", 0) == 1 else "http"
    snap_url = f"{protocol}://{cam['Address']}:{cam['Port']}/{cam['ImageURL']}"
    try:
        async with httpx.AsyncClient(timeout=12, verify=ctx) as client:
            snap = await client.get(snap_url)
    except Exception as exc:
        yield f"❌ Impossible d'accéder à la caméra **{cam['Name']}** : {exc}"
        return
    if snap.status_code != 200:
        yield f"❌ Snapshot indisponible (HTTP {snap.status_code})."
        return

    # Émettre l'image directement dans le chat
    yield f"\x00img\x00/api/cameras/{cam['idx']}/snapshot"

    if show_only:
        yield f"📷 **{cam['Name']}**"
        return

    img_b64 = base64.b64encode(snap.content).decode()
    vision_model = app_settings.get("models.vision", "gemma4:latest") or "gemma4:latest"
    base_ollama = _OLLAMA_URL.rstrip("/")
    if base_ollama.endswith("/api"):
        base_ollama = base_ollama[:-4]
    payload = {
        "model": vision_model,
        "messages": [{
            "role": "user",
            "content": question + " Réponds en français, sois précis et concis.",
            "images": [img_b64],
        }],
        "stream": True,
    }
    yield f"📷 Analyse de **{cam['Name']}** en cours…\n\n"
    async with httpx.AsyncClient(timeout=180) as client:
        async with client.stream("POST", f"{base_ollama}/api/chat", json=payload) as resp:
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if chunk.get("done"):
                        return
                except Exception:
                    continue


# Mots-clés qui signalent une demande d'analyse caméra
_CAMERA_TRIGGERS = (
    "analyse", "analyser", "regarde", "regarder", "scan", "scanner",
    "capture", "inspecte", "inspecter", "montre la cam", "affiche la cam",
    "caméra", "camera", "cam ", "cam-", "webcam",
    "parking",
)

_DOMOTIQUE_TRIGGERS = (
    "lumière", "lumières", "lumiere", "lumieres",
    "switch", "switches", "prise", "prises",
    "capteur", "capteurs", "sensor", "sensors",
    "domotique", "domoticz", "home assistant", "kasa",
    "allumé", "éteint", "allumée", "étein",
    "appareil connecté", "appareils connectés", "équipement connecté",
    "état de mes", "etat de mes", "état des", "etat des",
    "quelles lumières", "quels appareils", "quels capteurs",
    "température", "temperature", "humidité", "humidity",
    "volet", "volets", "portail", "thermostat",
)

# Patterns déterministes pour l'état des entités (évitent le LLM)
_STATE_QUERY_PATTERNS = (
    re.compile(r"quell?es?\s+(lumi[eè]res?|lumi[eè]re|switch|switches|prise[s]?|appareil[s]?|lampe[s]?)\s+(sont\s+)?(allum[ée]e?s?|on\b)", re.IGNORECASE),
    re.compile(r"quell?es?\s+(lumi[eè]res?|lumi[eè]re|switch|switches|prise[s]?|appareil[s]?|lampe[s]?)\s+(sont\s+)?(éteint[es]?|off\b)", re.IGNORECASE),
    re.compile(r"(lumi[eè]res?|switch|prises?|appareils?|lampes?)\s+(allum[ée]e?s?|on\b)", re.IGNORECASE),
    re.compile(r"(lumi[eè]res?|switch|prises?|appareils?|lampes?)\s+(éteint[es]?|off\b)", re.IGNORECASE),
    re.compile(r"(liste|montre|affiche|donne[- ]moi)\s+(les\s+)?(lumi[eè]res?|switch|prises?|appareils?)\s+(allum[ée]e?s?|éteint[es]?|on\b|off\b)", re.IGNORECASE),
    re.compile(r"état\s+des?\s+(lumi[eè]res?|switch|prises?|appareils?)", re.IGNORECASE),
    re.compile(r"(lumi[eè]res?|switch|prises?|appareils?)\s+(qui\s+)(sont\s+)?(allum[ée]e?s?|éteint[es]?|on\b|off\b)", re.IGNORECASE),
    re.compile(r"quoi\s+(est|sont)\s+(allum[ée]e?s?|on\b|éteint[es]?|off\b)", re.IGNORECASE),
    re.compile(r"(il y a quoi|qu['']est[- ]ce qui)\s+(est\s+)?(allum[ée]e?|on\b)", re.IGNORECASE),
)


# ---------------------------------------------------------------------------
# Agent web Playwright (pipeline version — sans SSE, yield chunks)
# ---------------------------------------------------------------------------
async def _web_agent_search(instruction: str) -> AsyncGenerator[str, None]:
    """Execute l'agent Playwright headless et yield le résultat final."""
    from playwright.async_api import async_playwright
    from core.agent.text_agent import _SYSTEM_PROMPT as _AGENT_SYSTEM
    from core.settings_store import settings as app_settings

    MAX_STEPS = 12
    MAX_PAGE_CHARS = 4000
    ollama_url = app_settings.get("ollama_url", OLLAMA_URL)
    base = ollama_url.rstrip("/")
    if base.endswith("/api"):
        base = base[:-4]
    chat_url = f"{base}/api/chat"

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
            _visited_urls: list[str] = []  # URLs non-Google visitées par l'agent

            for step in range(1, MAX_STEPS + 1):
                try:
                    url = page.url
                    title = await page.title()
                    body = await page.eval_on_selector("body", "el => el.innerText") or ""
                    body = re.sub(r"\s{3,}", "\n", body)[:MAX_PAGE_CHARS]
                    links = await page.eval_on_selector_all(
                        "a[href]",
                        "els => els.slice(0,30).map(e => ({t:e.innerText.trim(), h:e.href})).filter(l=>l.t)",
                    )
                    links_str = "\n".join(
                        f"  [{l['t'][:60]}] {l['h'][:80]}" for l in links[:20]
                    )
                    page_summary = f"URL: {url}\nTitle: {title}\nLinks:\n{links_str}\nBody:\n{body}"
                except Exception as e:
                    page_summary = f"(erreur lecture page: {e})"

                user_msg = (
                    f"Goal: {instruction}\n\nStep {step}/{MAX_STEPS}\n\n"
                    f"Current page:\n{page_summary[:MAX_PAGE_CHARS + 500]}\n\n"
                    "Output the next JSON action:"
                )
                messages_llm = [
                    {"role": "system", "content": _AGENT_SYSTEM},
                    *history,
                    {"role": "user", "content": user_msg},
                ]

                try:
                    async with httpx.AsyncClient(timeout=120.0) as client:
                        r = await client.post(
                            chat_url,
                            json={"model": _chat_model(), "messages": messages_llm,
                                  "stream": False, "think": False},
                        )
                        r.raise_for_status()
                        reply = r.json().get("message", {}).get("content", "").strip()
                except Exception as e:
                    yield f"Erreur LLM lors de la recherche : {e}"
                    await browser.close()
                    return

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
                    continue

                history.append({"role": "assistant", "content": json.dumps(action)})
                action_name = action.get("action", "")

                if action_name in ("done", "extract"):
                    result = action.get("result", reply)
                    # Ajouter les sources si l'agent ne les a pas citées
                    if _visited_urls:
                        _src_lower = result.lower()
                        if "source" not in _src_lower and "http" not in _src_lower:
                            _urls_str = "\n".join(f"- {u}" for u in _visited_urls[:5])
                            result += f"\n\n📎 **Sources :**\n{_urls_str}"
                    await browser.close()
                    yield result
                    return

                try:
                    if action_name == "navigate":
                        _nav_url = action.get("url", "")
                        # Mémoriser les pages de contenu (pas les SERP Google)
                        if (_nav_url
                                and "google.com/search" not in _nav_url
                                and "google.fr/search" not in _nav_url
                                and "bing.com/search" not in _nav_url
                                and _nav_url not in _visited_urls):
                            _visited_urls.append(_nav_url)
                        await page.goto(
                            _nav_url,
                            wait_until="domcontentloaded",
                            timeout=15_000,
                        )
                        for sel in [
                            "button:has-text('Tout accepter')",
                            "button:has-text('Accept all')",
                        ]:
                            try:
                                btn = page.locator(sel).first
                                if await btn.is_visible(timeout=800):
                                    await btn.click(timeout=2000)
                                    break
                            except Exception:
                                pass
                    elif action_name == "click":
                        await page.get_by_text(
                            action.get("link_text", ""), exact=False
                        ).first.click(timeout=5_000)
                        try:
                            await page.wait_for_load_state("domcontentloaded", timeout=10_000)
                        except Exception:
                            pass
                    elif action_name == "scroll_down":
                        await page.evaluate("window.scrollBy(0, window.innerHeight)")
                except Exception:
                    pass

            await browser.close()
            yield "Je n'ai pas pu trouver la réponse dans la limite d'étapes."
    except Exception as e:
        yield f"Erreur lors de la recherche web : {e}"


def _system_prompt(plugin_context_id: str | None = None) -> str:
    """System prompt de base, enrichi des capacités des plugins actifs."""
    base = (
        "Tu es ADA, une assistante IA locale. "
        "Réponds TOUJOURS en français. "
        "RÈGLE ABSOLUE : réponses courtes, 1 à 3 phrases max. "
        "Pas d'intro, pas de conclusion, pas de présentation de toi-même. "
        "Va directement à la réponse. "
        "RÈGLE SOURCES OBLIGATOIRE : si des documents de référence ou des résultats "
        "de recherche web sont fournis dans le contexte, tu DOIS citer les sources "
        "à la fin de ta réponse sous la forme \"📎 Sources : nom_fichier_ou_url\". "
        "Ne jamais omettre les sources quand elles sont disponibles."
    )
    try:
        from core.plugin_registry import plugin_registry as _pr
        injection = _pr.combined_system_prompt_injection(context_id=plugin_context_id)
        if injection:
            base += f"\n\n### Capacités disponibles ###\n{injection}"
    except Exception:
        pass
    return base


def _format_entity_state_answer(user_text: str) -> str | None:
    """
    Répond directement (sans LLM) aux questions sur l'état des entités.
    Retourne None si la question ne correspond pas à un pattern d'état.
    """
    text_lower = user_text.lower()

    # Détecter si la question porte sur les allumés ou les éteints
    want_on: bool | None = None
    if any(w in text_lower for w in ("allumé", "allumée", "allumées", "allumés", " on ", "qui sont on")):
        want_on = True
    elif any(w in text_lower for w in ("éteint", "éteinte", "éteintes", "éteints", " off ", "qui sont off")):
        want_on = False
    if text_lower.rstrip("? !").endswith(("allumé", "allumée", "allumées", "allumés", "on")):
        want_on = True
    if text_lower.rstrip("? !").endswith(("éteint", "éteinte", "éteintes", "éteints", "off")):
        want_on = False

    # Vérifier si un pattern regex correspond
    matched = any(p.search(user_text) for p in _STATE_QUERY_PATTERNS)
    # Fallback : lumière + (allumé|éteint) dans le même message
    if not matched:
        has_light_kw = any(w in text_lower for w in ("lumière", "lumières", "lumiere", "lumieres", "lampe", "lampes"))
        has_state_kw = any(w in text_lower for w in ("allumé", "allumée", "allumées", "allumés", "éteint", "éteinte", "éteintes", "éteints"))
        if has_light_kw and has_state_kw:
            matched = True

    if not matched:
        return None

    try:
        from core.unified_entities import unified_entity_service
        entities = unified_entity_service.get_unified_entities(force_refresh=True)
    except Exception as ex:
        return f"❌ Impossible de récupérer les entités domotiques : {ex}"

    # Filtrer par type — en Domoticz les lumières sont souvent des switch/scene
    TYPE_FILTER: list[str] = []
    if any(w in text_lower for w in ("switch", "switches", "prise", "prises")):
        TYPE_FILTER = ["switch"]
    elif any(w in text_lower for w in ("lumière", "lumières", "lumiere", "lumieres", "lampe", "lampes")):
        # Les lumières peuvent être light, switch ou scene selon le provider
        TYPE_FILTER = ["light", "switch", "scene"]
    # Sinon : pas de filtre → tous les types contrôlables

    filtered = [
        e for e in entities
        if (not TYPE_FILTER or e.type in TYPE_FILTER)
        and (want_on is None or (e.state == "on") == want_on)
    ]

    if want_on is True:
        state_label, icon = "allumées", "💡"
    elif want_on is False:
        state_label, icon = "éteintes", "🌑"
    else:
        state_label, icon = "actives", "📊"

    type_label = ""
    if TYPE_FILTER == ["switch"]:
        type_label = "prises/switches "

    if not filtered:
        return f"Aucune {type_label}entité {state_label} en ce moment."

    lines = [f"{icon} **{len(filtered)} {type_label}entité{'s' if len(filtered) > 1 else ''} {state_label} :**\n"]
    for e in filtered:
        zone = f" *[{e.zone}]*" if e.zone and e.zone != "Other" else ""
        extras = []
        if e.attributes and e.attributes.get("brightness") is not None:
            extras.append(f"{round(e.attributes['brightness'] / 2.55)}%")
        extra_str = f" ({', '.join(extras)})" if extras else ""
        lines.append(f"- **{e.name}**{zone}{extra_str}")
    return "\n".join(lines)


def _format_entities_context() -> str:
    """Retourne un résumé textuel des entités domotiques pour le contexte LLM."""
    try:
        from core.unified_entities import unified_entity_service
        entities = unified_entity_service.get_unified_entities(force_refresh=False)
        if not entities:
            return ""

        TYPE_FR = {
            "light": "Lumière", "switch": "Switch", "media_player": "Lecteur",
            "sensor": "Capteur", "binary_sensor": "Capteur binaire",
            "camera": "Caméra", "unknown": "Autre",
        }
        lines = [f"[Entités domotiques — {len(entities)} au total]"]
        by_type: dict = {}
        for e in entities:
            t = e.type or "unknown"
            by_type.setdefault(t, []).append(e)

        for t, group in sorted(by_type.items()):
            label = TYPE_FR.get(t, t)
            lines.append(f"\n{label}s ({len(group)}) :")
            for e in group[:40]:  # max 40 par type pour ne pas exploser le contexte
                state_str = e.state or "?"
                extras = []
                if e.attributes:
                    if e.attributes.get("brightness") is not None:
                        extras.append(f"{round(e.attributes['brightness'] / 2.55)}%")
                    if e.attributes.get("temperature") is not None:
                        extras.append(f"{e.attributes['temperature']}°C")
                    if e.attributes.get("humidity") is not None:
                        extras.append(f"{e.attributes['humidity']}%")
                zone = f" [{e.zone}]" if e.zone and e.zone != "Other" else ""
                extra_str = f" ({', '.join(extras)})" if extras else ""
                lines.append(f"  - {e.name}{zone} : {state_str}{extra_str}")
        return "\n".join(lines)
    except Exception as ex:
        return f"[Entités domotiques non disponibles : {ex}]"


# ---------------------------------------------------------------------------
# Streaming chat simple (qwen_basic / qwen_thinking)
# ---------------------------------------------------------------------------
async def _stream_ollama(
    messages: list[dict],
    thinking: bool = False,
) -> AsyncGenerator[str, None]:
    payload: dict = {
        "model": _chat_model(),
        "messages": messages,
        "stream": True,
        "options": {"num_predict": 1024, "temperature": 0.7},
    }
    if thinking:
        payload["think"] = True  # Qwen3 extended reasoning

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", _chat_url(), json=payload) as resp:
            resp.raise_for_status()
            async for raw in resp.aiter_lines():
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                # Skip thinking tokens, only yield visible content
                delta = data.get("message", {}).get("content", "")
                if delta:
                    yield delta
                if data.get("done"):
                    break


async def _call_llm(messages: list[dict], thinking: bool = False) -> str:
    payload: dict = {
        "model": _chat_model(),
        "messages": messages,
        "stream": False,
        "think": bool(thinking),
        "keep_alive": "5m",
    }
    async with httpx.AsyncClient(timeout=150.0) as client:
        r = await client.post(_chat_url(), json=payload)
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "").strip()


def _extract_func_call(text: str, func_defs: list[dict]) -> tuple[str, dict]:
    """
    Fallback : tente de détecter un appel de fonction dans le texte brut du LLM
    quand tool_calls est vide (ex: Mistral qui génère du texte Python au lieu de JSON).
    """
    known = {f["function"]["name"] for f in func_defs}
    m = re.search(r'\b([a-z_]+)\s*\(', text)
    if m and m.group(1) in known:
        func_name = m.group(1)
        start = m.end()
        depth = 1
        i = start
        while i < len(text) and depth > 0:
            if text[i] == '(':
                depth += 1
            elif text[i] == ')':
                depth -= 1
            if depth > 0:
                i += 1
        args_str = text[start:i].strip()
        params: dict = {}
        if args_str:
            if args_str.startswith('{'):
                try:
                    params = json.loads(args_str)
                except Exception:
                    pass
            else:
                first_arg = args_str.strip('"\'').split(',')[0].strip('"\'').strip()
                if first_arg:
                    params = {"instance_id": first_arg}
        return func_name, params
    return "", {}


async def _stream_with_tools(
    text: str,
    conversation_messages: list[dict],
    plugin_context_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Version streaming de l'ancien _call_with_tools.
    Yield :
      - '\x00think\x00<msg>' : étapes de réflexion visibles
      - '{"__type": "confirm_required", ...}' : carte de confirmation
      - chunks de texte : réponse finale (streamée depuis Ollama)
    """
    from config import FUNCTIONS as _FUNCTIONS
    from core.plugin_registry import plugin_registry as _pr
    from core.n8n_executor import n8n_executor

    plugin_functions = _pr.combined_function_definitions()
    effective_functions = _FUNCTIONS + plugin_functions

    plugin_sys = _pr.combined_system_prompt_injection(context_id=plugin_context_id)
    dispatcher_system = (
        "You are a function dispatcher. You MUST call one of the available tools. "
        "NEVER respond with plain text. "
        "For greetings or conversational questions: call passthrough.\n\n"
        "Tool selection rules:\n"
        "- control_light: ANY light/lamp/room lighting request\n"
        "- set_timer: countdown timers\n"
        "- shell_exec: system commands\n"
        "- web_search: internet searches\n"
        "- passthrough: ONLY for pure chitchat or greetings with NO possible action.\n"
        "- vm_list: ANY request to list, show, display VMs, CTs, containers, machines on Proxmox\n"
        "- vm_power: start/stop/reboot a VM or CT\n"
        "- vm_backup: backup/save a VM or CT\n"
        "- node_stats: stats, resources, CPU, RAM of a Proxmox node\n"
        "- For any other plugin function listed in 'Active plugin capabilities' below: use it when appropriate.\n\n"
        "IMPORTANT: If you cannot use the tool_calls format, respond with ONLY this JSON and nothing else:\n"
        '{"function": "function_name", "arguments": {"key": "value"}}'
    )
    if plugin_sys:
        dispatcher_system += f"\n\nActive plugin capabilities:\n{plugin_sys}"

    yield "\x00think\x00🔍 Sélection de l'outil…"

    try:
        async with httpx.AsyncClient(timeout=150.0) as client:
            r = await client.post(
                _chat_url(),
                json={
                    "model":      _chat_model(),
                    "messages":   [
                        {"role": "system", "content": dispatcher_system},
                        {"role": "user",   "content": text},
                    ],
                    "tools":      effective_functions,
                    "stream":     False,
                    "think":      False,
                    "keep_alive": "5m",
                },
            )
            r.raise_for_status()
            msg = r.json().get("message", {})
            tool_calls = msg.get("tool_calls", [])
    except Exception:
        async for chunk in _stream_ollama(conversation_messages, thinking=False):
            yield chunk
        return

    func_name = ""
    params: dict = {}

    if not tool_calls:
        # Fallback 1 : détecter func_name(...) dans le texte généré
        raw_text = msg.get("content", "")
        func_name, params = _extract_func_call(raw_text, effective_functions)
        if not func_name:
            # Fallback 2 : détecter {"function": "...", "arguments": {...}} dans le texte
            try:
                m = re.search(r'\{[^{}]*"function"\s*:\s*"([^"]+)"[^{}]*\}', raw_text, re.DOTALL)
                if not m:
                    # Essai plus large avec objets imbriqués
                    m = re.search(r'\{.*?"function"\s*:\s*"([^"]+)".*?\}', raw_text, re.DOTALL)
                if m:
                    parsed_json = json.loads(m.group())
                    fn = parsed_json.get("function", "")
                    known_names = {f["function"]["name"] for f in effective_functions}
                    if fn in known_names:
                        func_name = fn
                        params = parsed_json.get("arguments", {}) or {}
            except Exception:
                pass
        if func_name:
            yield f"\x00think\x00🔧 Outil détecté : `{func_name}`"
        else:
            async for chunk in _stream_ollama(conversation_messages, thinking=False):
                yield chunk
            return
    else:
        call = tool_calls[0]
        func_name = call.get("function", {}).get("name", "")
        params = call.get("function", {}).get("arguments", {}) or {}

    if func_name == "passthrough":
        thinking = bool(params.get("thinking", False))
        async for chunk in _stream_ollama(conversation_messages, thinking=thinking):
            yield chunk
        return

    # ── Vérification confirmation requise ─────────────────────────────────────
    func_def = next(
        (f for f in effective_functions if f["function"]["name"] == func_name),
        None,
    )
    if func_def and func_def["function"].get("x_confirm_required"):
        confirm_msg = func_def["function"].get(
            "x_confirm_message", f"Confirmer {func_name} ?"
        )
        confirm_cmd = func_def["function"].get("x_confirm_cmd", "")
        try:
            confirm_msg = confirm_msg.format(**params)
        except Exception:
            pass
        try:
            if confirm_cmd:
                confirm_cmd = confirm_cmd.format(**params)
        except Exception:
            pass
        yield json.dumps({
            "__type":  "confirm_required",
            "func":    func_name,
            "message": confirm_msg,
            "params":  json.dumps(params),
            "cmd":     confirm_cmd,
        })
        return

    yield f"\x00think\x00⚙️ Exécution de `{func_name}`…"

    # ── Dispatch : plugin → n8n → function_executor ───────────────────────────
    plugin_result = _pr.dispatch_action(func_name, params)
    if plugin_result is not None:
        result = plugin_result
    else:
        action = func_name.replace("_", "-")
        result = n8n_executor.call(action, params)

    success    = result.get("success", False)
    result_msg = result.get("message", "")

    if success and result_msg:
        # Bypass total du LLM de followup pour éviter toute hallucination :
        # le résultat est déjà formaté en markdown par handle_action.
        yield "\x00think\x00✅ Données reçues"
        yield result_msg
        return

    # Échec ou résultat vide : LLM formule un message d'erreur naturel (pas de données à inventer)
    yield "\x00think\x00⚠️ Erreur lors de l'exécution"
    followup = list(conversation_messages)
    error_hint = (
        f"[Résultat de l'action `{func_name}` : échec]\n"
        f"{result_msg}\n\n"
        "Explique cette erreur à l'utilisateur en français, de façon claire et concise. "
        "Ne propose PAS de solution inventée, indique juste ce qui s'est passé."
    )
    followup[-1] = {
        "role":    "user",
        "content": f"{text}\n\n{error_hint}",
    }
    async for chunk in _stream_ollama(followup, thinking=False):
        yield chunk


# ---------------------------------------------------------------------------
# Point d'entrée public
# ---------------------------------------------------------------------------
async def process_message(
    message: str,
    history: list[dict],
    company_context: str | None = None,   # compat existant — filtre infra
    plugin_context:  str | None = None,   # NOUVEAU : univers actif ("home", "opent"…)
    context_id:      str | None = None,   # NOUVEAU : sous-contexte (company_id, etc.)
) -> AsyncGenerator[str, None]:
    """
    Route et traite un message, yield les chunks de réponse au fil de l'eau.
    Compatible SSE : chaque chunk est une petite chaîne de texte.
    """
    session_id = "web_chat"
    user_text = (message or "").strip()
    if not user_text:
        return

    _effective_ctx = context_id or company_context or None

    # ── Radar : génération du request_id et événement d'entrée ──────────────
    _req_id    = f"req_{_uuid.uuid4().hex[:16]}"
    _req_start = _time.perf_counter()
    try:
        from web.radar.events import emit_event as _emit_ev
        _emit_ev(
            type="rag.query.received",
            level="info",
            module="web.pipeline",
            request_id=_req_id,
            session_id=session_id,
            metadata={"query_preview": user_text[:300]},
        )
    except Exception:
        pass

    text_lower = user_text.lower()

    # Ajout d'une URL à la surveillance d'infrastructure
    m_url = _ADD_URL_RE.search(user_text)
    if m_url and any(k in text_lower for k in ("infra", "infrastructure", "surveillance", "surveille", "monitore", "watch", "vérifie", "ajoute")):
        from urllib.parse import urlparse
        from core.runtime_state import add_custom_endpoint
        raw_url = m_url.group(1).rstrip(".,;)>")
        # Normaliser : ajouter https:// si pas de schéma
        if not raw_url.startswith(("http://", "https://")):
            raw_url = "https://" + raw_url
        name = urlparse(raw_url).netloc or raw_url
        # Extraire les tags depuis "avec le tag X" / "avec les tags X, Y"
        tags = ["local"]
        m_tag = _ADD_TAG_RE.search(user_text)
        if m_tag:
            raw_tags = m_tag.group(1)
            tags = [t.strip().lower() for t in re.split(r"[,\s]+", raw_tags) if t.strip()]
            if "local" not in tags:
                tags = ["local"] + tags
        add_custom_endpoint(name, raw_url, tags=tags)
        tags_str = ", ".join(f"`{t}`" for t in tags)
        response = (
            f"✅ **{name}** ajouté à la surveillance.\n"
            f"URL : `{raw_url}`\n"
            f"Tags : {tags_str}\n"
            "Il apparaîtra dans l'état infrastructure dès la prochaine demande."
        )
        memory_store.save(session_id, "user", user_text)
        memory_store.save(session_id, "assistant", response)
        yield response
        return

    # Détection d'une demande de recherche web → agent Playwright
    if any(trigger in text_lower for trigger in _WEB_TRIGGERS):
        yield "🔍 Recherche sur le web en cours…\n\n"
        full_response = "🔍 Recherche sur le web en cours…\n\n"
        async for chunk in _web_agent_search(user_text):
            full_response += chunk
            yield chunk
        memory_store.save(session_id, "user", user_text)
        memory_store.save(session_id, "assistant", full_response)
        return

    # Routing déterministe pour l'état d'infrastructure
    if any(trigger in text_lower for trigger in _INFRA_TRIGGERS):
        from core.runtime_state import runtime_state

        runtime_state.refresh()
        infra = runtime_state.format_infra_status_fr(filter_tag=company_context)
        memory_store.save(session_id, "user", user_text)
        memory_store.save(session_id, "assistant", infra)
        yield infra
        return

    # Routing déterministe : liste VM/CT Proxmox — bypass LLM dispatcher (trop instable)
    if _PROXMOX_VM_LIST_RE.search(user_text):
        from core.plugin_registry import plugin_registry as _pr_vmlist
        # Extraire instance_id depuis le texte ("de ot-mutu", "sur ot-mutu", etc.)
        _m_inst = re.search(
            r"\b(?:de|sur|pour|instance|proxmox)\s+([\w\-\.]+)",
            user_text, re.IGNORECASE
        )
        _inst_hint = _m_inst.group(1) if _m_inst else None
        _vmlist_result = _pr_vmlist.dispatch_action(
            "vm_list",
            {"instance_id": _inst_hint, "node": None}
        )
        if _vmlist_result and _vmlist_result.get("success") and _vmlist_result.get("message"):
            _vmlist_msg = _vmlist_result["message"]
            memory_store.save(session_id, "user", user_text)
            memory_store.save(session_id, "assistant", _vmlist_msg)
            yield _vmlist_msg
            return

    # Routing déterministe : backup Proxmox → carte de confirmation directe
    _m_backup = _PROXMOX_BACKUP_RE.search(user_text)
    if _m_backup:
        _bk_vmid = int(_m_backup.group(2))
        # Extraire storage depuis "sur <storage>" / "storage <storage>"
        _m_storage = re.search(r"\b(?:sur|storage|stockage)\s+([\w\-]+)", user_text, re.IGNORECASE)
        _bk_storage = _m_storage.group(1) if _m_storage else "local"
        _bk_params  = {"vmid": _bk_vmid, "storage": _bk_storage, "compress": "zstd"}
        _bk_card = json.dumps({
            "__type":  "confirm_required",
            "func":    "vm_backup",
            "message": f"Lancer la sauvegarde de VM/CT **{_bk_vmid}** → storage `{_bk_storage}` (zstd) ?",
            "params":  json.dumps(_bk_params),
            "cmd":     f"vzdump {_bk_vmid} --compress zstd --storage {_bk_storage}",
        })
        memory_store.save(session_id, "user", user_text)
        memory_store.save(session_id, "assistant", f"[backup {_bk_vmid} en attente de confirmation]")
        yield _bk_card
        return

    # Routing déterministe : power VM (stop/start/reboot) → carte de confirmation directe
    _m_power = _PROXMOX_POWER_RE.search(user_text)
    if _m_power:
        _pw_verb  = _m_power.group(1).lower()
        _pw_vmid  = int(_m_power.group(2))
        _pw_action = (
            "start"  if any(k in _pw_verb for k in ("start", "démarre", "demarre")) else
            "stop"   if any(k in _pw_verb for k in ("stop", "arrête", "arrete", "étein", "etein")) else
            "reboot"
        )
        _pw_label = {"start": "Démarrer", "stop": "Arrêter", "reboot": "Redémarrer"}[_pw_action]
        _pw_params = {"vmid": _pw_vmid, "action": _pw_action}
        _pw_card = json.dumps({
            "__type":  "confirm_required",
            "func":    "vm_power",
            "message": f"{_pw_label} la VM/CT **{_pw_vmid}** ?",
            "params":  json.dumps(_pw_params),
            "cmd":     f"qm {_pw_action} {_pw_vmid}",
        })
        memory_store.save(session_id, "user", user_text)
        memory_store.save(session_id, "assistant", f"[power {_pw_action} {_pw_vmid} en attente de confirmation]")
        yield _pw_card
        return

    # Analyse caméra : "analyse dep-parking", "caméra parking combien de voitures ?"
    if any(t in text_lower for t in _CAMERA_TRIGGERS):
        # Chercher directement le nom de la caméra dans le texte (match le plus long gagne)
        cam = await _find_camera_in_text(text_lower)
        # Fallback si pas trouvé via le texte : essayer via regex
        if cam is None:
            m_cam = _CAMERA_RE.search(text_lower)
            cam_hint = (
                (m_cam.group("name1") or m_cam.group("name2") or m_cam.group("name3") or "").strip()
                if m_cam else ""
            )
            if cam_hint:
                cam = await _find_camera_by_hint(cam_hint)
        if cam is None:
            cam = await _find_camera_by_hint("")
        if cam is not None:
            # Détecter si c'est juste "montre" ou une vraie analyse
            _show_only = (
                any(t in text_lower for t in _SHOW_ONLY_WORDS)
                and not any(t in text_lower for t in _ANALYZE_WORDS)
            )
            # La question pour le LLM vision = tout le message original
            full_answer = ""
            async for chunk in _analyze_camera_stream(cam, user_text, show_only=_show_only):
                full_answer += chunk
                yield chunk
            memory_store.save(session_id, "user", user_text)
            memory_store.save(session_id, "assistant", full_answer)
            return

    # Routing déterministe : état des entités domotiques (liste on/off sans LLM)
    state_answer = _format_entity_state_answer(user_text)
    if state_answer is not None:
        memory_store.save(session_id, "user", user_text)
        memory_store.save(session_id, "assistant", state_answer)
        yield state_answer
        return

    # Commandes de contrôle domotique : "allume X", "éteins X", "ouvre X"…
    m_ctrl = _CONTROL_RE.match(user_text.strip())
    if m_ctrl:
        action_word = m_ctrl.group("action").lower()
        entity_name = m_ctrl.group("name").strip()
        target_on = _ACTION_TO_ON.get(action_word)  # True / False / None

        entity = _find_entity_by_name(entity_name)
        if entity is None:
            response = f"❓ Aucune entité trouvée pour « {entity_name} ». Vérifiez le nom sur la page Domotique."
        elif entity.read_only:
            response = f"⚠️ **{entity.name}** est en lecture seule (capteur), impossible de le contrôler."
        else:
            from core.unified_entities import unified_entity_service
            ok = unified_entity_service.toggle_entity(entity.id, on=target_on)
            if ok:
                new_state = "on" if target_on is True else ("off" if target_on is False else ("off" if entity.state == "on" else "on"))
                verb = "allumé" if new_state == "on" else "éteint"
                response = f"✅ **{entity.name}** {verb}."
            else:
                response = f"❌ Impossible de contrôler **{entity.name}**. Vérifiez la connexion au provider ({entity.provider})."

        memory_store.save(session_id, "user", user_text)
        memory_store.save(session_id, "assistant", response)
        yield response
        return

    # Routing déterministe pour les timers (avant LLM — le LLM ignore souvent les phrases françaises)
    m_timer = _TIMER_RE.search(user_text)
    if m_timer:
        raw = m_timer.group(1).strip()
        # Cas 1 : "10 minutes pour les pâtes" → dur="10 minutes", label="les pâtes"
        m_pour = re.search(r"\bpour\s+(.+)$", raw, re.IGNORECASE)
        # Cas 2 : "test2 de 2 min" → label="test2", dur="2 min"
        m_label_de = re.match(r"^([A-Za-zÀ-ÿ][^\s]*(?:\s+[A-Za-zÀ-ÿ][^\s]*)?)\s+de\s+(.+)$", raw, re.IGNORECASE)
        if m_pour:
            duration_str = raw[: m_pour.start()].strip()
            label = m_pour.group(1).strip()
        elif m_label_de and not re.match(r'^\d', m_label_de.group(1)):
            label = m_label_de.group(1).strip()
            duration_str = m_label_de.group(2).strip()
        else:
            duration_str = raw
            label = "Timer"
        if not duration_str:
            duration_str = raw
            label = "Timer"
        result = function_executor.execute("set_timer", {"duration": duration_str, "label": label})
        if result.get("success"):
            response = f"⏱️ Timer **{label}** lancé pour {duration_str}. Visible dans le Planificateur."
        else:
            response = (
                f"❌ Durée non reconnue : `{duration_str}`. "
                "Essayez `10 minutes`, `1h30`, `30 secondes`, etc."
            )
        memory_store.save(session_id, "user", user_text)
        memory_store.save(session_id, "assistant", response)
        yield response
        return

    # Contexte conversationnel de base
    messages: list[dict] = [{"role": "system", "content": _system_prompt(_effective_ctx)}]
    messages.extend(history[-20:])

    # Injection du contexte domotique si la question concerne les entités
    if any(t in text_lower for t in _DOMOTIQUE_TRIGGERS):
        entity_ctx = _format_entities_context()
        if entity_ctx:
            messages[0] = {
                "role": "system",
                "content": messages[0]["content"] + "\n\n" + entity_ctx,
            }

    # Injection des skills + mémoire long terme, comme l'app
    messages = skill_manager.inject(messages, user_text)

    # AutoSkills SQLite : injection des apprentissages adaptatifs
    _autoskill_meta: dict = {"skills_injected": [], "skills_count": 0}
    try:
        from core.skills.autoskills_runtime import inject_autoskills
        messages, _autoskill_meta = inject_autoskills(
            messages,
            query=user_text,
            domain=_effective_ctx or plugin_context or "auto",
            request_id=_req_id,
            session_id=session_id,
        )
    except Exception:
        pass

    # MODULE_DOCUMENTS: injection RAG documentaire (entre skills et mémoire)
    _doc_meta = None
    _rag_start = _time.perf_counter()
    try:
        from core.documents.documents_injector import inject_documentation
        messages, _doc_meta = inject_documentation(messages, user_text, context_id=_effective_ctx)
    except Exception:
        pass
    try:
        from web.radar.events import emit_event as _emit_ev
        _chunks_found = len(_doc_meta) if _doc_meta else 0
        _emit_ev(
            type="rag.search.completed" if _chunks_found > 0 else "rag.context.empty",
            level="info",
            module="web.pipeline",
            request_id=_req_id,
            duration_ms=int((_time.perf_counter() - _rag_start) * 1000),
            metadata={"chunks_found": _chunks_found},
        )
    except Exception:
        pass

    mem = memory_store.build_context(user_text, current_session_id=session_id)
    if mem:
        # Injecter la mémoire comme échange user/assistant fictif en début d'historique.
        # Cela lui donne le poids d'une conversation passée ordinaire, et NON d'une
        # instruction système — les LLMs locaux sur-pondèrent fortement les system messages.
        # La conversation courante (après) reste donc prioritaire.
        messages.insert(1, {
            "role": "assistant",
            "content": "Compris, je prends note de ces informations comme contexte de fond.",
        })
        messages.insert(1, {
            "role": "user",
            "content": f"[Rappel de contexte — conversations passées, priorité inférieure à la conversation qui suit]\n{mem}",
        })

    messages.append({"role": "user", "content": user_text})

    try:
        route = semantic_route(user_text)
    except Exception:
        route = "function_gemma"

    # function_gemma: tool-calling complet puis réponse naturelle (streaming)
    if route == "function_gemma":
        try:
            from web.radar.events import emit_event as _emit_ev
            _emit_ev(type="llm.call.started", level="info", module="web.pipeline",
                     request_id=_req_id, metadata={"route": "function_gemma"})
        except Exception:
            pass
        _llm_start = _time.perf_counter()
        full_response = ""
        async for chunk in _stream_with_tools(user_text, messages, plugin_context_id=_effective_ctx):
            # Les tokens de réflexion et les cartes de confirmation passent tels quels
            if chunk.startswith("\x00think\x00") or chunk.startswith('{"__type"'):
                yield chunk
            else:
                full_response += chunk
                yield chunk
        try:
            from web.radar.events import emit_event as _emit_ev
            _emit_ev(type="llm.call.completed", level="info", module="web.pipeline",
                     request_id=_req_id,
                     duration_ms=int((_time.perf_counter() - _llm_start) * 1000))
        except Exception:
            pass
        memory_store.save(session_id, "user", user_text)
        memory_store.save(session_id, "assistant", full_response)
        try:
            import asyncio as _asyncio
            from core.skills.autoskills_runtime import maybe_update_autoskill
            _asyncio.create_task(maybe_update_autoskill(
                history=history, user_text=user_text, assistant_text=full_response,
                domain=_effective_ctx or plugin_context or "auto",
                request_id=_req_id, session_id=session_id, call_llm=_call_llm,
            ))
        except Exception:
            pass
        return

    # qwen_thinking ou chat standard (vision/youtube/cad/print inclus en fallback texte)
    thinking = route == "qwen_thinking"
    full_response = ""
    try:
        from web.radar.events import emit_event as _emit_ev
        _emit_ev(type="llm.call.started", level="info", module="web.pipeline",
                 request_id=_req_id, metadata={"route": route})
    except Exception:
        pass
    _llm_start = _time.perf_counter()
    async for chunk in _stream_ollama(messages, thinking=thinking):
        full_response += chunk
        yield chunk

    if full_response:
        try:
            from web.radar.events import emit_event as _emit_ev
            _emit_ev(type="rag.response.sent", level="info", module="web.pipeline",
                     request_id=_req_id,
                     duration_ms=int((_time.perf_counter() - _req_start) * 1000),
                     metadata={"llm_ms": int((_time.perf_counter() - _llm_start) * 1000)})
        except Exception:
            pass
        memory_store.save(session_id, "user", user_text)
        memory_store.save(session_id, "assistant", full_response)
        try:
            import asyncio as _asyncio
            from core.skills.autoskills_runtime import maybe_update_autoskill
            _asyncio.create_task(maybe_update_autoskill(
                history=history, user_text=user_text, assistant_text=full_response,
                domain=_effective_ctx or plugin_context or "auto",
                request_id=_req_id, session_id=session_id, call_llm=_call_llm,
            ))
        except Exception:
            pass