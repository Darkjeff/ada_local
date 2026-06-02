# ADA — Spécification Système de Plugins
**Version** : 0.1 — branche `univers`  
**Date** : mai 2026  
**Périmètre** : enrichissement du `PluginRegistry` existant pour intégration profonde dans le pipeline chat, le semantic_router, le n8n_executor et l'UI

---

## 1. Contexte et état de l'existant

### 1.1 Ce qui existe déjà (ne pas casser)

| Composant | Fichier | Rôle |
|---|---|---|
| `BasePlugin` + `PluginRegistry` | `core/plugin_registry.py` | Squelette : register, nav_items, chat_context, skills, quick_prompts |
| `SocietePlugin` | `core/societe/plugin.py` | Seul plugin implémenté — référence à suivre |
| `ChatContextBar` | `gui/components/societe_context_bar.py` | Barre de contexte société dans le chat |
| `ChatWorker` + `ChatHandlers` | `gui/handlers.py` | Tout le pipeline LLM + routing |
| `semantic_router` | `core/semantic_router.py` | Routes : qwen_basic, qwen_thinking, function_gemma, cad, print, vision, youtube |
| `n8n_executor` | `core/n8n_executor.py` | POST webhooks n8n + fallback FunctionExecutor |
| `pattern_dispatcher` | `core/pattern_dispatcher.py` | Regex déterministe pré-LLM |
| `MODULES_ENABLED` | `config.py` | Feature flags par module |
| `skill_manager` | injecté via `_stream_qwen_response` | Contexte compétences |

### 1.2 Le problème central

`_handle_function_gemma()` dans `handlers.py` est aujourd'hui **monolithique et fermé** :
- Les actions possibles (`control_light`, `set_timer`…) sont **hardcodées** dans le system prompt LLM et dans `FUNCTIONS` (config.py)
- `n8n_executor` ne sait pas quels webhooks les plugins ont enregistrés
- `semantic_router` ne connaît pas les utterances des plugins actifs
- Ajouter la domotique = modifier 5 fichiers à la main

**Objectif** : qu'ajouter un plugin suffise à tout câbler automatiquement.

---

## 2. Extensions de `BasePlugin`

### 2.1 Nouvelles méthodes abstraites / optionnelles

```python
class BasePlugin(ABC):

    # ── Existant (inchangé) ──────────────────────────────────
    plugin_id: str = ""
    display_name: str = ""
    icon: str = "🔌"

    def get_nav_items(self) -> list[dict]: ...
    def get_chat_context(self, company_id: str | None = None) -> str: ...
    def get_skills(self) -> list[str]: ...
    def get_quick_prompts(self, company_id: str | None = None) -> list[str]: ...
    def on_enable(self) -> None: ...
    def on_disable(self) -> None: ...

    # ── NOUVEAU ──────────────────────────────────────────────

    # Univers d'appartenance — "home" | "opent" | "uscss" | "margep" | "global"
    universe: str = "global"

    # Couleur d'accentuation hex pour l'UI
    color: str = "#8b9bb4"

    def get_function_definitions(self) -> list[dict]:
        """
        Retourne les définitions de fonctions au format JSON Schema Ollama
        (même format que FUNCTIONS dans config.py).
        Ces fonctions sont injectées dans le tool-calling LLM quand le plugin est actif.

        Exemple :
        [{
            "type": "function",
            "function": {
                "name": "control_light",
                "description": "...",
                "parameters": { ... }
            }
        }]
        """
        return []

    def get_semantic_utterances(self) -> dict[str, list[str]]:
        """
        Retourne les utterances à ajouter au semantic_router.
        Clé = route cible (ex: "function_gemma"), valeur = liste de phrases.

        Ces utterances sont fusionnées avec les utterances natives du router
        au démarrage, ou à chaque activation du plugin.

        Exemple :
        {
            "function_gemma": [
                "allume la lumière", "éteins le salon",
                "active le mode nuit", "thermostat bureau"
            ]
        }
        """
        return {}

    def get_n8n_webhooks(self) -> dict[str, str]:
        """
        Mapping action → URL de webhook n8n.
        Surcharge ou complète le mapping _WEBHOOK_TO_FUNC du n8n_executor.

        Exemple :
        {
            "control-light": "http://n8n.local/webhook/ha-control-light",
            "scene-activate": "http://n8n.local/webhook/ha-scene"
        }
        """
        return {}

    def handle_action(self, action: str, params: dict) -> dict:
        """
        Exécution locale d'une action (fallback si n8n indisponible).
        Retourne { success: bool, message: str, data: Any }.

        N'est appelé que si l'action figure dans get_function_definitions()
        ET que n8n est indisponible ou ne couvre pas cette action.
        """
        return {"success": False, "message": f"Action {action} non implémentée", "data": None}

    def get_system_prompt_injection(self, context_id: str | None = None) -> str:
        """
        Bloc texte injecté dans le system prompt du LLM quand ce plugin est actif.
        Plus ciblé que get_chat_context() : décrit les capacités d'action,
        pas le contexte métier.

        Exemple pour DomotiquePlugin :
        "Tu peux contrôler les appareils domotiques via les fonctions control_light,
        scene_activate et thermostat_set. Pour les actions sensibles (alarme),
        demande toujours confirmation."
        """
        return ""

    def get_dashboard_kpis(self) -> list[dict]:
        """
        KPIs à afficher dans le dashboard global.
        Chaque KPI : { id, label, value, unit?, trend?, color?, tab_link? }
        """
        return []
```

