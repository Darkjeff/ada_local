# Spécification fonctionnelle et technique — Radar Local Event Console pour ADA

**Projet :** ADA Local / couche web / RAG documentaire  
**Branche cible :** `univers`  
**Zone concernée :** principalement le dossier `web` et les composants locaux nécessaires à l’observabilité  
**Date :** 2026-06-01  
**Statut :** Spécification à confier à un agent de développement

---

## 1. Résumé exécutif

Le projet ADA doit intégrer un système autonome de visualisation des événements internes appelé **Radar Local Event Console**.

Cette console ne doit pas être une simple page de logs intégrée à l’interface web principale. Elle doit être un **processus local indépendant**, lancé via un script ou une commande dédiée, exposant une interface web uniquement sur `127.0.0.1` et sur un port spécifique, par exemple `8787`.

Le système principal ADA/RAG doit émettre des événements structurés décrivant ce qui se passe dans le système : ingestion documentaire, parsing, chunking, embeddings, indexation, recherche RAG, appels LLM, génération de réponse, erreurs, warnings et changements d’état.

Radar doit permettre de consulter ces événements en temps réel et en historique, sans dépendre du serveur web principal d’ADA et sans exposer ces informations via le mécanisme d’accès web distant déjà existant.

---

## 2. Objectifs

### 2.1 Objectifs principaux

- Visualiser localement tous les événements importants produits par ADA.
- Comprendre ce qui se passe dans le moteur RAG et la base documentaire.
- Suivre le cycle de vie complet d’un document.
- Suivre le cycle de vie complet d’une requête utilisateur.
- Diagnostiquer les erreurs d’ingestion, de parsing, d’embedding, d’indexation, de recherche et de génération.
- Disposer d’un outil de diagnostic disponible même si l’interface web principale est indisponible.
- Ne pas exposer les événements internes via le serveur web principal.
- Ne jamais bloquer le fonctionnement naturel d’ADA si Radar est désactivé, absent ou en erreur.

### 2.2 Objectifs secondaires

- Faciliter le support et le debug local.
- Fournir une vue claire des performances : durées, volumes, erreurs, taux de réussite.
- Permettre l’export des événements pour analyse.
- Préparer une base saine pour une future observabilité plus avancée.

---

## 3. Non-objectifs

Radar ne doit pas devenir :

- un système de monitoring cloud ;
- une interface publique ;
- une dépendance obligatoire du RAG ;
- un remplaçant des logs système classiques ;
- une interface d’administration complète d’ADA ;
- un outil d’exposition de prompts complets, contenus documentaires complets ou secrets techniques.

Radar est une **console locale d’observabilité événementielle**, pas une interface métier principale.

---

## 4. Principes d’architecture

### 4.1 Séparation stricte des responsabilités

L’architecture doit séparer :

1. **ADA / RAG / système principal**  
   Produit des événements mais ne dépend pas de Radar.

2. **Event Store local**  
   Persiste les événements localement.

3. **Radar Local Console**  
   Processus indépendant qui lit l’Event Store et affiche les événements.

### 4.2 Schéma d’ensemble

```text
ADA / RAG / système principal
        │
        │ emit_event(...)
        ▼
Event Store local
SQLite ou NDJSON
        │
        │ lecture locale
        ▼
Radar Local Event Console
http://127.0.0.1:8787
```

### 4.3 Indépendance du processus Radar

Radar doit être lancé séparément, par exemple :

```bash
python tools/radar_console.py --host 127.0.0.1 --port 8787
```

ou :

```bash
python -m ada.radar.console --host 127.0.0.1 --port 8787
```

Le serveur web principal d’ADA ne doit pas servir directement la console Radar.

---

## 5. Contraintes de sécurité

### 5.1 Accès local uniquement

Par défaut, Radar doit écouter uniquement sur :

```text
127.0.0.1
```

Le port par défaut recommandé est :

