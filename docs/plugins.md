# Guide des Plugins ADA

> **Version :** ADA local · Python 3.11 · FastAPI · PySide6  
> **Fichier de référence :** `core/plugin_registry.py`

---

## Vue d'ensemble

Le système de plugins ADA permet d'ajouter des modules fonctionnels indépendants sans toucher au cœur de l'application. Chaque plugin expose ses fonctionnalités via une interface commune (`BasePlugin`) et s'enregistre dans un registry singleton.

```
core/
  plugin_registry.py      ← BasePlugin + PluginRegistry + register_enabled_plugins()
  <mon_plugin>/
    __init__.py
    plugin.py             ← Classe MyPlugin(BasePlugin)
    ...

config.py                 ← MODULES_ENABLED : activation par défaut
core/settings_store.py    ← modules.<key> : override utilisateur
web/router_plugins.py     ← PLUGIN_CATALOG : métadonnées UI
```

---

## 1. Créer un nouveau plugin

### 1.1 Structure des fichiers

```
core/mon_plugin/
  __init__.py          (vide)
  plugin.py            (obligatoire)
```

### 1.2 Squelette minimal (`plugin.py`)

```python
"""
MonPlugin — Description courte.
Univers : <home|opent|uscss|margep|global>

Guard : ce fichier ne doit être importé QUE si MODULES_ENABLED["mon_plugin"] = True.
"""
from __future__ import annotations
from core.plugin_registry import BasePlugin


class MonPlugin(BasePlugin):

    # ── Identité ────────────────────────────────────────────────────
    plugin_id:    str = "mon_plugin"          # snake_case, unique
    display_name: str = "Mon Plugin"          # Affiché dans la nav
    icon:         str = "🔌"                  # Emoji ou chemin
    universe:     str = "global"              # Voir §2 — Univers
    color:        str = "#8b9bb4"             # Couleur hex UI

    # ── Méthodes obligatoires ────────────────────────────────────────

    def get_nav_items(self) -> list[dict]:
        """Items de navigation ajoutés à l'univers."""
        return [
            {"label": "Mon Plugin", "icon": "🔌", "route": "mon_plugin"}
        ]

    def get_chat_context(self, company_id: str | None = None) -> str:
        """Contexte injecté dans le system prompt du chat."""
        return "Mon plugin est actif. Il fait X, Y, Z."

    def get_skills(self) -> list[str]:
        """Fichiers skill .txt à charger depuis skills/mon_plugin/."""
        return ["mon_plugin_general"]

    def get_quick_prompts(self, company_id: str | None = None) -> list[str]:
        """Suggestions rapides affichées dans la barre de chat."""
        return ["État de mon plugin", "Que peut faire mon plugin ?"]
```

---

## 2. Univers disponibles

| Clé | Description | Exemple |
|---|---|---|
| `home` | Maison — domotique, caméras | DomotiquePlugin |
| `opent` | OpenTechno — infra, RMM | ProxmoxPlugin, RmmPlugin |
| `uscss` | USCSS — sociétés CRM | SocietePlugin |
| `margep` | MargePro — commercial | MargeProPlugin |
| `global` | Tous univers | Plugins génériques |

---

## 3. Méthodes optionnelles de BasePlugin

### 3.1 Tool-calling LLM — `get_function_definitions()`

Définit les fonctions que le LLM peut appeler via tool-calling Ollama.

```python
def get_function_definitions(self) -> list[dict]:
    return [
        {
            "name": "mon_action",
            "description": "Description pour le LLM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "param1": {"type": "string", "description": "…"},
                },
                "required": ["param1"],
            },
            # Confirmation obligatoire avant exécution :
            "x_confirm_required": True,
            "x_confirm_message":  "Confirmer l'action sur {param1} ?",
            "x_confirm_cmd":      "commande {param1}",   # affiché dans la carte
        }
    ]
```

> **Confirmation :** si `x_confirm_required: True`, le pipeline intercepte l'appel et affiche une carte de confirmation dans le chat avant d'exécuter. Les placeholders `{param}` sont interpolés avec les vraies valeurs.

### 3.2 Webhooks n8n — `get_n8n_webhooks()`

```python
def get_n8n_webhooks(self) -> dict[str, str]:
    return {
        "mon-action": "https://n8n.example.com/webhook/mon-action",
    }
```

L'action kebab-case doit correspondre au `name` snake→kebab de la fonction définie dans `get_function_definitions()`.

### 3.3 Exécution locale — `handle_action()`

Fallback si n8n est indisponible ou ne couvre pas l'action.

