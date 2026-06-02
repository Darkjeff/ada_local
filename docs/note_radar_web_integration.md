# Note de cadrage — Intégration Radar Local Event Console dans la couche web ADA

**Projet :** ADA Local  
**Branche :** `univers`  
**Périmètre :** couche `web` uniquement — pas de `main.py`, pas de `/gui`  
**Date :** 2026-06-01  
**Statut :** À transmettre à l'agent de développement

---

## 1. Contexte et rappel de la contrainte principale

La spec Radar (`spec_radar_local_event_console.md`) définit un processus indépendant écoutant sur `127.0.0.1:8787`.

La contrainte de ce sprint est stricte : **tout travail se situe dans la couche `web`**. Ni `main.py`, ni les modules `/gui` ne sont touchés. La couche web est le seul endroit où des fichiers sont créés ou modifiés.

---

## 2. Ce que la couche web doit fournir

### 2.1 Le module d'émission d'événements

Emplacement dans la couche web :

```
web/radar/
    __init__.py
    events.py       ← emit_event() réside ici
    store.py        ← lecture/écriture SQLite
    sanitize.py     ← masquage des champs sensibles
```

`emit_event()` doit être importable depuis n'importe quel module de la couche web sans créer de dépendance cyclique. La fonction ne lève jamais d'exception vers l'appelant.

### 2.2 L'Event Store SQLite

Chemin par défaut, cohérent avec l'arborescence existante du projet :

```
data/radar/events.sqlite
```

Ce chemin doit être configurable via `config.py` (clé `RADAR_DB_PATH`). Si la clé est absente, la valeur par défaut s'applique silencieusement.

### 2.3 Le script autonome Radar

Emplacement :

```
tools/radar_console.py
```

Ce script est lancé séparément. Il démarre son propre serveur HTTP (Flask léger ou `http.server` standard). Il ne doit **pas** être importé ni déclenché par la couche web principale.

---

## 3. Ce que la couche web ne doit pas faire

| Interdit | Raison |
|---|---|
| Exposer `/web/radar`, `/api/radar` ou toute route radar | Radar reste local et inaccessible via le web principal |
| Importer `radar_console.py` depuis un module web | Ce script est un process distinct |
| Ajouter Radar dans le router/app principal de la couche web | Risque d'exposition publique |
| Appeler `emit_event()` de façon bloquante sans try/except | ADA ne doit jamais être bloqué par Radar |

---

## 4. Points d'instrumentation dans la couche web

Les appels à `emit_event()` sont à placer dans la couche web aux endroits suivants.

### Ingestion documentaire

```python
# Début ingestion
emit_event(type="document.ingest.started", level="info", module="web.ingest", document_id=doc_id)

# Parsing
emit_event(type="document.parse.completed", level="info", module="web.parse",
           document_id=doc_id, duration_ms=elapsed, metadata={"pages": n})

# Chunking
emit_event(type="document.chunk.completed", level="info", module="web.chunk",
           document_id=doc_id, metadata={"chunks": len(chunks)})

# Embeddings
emit_event(type="document.embedding.started", level="info", module="web.embed", document_id=doc_id)
emit_event(type="document.embedding.completed", level="info", module="web.embed",
           document_id=doc_id, duration_ms=elapsed)

# Indexation
emit_event(type="document.index.completed", level="info", module="web.index", document_id=doc_id)

# Erreur (exemple)
emit_event(type="document.ingest.failed", level="error", module="web.ingest",
           document_id=doc_id, error_code="PARSE_FAILED", exception=exc)
```

### Requête RAG

```python
emit_event(type="rag.query.received", level="info", module="web.rag",
           request_id=req_id, session_id=sess_id, metadata={"query_preview": query[:200]})

emit_event(type="rag.search.completed", level="info", module="web.rag",
           request_id=req_id, duration_ms=elapsed, metadata={"chunks_found": n})

emit_event(type="rag.llm.started", level="info", module="web.llm", request_id=req_id)

emit_event(type="rag.llm.completed", level="info", module="web.llm",
           request_id=req_id, duration_ms=elapsed)

emit_event(type="rag.response.sent", level="info", module="web.rag", request_id=req_id)
```

### Appels sortants LLM / Mistral

```python
emit_event(type="llm.call.started", level="info", module="web.llm",
           request_id=req_id, metadata={"model": model_name, "tokens_in": n})

emit_event(type="llm.call.completed", level="info", module="web.llm",
           request_id=req_id, duration_ms=elapsed, metadata={"tokens_out": n})

emit_event(type="llm.call.failed", level="error", module="web.llm",
           request_id=req_id, error_code="LLM_TIMEOUT", exception=exc)
```

---

## 5. Clés de configuration à ajouter dans `config.py`