```text
8787
```

Le bind sur `0.0.0.0` doit être interdit par défaut.

S’il est malgré tout nécessaire d’autoriser un accès réseau, cela doit passer par une option explicite, par exemple :

```bash
python tools/radar_console.py --allow-network-access --host 0.0.0.0 --port 8787
```

Cette option doit afficher un avertissement clair au démarrage.

### 5.2 Non-exposition via le web principal

Radar ne doit pas être accessible via :

```text
/web/radar
/api/radar
/admin/radar
```

ou toute autre route exposée par le serveur web principal d’ADA.

### 5.3 Masquage des données sensibles

Le système doit masquer automatiquement les champs sensibles dans les événements :

- `api_key`
- `token`
- `access_token`
- `refresh_token`
- `authorization`
- `password`
- `secret`
- `cookie`
- `session_cookie`
- `private_key`
- chemins locaux trop sensibles si nécessaire

Exemple :

```json
{
  "authorization": "Bearer sk-xxxxx"
}
```

devient :

```json
{
  "authorization": "[REDACTED]"
}
```

### 5.4 Protection des contenus documentaires

Les événements ne doivent pas contenir de documents complets.

Les extraits de texte doivent être :

- courts ;
- optionnels ;
- désactivables ;
- limités par configuration ;
- masqués si le document est marqué sensible.

---

## 6. Composants à implémenter

## 6.1 Module d’émission d’événements

Créer un module interne chargé d’émettre des événements structurés.

Nom proposé :

```text
ada/radar/events.py
```

ou, selon l’arborescence existante :

```text
web/radar/events.py
```

Le module doit exposer une fonction simple :

```python
emit_event(
    type: str,
    level: str = "info",
    message: str = "",
    module: str | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    job_id: str | None = None,
    document_id: str | None = None,
    metadata: dict | None = None,
    duration_ms: int | None = None,
    error_code: str | None = None,
    exception: Exception | None = None,
) -> None
```

### Règle impérative

`emit_event()` ne doit jamais bloquer ADA.

En cas d’erreur interne dans Radar :

- l’exception doit être absorbée ;
- ADA doit continuer à fonctionner ;
- une trace locale minimale peut être écrite dans un fichier de secours.

---

## 6.2 Event Store local

Deux modes de stockage peuvent être prévus.

### Option recommandée : SQLite

Chemin par défaut :

```text
data/radar/events.sqlite
```

Avantages :

- filtres rapides ;
- pagination ;
- recherche ;
- requêtes par `request_id`, `document_id`, `job_id` ;
- meilleure base pour l’interface web.

### Option secondaire : NDJSON

Chemin par défaut :

```text
data/radar/events.ndjson
```

Chaque ligne contient un événement JSON.

Avantages :

- simplicité ;
- robustesse ;
- lisible avec `tail -f` ;
- facile à exporter.

### Recommandation finale

Implémenter d’abord SQLite, puis prévoir un export NDJSON.

---

## 6.3 Script Radar autonome

Créer un script dédié :

```text
tools/radar_console.py
```

Ce script doit :

- charger la configuration Radar ;
- ouvrir l’Event Store local ;
- démarrer un serveur HTTP local ;
- servir une interface web légère ;
- exposer une API locale de consultation ;
- exposer un flux temps réel via Server-Sent Events ou WebSocket.

Commande minimale :

```bash
python tools/radar_console.py
```

Commande complète :

```bash
python tools/radar_console.py \
  --host 127.0.0.1 \
  --port 8787 \
  --db data/radar/events.sqlite
```

---

## 6.4 Interface web locale

L’interface doit être simple, rapide et autonome.

Elle peut être servie par le script Radar lui-même.

Fonctions minimales :

- flux temps réel des événements ;
- historique paginé ;
- filtres ;
- recherche plein texte ;
- vue détail d’un événement ;
- timeline par requête ;
- timeline par document ;
- vue erreurs ;
- export JSON ou NDJSON.

