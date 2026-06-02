Spécification — Base documentaire locale ADA Web
1. Objectif

Ajouter à ADA, côté web uniquement, une base documentaire locale permettant d’indexer une documentation Markdown importante stockée sur un disque NVMe, puis de l’utiliser dans le chat ADA comme source de connaissance.

Le système doit être distinct des skills. Les skills restent dédiées à la personnalisation, aux règles procédurales et aux comportements. La base documentaire sert à stocker, rechercher et citer de la documentation projet.

Le périmètre est limité à la branche univers, dossier web/, avec intégration dans le serveur FastAPI et le pipeline chat web existants. Le serveur web actuel est basé sur FastAPI dans web/server.py , et le chat passe par /api/chat, qui délègue à web.pipeline.process_message() .

2. Non-objectifs

Ne pas modifier la GUI native desktop.

Ne pas remplacer le système de skills.

Ne pas stocker la documentation dans la mémoire conversationnelle.

Ne pas envoyer la documentation vers un service cloud.

Ne pas injecter toute la documentation dans le prompt. Seuls les passages pertinents doivent être injectés.

3. Architecture cible
Dossier documentaire NVMe
ex: /mnt/nvme/ada_docs
        ↓
Scanner Markdown
        ↓
Découpage en chunks
        ↓
Index SQLite local + FTS5
        ↓
Recherche documentaire
        ↓
Injection contrôlée dans web/pipeline.py
        ↓
Réponse ADA avec références aux fichiers sources

L’architecture doit suivre la logique existante d’ADA : SQLite local, FastAPI, stockage sous data/, et injection de contexte dans le pipeline web. ADA utilise déjà SQLite + FTS5 pour la mémoire sémantique , et le système de skills utilise aussi FTS5 pour indexer du contenu Markdown .

4. Nouveaux fichiers à créer

Créer un module dédié :

core/documents/
  __init__.py
  documents_db.py
  documents_indexer.py
  documents_search.py
  documents_injector.py
  documents_mount.py

Créer un routeur web :

web/router_documents.py

Optionnel mais recommandé :

docs/documentation_rag.md
5. Paramètres à ajouter

Modifier core/settings_store.py dans DEFAULT_SETTINGS.

Ajouter :

"documents": {
    "enabled": True,
    "root_path": "",
    "require_mount": True,
    "expected_mount_path": "",
    "expected_device_hint": "",
    "index_path": "",
    "extensions": [".md"],
    "ignore_dirs": [".git", "node_modules", "__pycache__", ".venv", "venv"],
    "auto_index_on_startup": True,
    "chunk_size": 1200,
    "chunk_overlap": 200,
    "max_context_chunks": 6,
    "max_context_chars": 9000,
    "min_query_length": 3,
    "include_sources_in_answer": True
}

Règles :

root_path
- Dossier racine de la documentation Markdown.
- Doit idéalement pointer vers le disque NVMe.

expected_mount_path
- Point de montage attendu.
- Exemple Linux : /mnt/nvme/ada_docs
- Exemple Windows : D:\ADA_DOCS

expected_device_hint
- Chaîne optionnelle à retrouver dans les infos disque/montage.
- Exemple : nvme, Samsung, WD_BLACK, etc.

index_path
- Si vide : utiliser data/documents.db.
- Si renseigné : utiliser ce chemin.
- Recommandé pour grosse base : /mnt/nvme/ada_docs/.ada_index/documents.db

Important : si l’objectif est de garantir que l’index lui-même reste sur le NVMe, alors index_path doit être configurable et placé sur le NVMe.

6. Vérification du montage NVMe

Créer core/documents/documents_mount.py.

Fonctions attendues :

from pathlib import Path

def get_mount_status(root_path: str, expected_mount_path: str = "", expected_device_hint: str = "") -> dict:
    """
    Retourne l'état du dossier documentaire.

    Return:
    {
        "ok": bool,
        "root_path": str,
        "exists": bool,
        "is_dir": bool,
        "is_mount": bool | None,
        "device": str | None,
        "filesystem": str | None,
        "reason": str
    }
    """

Comportement :

Sur Linux :

Lire /proc/mounts.
Trouver le point de montage parent le plus proche de root_path.
Vérifier que root_path existe.
Vérifier que expected_mount_path, si fourni, correspond ou est parent de root_path.
Vérifier que expected_device_hint, si fourni, est présent dans le périphérique ou le point de montage.
Ne pas indexer si require_mount=True et que le montage n’est pas valide.

Sur Windows :

