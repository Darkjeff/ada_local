# Radar Local Event Console — Documentation

**Version :** 1.0  
**Projet :** ADA Local  
**Date :** 2026-06-01

---

## Qu'est-ce que Radar ?

Radar est une **console locale d'observabilité événementielle** pour ADA.

Elle permet de visualiser, depuis un navigateur local, tout ce qui se passe dans ADA et son moteur RAG :

- Documents importés, parsés, chunkés, indexés
- Requêtes RAG reçues, recherches effectuées, contextes sélectionnés
- Appels LLM démarrés, réponses générées
- Erreurs et warnings à tous les niveaux
- Durées et métriques de performance

Radar est un **processus indépendant** : il n'est pas intégré au serveur web principal d'ADA, ne partage aucune route avec lui, et ne peut pas être atteint depuis l'extérieur.

---

## Pourquoi Radar est local

- ADA gère des informations internes (prompts, extraits de documents, contextes de session).
- Ces informations ne doivent pas être exposées sur le réseau.
- Radar écoute **uniquement sur `127.0.0.1`** par défaut.
- Il n'y a aucune route `/radar` dans le serveur web principal d'ADA.
- Radar peut être désactivé sans affecter ADA (`RADAR_ENABLED = False`).

---

## Comment activer Radar

### 1. Vérifier la configuration

Dans `config.py` (racine du projet) :

```python
RADAR_ENABLED: bool = True              # False = no-op complet, aucune I/O
RADAR_DB_PATH: str = "data/radar/events.sqlite"
RADAR_MAX_EVENTS: int = 100_000
RADAR_RETENTION_DAYS: int = 30
RADAR_TEXT_PREVIEW_MAX: int = 300       # Longueur max des extraits de texte
RADAR_SENSITIVE_FIELDS: list = [
    "api_key", "token", "access_token", "refresh_token",
    "authorization", "password", "secret", "cookie",
    "session_cookie", "private_key",
]
```

Par défaut, `RADAR_ENABLED = True`. Les événements sont stockés dans `data/radar/events.sqlite` (créé automatiquement).

### 2. Lancer ADA normalement

```bash
python web_server.py --port 7654
```

Les événements sont émis automatiquement par le pipeline RAG et l'indexeur documentaire.

---

## Comment lancer la console

```bash
python tools/radar_console.py
```

Options disponibles :

```bash
python tools/radar_console.py --host 127.0.0.1 --port 8787
python tools/radar_console.py --db /chemin/custom/events.sqlite
python tools/radar_console.py --cleanup      # Purge les anciens événements
python tools/radar_console.py --export events.ndjson  # Export et quitte
```

**La console est accessible à :**

```
http://127.0.0.1:8787
```

---

## Comment lire les événements

### Flux temps réel

La vue **Temps réel** (vue par défaut) affiche les événements en direct via Server-Sent Events (SSE). Chaque événement émis par ADA apparaît en moins de 2 secondes.

Indicateurs visuels :
- 🟢 Indicateur vert = SSE connecté
- 🔴 Indicateur rouge = SSE déconnecté (reconnexion automatique toutes les 3s)
- Bandeau vert en haut = confirmation de la connexion SSE

### Historique

La vue **Historique** affiche les événements paginés (50 par page) avec filtres.

---

## Comment filtrer

### Filtres disponibles dans l'historique

| Filtre | Description | Exemple |
|---|---|---|
| Recherche | Plein texte sur message + metadata | `"timeout"` |
| Level | Niveau de sévérité | `error` |
| Type | Type d'événement (exact) | `rag.search.completed` |
| Module | Module source | `web.pipeline` |
| request_id | Filtre par requête | `req_abc123` |
| document_id | Filtre par document | `3fa85f64...` |

### Navigation

- ← Préc / Suiv → pour naviguer entre les pages
- Les filtres s'appliquent immédiatement (debounce 350ms pour la recherche)

---

## Timelines

### Timeline par requête

Affiche tous les événements d'une requête RAG de bout en bout, dans l'ordre chronologique.

Accès : panneau gauche → **Requête** → saisir le `request_id`

Exemple de timeline complète :

```
rag.query.received        → Question reçue
rag.search.completed      → 7 chunks trouvés (342ms)
rag.context.empty         → (si aucun chunk)
llm.call.started          → Appel LLM démarré
rag.response.sent         → Réponse envoyée (1240ms total)
```

### Timeline par document

Affiche le cycle de vie complet d'un document.

Accès : panneau gauche → **Document** → saisir le `document_id`

Exemple :

```
document.parsing.started  → Parsing démarré
document.indexing.completed → 47 chunks indexés (156ms)
```

### Timeline par job

Affiche le déroulement d'une tâche d'indexation (job batch).

Accès : panneau gauche → **Job** → saisir le `job_id`

---

## Vue erreurs

La vue **Erreurs** filtre automatiquement les niveaux `error` et `critical`.