---

## 7. Modèle de données événementiel

Chaque événement doit être structuré.

### 7.1 Champs obligatoires

```json
{
  "id": "evt_...",
  "timestamp": "2026-06-01T10:43:03.123Z",
  "level": "info",
  "type": "rag.search.completed",
  "module": "radar",
  "message": "Recherche RAG terminée"
}
```

### 7.2 Champs optionnels

```json
{
  "session_id": "sess_...",
  "request_id": "req_...",
  "job_id": "job_...",
  "document_id": "doc_...",
  "user_id": "user_...",
  "duration_ms": 342,
  "error_code": null,
  "metadata": {}
}
```

### 7.3 Exemple complet

```json
{
  "id": "evt_01HZ...",
  "timestamp": "2026-06-01T10:43:03.123Z",
  "level": "info",
  "type": "rag.search.completed",
  "module": "rag.search",
  "message": "Recherche vectorielle terminée",
  "session_id": "sess_123",
  "request_id": "req_456",
  "job_id": null,
  "document_id": null,
  "duration_ms": 342,
  "error_code": null,
  "metadata": {
    "query_preview": "Comment fonctionne le module customdoc ?",
    "top_k": 8,
    "chunks_found": 7,
    "collection": "dolibarr_docs"
  }
}
```

---

## 8. Nomenclature des événements

Les types d’événements doivent être nommés de manière stable et hiérarchique.

Format recommandé :

```text
domaine.action.status
```

Exemples :

```text
document.uploaded
document.parsing.started
document.parsing.completed
document.parsing.failed
```

---

## 8.1 Événements documentaires

```text
document.uploaded
document.deleted
document.updated
document.metadata.updated

document.parsing.started
document.parsing.completed
document.parsing.failed

document.chunking.started
document.chunking.completed
document.chunking.failed

document.embedding.started
document.embedding.completed
document.embedding.failed

document.indexing.started
document.indexing.completed
document.indexing.failed
```

---

## 8.2 Événements RAG

```text
rag.query.received
rag.query.normalized
rag.search.started
rag.search.completed
rag.search.failed
rag.context.selected
rag.context.empty
rag.answer.started
rag.answer.completed
rag.answer.failed
```

---

## 8.3 Événements LLM

```text
llm.request.started
llm.request.completed
llm.request.failed
llm.response.stream.started
llm.response.stream.completed
llm.response.stream.failed
```

---

## 8.4 Événements système

```text
system.started
system.stopped
system.warning
system.error
system.health.changed
system.config.loaded
system.config.failed
```

---

## 8.5 Événements jobs / tâches

```text
job.created
job.started
job.progress
job.completed
job.failed
job.cancelled
job.retried
```

---

## 9. Niveaux de sévérité

Les niveaux supportés doivent être :

```text
debug
info
warning
error
critical
```

Usage recommandé :

- `debug` : détails techniques utiles au développeur ;
- `info` : événement normal ;
- `warning` : anomalie non bloquante ;
- `error` : échec d’une action ;
- `critical` : problème majeur affectant fortement le système.

---

## 10. Corrélation des événements

La valeur de Radar vient de la capacité à relier les événements entre eux.

### 10.1 `request_id`

Identifie une requête utilisateur de bout en bout.

Exemple :

```text
rag.query.received
rag.search.started
rag.search.completed
rag.context.selected
llm.request.started
llm.request.completed
rag.answer.completed
```

Tous ces événements doivent partager le même `request_id`.

### 10.2 `document_id`

Identifie un document dans son cycle de vie.

Exemple :

```text
document.uploaded
document.parsing.started
document.parsing.completed
document.chunking.completed
document.embedding.completed
document.indexing.completed
```

Tous ces événements doivent partager le même `document_id`.

### 10.3 `job_id`

Identifie une tâche longue ou asynchrone.

Exemples :