---

## 3. Plugins à créer

### 3.1 `DomotiquePlugin` — `core/domotique/plugin.py`

**Univers** : `home`  
**Dépendance existante** : `core/ha_state_watcher.py` (déjà actif au démarrage)

#### Fonctions exposées au LLM

| Nom fonction | Description | Params clés |
|---|---|---|
| `control_light` | Allume / éteint / dimme une lumière | `action: on/off/dim`, `device_name`, `brightness?` |
| `scene_activate` | Active une scène HA | `scene: focus/relax/night/off/security` |
| `thermostat_set` | Règle le thermostat | `zone`, `temperature` |
| `alarm_set` | Arme / désarme l'alarme | `state: arm/disarm` — `confirmRequired: true` |
| `cover_control` | Volets / portail | `entity`, `action: open/close/stop` |
| `device_status` | État d'un ou tous les appareils | `entity?` |

#### Webhooks n8n

```
control-light   → /webhook/ha-control-light
scene-activate  → /webhook/ha-scene
thermostat-set  → /webhook/ha-thermostat
alarm-set       → /webhook/ha-alarm
cover-control   → /webhook/ha-cover
```

#### Utterances semantic_router (route : `function_gemma`)

```
allume, éteins, lumière, lampe, salon, bureau, chambre,
mode nuit, mode focus, mode relax, thermostat, chauffage,
alarme, portail, volet, éclairage, scène, ambiance
```

#### System prompt injection

```
Tu contrôles la domotique via Home Assistant.
Fonctions disponibles : control_light, scene_activate, thermostat_set, alarm_set, cover_control.
Pour alarm_set demande TOUJOURS une confirmation explicite avant d'exécuter.
Utilise device_status pour vérifier l'état avant d'agir si l'utilisateur pose une question.
```

#### KPIs dashboard

```python
[
    { "id": "domo_devices_on", "label": "Appareils actifs", "value": <depuis HA>, "color": "#7c5cfc" },
    { "id": "domo_temp", "label": "Température salon", "value": <depuis HA>, "unit": "°C" },
    { "id": "domo_alarm", "label": "Alarme", "value": "Armée/Désarmée", "color": dynamic },
]
```

---

### 3.2 `ProxmoxPlugin` — `core/infra/plugin.py`

**Univers** : `opent`

#### Fonctions exposées au LLM

| Nom fonction | Description | `confirmRequired` |
|---|---|---|
| `vm_list` | Liste les VMs d'un node | non |
| `vm_power` | Start / stop / reboot VM | **oui** |
| `vm_backup` | Lance vzdump vers NAS | **oui** |
| `vm_snapshot` | Crée un snapshot | **oui** |
| `node_stats` | CPU / RAM / uptime | non |
| `storage_status` | Capacité NAS / datastores | non |