Elle affiche :
- L'heure de l'erreur
- Le type d'événement
- L'error_code si disponible
- Le message d'erreur
- La stack trace dans le panneau détail (cliquer sur une ligne)

---

## Comment exporter

### Depuis la console web

Panneau gauche → **Export NDJSON**

Le fichier `radar_events.ndjson` est téléchargé directement.

### Depuis la ligne de commande

```bash
python tools/radar_console.py --export events.ndjson
```

### Via l'API

```bash
curl http://127.0.0.1:8787/api/export?format=ndjson > events.ndjson
curl http://127.0.0.1:8787/api/export?format=json  > events.json
```

---

## Données masquées

Les champs suivants sont automatiquement remplacés par `[REDACTED]` dans les métadonnées des événements avant stockage :

```
api_key, token, access_token, refresh_token,
authorization, password, secret, cookie,
session_cookie, private_key
```

Exemple :

```json
{
  "authorization": "Bearer sk-xxxxx"
}
```

→ stocké comme :

```json
{
  "authorization": "[REDACTED]"
}
```

Les extraits de texte (requêtes, messages) sont tronqués à `RADAR_TEXT_PREVIEW_MAX` caractères (300 par défaut). Aucun document complet ne transite dans Radar.

---

## Comment désactiver Radar

### Désactivation complète

Dans `config.py` :

```python
RADAR_ENABLED = False
```

Avec ce réglage, `emit_event()` est un no-op immédiat — aucune I/O, aucun accès SQLite, aucun impact sur les performances d'ADA.

### Ne pas lancer la console

Il suffit de ne pas exécuter `tools/radar_console.py`. Cela n'affecte pas ADA.

---

## API locale de Radar

Toutes les routes sont sur `http://127.0.0.1:8787` (non accessible depuis l'extérieur).

| Route | Description |
|---|---|
| `GET /api/health` | Santé du serveur |
| `GET /api/stats` | Statistiques globales |
| `GET /api/events` | Liste filtrée + paginée |
| `GET /api/events/{id}` | Détail d'un événement |
| `GET /api/timeline/{field}/{value}` | Timeline par request_id / document_id / job_id |
| `GET /api/errors` | Erreurs récentes |
| `GET /api/export?format=ndjson` | Export NDJSON |
| `GET /sse/events` | Flux SSE temps réel |

Paramètres de `/api/events` :

```
level, type, module, request_id, document_id, job_id, session_id,
from_ts, to_ts, q (recherche plein texte), limit (max 200), offset
```

---

## Événements émis par ADA

### Pipeline RAG (`web/pipeline.py`)

| Type | Niveau | Déclencheur |
|---|---|---|
| `rag.query.received` | info | Début de traitement d'un message |
| `rag.search.completed` | info | Fin de la recherche documentaire (chunks trouvés) |
| `rag.context.empty` | info | Aucun chunk trouvé pour la requête |
| `llm.call.started` | info | Début d'appel au LLM (Mistral / Qwen) |
| `llm.call.completed` | info | Fin d'appel au LLM (route function_gemma) |
| `rag.response.sent` | info | Réponse complète envoyée à l'utilisateur |

### Indexation documentaire (`core/documents/documents_indexer.py`)

| Type | Niveau | Déclencheur |
|---|---|---|
| `job.started` | info | Début d'une indexation batch |
| `document.parsing.started` | info | Début du parsing d'un fichier |
| `document.indexing.completed` | info | Fin de l'indexation d'un fichier |
| `job.completed` | info | Fin de l'indexation batch |

---

## Structure des fichiers

```
web/
  radar/
    __init__.py       ← export de emit_event
    events.py         ← emit_event() + gestion SSE
    store.py          ← SQLiteStore (init, insert, query, timeline, purge)
    sanitize.py       ← redact_sensitive_fields(), safe_serialize()

tools/
  radar_console.py    ← serveur FastAPI autonome sur 127.0.0.1:8787

data/
  radar/
    events.sqlite     ← créé automatiquement au premier emit
    fallback.log      ← erreurs internes Radar uniquement (si SQLite échoue)
```

---

## Nettoyage automatique

La purge s'effectue manuellement :

```bash
python tools/radar_console.py --cleanup
```

Paramètres depuis `config.py` :

```python
RADAR_RETENTION_DAYS = 30      # Garder 30 jours d'historique
RADAR_MAX_EVENTS     = 100_000 # Garder au maximum 100 000 événements
```

---

## Résilience

`emit_event()` est conçu pour ne **jamais bloquer ADA** :

- Toujours dans un `try/except Exception` global
- Si SQLite est verrouillé ou absent → erreur absorbée, log dans `data/radar/fallback.log`
- Si `RADAR_ENABLED = False` → retour immédiat, aucune opération
- Les métadonnées non sérialisables sont converties en `str()` plutôt que de lever une erreur
- Les exceptions Radar ne remontent jamais dans le flux métier d'ADA