- import massif ;
- réindexation ;
- embedding batch ;
- nettoyage d’index ;
- reconstruction de base documentaire.

### 10.4 `session_id`

Identifie une session utilisateur ou conversationnelle lorsque l’information existe.

---

## 11. Stockage SQLite

### 11.1 Table `radar_events`

Schéma proposé :

```sql
CREATE TABLE IF NOT EXISTS radar_events (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    type TEXT NOT NULL,
    module TEXT,
    message TEXT,
    session_id TEXT,
    request_id TEXT,
    job_id TEXT,
    document_id TEXT,
    user_id TEXT,
    duration_ms INTEGER,
    error_code TEXT,
    metadata_json TEXT,
    exception_json TEXT,
    created_at TEXT NOT NULL
);
```

### 11.2 Index recommandés

```sql
CREATE INDEX IF NOT EXISTS idx_radar_events_timestamp ON radar_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_radar_events_level ON radar_events(level);
CREATE INDEX IF NOT EXISTS idx_radar_events_type ON radar_events(type);
CREATE INDEX IF NOT EXISTS idx_radar_events_request_id ON radar_events(request_id);
CREATE INDEX IF NOT EXISTS idx_radar_events_document_id ON radar_events(document_id);
CREATE INDEX IF NOT EXISTS idx_radar_events_job_id ON radar_events(job_id);
CREATE INDEX IF NOT EXISTS idx_radar_events_session_id ON radar_events(session_id);
```

---

## 12. API locale de Radar

Le script Radar doit exposer une API HTTP locale.

Cette API n’est pas destinée à être publique.

### 12.1 Santé du serveur

```http
GET /api/health
```

Réponse :

```json
{
  "status": "ok",
  "service": "radar-local-console",
  "event_store": "ok"
}
```

### 12.2 Liste des événements

```http
GET /api/events
```

Paramètres :

```text
limit
offset
level
type
module
request_id
document_id
job_id
session_id
from
to
q
```

Exemple :

```http
GET /api/events?level=error&limit=50
```

### 12.3 Détail d’un événement

```http
GET /api/events/{id}
```

### 12.4 Timeline d’une requête

```http
GET /api/requests/{request_id}/timeline
```

### 12.5 Timeline d’un document

```http
GET /api/documents/{document_id}/timeline
```

### 12.6 Timeline d’un job

```http
GET /api/jobs/{job_id}/timeline
```

### 12.7 Flux temps réel

Option recommandée : Server-Sent Events.

```http
GET /api/events/stream
```

Alternative acceptable : WebSocket.

```text
/ws/events
```

---

## 13. Interface utilisateur

### 13.1 Page principale

La page principale doit afficher :

- un bandeau d’état ;
- les derniers événements ;
- les filtres principaux ;
- une zone de recherche ;
- une indication de connexion au flux temps réel.

Exemple visuel :

```text
Radar Local Event Console
Status: OK | Events: 1243 | Errors: 3 | Last event: 2s ago

[Search...] [Level] [Type] [Module] [Request] [Document]

10:42:12 INFO    document.uploaded          guide_customdoc.pdf
10:42:13 INFO    document.parsing.started   Parsing started
10:42:16 INFO    document.chunking.completed 184 chunks generated
10:42:18 ERROR   document.embedding.failed  Embedding provider timeout
```

### 13.2 Vue détail événement

Chaque événement doit être ouvrable.

La vue détail doit afficher :

- timestamp ;
- type ;
- niveau ;
- module ;
- message ;
- identifiants de corrélation ;
- metadata formatée ;
- exception masquable si présente.

### 13.3 Vue requête RAG

Une requête doit être affichable sous forme de timeline :

```text
Question reçue
↓
Recherche RAG démarrée
↓
7 chunks trouvés
↓
Contexte sélectionné
↓
Appel LLM démarré
↓
Réponse générée
```

La vue doit montrer :