#### Webhooks n8n

```
vm-list     → /webhook/proxmox-vm-list
vm-power    → /webhook/proxmox-vm-power
vm-backup   → /webhook/proxmox-vm-backup
node-stats  → /webhook/proxmox-node-stats
```

#### Utterances semantic_router

```
proxmox, vm, machine virtuelle, backup, sauvegarde, snapshot,
serveur, node, RAM serveur, CPU serveur, infrastructure,
redémarre, stoppe la vm, vzdump, NAS
```

#### KPIs dashboard

```python
[
    { "id": "prox_nodes", "label": "Nodes online", "value": "2/2", "color": "#00d4ff" },
    { "id": "prox_cpu", "label": "CPU global", "value": "%", "unit": "%" },
    { "id": "prox_ram", "label": "RAM utilisée", "value": "GB / GB" },
    { "id": "prox_backups", "label": "Backups 24h", "value": "✓/✗" },
]
```

---

### 3.3 `RmmPlugin` — `core/rmm/plugin.py`

**Univers** : `opent`

#### Fonctions exposées au LLM

| Nom fonction | Description |
|---|---|
| `rmm_alerts_list` | Liste les alertes actives tous clients |
| `rmm_client_status` | État d'un client spécifique |
| `rmm_service_restart` | Redémarre un service Windows distant |
| `rmm_disk_cleanup` | Lance nettoyage disque distant |

#### Utterances

```
rmm, client, alerte client, disque plein, service arrêté,
monitoring client, supervision, Dupont, Martin, poste distant
```

---

### 3.4 `TelephonyPlugin` — `core/telephony/plugin.py`

**Univers** : `opent`

#### Fonctions exposées au LLM

| Nom fonction | Description |
|---|---|
| `call_status` | État des lignes actives |
| `call_history` | Historique des appels |
| `extension_list` | Liste des extensions SIP |

---

### 3.5 `MargeProPlugin` — `core/margepro/plugin.py`

**Univers** : `margep`  
**Skill existant** : `skills/margepro/SKILL.md` (déjà chargé via skill_manager)

#### Fonctions exposées au LLM

| Nom fonction | Description |
|---|---|
| `generate_post` | Génère un post social media | 
| `schedule_post` | Planifie une publication via n8n |
| `get_analytics` | Métriques de performance posts |

#### Webhooks n8n

```
generate-post   → /webhook/margepro-generate
schedule-post   → /webhook/margepro-schedule
```

#### Utterances

```
post linkedin, post facebook, post instagram, rédige un post,
contenu marketing, accroche, copywriting, margepro,
planifie une publication, calendrier éditorial
```

---

## 4. Modifications du pipeline existant

### 4.1 `core/plugin_registry.py` — méthodes à ajouter

```python
# Agrège toutes les function definitions des plugins actifs
def combined_function_definitions(self) -> list[dict]:
    definitions = []
    for p in self._plugins.values():
        definitions.extend(p.get_function_definitions())
    return definitions

# Agrège les webhooks de tous les plugins actifs
def combined_n8n_webhooks(self) -> dict[str, str]:
    webhooks = {}
    for p in self._plugins.values():
        webhooks.update(p.get_n8n_webhooks())
    return webhooks

# Agrège les injections system prompt
def combined_system_prompt_injection(self, context_id: str | None = None) -> str:
    parts = [p.get_system_prompt_injection(context_id) for p in self._plugins.values()]
    return "\n\n".join(p for p in parts if p.strip())

# Dispatch d'une action vers le bon plugin
def dispatch_action(self, action: str, params: dict) -> dict | None:
    """
    Cherche le plugin qui déclare cette action dans get_function_definitions().
    Retourne None si aucun plugin ne la reconnaît (fallback FunctionExecutor).
    """
    for p in self._plugins.values():
        func_names = [
            f["function"]["name"]
            for f in p.get_function_definitions()
        ]
        if action in func_names:
            return p.handle_action(action, params)
    return None

# Agrège les utterances pour le semantic_router
def combined_semantic_utterances(self) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for p in self._plugins.values():
        for route, utterances in p.get_semantic_utterances().items():
            result.setdefault(route, []).extend(utterances)
    return result
```