Vérifier que le lecteur existe.
Utiliser Path(root_path).exists().
Si possible, utiliser psutil.disk_partitions() pour identifier le volume.
Si expected_device_hint est fourni, faire une vérification best-effort.
Ne pas bloquer si l’information disque n’est pas disponible, sauf si require_mount=True.
7. Schéma SQLite

Créer core/documents/documents_db.py.

Base par défaut :

data/documents.db

Mais si settings.get("documents.index_path") est défini, utiliser ce chemin.

Schéma :

CREATE TABLE IF NOT EXISTS documents (
    id              TEXT PRIMARY KEY,
    path            TEXT NOT NULL UNIQUE,
    rel_path        TEXT NOT NULL,
    title           TEXT NOT NULL,
    hash            TEXT NOT NULL,
    size_bytes      INTEGER NOT NULL DEFAULT 0,
    mtime           REAL NOT NULL DEFAULT 0,
    extension       TEXT NOT NULL DEFAULT '.md',
    tags            TEXT NOT NULL DEFAULT '[]',
    frontmatter     TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id              TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    heading         TEXT NOT NULL DEFAULT '',
    content         TEXT NOT NULL,
    token_estimate  INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts USING fts5(
    id UNINDEXED,
    document_id UNINDEXED,
    heading,
    content,
    tokenize = "unicode61"
);

CREATE TABLE IF NOT EXISTS document_index_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    level       TEXT NOT NULL,
    message     TEXT NOT NULL,
    path        TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_documents_path ON documents(path);
CREATE INDEX IF NOT EXISTS idx_documents_rel_path ON documents(rel_path);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON document_chunks(document_id);

Triggers FTS :

CREATE TRIGGER IF NOT EXISTS document_chunks_ai AFTER INSERT ON document_chunks BEGIN
    INSERT INTO document_chunks_fts(id, document_id, heading, content)
    VALUES (new.id, new.document_id, new.heading, new.content);
END;

CREATE TRIGGER IF NOT EXISTS document_chunks_au AFTER UPDATE ON document_chunks BEGIN
    DELETE FROM document_chunks_fts WHERE id = old.id;
    INSERT INTO document_chunks_fts(id, document_id, heading, content)
    VALUES (new.id, new.document_id, new.heading, new.content);
END;

CREATE TRIGGER IF NOT EXISTS document_chunks_ad AFTER DELETE ON document_chunks BEGIN
    DELETE FROM document_chunks_fts WHERE id = old.id;
END;
8. Indexation Markdown

Créer core/documents/documents_indexer.py.

Fonctions attendues :

def index_all(force: bool = False) -> dict:
    """
    Scanne root_path et indexe tous les fichiers Markdown.
    Si force=False, ne réindexe que les fichiers nouveaux ou modifiés.
    """

def index_file(path: Path, root_path: Path, force: bool = False) -> dict:
    """
    Indexe un fichier Markdown unique.
    """

def remove_missing_files() -> int:
    """
    Supprime de la base les documents qui n'existent plus sur disque.
    """

Algorithme :

Lire les paramètres documents.*.
Vérifier documents.enabled.
Vérifier le montage via documents_mount.get_mount_status().
Scanner récursivement root_path.
Ignorer les dossiers dans ignore_dirs.
Ne prendre que les extensions autorisées, par défaut .md.
Calculer :
chemin absolu,
chemin relatif,
taille,
mtime,
hash SHA256 du contenu.
Si fichier inchangé, ne rien faire.
Parser le frontmatter YAML simple si présent.
Déterminer le titre :
title du frontmatter,
sinon premier # Titre,
sinon nom du fichier.
Découper en chunks.
Remplacer les chunks du document si le hash a changé.
Écrire un résumé d’indexation.

Format Markdown recommandé :

---
title: Architecture ADA Web
tags: [ada, web, fastapi, pipeline]
domain: ada
---

# Architecture ADA Web

## Vue générale

...

Le parseur frontmatter peut rester simple au départ, comme celui des skills existants, qui lit un bloc --- puis infère les métadonnées depuis le fichier .

9. Découpage en chunks

Règles :

Découper prioritairement par titres Markdown #, ##, ###.
Garder le titre courant dans heading.
Si une section dépasse chunk_size, découper par paragraphes.
Ajouter chunk_overlap caractères entre deux chunks longs.
Ne jamais produire de chunk vide.
Limiter un chunk à environ chunk_size + overlap.

Exemple de fonction :

def chunk_markdown(content: str, chunk_size: int = 1200, overlap: int = 200) -> list[dict]:
    """
    Return:
    [
        {
            "heading": "## Installation",
            "content": "...",
            "token_estimate": 340
        }
    ]
    """

Estimation tokens simple :

token_estimate = max(1, len(content) // 4)
10. Recherche documentaire

Créer core/documents/documents_search.py.

Fonctions :

def search_documents(query: str, limit: int = 6) -> list[dict]:
    """
    Recherche FTS5 dans les chunks documentaires.
    """

def get_document(document_id: str) -> dict | None:
    """
    Récupère un document et ses métadonnées.
    """

def list_documents(limit: int = 200, offset: int = 0) -> list[dict]:
    """
    Liste les documents indexés.
    """

def stats() -> dict:
    """
    Retourne le nombre de documents, chunks, taille totale, dernier index.
    """

Résultat de recherche :

{
    "chunk_id": "...",
    "document_id": "...",
    "title": "Architecture ADA Web",
    "path": "/mnt/nvme/ada_docs/ada/web.md",
    "rel_path": "ada/web.md",
    "heading": "## Pipeline chat",
    "content": "...",
    "score": -1.42
}

La recherche doit utiliser BM25 via FTS5. Le projet a déjà un exemple clair de recherche FTS5 dans core/skills/skills_manager.py .

11. Injection dans le chat

Créer core/documents/documents_injector.py.

Fonction :

def inject_documentation(messages: list[dict], query: str, context_id: str | None = None) -> tuple[list[dict], dict]:
    """
    Recherche les chunks documentaires pertinents et les injecte dans le system prompt.

    Return:
    (
        messages,
        {
            "documents_injected": [...],
            "chunks_count": 0
        }
    )
    """

Comportement :

Si documents.enabled=False, ne rien faire.
Si la requête est trop courte, ne rien faire.
Rechercher max_context_chunks.
Tronquer à max_context_chars.
Injecter dans le message system existant.
Ne jamais remplacer le prompt système existant.
Ajouter une instruction explicite : répondre à partir de la documentation quand elle est pertinente, et citer les fichiers.

Format d’injection :

---
## Documentation locale ADA

Les extraits suivants proviennent de la base documentaire locale.
Utilise-les uniquement s'ils sont pertinents pour répondre à la question.
Quand tu t'appuies sur un extrait, cite le fichier source sous la forme `source: chemin/fichier.md`.

### Source: ada/web/pipeline.md
Section: ## Pipeline chat
...

Intégration dans web/pipeline.py.

Actuellement, le pipeline construit les messages, injecte éventuellement le contexte domotique, puis injecte les skills et la mémoire . Ajouter l’injection documentaire juste avant ou juste après les skills :

from core.documents.documents_injector import inject_documentation

messages, doc_meta = inject_documentation(messages, user_text, context_id=_effective_ctx)

Ordre recommandé :

1. System prompt ADA
2. Contexte plugins / univers
3. Contexte domotique si nécessaire
4. Documentation locale ADA
5. Skills
6. Mémoire conversationnelle
7. Message utilisateur

Justification : la documentation est une source de connaissance projet. Les skills restent des règles ou procédures. La mémoire conversationnelle reste un contexte de fond de priorité plus faible.

12. Routes API web

Créer web/router_documents.py.

Inclure ce routeur dans web/server.py :

from web.router_documents import router as _documents_router
app.include_router(_documents_router)

Le serveur inclut déjà plusieurs routeurs FastAPI, notamment auth, profils, plugins, etc.

Routes à créer :

GET /api/documents/status

Retourne :

{
  "enabled": true,
  "root_path": "/mnt/nvme/ada_docs",
  "mount": {
    "ok": true,
    "exists": true,
    "is_dir": true,
    "is_mount": true,
    "device": "/dev/nvme0n1p1",
    "filesystem": "ext4",
    "reason": "OK"
  },
  "stats": {
    "documents": 42,
    "chunks": 380,
    "size_bytes": 1234567
  }
}
GET /api/documents

Paramètres :

limit: int = 100
offset: int = 0

Retourne les documents indexés.

POST /api/documents/reindex

Body :

{
  "force": false
}

Retour :

{
  "ok": true,
  "indexed": 12,
  "updated": 3,
  "skipped": 40,
  "deleted": 2,
  "errors": 0
}
POST /api/documents/search

Body :

{
  "query": "comment fonctionne le pipeline web ADA ?",
  "limit": 6
}

Retourne les chunks pertinents.

GET /api/documents/logs

Retourne les derniers logs d’indexation.

DELETE /api/documents/index

Vide uniquement l’index documentaire, pas les fichiers sources.

13. Démarrage automatique

Dans web/server.py, ajouter au startup :

try:
    from core.documents.documents_db import init_db as _documents_init_db
    from core.documents.documents_indexer import index_all as _documents_index_all
    from core.settings_store import settings as _settings

    _documents_init_db()
    if _settings.get("documents.enabled", True) and _settings.get("documents.auto_index_on_startup", True):
        _documents_index_all(force=False)
except Exception as _e:
    import logging as _log
    _log.getLogger(__name__).warning("[Documents] Erreur init : %s", _e)

Le startup web initialise déjà mémoire, profils, plugins, skills et maintenance . L’index documentaire doit suivre le même modèle : erreur loggée, mais le serveur web ne doit pas tomber.

14. Interface web minimale

Dans web/static/index.html, ajouter une page ou sous-page “Documentation”.

Fonctions minimales :

- Afficher le chemin documentaire configuré.
- Afficher l’état du montage.
- Afficher nombre de fichiers et chunks indexés.
- Bouton “Réindexer”.
- Champ de recherche documentaire.
- Liste des résultats avec fichier source et section.

La page peut être simple au départ. L’important est de pouvoir vérifier que la base est montée, indexée et recherchable.

15. Sécurité et robustesse

Le système doit :

Refuser d’indexer si root_path est vide.
Refuser d’indexer si require_mount=True et que le montage attendu n’est pas valide.
Ne jamais suivre de symlinks en dehors du root_path.
Ignorer les fichiers binaires.
Limiter la taille maximale d’un fichier Markdown indexable, par exemple 5 Mo par défaut.
Logguer les erreurs par fichier sans interrompre toute l’indexation.
Ne jamais supprimer les fichiers sources.
Ne supprimer que les entrées SQLite correspondant à des fichiers disparus.
16. Critères d’acceptation
Indexation
Quand documents.root_path pointe vers un dossier contenant des .md, /api/documents/reindex crée un index SQLite.
Les fichiers inchangés sont ignorés lors d’une indexation incrémentale.
Un fichier modifié est réindexé.
Un fichier supprimé est retiré de l’index.
Les dossiers ignorés ne sont pas scannés.
Montage NVMe
Si le dossier documentaire n’existe pas, /api/documents/status retourne ok=false.
Si require_mount=True et que le point de montage attendu n’est pas valide, l’indexation est refusée.
Si le montage est valide, l’indexation fonctionne.
Recherche
/api/documents/search retourne des chunks pertinents.
Chaque résultat contient title, rel_path, heading, content.
Une recherche vide ou trop courte ne retourne pas de résultats.
Chat
Une question liée à la documentation ADA déclenche l’injection de chunks pertinents.
ADA répond en s’appuyant sur les extraits injectés.
ADA mentionne les fichiers sources quand elle utilise la documentation.
Une question sans rapport avec la documentation ne doit pas être polluée par des extraits inutiles.
Web uniquement
Aucune dépendance à la GUI native.
Aucun fichier GUI desktop ne doit être modifié.
17. Plan de tests manuel

Créer un dossier de test :

/mnt/nvme/ada_docs/
  architecture.md
  web_pipeline.md
  plugins.md

Contenu exemple :

---
title: Pipeline Web ADA
tags: [ada, web, pipeline]
---

# Pipeline Web ADA

Le pipeline web ADA reçoit les messages depuis `/api/chat`, construit le contexte, puis appelle le modèle local via Ollama.

Tests :

1. Configurer documents.root_path.
2. Lancer ADA web.
3. Appeler GET /api/documents/status.
4. Appeler POST /api/documents/reindex.
5. Appeler POST /api/documents/search avec “pipeline web ADA”.
6. Poser dans le chat : “Comment fonctionne le pipeline web ADA ?”
7. Vérifier qu’ADA répond avec une référence à web_pipeline.md.
8. Modifier web_pipeline.md.
9. Relancer /api/documents/reindex.
10. Vérifier que le hash et les chunks sont mis à jour.
18. Évolution future : recherche vectorielle

La V1 doit être FTS5 uniquement. C’est simple, local, robuste et cohérent avec ADA.

Prévoir cependant une extension V2 :

document_embeddings
- chunk_id
- model
- embedding

Modèle local recommandé :

nomic-embed-text via Ollama

Le settings existant mentionne déjà nomic-embed-text comme modèle d’embedding du routeur sémantique . Une V2 pourrait faire une recherche hybride :

score_final = score_fts + score_vectoriel

Mais ne pas implémenter cette partie dans la première passe.

19. Résultat attendu

À la fin de l’implémentation, ADA web doit pouvoir :

- utiliser un dossier documentaire Markdown local ;
- vérifier que ce dossier est bien monté sur le volume attendu ;
- indexer une grosse base documentaire de façon incrémentale ;
- rechercher rapidement dans cette base ;
- injecter uniquement les passages pertinents dans le chat ;
- répondre avec des références aux fichiers sources ;
- fonctionner entièrement en local.


