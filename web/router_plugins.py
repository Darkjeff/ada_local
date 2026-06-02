"""
web/router_plugins.py — Router FastAPI générique pour les plugins ADA.

Expose :
  GET  /api/plugins                      → liste des plugins actifs
  GET  /api/plugins/universes            → univers actifs + plugins
  GET  /api/plugins/kpis/all             → KPIs agrégés tous plugins
  GET  /api/plugins/quick-prompts/all    → quick-prompts tous plugins
  GET  /api/plugins/context/system-prompt → system prompt combiné
  GET  /api/plugins/{id}/kpis            → KPIs d'un plugin
  GET  /api/plugins/{id}/quick-prompts   → quick-prompts d'un plugin
  POST /api/plugins/{id}/action          → action sur un plugin spécifique
  POST /api/plugins/dispatch             → dispatch global (plugin → n8n → executor)
  POST /api/plugins/confirm              → exécution après confirmation utilisateur

Branchement dans server.py (sans guard — liste vide si aucun plugin) :
    from web.router_plugins import router as _plugins_router
    app.include_router(_plugins_router)
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.plugin_registry import plugin_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


# ── Schémas ───────────────────────────────────────────────────────────────────

class ActionRequest(BaseModel):
    action: str
    params: dict = {}


# ── Endpoints liste / metadata ────────────────────────────────────────────────

@router.get("")
async def list_plugins():
    """Liste tous les plugins actifs avec leurs métadonnées."""
    return [
        {
            "id":            p.plugin_id,
            "label":         p.display_name,
            "icon":          p.icon,
            "universe":      p.universe,
            "color":         p.color,
            "nav_items":     p.get_nav_items(),
            "quick_prompts": p.get_quick_prompts(),
        }
        for p in plugin_registry.all()
    ]


# ── Catalogue de tous les modules (actifs ou non) ────────────────────────────
# Source de vérité unique côté serveur. Ajouter ici tout nouveau plugin.
PLUGIN_CATALOG = [
    {"key": "domotique",    "label": "Domotique",      "icon": "🏠", "sub": "HA, Kasa, Domoticz"},
    {"key": "proxmox",      "label": "Infrastructure", "icon": "🖥️", "sub": "Proxmox, VMs, NAS"},
    {"key": "rmm",          "label": "RMM Clients",    "icon": "🔧", "sub": "Gestion postes clients"},
    {"key": "telephony",    "label": "Téléphonie",     "icon": "📞", "sub": "IPBX, lignes SIP"},
    {"key": "print3d",      "label": "Impression 3D",  "icon": "🖨️", "sub": "K1, OctoPrint…"},
    {"key": "music",        "label": "Musique",        "icon": "🎵", "sub": "Navidrome"},
    {"key": "bibliotheque", "label": "Bibliothèque",   "icon": "📚", "sub": "Calibre-Web"},
    {"key": "societe",      "label": "Sociétés CRM",   "icon": "🏢", "sub": "Tableau de bord"},
    {"key": "margepro",     "label": "MargePro",       "icon": "💰", "sub": "Calcul marges"},
]


@router.get("/catalog")
async def plugin_catalog():
    """
    Retourne la liste de tous les modules déclarés (actifs ou non)
    avec leur état courant.
    settings_store.modules.<key> a la priorité sur config.MODULES_ENABLED.
    Utilisé par le panneau Plugins des paramètres.
    """
    from config import MODULES_ENABLED
    from core.settings_store import settings as _settings

    def _is_enabled(key: str) -> bool:
        store_val = _settings.get(f"modules.{key}")
        return store_val if store_val is not None else MODULES_ENABLED.get(key, False)

    return [
        {
            "key":     entry["key"],
            "label":   entry["label"],
            "icon":    entry["icon"],
            "sub":     entry["sub"],
            "enabled": _is_enabled(entry["key"]),
            "loaded":  plugin_registry.is_active(entry["key"]),
        }
        for entry in PLUGIN_CATALOG
    ]


@router.get("/universes")
async def list_universes():
    """Liste les univers actifs avec leurs plugins regroupés."""
    universes: dict[str, list] = {}
    for p in plugin_registry.all():
        universes.setdefault(p.universe, []).append({
            "id":    p.plugin_id,
            "label": p.display_name,
            "icon":  p.icon,
            "color": p.color,
        })
    return universes


# ── KPIs ──────────────────────────────────────────────────────────────────────

@router.get("/kpis/all")
async def all_plugins_kpis():
    """KPIs de tous les plugins actifs agrégés — pour le dashboard global."""
    result = []
    for p in plugin_registry.all():
        try:
            kpis = p.get_dashboard_kpis()
        except Exception as exc:
            logger.warning("[router_plugins] KPIs %s: %s", p.plugin_id, exc)
            kpis = []
        for kpi in kpis:
            kpi["plugin_id"]    = p.plugin_id
            kpi["universe"]     = p.universe
            kpi["plugin_color"] = p.color
        result.extend(kpis)
    return result


@router.get("/{plugin_id}/kpis")
async def plugin_kpis(plugin_id: str):
    """KPIs temps-réel d'un plugin spécifique."""
    plugin = plugin_registry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' introuvable")
    try:
        return plugin.get_dashboard_kpis()
    except Exception as exc:
        logger.error("[router_plugins] KPIs %s: %s", plugin_id, exc)
        return []