---

### 4.2 `core/semantic_router.py` — fonction à ajouter

```python
def inject_plugin_utterances(extra: dict[str, list[str]]) -> None:
    """
    Fusionne des utterances supplémentaires dans _ROUTES.
    Appelé au démarrage après register_enabled_plugins().
    Invalide le cache d'embeddings pour forcer le recalcul.
    """
    for route, utterances in extra.items():
        if route in _ROUTES:
            _ROUTES[route].extend(utterances)
        else:
            _ROUTES[route] = utterances
    # Invalider le cache d'embeddings si existant
    _invalidate_embedding_cache()   # à implémenter selon la logique interne
```

**Point d'appel** : dans `main.py`, après `register_enabled_plugins()` :

```python
from core.plugin_registry import plugin_registry
from core.semantic_router import inject_plugin_utterances

register_enabled_plugins()
inject_plugin_utterances(plugin_registry.combined_semantic_utterances())
```

---

### 4.3 `core/n8n_executor.py` — méthode à ajouter

```python
def register_plugin_webhooks(self, webhooks: dict[str, str]) -> None:
    """
    Enregistre dynamiquement les webhooks des plugins actifs.
    Surcharge _WEBHOOK_TO_FUNC pour les entrées correspondantes.
    Appelé au démarrage après register_enabled_plugins().
    """
    for action, url in webhooks.items():
        self._plugin_webhooks[action] = url   # dict séparé pour tracabilité
```

La méthode `call()` existante doit chercher en priorité dans `_plugin_webhooks`
avant `_WEBHOOK_TO_FUNC`.

**Point d'appel** : dans `main.py` :

```python
from core.n8n_executor import n8n_executor
n8n_executor.register_plugin_webhooks(plugin_registry.combined_n8n_webhooks())
```

---

### 4.4 `gui/handlers.py` — `_handle_function_gemma()` — modifications

**Deux changements ciblés, le reste est inchangé :**

**a) FUNCTIONS dynamiques** — remplacer `FUNCTIONS` hardcodé dans le payload LLM :

```python
# Avant (hardcodé)
"tools": FUNCTIONS,

# Après (dynamique)
from core.plugin_registry import plugin_registry
plugin_functions = plugin_registry.combined_function_definitions()
effective_functions = FUNCTIONS + plugin_functions   # FUNCTIONS = fonctions natives (timer, calendar, etc.)
"tools": effective_functions,
```

**b) Dispatch vers le bon plugin** — après la résolution du `func_name` par le LLM :

```python
# Après la récupération de func_name et params depuis tool_calls...

# Tenter dispatch plugin avant FunctionExecutor / n8n_executor
plugin_result = plugin_registry.dispatch_action(func_name, params)
if plugin_result is not None:
    result = plugin_result
else:
    # Comportement actuel inchangé
    action = func_name.replace("_", "-")
    result = n8n_executor.call(action, params)
```

**c) System prompt injection** — dans `send_message()` / `ChatHandlers.__init__()` :

```python
# Au moment de construire le system prompt, ajouter le bloc plugins
plugin_context = plugin_registry.combined_system_prompt_injection(
    context_id=self._societe_context or None
)
if plugin_context:
    system_content += f"\n\n### Capacités disponibles ###\n{plugin_context}"
```

---

### 4.5 `config.py` — extensions `MODULES_ENABLED`

```python
MODULES_ENABLED: dict = {
    "societe":    True,
    "domotique":  True,   # → DomotiquePlugin (univers: home)
    "proxmox":    True,   # → ProxmoxPlugin (univers: opent)
    "rmm":        True,   # → RmmPlugin (univers: opent)
    "telephony":  False,  # → TelephonyPlugin (off par défaut)
    "margepro":   True,   # → MargeProPlugin (univers: margep)
}
```

---

### 4.6 `register_enabled_plugins()` — extensions