- durée totale ;
- nombre de chunks trouvés ;
- sources utilisées si disponible ;
- erreurs éventuelles ;
- étapes lentes.

### 13.4 Vue document

Un document doit être affichable sous forme de cycle de traitement :

```text
Upload: OK
Parsing: OK
Chunking: OK — 184 chunks
Embedding: OK
Indexing: OK
Last used in RAG: 2026-06-01 10:43:03
```

En cas d’échec :

```text
Embedding: FAILED
Reason: provider timeout
Action: consulter détails
```

### 13.5 Vue erreurs

Une vue dédiée doit lister :

- erreurs récentes ;
- erreurs critiques ;
- erreurs par module ;
- événements `failed` ;
- stack traces masquables.

---

## 14. Configuration

Ajouter une section de configuration Radar.

Exemple YAML :

```yaml
radar:
  enabled: true

  event_store:
    type: "sqlite"
    path: "data/radar/events.sqlite"
    retention_days: 30
    max_events: 100000

  local_console:
    enabled: true
    host: "127.0.0.1"
    port: 8787
    require_token: false
    allow_network_access: false

  redaction:
    enabled: true
    mask_fields:
      - api_key
      - token
      - access_token
      - refresh_token
      - authorization
      - password
      - secret
      - cookie
      - private_key

  content_safety:
    store_query_preview: true
    max_query_preview_chars: 300
    store_chunk_preview: false
    max_chunk_preview_chars: 300

  realtime:
    enabled: true
    transport: "sse"
```

---

## 15. Intégration dans le RAG ADA

### 15.1 Ingestion documentaire

Ajouter des événements aux étapes suivantes :

- document reçu ;
- document validé ;
- parsing commencé ;
- parsing terminé ;
- parsing échoué ;
- chunking commencé ;
- chunking terminé ;
- embedding commencé ;
- embedding terminé ;
- embedding échoué ;
- indexation commencée ;
- indexation terminée ;
- indexation échouée.

### 15.2 Recherche RAG

Ajouter des événements aux étapes suivantes :

- question reçue ;
- question normalisée ;
- recherche démarrée ;
- recherche terminée ;
- contexte sélectionné ;
- aucun contexte trouvé ;
- génération démarrée ;
- génération terminée ;
- génération échouée.

### 15.3 Appels LLM

Ajouter des événements aux étapes suivantes :

- appel modèle démarré ;
- réponse reçue ;
- streaming démarré ;
- streaming terminé ;
- timeout ;
- erreur provider ;
- erreur de parsing réponse.

---

## 16. Exemples d’utilisation côté code

### 16.1 Événement simple

```python
from ada.radar.events import emit_event

emit_event(
    type="document.uploaded",
    level="info",
    module="documents.upload",
    message="Document uploaded",
    document_id=document.id,
    metadata={
        "filename": document.filename,
        "size_bytes": document.size_bytes,
        "mime_type": document.mime_type,
    },
)
```

### 16.2 Événement avec durée

```python
start = time.perf_counter()

chunks = chunk_document(document)

duration_ms = int((time.perf_counter() - start) * 1000)

emit_event(
    type="document.chunking.completed",
    level="info",
    module="documents.chunking",
    message="Document chunking completed",
    document_id=document.id,
    duration_ms=duration_ms,
    metadata={
        "chunks_count": len(chunks),
    },
)
```

### 16.3 Événement d’erreur

```python
try:
    embed_chunks(chunks)
except Exception as exc:
    emit_event(
        type="document.embedding.failed",
        level="error",
        module="documents.embedding",
        message="Embedding failed",
        document_id=document.id,
        error_code="EMBEDDING_FAILED",
        exception=exc,
        metadata={
            "chunks_count": len(chunks),
            "provider": embedding_provider_name,
        },
    )
    raise
```

### 16.4 Requête RAG corrélée