```python
# --- Radar Local Event Console ---
RADAR_ENABLED: bool = True          # Désactive tout le système si False
RADAR_DB_PATH: str = "data/radar/events.sqlite"
RADAR_MAX_EVENTS: int = 100_000     # Seuil de nettoyage automatique
RADAR_RETENTION_DAYS: int = 30
RADAR_TEXT_PREVIEW_MAX: int = 300   # Nb de caractères max pour les extraits texte
RADAR_SENSITIVE_FIELDS: list[str] = [
    "api_key", "token", "access_token", "refresh_token",
    "authorization", "password", "secret", "cookie",
    "session_cookie", "private_key",
]
```

Ces clés sont lues par `web/radar/events.py` au démarrage. Si `RADAR_ENABLED` est `False`, `emit_event()` est un no-op immédiat.

---

## 6. Arborescence cible dans la couche web

```
web/
  radar/
    __init__.py
    events.py         ← emit_event() + file locale de secours
    store.py          ← SQLiteStore : insert, query, pagination
    sanitize.py       ← redact_sensitive_fields()

tools/
  radar_console.py    ← serveur HTTP autonome 127.0.0.1:8787

data/
  radar/
    events.sqlite     ← créé automatiquement au premier emit
    fallback.log      ← erreurs internes Radar uniquement
```

---

## 7. Règles d'implémentation non-négociables

1. `emit_event()` est toujours dans un `try/except Exception` global. Aucune exception ne remonte.
2. `RADAR_ENABLED = False` court-circuite `emit_event()` avant toute opération I/O.
3. Le dossier `data/radar/` est créé automatiquement (`mkdir -p`) à la première écriture.
4. Les métadonnées non sérialisables sont converties en `str()` plutôt que de lever une erreur.
5. Les champs de `RADAR_SENSITIVE_FIELDS` sont remplacés par `"[REDACTED]"` dans `metadata` avant insertion.
6. Les extraits de texte sont tronqués à `RADAR_TEXT_PREVIEW_MAX` caractères.
7. Aucun document complet ne transite dans un événement Radar.
8. `tools/radar_console.py` n'est jamais importé par un module `web/`.

---

## 8. Interface web Radar (dans `tools/radar_console.py`)

Le script sert une SPA HTML autonome via son propre serveur. Le design suit le langage visuel d'ADA (`ada-interface.html`) : fond `#080c10`, typographies Syne + JetBrains Mono, palette accent cyan/vert/orange.

Vues minimales requises :

- **Flux temps réel** — SSE sur `/sse/events`, affichage en direct
- **Historique** — pagination 50/page, tri par timestamp desc
- **Filtres** — level, type, module, request_id, document_id, job_id
- **Recherche** — plein texte sur `message` + `metadata`
- **Détail événement** — JSON formaté, champs masqués visibles comme `[REDACTED]`
- **Timeline requête** — tous les événements d'un `request_id` en ordre chronologique
- **Timeline document** — tous les événements d'un `document_id`
- **Vue erreurs** — filtre `level=error|critical` avec `error_code` et stack trace tronquée
- **Export** — `GET /api/export?format=ndjson` ou `?format=json`

API locale exposée par le script :

```
GET /api/health
GET /api/events?level=&type=&module=&request_id=&document_id=&page=&limit=
GET /api/events/{id}
GET /api/timeline/request/{request_id}
GET /api/timeline/document/{document_id}
GET /api/errors
GET /api/export?format=ndjson
GET /sse/events                    ← Server-Sent Events temps réel
```

---

## 9. Ordre de développement recommandé

1. `web/radar/sanitize.py` — redaction des champs sensibles, testé isolément
2. `web/radar/store.py` — SQLiteStore, schéma, insert, query
3. `web/radar/events.py` — `emit_event()` complet avec fallback
4. Config `config.py` — ajout des clés Radar
5. Instrumentation dans les modules web existants (ingestion, RAG, LLM)
6. `tools/radar_console.py` — serveur HTTP + API
7. Interface web dans le script (HTML/JS inline ou template statique)
8. SSE temps réel
9. Tests unitaires (sanitize, store, emit)
10. Tests de sécurité (bind 127.0.0.1, absence de route dans le web principal)

---

## 10. Critères de validation propres à la couche web

- [ ] `emit_event()` importable depuis `web/` sans erreur
- [ ] `emit_event()` ne lève jamais d'exception
- [ ] `RADAR_ENABLED = False` → aucune écriture SQLite, aucune I/O
- [ ] Les modules d'ingestion et RAG de la couche web appellent `emit_event()` aux points listés en §4
- [ ] Aucune route `/radar*` dans le router web principal
- [ ] `tools/radar_console.py` lance un serveur sur `127.0.0.1:8787` par défaut
- [ ] `http://127.0.0.1:8787` affiche la console avec les événements récents
- [ ] SSE fonctionne : un `emit_event()` déclenché dans ADA apparaît dans le navigateur < 2 s
- [ ] Un événement avec `authorization: Bearer sk-xxx` dans metadata est stocké comme `[REDACTED]`
- [ ] Export NDJSON disponible et conforme au masquage

---

*Note transmise à l'agent de développement. Aucun code produit ici.*