```python
def register_enabled_plugins() -> None:
    from config import MODULES_ENABLED
    from core.settings_store import settings as _settings

    def _is_enabled(key: str) -> bool:
        store_val = _settings.get(f"modules.{key}")
        return store_val if store_val is not None else MODULES_ENABLED.get(key, False)

    # MODULE_SOCIETE (existant)
    if _is_enabled("societe"):
        from core.societe.plugin import SocietePlugin
        plugin_registry.register(SocietePlugin())

    # MODULE_DOMOTIQUE (nouveau)
    if _is_enabled("domotique"):
        from core.domotique.plugin import DomotiquePlugin
        plugin_registry.register(DomotiquePlugin())

    # MODULE_PROXMOX (nouveau)
    if _is_enabled("proxmox"):
        from core.infra.plugin import ProxmoxPlugin
        plugin_registry.register(ProxmoxPlugin())

    # MODULE_RMM (nouveau)
    if _is_enabled("rmm"):
        from core.rmm.plugin import RmmPlugin
        plugin_registry.register(RmmPlugin())

    # MODULE_TELEPHONY (nouveau)
    if _is_enabled("telephony"):
        from core.telephony.plugin import TelephonyPlugin
        plugin_registry.register(TelephonyPlugin())

    # MODULE_MARGEPRO (nouveau)
    if _is_enabled("margepro"):
        from core.margepro.plugin import MargeProPlugin
        plugin_registry.register(MargeProPlugin())
```

---

## 5. UI — Généralisations

### 5.1 `gui/components/plugin_context_bar.py` (nouveau)

Généralisation de `societe_context_bar.py` pour tous les plugins.

```
ChatContextBar (existant, societe seulement)
    → PluginContextBar (nouveau, tous univers)
```