```python
request_id = create_request_id()

emit_event(
    type="rag.query.received",
    level="info",
    module="rag.query",
    message="RAG query received",
    request_id=request_id,
    session_id=session_id,
    metadata={
        "query_preview": query[:300],
    },
)

results = search_rag(query)

emit_event(
    type="rag.search.completed",
    level="info",
    module="rag.search",
    message="RAG search completed",
    request_id=request_id,
    metadata={
        "chunks_found": len(results),
        "top_k": top_k,
    },
)
```

---

## 17. Résilience

### 17.1 Radar ne doit jamais bloquer ADA

Cas à gérer :

- base SQLite verrouillée ;
- fichier absent ;
- dossier non accessible ;
- disque plein ;
- erreur de sérialisation JSON ;
- metadata non sérialisable ;
- problème de permission ;
- configuration invalide.

Dans tous les cas :

- ADA continue ;
- l’erreur Radar est ignorée ou loggée dans un fallback minimal ;
- aucune exception Radar ne remonte dans le flux métier.

### 17.2 Écriture asynchrone optionnelle

Si l’écriture synchrone ralentit ADA, prévoir une file locale en mémoire :

```text
emit_event()
    ↓
queue mémoire
    ↓
worker local
    ↓
SQLite
```

Mais la première version peut utiliser une écriture directe robuste si elle reste simple et rapide.

---

## 18. Rétention et nettoyage

Prévoir une politique de rétention configurable :

```yaml
retention_days: 30
max_events: 100000
```

Le nettoyage peut être :

- effectué au démarrage du script Radar ;
- effectué périodiquement ;
- déclenché manuellement.

Exemples :

```bash
python tools/radar_console.py --cleanup
```

ou :

```bash
python -m ada.radar.cleanup --days 30
```

---

## 19. Export

La console doit permettre l’export des événements filtrés.

Formats :

- JSON ;
- NDJSON ;
- ZIP contenant JSON + informations système minimales.

Les exports doivent respecter le masquage des données sensibles.

---

## 20. Tests attendus

### 20.1 Tests unitaires

Tester :

- création d’événement ;
- génération d’ID ;
- sérialisation JSON ;
- masquage des secrets ;
- insertion SQLite ;
- lecture SQLite ;
- filtres ;
- recherche ;
- gestion d’erreur silencieuse ;
- metadata non sérialisable.

### 20.2 Tests d’intégration

Tester :

- émission d’événements depuis une ingestion documentaire ;
- émission d’événements depuis une requête RAG ;
- lecture par la console Radar ;
- affichage de la timeline par `request_id` ;
- affichage de la timeline par `document_id` ;
- flux temps réel SSE ou WebSocket.

### 20.3 Tests de sécurité

Tester :

- bind par défaut sur `127.0.0.1` ;
- refus ou avertissement pour `0.0.0.0` ;
- absence de route Radar dans le serveur web principal ;
- masquage des champs sensibles ;
- absence de documents complets dans les événements.

---

## 21. Critères d’acceptation

Le développement sera considéré comme terminé lorsque :

1. ADA peut émettre des événements structurés via une fonction unique `emit_event()`.
2. Les événements sont persistés localement dans SQLite.
3. Une commande permet de lancer Radar indépendamment du serveur web principal.
4. Radar écoute par défaut uniquement sur `127.0.0.1`.
5. Radar expose une interface web locale sur un port dédié.
6. La console affiche les événements récents.
7. La console permet de filtrer par niveau, type, module, requête, document et job.
8. La console permet de voir le détail d’un événement.
9. La console permet de voir une timeline par `request_id`.
10. La console permet de voir une timeline par `document_id`.
11. Les erreurs sont visibles dans une vue dédiée.
12. Les champs sensibles sont masqués.
13. Une erreur dans Radar ne bloque jamais ADA.
14. Radar n’est pas accessible via le serveur web principal.
15. Un export JSON ou NDJSON est disponible.

