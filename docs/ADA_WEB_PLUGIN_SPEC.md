# ADA Web — Spec d'intégration plugins dans `web/pipeline.py`
**Version** : 0.2 — couche web uniquement (`web/`)  
**Date** : mai 2026  
**Base** : branche `univers` — `web/server.py` + `web/pipeline.py`

---

## 1. État des lieux après implémentation des plugins

### Ce qui est déjà en place (✓)

`web/server.py` — `_startup()` :
```python
register_enabled_plugins()
inject_plugin_utterances(plugin_registry.combined_semantic_utterances())
n8n_executor.register_plugin_webhooks(plugin_registry.combined_n8n_webhooks())
```
Les plugins sont enregistrés, le semantic_router les connaît, n8n_executor a leurs webhooks.

### Ce qui manque (✗)

| Fichier | Problème |
|---|---|
| `web/pipeline.py` — `_call_with_tools()` | `FUNCTIONS` hardcodé, ne voit pas les fonctions des plugins |
| `web/pipeline.py` — `_call_with_tools()` | fallback sur `function_executor.execute()` uniquement — jamais `plugin_registry.dispatch_action()` |
| `web/pipeline.py` — `process_message()` | system prompt fixe — pas d'injection `combined_system_prompt_injection()` |
| `web/pipeline.py` — `process_message()` | `company_context` limité au filtre infra — pas branché aux univers plugins |
| `web/server.py` | pas de `router_plugins.py` pour les endpoints REST des plugins (KPIs, actions directes) |

---

## 2. Modifications `web/pipeline.py`

### 2.1 `_call_with_tools()` — fonctions dynamiques + dispatch plugin

**Remplacement complet de la fonction** (le reste du fichier est inchangé) :

```python
async def _call_with_tools(
    text: str,
    conversation_messages: list[dict],
    plugin_context_id: str | None = None,
) -> str:
    """
    Tool-calling avec fonctions natives + fonctions des plugins actifs.
    Dispatch : plugin_registry.dispatch_action() → n8n_executor → function_executor.
    """
    from config import FUNCTIONS
    from core.plugin_registry import plugin_registry as _pr
    from core.n8n_executor import n8n_executor

    # Fonctions effectives = natives + plugins actifs
    plugin_functions = _pr.combined_function_definitions()
    effective_functions = FUNCTIONS + plugin_functions

    # Bloc system prompt incluant les capacités plugins
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
        "- passthrough: ONLY for greetings, chitchat, or questions needing no action."
    )
    if plugin_sys:
        dispatcher_system += f"\n\nActive plugin capabilities:\n{plugin_sys}"

    try:
        async with httpx.AsyncClient(timeout=150.0) as client:
            r = await client.post(
                _chat_url(),
                json={
                    "model": _chat_model(),
                    "messages": [
                        {"role": "system", "content": dispatcher_system},
                        {"role": "user",   "content": text},
                    ],
                    "tools":  effective_functions,
                    "stream": False,
                    "think":  False,
                    "keep_alive": "5m",
                },
            )
            r.raise_for_status()
            tool_calls = r.json().get("message", {}).get("tool_calls", [])
    except Exception:
        return await _call_llm(conversation_messages, thinking=False)

    if not tool_calls:
        return await _call_llm(conversation_messages, thinking=False)

    call      = tool_calls[0]
    func_name = call.get("function", {}).get("name", "")
    params    = call.get("function", {}).get("arguments", {}) or {}

    if func_name == "passthrough":
        thinking = bool(params.get("thinking", False))
        return await _call_llm(conversation_messages, thinking=thinking)

    # ── Vérification confirmation requise (actions sensibles) ──────────────
    func_def = next(
        (f for f in effective_functions if f["function"]["name"] == func_name), None
    )
    if func_def and func_def["function"].get("x_confirm_required"):
        confirm_msg = func_def["function"].get(
            "x_confirm_message", f"Confirmer {func_name} ?"
        )
        # Côté web : retourner un message de confirmation au lieu d'exécuter
        # Le frontend détecte "__confirm__" et affiche une carte de confirmation
        return f"__confirm__{func_name}|{confirm_msg}|{json.dumps(params)}"

    # ── Dispatch : plugin → n8n → function_executor ───────────────────────
    plugin_result = _pr.dispatch_action(func_name, params)
    if plugin_result is not None:
        result = plugin_result
    else:
        action = func_name.replace("_", "-")
        result = n8n_executor.call(action, params)

    success    = result.get("success", False)
    result_msg = result.get("message", "")

    # Réponse naturelle en contexte
    followup = list(conversation_messages)
    hint = f"[Résultat: {'succès' if success else 'échec'}. {result_msg}]"
    followup[-1] = {
        "role": "user",
        "content": (
            f"{text}\n{hint}\n"
            "Réponds en français de façon naturelle et concise."
        ),
    }
    return await _call_llm(followup, thinking=False)
```