```python
def handle_action(self, action: str, params: dict) -> dict:
    if action == "mon_action":
        # … logique locale …
        return {"success": True, "message": "Fait.", "data": {}}
    return {"success": False, "message": f"Action inconnue : {action}"}
```

### 3.4 Semantic router — `get_semantic_utterances()`

Phrases d'exemple qui déclenchent le plugin dans le routeur sémantique.

```python
def get_semantic_utterances(self) -> dict[str, list[str]]:
    return {
        "function_gemma": [
            "lance mon action",
            "exécute mon plugin",
            "active le truc",
        ]
    }
```

### 3.5 KPIs dashboard — `get_kpis()`

```python
def get_kpis(self) -> list[dict]:
    return [
        {
            "id":    "mon_kpi",
            "label": "Ma métrique",
            "value": "42",
            "unit":  "unités",
            "color": "#7c5cfc",   # optionnel
            "trend": "+5%",       # optionnel
        }
    ]
```

### 3.6 System prompt — `get_system_prompt_injection()`

Complément au `get_chat_context()` — injecté dans le system prompt global.

```python
def get_system_prompt_injection(self, context_id: str | None = None) -> str:
    return """
## Mon Plugin
- Capacités : X, Y, Z
- Fonctions disponibles : mon_action (confirmation requise)
- IMPORTANT : toujours demander confirmation avant d'exécuter mon_action.
"""
```

### 3.7 Lifecycle — `on_enable()` / `on_disable()`

```python
def on_enable(self) -> None:
    """Appelé quand le plugin est activé depuis les paramètres."""
    # Initialiser des ressources, démarrer des watchers, etc.

def on_disable(self) -> None:
    """Appelé quand le plugin est désactivé."""
    # Libérer les ressources.
```

---

## 4. Enregistrer le plugin (checklist)

### 4.1 `config.py` — Activer par défaut

```python
# config.py
MODULES_ENABLED: dict = {
    # … plugins existants …
    "mon_plugin": True,   # ← ajouter ici
}
```

### 4.2 `core/plugin_registry.py` — Ajouter au loader

Dans la fonction `register_enabled_plugins()` :

```python
# MODULE_MON_PLUGIN
if _is_enabled("mon_plugin"):
    from core.mon_plugin.plugin import MonPlugin
    plugin_registry.register(MonPlugin())
else:
    print("[PluginRegistry] Module 'mon_plugin' désactivé")
```

### 4.3 `core/settings_store.py` — Valeur par défaut

```python
# Dans _DEFAULT_SETTINGS → "modules"
"modules": {
    # … clés existantes …
    "mon_plugin": True,   # ← ajouter ici
},
```

### 4.4 `web/router_plugins.py` — Catalogue UI

```python
PLUGIN_CATALOG = [
    # … entrées existantes …
    {"key": "mon_plugin", "label": "Mon Plugin", "icon": "🔌", "sub": "Description courte"},
]
```

> C'est **la seule modification frontend nécessaire**. Le panneau Plugins des paramètres se met à jour automatiquement depuis cet endpoint.

---

## 5. Ajouter des skills LLM (optionnel)

Créer les fichiers dans `skills/mon_plugin/` :

```
skills/mon_plugin/
  mon_plugin_general.txt    ← fichier principal
```

Le fichier `.txt` est un bloc de contexte textuel chargé dans le system prompt quand le plugin est actif. Le nom doit correspondre à ce que retourne `get_skills()`.

---

## 6. Résumé — checklist complète

```
□ core/mon_plugin/__init__.py              (vide)
□ core/mon_plugin/plugin.py               (classe MonPlugin extends BasePlugin)
□ config.py                               MODULES_ENABLED["mon_plugin"] = True
□ core/plugin_registry.py                 bloc if _is_enabled("mon_plugin") dans register_enabled_plugins()
□ core/settings_store.py                  "mon_plugin": True dans _DEFAULT_SETTINGS["modules"]
□ web/router_plugins.py                   entrée dans PLUGIN_CATALOG
□ skills/mon_plugin/xxx.txt               (optionnel — fichiers skill LLM)
```

---

## 7. Exemple complet — plugin minimal fonctionnel

Voir `core/rmm/plugin.py` pour un exemple complet avec :
- `get_function_definitions()` avec confirmation (`x_confirm_required`, `x_confirm_message`, `x_confirm_cmd`)
- `get_n8n_webhooks()` pour exécution via n8n
- `handle_action()` pour fallback local
- `get_semantic_utterances()` pour le routeur sémantique
- `get_system_prompt_injection()` avec instructions LLM détaillées
- KPIs dashboard via `get_kpis()`