---

## 22. Plan de mise en œuvre proposé

### Phase 1 — Socle événementiel

- Créer le module `emit_event()`.
- Définir le modèle d’événement.
- Ajouter le masquage des données sensibles.
- Ajouter le stockage SQLite.
- Ajouter les tests unitaires.

### Phase 2 — Instrumentation RAG

- Ajouter les événements sur l’ingestion documentaire.
- Ajouter les événements sur le chunking.
- Ajouter les événements sur les embeddings.
- Ajouter les événements sur l’indexation.
- Ajouter les événements sur la recherche RAG.
- Ajouter les événements sur les appels LLM.

### Phase 3 — Console locale

- Créer `tools/radar_console.py`.
- Exposer `/api/health`.
- Exposer `/api/events`.
- Exposer `/api/events/{id}`.
- Exposer les timelines par requête, document et job.
- Ajouter l’interface web locale.

### Phase 4 — Temps réel et ergonomie

- Ajouter SSE ou WebSocket.
- Ajouter les filtres dynamiques.
- Ajouter la recherche.
- Ajouter la vue erreurs.
- Ajouter l’export.

### Phase 5 — Durcissement

- Vérifier la sécurité locale.
- Ajouter les tests d’intégration.
- Ajouter la rétention.
- Documenter l’usage.

---

## 23. Commandes attendues

### Lancer Radar

```bash
python tools/radar_console.py
```

### Lancer Radar avec options

```bash
python tools/radar_console.py \
  --host 127.0.0.1 \
  --port 8787 \
  --db data/radar/events.sqlite
```

### Accéder à la console

```text
http://127.0.0.1:8787
```

### Exporter les événements

```bash
python tools/radar_console.py --export events.ndjson
```

---

## 24. Documentation à fournir

Ajouter une documentation courte :

```text
docs/radar-local-console.md
```

Elle doit expliquer :

- ce qu’est Radar ;
- pourquoi il est local ;
- comment l’activer ;
- comment lancer la console ;
- comment lire les événements ;
- comment filtrer ;
- comment exporter ;
- quelles données sont masquées ;
- comment désactiver Radar.

---

## 25. Points de vigilance pour l’agent de développement

- Ne pas intégrer Radar comme route du serveur web principal.
- Ne pas rendre Radar accessible via le mécanisme web distant d’ADA.
- Ne pas faire dépendre ADA de Radar.
- Ne pas stocker de secrets en clair.
- Ne pas stocker de documents complets dans les événements.
- Ne pas casser les flux RAG existants.
- Ne pas instrumenter uniquement les erreurs : il faut aussi les événements métier normaux.
- Ne pas confondre logs techniques et événements Radar.

---

## 26. Définition synthétique

Radar Local Event Console est une console locale autonome permettant de visualiser, depuis un navigateur local, les événements internes d’ADA et de son moteur RAG.

Elle est :

- locale ;
- indépendante ;
- non exposée publiquement ;
- centrée sur les événements ;
- utile au diagnostic ;
- non bloquante pour ADA ;
- conçue pour suivre les documents, requêtes, jobs, erreurs et appels LLM.

---

## 27. Résultat attendu

À la fin de l’implémentation, un développeur doit pouvoir :

1. lancer ADA normalement ;
2. utiliser le RAG ;
3. importer des documents ;
4. poser des questions ;
5. lancer séparément :

```bash
python tools/radar_console.py --port 8787
```

6. ouvrir :

```text
http://127.0.0.1:8787
```

7. voir en temps réel tout ce qui se passe dans ADA :

```text
Document importé
Parsing démarré
Chunking terminé
Embeddings générés
Indexation terminée
Question reçue
Recherche RAG terminée
Réponse générée
Erreur LLM éventuelle
```

Cette console doit donner une vision claire et exploitable de l’activité interne d’ADA, sans compromettre la sécurité ni l’indépendance du système principal.