# ── Quick-prompts ─────────────────────────────────────────────────────────────

@router.get("/quick-prompts/all")
async def all_quick_prompts(universe: str | None = None):
    """
    Quick-prompts de tous les plugins, optionnellement filtrés par univers.
    Utilisé pour peupler la barre de quick-prompts du chat selon le contexte actif.
    """
    result = []
    for p in plugin_registry.all():
        if universe and p.universe != universe:
            continue
        try:
            prompts = p.get_quick_prompts()
        except Exception:
            prompts = []
        result.append({
            "plugin_id": p.plugin_id,
            "universe":  p.universe,
            "color":     p.color,
            "icon":      p.icon,
            "prompts":   prompts,
        })
    return result


@router.get("/{plugin_id}/quick-prompts")
async def plugin_quick_prompts(plugin_id: str, context_id: str | None = None):
    """Quick-prompts d'un plugin, optionnellement filtrés par context_id."""
    plugin = plugin_registry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' introuvable")
    return plugin.get_quick_prompts(company_id=context_id)


# ── System prompt ─────────────────────────────────────────────────────────────

@router.get("/context/system-prompt")
async def plugins_system_prompt(context_id: str | None = None):
    """
    Retourne le system prompt combiné de tous les plugins actifs.
    Utilisé par le frontend pour afficher les capacités à l'utilisateur.
    """
    return {
        "context_id":    context_id,
        "system_prompt": plugin_registry.combined_system_prompt_injection(context_id),
    }


# ── Actions ───────────────────────────────────────────────────────────────────

@router.post("/{plugin_id}/action")
async def plugin_action(plugin_id: str, req: ActionRequest):
    """
    Dispatch une action vers un plugin spécifique.
    Vérifie les confirmations requises avant exécution.
    Retourne { success, message, data } ou { confirm_required, ... }.
    """
    plugin = plugin_registry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' introuvable")

    # Vérifier si confirmation requise
    func_def = next(
        (f for f in plugin.get_function_definitions()
         if f["function"]["name"] == req.action),
        None,
    )
    if func_def and func_def["function"].get("x_confirm_required"):
        confirm_msg = func_def["function"].get(
            "x_confirm_message", f"Confirmer {req.action} ?"
        )
        return {
            "confirm_required": True,
            "message":          confirm_msg,
            "func":             req.action,
            "params":           req.params,
        }

    try:
        return plugin.handle_action(req.action, req.params)
    except Exception as exc:
        logger.error("[router_plugins] action %s.%s: %s", plugin_id, req.action, exc)
        return {"success": False, "message": str(exc), "data": None}


@router.post("/dispatch")
async def global_dispatch(req: ActionRequest):
    """
    Dispatch global d'une action :
    1. Cherche dans plugin_registry.dispatch_action()
    2. Fallback n8n_executor si aucun plugin ne la reconnaît
    3. Fallback function_executor si n8n indisponible (via n8n_executor)

    Vérifie les confirmations requises (toutes les function_definitions).
    """
    # Vérifier confirmation sur tous les plugins
    from config import FUNCTIONS
    all_defs = FUNCTIONS + plugin_registry.combined_function_definitions()
    func_def = next(
        (f for f in all_defs if f["function"]["name"] == req.action), None
    )
    if func_def and func_def["function"].get("x_confirm_required"):
        confirm_msg = func_def["function"].get(
            "x_confirm_message", f"Confirmer {req.action} ?"
        )
        return {
            "confirm_required": True,
            "message":          confirm_msg,
            "func":             req.action,
            "params":           req.params,
        }

    # Dispatch plugin
    result = plugin_registry.dispatch_action(req.action, req.params)
    if result is not None:
        return result

    # Fallback n8n_executor (avec fallback function_executor intégré)
    from core.n8n_executor import n8n_executor
    action_kebab = req.action.replace("_", "-")
    return n8n_executor.call(action_kebab, req.params)


# ── Confirmation (exécution après confirmation utilisateur) ───────────────────

class ConfirmRequest(BaseModel):
    func:   str
    params: dict = {}


@router.post("/confirm")
async def confirm_action(req: ConfirmRequest):
    """
    Exécute une action après confirmation explicite de l'utilisateur.
    Utilisé par le frontend après que l'utilisateur a cliqué "Confirmer".
    Bypass la vérification x_confirm_required.
    """
    # Dispatch direct sans vérification confirmation (déjà confirmé)
    result = plugin_registry.dispatch_action(req.func, req.params)
    if result is not None:
        return result

    from core.n8n_executor import n8n_executor
    action_kebab = req.func.replace("_", "-")
    return n8n_executor.call(action_kebab, req.params)