### 2.2 `_system_prompt()` — injection contexte plugin

```python
def _system_prompt(plugin_context_id: str | None = None) -> str:
    base = (
        "Tu es ADA, une assistante IA locale. "
        "Réponds TOUJOURS en français. "
        "RÈGLE ABSOLUE : réponses courtes, 1 à 3 phrases max. "
        "Pas d'intro, pas de conclusion, pas de présentation de toi-même. "
        "Va directement à la réponse."
    )
    try:
        from core.plugin_registry import plugin_registry as _pr
        injection = _pr.combined_system_prompt_injection(context_id=plugin_context_id)
        if injection:
            base += f"\n\n### Capacités disponibles ###\n{injection}"
    except Exception:
        pass
    return base
```

### 2.3 `process_message()` — signature étendue + branchements

**Changements ciblés dans la fonction existante** (les blocs inchangés sont omis) :

```python
async def process_message(
    message: str,
    history: list[dict],
    company_context: str | None = None,   # ← existant, renommé sémantiquement
    plugin_context: str | None = None,    # ← NOUVEAU : univers actif ("home", "opent"…)
    context_id: str | None = None,        # ← NOUVEAU : sous-contexte (company_id, etc.)
) -> AsyncGenerator[str, None]:
```

> **Compatibilité** : `company_context` reste identique pour ne pas casser `server.py`. Les nouveaux paramètres sont optionnels avec valeur par défaut `None`.

**Dans le corps de `process_message()`, remplacer :**

```python
# AVANT
messages: list[dict] = [{"role": "system", "content": _system_prompt()}]

# APRÈS — résoudre le context_id effectif
_effective_ctx = context_id or company_context or None
messages: list[dict] = [{"role": "system", "content": _system_prompt(_effective_ctx)}]
```

**Et remplacer l'appel à `_call_with_tools` :**

```python
# AVANT
response = await _call_with_tools(user_text, messages)

# APRÈS
response = await _call_with_tools(user_text, messages, plugin_context_id=_effective_ctx)
```

**Gérer le token de confirmation dans le yield final :**

```python
# Après l'appel _call_with_tools, avant le yield :
if response and response.startswith("__confirm__"):
    # Format : __confirm__<func_name>|<message>|<params_json>
    _, payload = response.split("__confirm__", 1)
    parts = payload.split("|", 2)
    confirm_func    = parts[0] if len(parts) > 0 else ""
    confirm_message = parts[1] if len(parts) > 1 else "Confirmer ?"
    confirm_params  = parts[2] if len(parts) > 2 else "{}"
    # Émettre un event JSON spécial que le frontend intercepte
    yield json.dumps({
        "__type": "confirm_required",
        "func":    confirm_func,
        "message": confirm_message,
        "params":  confirm_params,
    })
    return
```

---

## 3. Nouveau fichier : `web/router_plugins.py`

Router FastAPI générique pour tous les plugins actifs.
Branché dans `server.py` de façon conditionnelle (pattern identique à `router_societe`).