Logique :
- Affiche un bouton par univers actif (`home`, `opent`, `uscss`, `margep`)
- Chaque univers peut avoir des sous-contextes (ex: sélection d'une société dans `margep`)
- Signal `context_changed(universe: str, context_id: str | None)`
- `ChatHandlers.set_plugin_context(universe, context_id)` reconstruit le system prompt

### 5.2 `gui/app.py` — navigation dynamique

Après `register_enabled_plugins()`, itérer sur `plugin_registry.all_nav_items()`
et appeler `addSubInterface()` pour chaque item avec `lazy=True`.

Pattern identique aux tabs `CompaniesDashboard` / `CompanyDetail` déjà en place.

### 5.3 `gui/tabs/dashboard.py` — KPIs dynamiques

```python
# Dans le rafraîchissement du dashboard :
for plugin in plugin_registry.all():
    for kpi in plugin.get_dashboard_kpis():
        dashboard.add_kpi_card(kpi)
```

---

## 6. Séquence de démarrage complète (après modifications)

```
main.py
  ├── memory_store.initialize()
  ├── telegram_adapter.start()
  ├── morning_briefing scheduler
  ├── ha_state_watcher.start()
  │
  ├── register_enabled_plugins()          ← enregistre tous les plugins actifs
  │     ├── SocietePlugin.on_enable()
  │     ├── DomotiquePlugin.on_enable()   ← subscribe ha_state_watcher
  │     ├── ProxmoxPlugin.on_enable()
  │     └── ...
  │
  ├── inject_plugin_utterances(           ← enrichit semantic_router
  │     plugin_registry.combined_semantic_utterances()
  │   )
  │
  ├── n8n_executor.register_plugin_webhooks(   ← enregistre les webhooks plugins
  │     plugin_registry.combined_n8n_webhooks()
  │   )
  │
  └── QApplication → MainWindow
        └── _init_window()
              └── nav dynamique via plugin_registry.all_nav_items()
```

---

## 7. Convention de nommage des actions

| Couche | Format | Exemple |
|---|---|---|
| Nom de fonction LLM (Ollama tool) | `snake_case` | `control_light` |
| Action n8n (webhook path) | `kebab-case` | `control-light` |
| Méthode `handle_action` | premier arg `snake_case` | `plugin.handle_action("control_light", params)` |
| Clé `get_n8n_webhooks()` | `kebab-case` | `"control-light"` |

La conversion `func_name.replace("_", "-")` déjà présente dans `handlers.py` reste valide.

---

## 8. Règles de confirmation des actions sensibles

Certaines actions requièrent confirmation explicite de l'utilisateur avant exécution.
Le flag est déclaré dans la function definition :

```python
{
    "type": "function",
    "function": {
        "name": "alarm_set",
        "description": "...",
        "parameters": { ... },
        "x_confirm_required": True,   # extension custom ignorée par Ollama, lue par handlers
        "x_confirm_message": "Confirmer l'armement de l'alarme ?"
    }
}
```

Dans `handlers.py`, avant d'appeler `dispatch_action()` ou `n8n_executor.call()` :

```python
func_def = next((f for f in effective_functions if f["function"]["name"] == func_name), None)
if func_def and func_def["function"].get("x_confirm_required"):
    confirm_msg = func_def["function"].get("x_confirm_message", f"Confirmer {func_name} ?")
    # Émettre signal confirm → UI affiche carte de confirmation (pattern déjà dans ada-interface.html)
    self.confirm_required.emit(func_name, params, confirm_msg)
    return  # Suspendre jusqu'à confirmation
```

---

## 9. Gestion des contextes multi-univers

Quand plusieurs plugins actifs, le system prompt est construit ainsi :

```
[System de base ADA]

### Contexte société ###         ← si MODULE_SOCIETE actif et société sélectionnée
[SocietePlugin.get_chat_context(company_id)]

### Capacités disponibles ###    ← systématique si au moins 1 plugin actif
[DomotiquePlugin.get_system_prompt_injection()]
[ProxmoxPlugin.get_system_prompt_injection()]
...

### Mémoire sémantique ###       ← memory_store.build_context() (existant)
[...]
```

Le LLM voit les capacités de tous les plugins actifs et choisit la bonne action.

---

## 10. Fichiers à créer / modifier — récapitulatif

### Modifications (fichiers existants)

| Fichier | Nature de la modification |
|---|---|
| `core/plugin_registry.py` | Ajouter 5 méthodes : `combined_function_definitions`, `combined_n8n_webhooks`, `combined_system_prompt_injection`, `dispatch_action`, `combined_semantic_utterances` + nouvelles abstractions `BasePlugin` |
| `core/semantic_router.py` | Ajouter `inject_plugin_utterances()` + `_invalidate_embedding_cache()` |
| `core/n8n_executor.py` | Ajouter `register_plugin_webhooks()` + priorité `_plugin_webhooks` dans `call()` |
| `gui/handlers.py` | 3 points ciblés dans `_handle_function_gemma()` et `send_message()` |
| `config.py` | Compléter `MODULES_ENABLED` avec les 5 nouveaux modules |
| `main.py` | Ajouter les 2 appels post-`register_enabled_plugins()` |

### Créations (nouveaux fichiers)

| Fichier | Contenu |
|---|---|
| `core/domotique/__init__.py` | vide |
| `core/domotique/plugin.py` | `DomotiquePlugin(BasePlugin)` |
| `core/infra/__init__.py` | vide |
| `core/infra/plugin.py` | `ProxmoxPlugin(BasePlugin)` |
| `core/rmm/__init__.py` | vide |
| `core/rmm/plugin.py` | `RmmPlugin(BasePlugin)` |
| `core/telephony/__init__.py` | vide |
| `core/telephony/plugin.py` | `TelephonyPlugin(BasePlugin)` |
| `core/margepro/__init__.py` | vide |
| `core/margepro/plugin.py` | `MargeProPlugin(BasePlugin)` |
| `gui/components/plugin_context_bar.py` | Remplacement généralisé de `societe_context_bar` |

---

## 11. Ce qui n'est PAS dans cette spec

- Implémentation des appels réels HA / Proxmox / RMM (dépend de tes URLs locales)
- Workflows n8n internes (hors périmètre Python)
- Migration de l'interface HTML `ada-interface.html` (interface séparée, voir spec UI dédiée)
- Gestion multi-utilisateurs / permissions par univers
