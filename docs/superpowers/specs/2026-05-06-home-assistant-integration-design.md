# Home Assistant Integration — Design Spec
**Date:** 2026-05-06  
**Project:** ada_local (A.D.A - Pocket AI)  
**Target:** PR contribution to nazirlouis/ada_local

---

## Overview

Integrate Home Assistant (HA) local REST API into the Environmental Control tab alongside the existing TP-Link Kasa integration. HA takes priority over Kasa when configured and connected. Zero new dependencies — uses `requests` already in `requirements.txt`.

---

## Decisions

| Question | Decision |
|---|---|
| UI layout | Sous-onglets distincts : **Kasa** \| **Home Assistant** dans `HomeAutomationTab` |
| Header badge | Indicateur de connexion dynamique (● Connected / ● Disconnected) |
| Entity scope | Tous les domaines contrôlables : `light`, `switch`, `script`, `scene`, `media_player`, `climate` |
| Voice routing | HA en priorité si configuré + connecté, fallback Kasa sinon |
| Configuration | Nouveau groupe "Home Assistant" dans l'onglet Settings |

---

## Architecture

```
SettingsStore  (home_assistant.url / .token / .enabled)
      ↓
  HAManager  (core/ha_control.py)
     │
     │  GET  /api/                    ← test connection
     │  GET  /api/states              ← fetch all entities
     │  GET  /api/states/{entity_id}  ← single entity state
     │  POST /api/services/{domain}/{service}  ← control
     │
  FunctionExecutor  (core/function_executor.py)
     │  ha_manager prioritaire si connecté
     │  fallback kasa_manager sinon
     │
  HomeAutomationTab  (gui/tabs/home_automation.py)
     │  QTabWidget [Kasa | Home Assistant]
     │  Badge connexion HA dans le header
     │
  SettingsTab  (gui/tabs/settings.py)
     └  Groupe "Home Assistant" : URL + Token + Enable switch
```

---

## Files

| Fichier | Action | Description |
|---|---|---|
| `core/ha_control.py` | CREATE | HAManager — client REST HA |
| `core/function_executor.py` | MODIFY | Ajout ha_manager + priorité HA |
| `core/settings_store.py` | MODIFY | Defaults `home_assistant.*` |
| `gui/tabs/home_automation.py` | MODIFY | Sous-onglets + badge + HAEntityCard |
| `gui/tabs/settings.py` | MODIFY | Groupe "Home Assistant" |

---

## `core/ha_control.py` — HAManager

Classe synchrone (pas d'async — cohérent avec l'architecture existante).

```python
class HAManager:
    def __init__(self)           # lit url/token depuis settings_store
    def is_connected(self) -> bool              # état en cache
    def test_connection(self) -> bool           # GET /api/
    def get_entities(self) -> dict              # GET /api/states → cache self.entities
    def get_state(self, entity_id) -> dict      # GET /api/states/{entity_id}
    def call_service(self, domain, service, entity_id, **kwargs) -> bool
    def turn_on(self, entity_id, **kwargs) -> bool
    def turn_off(self, entity_id) -> bool
    def reload_config(self)       # relit url/token depuis settings_store (appelé après save settings)
```

**Headers :** `Authorization: Bearer {token}`, `Content-Type: application/json`  
**Timeout :** 5 secondes sur tous les appels  
**Erreurs :** log + retourne `False`/`{}` selon le type, jamais d'exception propagée

**Domain → service mapping :**

| Domaine | turn_on service | turn_off service | Extras supportés |
|---|---|---|---|
| `light` | `light/turn_on` | `light/turn_off` | `brightness_pct` (0-100), `rgb_color` ([r,g,b]) |
| `switch` | `switch/turn_on` | `switch/turn_off` | — |
| `script` | `script/turn_on` | — | — |
| `scene` | `scene/turn_on` | — | — |
| `media_player` | `media_player/media_play` | `media_player/media_pause` | `volume_level` (0.0-1.0) |
| `climate` | `climate/set_hvac_mode` | `climate/turn_off` | `temperature`, `hvac_mode` |

**Instance globale :** `ha_manager = HAManager()` en bas de fichier (pattern identique à `kasa_manager`).

---

## `core/function_executor.py` — Modifications

### `_init_managers()`
```python
try:
    from core.ha_control import ha_manager
    self.ha_manager = ha_manager
except Exception as e:
    print(f"[FunctionExecutor] HAManager init failed: {e}")
```