```python
"""
web/router_plugins.py — Router FastAPI générique pour les plugins ADA.
Expose :
  GET  /api/plugins                     → liste des plugins actifs
  GET  /api/plugins/{id}/kpis           → KPIs dashboard d'un plugin
  POST /api/plugins/{id}/action         → dispatch d'une action plugin
  GET  /api/plugins/{id}/quick-prompts  → quick-prompts pour le chat
  GET  /api/plugins/context/{id}        → system prompt injection d'un plugin
"""
from __future__ import annotations

import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

from core.plugin_registry import plugin_registry

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


# ── Schémas ───────────────────────────────────────────────────────────────────

class ActionRequest(BaseModel):
    action: str
    params: dict = {}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_plugins():
    """Liste tous les plugins actifs avec leurs métadonnées."""
    return [
        {
            "id":           p.plugin_id,
            "label":        p.display_name,
            "icon":         p.icon,
            "universe":     p.universe,
            "color":        p.color,
            "nav_items":    p.get_nav_items(),
            "quick_prompts": p.get_quick_prompts(),
        }
        for p in plugin_registry.all()
    ]


@router.get("/{plugin_id}/kpis")
async def plugin_kpis(plugin_id: str):
    """KPIs temps-réel d'un plugin (dashboard)."""
    plugin = plugin_registry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' introuvable")
    return plugin.get_dashboard_kpis()


@router.get("/kpis/all")
async def all_plugins_kpis():
    """KPIs de tous les plugins actifs agrégés."""
    result = []
    for p in plugin_registry.all():
        kpis = p.get_dashboard_kpis()
        for kpi in kpis:
            kpi["plugin_id"]    = p.plugin_id
            kpi["universe"]     = p.universe
            kpi["plugin_color"] = p.color
        result.extend(kpis)
    return result


@router.post("/{plugin_id}/action")
async def plugin_action(plugin_id: str, req: ActionRequest):
    """
    Dispatch une action vers un plugin.
    Retourne { success, message, data }.
    """
    plugin = plugin_registry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' introuvable")

    # Vérifier confirmation requise
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

    result = plugin.handle_action(req.action, req.params)
    return result


@router.post("/dispatch")
async def global_dispatch(req: ActionRequest):
    """
    Dispatch global : cherche le plugin qui déclare l'action et l'exécute.
    Fallback n8n_executor si aucun plugin ne la reconnaît.
    """
    result = plugin_registry.dispatch_action(req.action, req.params)
    if result is not None:
        return result

    # Fallback n8n_executor
    from core.n8n_executor import n8n_executor
    action_kebab = req.action.replace("_", "-")
    return n8n_executor.call(action_kebab, req.params)


@router.get("/{plugin_id}/quick-prompts")
async def plugin_quick_prompts(plugin_id: str, context_id: str | None = None):
    """Quick-prompts d'un plugin (optionnellement filtrés par context_id)."""
    plugin = plugin_registry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' introuvable")
    return plugin.get_quick_prompts(company_id=context_id)


@router.get("/quick-prompts/all")
async def all_quick_prompts(universe: str | None = None):
    """Quick-prompts de tous les plugins, optionnellement filtrés par univers."""
    result = []
    for p in plugin_registry.all():
        if universe and p.universe != universe:
            continue
        prompts = p.get_quick_prompts()
        result.append({
            "plugin_id": p.plugin_id,
            "universe":  p.universe,
            "color":     p.color,
            "prompts":   prompts,
        })
    return result


@router.get("/context/system-prompt")
async def plugins_system_prompt(context_id: str | None = None):
    """Retourne le system prompt combiné de tous les plugins actifs."""
    return {
        "context_id":    context_id,
        "system_prompt": plugin_registry.combined_system_prompt_injection(context_id),
    }


@router.get("/universes")
async def list_universes():
    """Liste les univers actifs avec leurs plugins."""
    universes: dict[str, list] = {}
    for p in plugin_registry.all():
        universes.setdefault(p.universe, []).append({
            "id":    p.plugin_id,
            "label": p.display_name,
            "icon":  p.icon,
            "color": p.color,
        })
    return universes
```

