# ADA ↔ n8n Integration — Design Spec

**Date:** 2026-05-18
**Projet:** ADA — Phase 2 de l'évolution multi-agents
**Statut:** Approuvé

---

## Objectif

Remplacer `FunctionExecutor` (exécution Python directe de HA/Kasa/shell/web) par **n8n** comme orchestrateur d'actions, via webhooks HTTP. Conserver un fallback transparent vers `FunctionExecutor` si n8n est indisponible.

---

## Contexte

### Problème actuel

`_handle_function_gemma()` dans `handlers.py` délègue l'exécution des actions à `FunctionExecutor` via un LLM tool-call (qwen3 ou gemma4). Ce mécanisme est fragile : le modèle génère parfois du texte libre au lieu d'un `tool_call` JSON, ce qui produit des réponses inventées ("L'éclairage est désactivé") sans qu'aucune action ne soit réellement exécutée.

### Solution retenue

**Approche A — ADA dispatcher → n8n exécuteur :**
- `PatternDispatcher` : règles regex déterministes, couvre les cas courants sans LLM
- `N8NExecutor` : client HTTP vers les webhooks n8n, remplace `FunctionExecutor`
- LLM (qwen3) conservé en fallback pour les formulations ambiguës
- `FunctionExecutor` conservé comme fallback silencieux si n8n est down

---

## Architecture

```
prompt
  │
  ▼
PatternDispatcher.match(prompt)          ← core/pattern_dispatcher.py
  ├── match  → (action, params)
  └── no match
        │
        ▼
      LLMIntentParser (qwen3 + FUNCTIONS)
        ├── tool_calls → (action, params)
        └── no tool_calls → stream_qwen_response()
                │
                ▼
          N8NExecutor.call(action, params) ← core/n8n_executor.py
                │
                ├── n8n UP   → POST /webhook/<action> → résultat
                └── n8n DOWN → FunctionExecutor.execute() (fallback)
```

### Fichiers touchés

| Fichier | Action |
|---|---|
| `core/pattern_dispatcher.py` | **Créé** — règles regex + extraction de paramètres |
| `core/n8n_executor.py` | **Créé** — client HTTP webhooks + fallback |
| `core/settings_store.py` | **Modifié** — bloc `n8n` dans `DEFAULT_SETTINGS` |
| `gui/handlers.py` | **Modifié** — `_handle_function_gemma()` utilise les deux nouveaux modules |
| `core/function_executor.py` | **Inchangé** — conservé comme fallback |
| `tests/test_pattern_dispatcher.py` | **Créé** — 15 tests |
| `tests/test_n8n_executor.py` | **Créé** — 8 tests |

**Aucun autre fichier modifié.** Semantic router, routes qwen/youtube/vision/cad, toute l'UI : inchangés.

---

## Installation n8n

**Méthode : Docker Compose sur Ubuntu**

```yaml
# ~/n8n/docker-compose.yml
services:
  n8n:
    image: n8nio/n8n
    restart: unless-stopped
    ports:
      - "5678:5678"
    volumes:
      - ~/.n8n:/home/node/.n8n
    environment:
      - N8N_BASIC_AUTH_ACTIVE=true
      - N8N_BASIC_AUTH_USER=ada
      - N8N_BASIC_AUTH_PASSWORD=<mot_de_passe>
      - WEBHOOK_URL=http://localhost:5678
```

Interface : `http://localhost:5678`
Démarrage : `docker compose up -d`

---

## Webhooks n8n

Chaque workflow expose un endpoint `POST /webhook/<action>` qui reçoit `{"params": {...}}` et retourne :

```json
{ "success": true, "message": "texte lisible", "data": {} }
```

### Contrat d'interface

| Webhook | Payload `params` | Implémentation n8n |
|---|---|---|
| `/webhook/control-light` | `{action, device_name, brightness?}` | Nodes HA `light.turn_on/off` + Kasa HTTP |
| `/webhook/set-timer` | `{duration, label}` | Node Wait + réponse |
| `/webhook/set-alarm` | `{time, label}` | Node Schedule |
| `/webhook/web-search` | `{query}` | Node HTTP Request → DuckDuckGo |
| `/webhook/shell-exec` | `{command, timeout?}` | Node Execute Command |
| `/webhook/get-info` | `{}` | Node Execute Command (df, free, top) |
| `/webhook/calendar-event` | `{title, date, time, duration?}` | Node Google Calendar ou fichier local |
| `/webhook/weather` | `{lat, lon}` | Node HTTP Request → OpenMeteo API |

---

## `PatternDispatcher`

**Fichier :** `core/pattern_dispatcher.py`

Règles déterministes (regex + extracteur), ordonnées du plus spécifique au plus général.
Retourne `(action: str, params: dict)` ou `None` si aucune règle ne matche.

### Règles