### `_async_control_light()` — non renommée, logique HA insérée en tête
La méthode reste `_async_control_light` (l'appel depuis `_control_light` via `asyncio.run()` est inchangé). Le check HA est synchrone et retourne early avant tout code Kasa :

```python
async def _async_control_light(self, params):
    # --- HA priority check (synchronous, no await needed) ---
    if self.ha_manager and self.ha_manager.is_connected and self.ha_manager.entities:
        # fuzzy match + call_service → return result
        ...
    # --- existing Kasa logic unchanged below ---
    ...
```

Logique de priorité :
1. Si `self.ha_manager` existe ET `self.ha_manager.is_connected` ET entités non vides → chercher dans HA (synchrone), retourner résultat
2. Sinon → comportement Kasa actuel inchangé

Le matching fuzzy reste identique : `device_name_lower in alias or alias in device_name_lower`.

**Mapping actions vocales → services HA :**
- `"on"` → `turn_on`
- `"off"` → `turn_off`
- `"dim"` avec `brightness` → `turn_on` avec `brightness_pct`
- `"color"` → `turn_on` avec `rgb_color`

---

## `core/settings_store.py` — Modifications

Ajout dans `DEFAULT_SETTINGS` :
```python
"home_assistant": {
    "url": "",
    "token": "",
    "enabled": False
}
```

---

## `gui/tabs/home_automation.py` — Modifications

### Badge header
Remplace le `QLabel` statique "Coming Soon!" par un `QLabel` dynamique mis à jour par un `HAConnectionThread(QThread)` :
- Au chargement : `● Connecting...` (couleur `#6e7a8e`)
- Succès : `● Connected` (couleur `#4CAF50`)
- Échec : `● Disconnected` (couleur `#f44336`)
- Rafraîchi à chaque clic sur le bouton Refresh existant

### QTabWidget
```
HomeAutomationTab
└── QTabWidget
    ├── Tab "Kasa"           ← contenu actuel déplacé tel quel
    └── Tab "Home Assistant" ← nouveau
```

Style des onglets : cohérent avec le dark theme (`#1a2236` background, `#33b5e5` actif).

### Onglet Home Assistant — 3 états

**État 1 — Non configuré** (`home_assistant.url` vide ou `enabled` = False) :
- Message centré : "Home Assistant is not configured."
- Sous-titre : "Add your HA URL and token in Settings."
- Bouton "Open Settings" → `HomeAutomationTab` expose un `Signal() navigate_to_settings` ; `app.py` le connecte au tab switcher (même pattern que les autres signaux inter-tabs existants)

**État 2 — Configuré mais déconnecté** :
- Message d'erreur avec l'URL tentée
- Bouton "Retry" qui relance `HAConnectionThread`

**État 3 — Connecté** :
- `HADataFetchThread(QThread)` : appelle `ha_manager.get_entities()`, émet `entities_found(dict)`
- Grille de `HAEntityCard` identique à la grille Kasa (même `QGridLayout`, même filtres par pièce)
- Bouton Refresh global lance à la fois Kasa discovery ET HA entity fetch

### HAEntityCard
Reprend exactement le style de `DeviceCard` (300×160, `#1a2236`, border-radius 20px).

| Domaine | Icône | Contrôle |
|---|---|---|
| `light` | `FIF.BRIGHTNESS` | Toggle + Slider brightness si supporté |
| `switch` | `FIF.TILES` | Toggle on/off |
| `script` | `FIF.PLAY` | Bouton "Run" (pas de toggle) |
| `scene` | `FIF.PHOTO` | Bouton "Activate" |
| `media_player` | `FIF.MUSIC` | Toggle play/pause |
| `climate` | `FIF.CLOUD` | Toggle + label température |

`HAActionThread(QThread)` : même pattern que `ActionThread`, appelle `ha_manager.turn_on/turn_off/call_service`.

---

## `gui/tabs/settings.py` — Modifications

Nouveau groupe inséré entre "Connection" et "Voice & Audio" :

```python
self.ha_group = SettingCardGroup("Home Assistant", self.scrollWidget)

# 1. Enable switch
SwitchCard(FIF.HOME, "Enable Home Assistant", 
           "Use HA as primary smart home backend", 
           "home_assistant.enabled")

# 2. URL input avec Test
UrlInputCard(FIF.LINK, "Home Assistant URL",
             "e.g. http://homeassistant.local:8123",
             "home_assistant.url")
# → le test appelle HAManager.test_connection() via un thread dédié
# → réutilise ConnectionTester en passant l'URL HA (pas d'endpoint /api/tags)
#   → adapter : tester GET {url}/api/ au lieu de {url}/api/tags

# 3. Token input
TextInputCard(FIF.CERTIFICATE, "Long-lived Token",
              "Bearer token from HA profile page",
              "home_assistant.token",
              placeholder="eyJ0eXAiOiJKV1Q...")
```

**Note :** `ConnectionTester` doit être adapté (ou sous-classé) pour tester `/api/` au lieu de `/api/tags`. Option propre : ajouter un paramètre `endpoint` à `ConnectionTester`.

---

## Error Handling

| Scénario | Comportement |
|---|---|
| HA non configuré | FunctionExecutor ignore ha_manager, utilise Kasa |
| HA configuré mais timeout | `is_connected = False`, fallback Kasa, log warning |
| Token invalide (HTTP 401) | `is_connected = False`, message dans l'UI |
| Entité introuvable dans HA | Fallback Kasa (même logique de rediscovery) |
| Kasa absent ET HA absent | Message "No devices found" existant |

---

## Testing

- `tests/test_ha_control.py` — mock `requests.get/post`, vérifier turn_on/turn_off/get_entities
- Vérifier que `function_executor` route bien vers HA quand `is_connected = True`
- Vérifier le fallback Kasa quand `is_connected = False`
- Vérifier les 3 états UI de l'onglet HA (non configuré / déconnecté / connecté)

---

## Out of Scope

- WebSocket HA (temps réel / push) — v2 potentielle
- Automations HA (création/modification) — hors périmètre
- HACS / add-ons HA — hors périmètre
- Sécurité TLS (HTTPS avec certificat auto-signé) — `verify=False` acceptable pour usage local, à documenter