### Branchement dans `server.py`

Ajouter après les imports existants des routers :

```python
# web/server.py — après les autres include_router
from web.router_plugins import router as _plugins_router
app.include_router(_plugins_router)
```

> Pas de guard `MODULES_ENABLED` ici — le router est toujours actif, mais retourne une liste vide si aucun plugin n'est enregistré.

---

## 4. Gestion des confirmations côté frontend

Le pipeline émet maintenant un JSON spécial pour les actions sensibles :

```json
{
  "__type": "confirm_required",
  "func":   "alarm_set",
  "message": "Confirmer le changement d'état de l'alarme ?",
  "params":  "{\"state\": \"arm\"}"
}
```

Le frontend (`web/static/index.html`) doit :

1. Dans le handler SSE, détecter `data.__type === "confirm_required"`
2. Afficher une carte de confirmation avec boutons Confirmer / Annuler
3. Sur confirmation : POST `/api/plugins/dispatch` avec `{ action: func, params: JSON.parse(params) }`
4. Sur annulation : émettre un message `"Action annulée."` dans le chat

---

## 5. Extension `web/static/index.html` — PluginContextBar

Le frontend doit exposer une barre de sélection d'univers/contexte,
équivalent web de `ChatContextBar` Qt.

### Endpoint à appeler au chargement

```
GET /api/plugins/universes
```

Réponse :
```json
{
  "home":   [{ "id": "domotique", "label": "Domotique", "icon": "🏠", "color": "#7c5cfc" }],
  "opent":  [{ "id": "proxmox",   ... }, { "id": "rmm", ... }],
  "margep": [{ "id": "margepro",  ... }],
  "global": [{ "id": "societe",   ... }]
}
```

### Payload `ChatRequest` étendu

```typescript
// Côté frontend — à envoyer avec chaque message
{
  message:        "Allume le salon",
  history:        [...],
  company_context: null,     // compat existant
  plugin_context: "home",    // univers sélectionné
  context_id:     null       // sous-contexte (ex: company_id)
}
```

### Dans `server.py` — `ChatRequest` étendu

```python
class ChatRequest(BaseModel):
    message:         str
    history:         list[dict] = []
    company_context: str | None = None   # compat existant
    plugin_context:  str | None = None   # NOUVEAU : univers actif
    context_id:      str | None = None   # NOUVEAU : sous-contexte
```

Et dans `/api/chat` :

```python
async for chunk in process_message(
    req.message,
    req.history,
    company_context=req.company_context,
    plugin_context=req.plugin_context,
    context_id=req.context_id,
):
```

---

## 6. Récapitulatif des fichiers à modifier/créer

| Fichier | Action | Nature |
|---|---|---|
| `web/pipeline.py` | Modifier `_call_with_tools()` | fonctions dynamiques + dispatch plugin + confirm |
| `web/pipeline.py` | Modifier `_system_prompt()` | injection plugin context |
| `web/pipeline.py` | Modifier `process_message()` | signature étendue + branchements |
| `web/server.py` | Modifier `ChatRequest` + `/api/chat` | nouveaux paramètres plugin_context |
| `web/server.py` | Ajouter `include_router(_plugins_router)` | branchement router plugins |
| `web/router_plugins.py` | **Créer** | nouveau router générique plugins |
| `web/static/index.html` | Modifier | PluginContextBar + gestion confirm_required SSE |

---

## 7. Ordre d'implémentation recommandé

1. `web/router_plugins.py` — autonome, ne dépend de rien de nouveau
2. Branchement dans `web/server.py` (2 lignes)
3. `web/pipeline.py` — `_call_with_tools()` + `_system_prompt()` + `process_message()`
4. Extension `ChatRequest` dans `web/server.py`
5. Frontend — PluginContextBar + gestion `confirm_required`