```python
PATTERNS = [
    # Lumières — off
    (r"\b(éteins?|désactiv\w+|coupe?|arrête?\s+l[ae]s?)\b.*(lumière|lampe|éclairage|led)",
     lambda m, t: ("control-light", {"action": "off",
                                      "device_name": _extract_room(t) or "all"})),
    # Lumières — on
    (r"\b(allume?|activ\w+|mets?\s+l[ae]s?)\b.*(lumière|lampe|éclairage|led)",
     lambda m, t: ("control-light", {"action": "on",
                                      "device_name": _extract_room(t) or "all"})),
    # Lumières — dim
    (r"\b(baisse?|réduis?|dimme?|atténue?)\b.*(lumière|lampe)",
     lambda m, t: ("control-light", {"action": "dim",
                                      "device_name": _extract_room(t) or "all",
                                      "brightness": 30})),
    # Timers
    (r"\b(minuterie|timer|chrono)\b",
     lambda m, t: ("set-timer", {"duration": _extract_duration(t), "label": "Timer"})),
    # Shell — disk
    (r"\b(espace|disque|disk|df|stockage|libre)\b",
     lambda m, t: ("shell-exec", {"command": "df -h"})),
    # Shell — RAM
    (r"\b(ram|mémoire|memory)\b",
     lambda m, t: ("shell-exec", {"command": "free -h"})),
    # Shell — CPU
    (r"\b(cpu|processeur|charge\s+système|load)\b",
     lambda m, t: ("shell-exec", {"command": "top -bn1 | head -15"})),
    # Météo
    (r"\b(météo|temps\s+qu[']il\s+fait|weather|température\s+extérieure)\b",
     lambda m, t: ("weather", {})),
    # Recherche web
    (r"\b(cherche?|recherche?|search|trouve?)\b\s+(.+)",
     lambda m, t: ("web-search", {"query": m.group(2).strip()})),
]
```

### Fonctions d'extraction

```python
_ROOMS = ["bureau", "salon", "chambre", "cuisine", "couloir",
          "salle de bain", "garage", "extérieur", "jardin", "chillout"]

def _extract_room(text: str) -> str | None:
    text_lower = text.lower()
    return next((r for r in _ROOMS if r in text_lower), None)

def _extract_duration(text: str) -> str:
    """Retourne '10 minutes', '1 heure', etc. depuis le texte."""
    ...
```

---

## `N8NExecutor`

**Fichier :** `core/n8n_executor.py`

```python
class N8NExecutor:
    """
    Client HTTP vers les webhooks n8n.
    Fallback transparent vers FunctionExecutor si n8n est indisponible.
    Ne lève jamais d'exception.
    """

    def call(self, action: str, params: dict) -> dict:
        """
        POST /webhook/<action> avec {"params": params}.
        Retourne {success, message, data}.
        """
        if self._is_in_cooldown():
            return self._fallback(action, params)
        try:
            resp = requests.post(
                f"{self._base_url}/{action}",
                json={"params": params},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            return self._normalize(resp.json())
        except requests.exceptions.ConnectionError:
            self._mark_down()
            logger.warning("[N8N] Indisponible, fallback FunctionExecutor")
            return self._fallback(action, params)
        except Exception as e:
            logger.error("[N8N] Erreur: %s", e)
            return {"success": False, "message": str(e), "data": None}
```

**Singleton module-level :** `n8n_executor = N8NExecutor()`

---

## Configuration

Bloc ajouté dans `DEFAULT_SETTINGS` de `core/settings_store.py` :

```python
"n8n": {
    "url": "http://localhost:5678",
    "timeout_s": 10.0,
    "fallback_enabled": True,
    "cooldown_s": 30.0,
}
```

---

## Gestion d'erreurs

| Situation | Comportement | Log |
|---|---|---|
| n8n down au premier appel | Fallback `FunctionExecutor`, cooldown 30s | WARNING |
| n8n timeout | Fallback immédiat, cooldown | WARNING |
| n8n retourne `success: false` | Message d'erreur transmis (toast UI) | silent |
| Workflow inexistant (404) | Fallback + log | ERROR |
| PatternDispatcher no match + LLM no tool_calls | `stream_qwen_response(False)` | silent |
| Exception inattendue | `{success: False, message: ...}` | ERROR |

**Invariant :** `N8NExecutor.call()` ne lève jamais d'exception.

---

## Tests

### `tests/test_pattern_dispatcher.py` (15 tests)

| Test | Vérifie |
|---|---|
| `test_light_off_eteins` | "éteins la lumière" → `control-light` off all |
| `test_light_off_desactive` | "désactive l'éclairage du bureau" → off bureau |
| `test_light_off_coupe` | "coupe les lumières du salon" → off salon |
| `test_light_on` | "allume les lumières" → on all |
| `test_light_on_room` | "allume la lampe du bureau" → on bureau |
| `test_light_dim` | "baisse la lumière" → dim all brightness=30 |
| `test_timer` | "minuterie de 10 minutes" → set-timer 10m |
| `test_shell_disk` | "espace disque" → shell-exec df -h |
| `test_shell_ram` | "utilisation mémoire" → shell-exec free -h |
| `test_shell_cpu` | "charge cpu" → shell-exec top -bn1 |
| `test_weather` | "météo" → weather |
| `test_web_search` | "cherche python tutorial" → web-search |
| `test_no_match_bonjour` | "bonjour" → None |
| `test_no_match_explain` | "explique la relativité" → None |
| `test_room_extraction` | `_extract_room("bureau")` → "bureau" |

### `tests/test_n8n_executor.py` (8 tests)

| Test | Vérifie |
|---|---|
| `test_successful_call` | POST → `{success:true}` retourné intact |
| `test_connection_error_fallback` | `ConnectionError` → `FunctionExecutor` appelé |
| `test_timeout_fallback` | `Timeout` → fallback |
| `test_cooldown_respected` | Pas de retry dans les 30s après échec |
| `test_cooldown_expires` | Retry autorisé après cooldown |
| `test_fallback_disabled` | `fallback_enabled=False` → erreur propre sans FunctionExecutor |
| `test_404_fallback` | HTTP 404 → fallback |
| `test_normalizes_response` | Réponse n8n non-standard normalisée en `{success, message, data}` |

---

## Non-périmètre

- Interface graphique pour gérer les workflows n8n depuis ADA
- Authentification n8n avancée (OAuth, certificats TLS)
- n8n sur machine distante avec tunnel réseau
- Webhooks entrants depuis n8n vers ADA (Phase 3 éventuelle)
- Modification du semantic router ou des routes qwen/youtube/vision/cad
- Toute l'UI ADA
