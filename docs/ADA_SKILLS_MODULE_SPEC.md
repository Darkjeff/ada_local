# SPEC COMPLÈTE — MODULE SKILLS ADA
## Document de référence pour implémentation par agent

**Version** : 1.0  
**Projet** : ADA — Système de Pilotage Unifié  
**Auteur** : Aurélien  
**Date** : 2026-05-31  
**Stack cible** : Python 3.11+, SQLite (FTS5), backend ADA existant

---

## 1. CONTEXTE ET OBJECTIF

### 1.1 Pourquoi ce module

ADA dispose actuellement d'une mémoire sémantique brute qui stocke l'ensemble des échanges. Ce système présente deux limites :
- Il pollue le contexte LLM avec des échanges anodins ou non réutilisables
- Il ne capitalise pas le savoir-faire : ADA repart de zéro à chaque tâche similaire

Le module Skills remplace et améliore cette mémoire en stockant non pas *ce qui s'est passé*, mais *comment bien faire*. Inspiré du système Hermes Agent (Nous Research, 2026), il est adapté à l'architecture ADA et simplifié au maximum.

### 1.2 Ce que fait le module

- Indexer des skills (procédures, savoir-faire, personnalité, configurations) dans une base SQLite
- Rechercher les skills pertinents avant chaque réponse LLM via recherche full-text (FTS5)
- Injecter automatiquement les skills sélectionnés dans le system prompt
- Générer de nouveaux skills AUTO à partir des conversations complexes
- Gérer un système de priorité, de promotion et d'archivage
- Proposer un fallback en cascade si aucun skill actif ne couvre la demande

### 1.3 Ce que le module ne fait PAS

- Il ne remplace pas le moteur LLM
- Il ne gère pas les sessions de conversation (c'est le rôle du backend existant)
- Il ne fait pas de recherche vectorielle / embeddings (prévu v2 si besoin)
- Il ne purge jamais automatiquement un skill de priorité 1, 2 ou 3

---

## 2. STRUCTURE DES FICHIERS

```
ada/
├── skills/
│   ├── __init__.py
│   ├── skills_manager.py       # Module principal — CRUD, recherche, cascade
│   ├── skills_injector.py      # Injection dans le system prompt LLM
│   ├── skills_generator.py     # Génération automatique de skills depuis conversations
│   └── skills_db.py            # Initialisation et migrations SQLite
├── data/
│   └── skills.db               # Base SQLite (créée automatiquement)
└── skills_seed/
    ├── core/                   # Skills CORE livrés avec ADA (fichiers .md)
    │   ├── ada_identity.md
    │   ├── ada_personality.md
    │   └── ada_response_format.md
    └── domain/                 # Skills DOMAIN livrés avec ADA
        ├── opentechno.md
        ├── maison.md
        ├── uscss.md
        └── margep.md
```

---

## 3. SCHÉMA BASE DE DONNÉES

### 3.1 Table principale `skills`

```sql
CREATE TABLE IF NOT EXISTS skills (
    id              TEXT PRIMARY KEY,
    -- Identifiant unique, format snake_case : "infra_backup_proxmox"
    -- Jamais de majuscules, jamais d'espaces, jamais de caractères spéciaux

    title           TEXT NOT NULL,
    -- Titre lisible humain : "Procédure backup Proxmox via vzdump"

    keywords        TEXT NOT NULL,
    -- Mots-clés séparés par des espaces, minuscules, sans accents
    -- Exemple : "backup proxmox vzdump vm sauvegarde snapshot"
    -- Ces mots-clés sont la base de la recherche FTS — ils doivent être exhaustifs

    domain          TEXT NOT NULL DEFAULT 'global',
    -- Valeurs autorisées : global | maison | opentechno | uscss | margep
    -- "global" = applicable à tous les contextes

    priority        INTEGER NOT NULL DEFAULT 4,
    -- 1 = CORE       : identité, personnalité ADA — toujours chargé, jamais purgé
    -- 2 = DOMAIN     : connaissances sociétés et missions — chargé si domaine actif
    -- 3 = OPERATIONAL: procédures métier validées manuellement — jamais purgé
    -- 4 = AUTO       : généré automatiquement — archivable, promouvable

    status          TEXT NOT NULL DEFAULT 'active',
    -- active   : chargé normalement dans la cascade
    -- archived : exclu du chargement normal, accessible via fallback uniquement

    content         TEXT NOT NULL,
    -- Le contenu complet du skill en Markdown
    -- Voir section 5 pour le format attendu

    usage_count     INTEGER NOT NULL DEFAULT 0,
    -- Incrémenté à chaque fois que ce skill est chargé en contexte

    success_count   INTEGER NOT NULL DEFAULT 0,
    -- Incrémenté uniquement quand l'utilisateur confirme une action
    -- ou ne corrige pas la réponse dans les 60 secondes suivantes
    -- C'est l'indicateur de qualité principal

    last_used       TEXT,
    -- ISO 8601 : "2026-05-31T14:23:00"

    created_at      TEXT NOT NULL,
    -- ISO 8601 : "2026-05-31T14:23:00"

    auto_generated  INTEGER NOT NULL DEFAULT 0,
    -- 0 = créé manuellement, 1 = généré automatiquement

    promoted_at     TEXT DEFAULT NULL,
    -- ISO 8601 : date de promotion AUTO (priority 4) → OPERATIONAL (priority 3)
    -- NULL si jamais promu ou si créé directement en priority <= 3

    source_conversation_id TEXT DEFAULT NULL
    -- ID de la conversation ayant généré ce skill (pour traçabilité)
    -- NULL si créé manuellement
);
```

### 3.2 Index full-text FTS5

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS skills_fts
USING fts5(
    id,
    title,
    keywords,
    content,
    content='skills',
    content_rowid='rowid'
);
```

**Important** : La table FTS5 est un miroir de la table `skills`. Elle doit être synchronisée via des triggers.

### 3.3 Triggers de synchronisation FTS

```sql
-- Insertion
CREATE TRIGGER skills_ai AFTER INSERT ON skills BEGIN
    INSERT INTO skills_fts(rowid, id, title, keywords, content)
    VALUES (new.rowid, new.id, new.title, new.keywords, new.content);
END;

-- Suppression
CREATE TRIGGER skills_ad AFTER DELETE ON skills BEGIN
    INSERT INTO skills_fts(skills_fts, rowid, id, title, keywords, content)
    VALUES ('delete', old.rowid, old.id, old.title, old.keywords, old.content);
END;

-- Mise à jour
CREATE TRIGGER skills_au AFTER UPDATE ON skills BEGIN
    INSERT INTO skills_fts(skills_fts, rowid, id, title, keywords, content)
    VALUES ('delete', old.rowid, old.id, old.title, old.keywords, old.content);
    INSERT INTO skills_fts(rowid, id, title, keywords, content)
    VALUES (new.rowid, new.id, new.title, new.keywords, new.content);
END;
```

### 3.4 Index de performance

```sql
CREATE INDEX IF NOT EXISTS idx_skills_priority ON skills(priority);
CREATE INDEX IF NOT EXISTS idx_skills_status ON skills(status);
CREATE INDEX IF NOT EXISTS idx_skills_domain ON skills(domain);
CREATE INDEX IF NOT EXISTS idx_skills_priority_status ON skills(priority, status);
```

---

## 4. SYSTÈME DE PRIORITÉ ET RÈGLES DE GESTION

### 4.1 Priorité 1 — CORE

- **Rôle** : Identité d'ADA, personnalité, format de réponse, règles de comportement
- **Chargement** : TOUJOURS injecté en tête de system prompt, quelle que soit la requête
- **Purge** : JAMAIS — suppression manuelle uniquement via commande admin explicite
- **Modification** : Manuelle uniquement, jamais auto-générée
- **Exemples** : `ada_identity`, `ada_personality`, `ada_response_format`
- **Nombre attendu** : 3 à 10 skills maximum

### 4.2 Priorité 2 — DOMAIN

- **Rôle** : Connaissances spécifiques à chaque société ou mission principale
- **Chargement** : Injecté si le domaine correspondant est actif dans la conversation
- **Purge** : JAMAIS — suppression manuelle uniquement
- **Modification** : Manuelle uniquement
- **Exemples** : `opentechno_context`, `maison_config`, `uscss_context`, `margep_context`
- **Nombre attendu** : 1 à 5 skills par domaine

### 4.3 Priorité 3 — OPERATIONAL

- **Rôle** : Procédures métier validées, how-to techniques, configurations connues
- **Chargement** : Via recherche FTS si keywords matchent la requête
- **Purge** : JAMAIS après création ou promotion — suppression manuelle uniquement
- **Modification** : Manuelle ou via promotion depuis AUTO
- **Exemples** : `infra_backup_proxmox`, `domotique_scene_nuit`, `rmm_alerte_disque`
- **Promotion depuis AUTO** : Automatique dès `success_count >= 2`

### 4.4 Priorité 4 — AUTO

- **Rôle** : Skills générés automatiquement par ADA depuis les conversations
- **Chargement** : Via recherche FTS, après les skills OPERATIONAL
- **Archivage** : Automatique si `usage_count = 0` ET `last_used` > 30 jours
- **Suppression** : JAMAIS automatique — archivage uniquement
- **Promotion** : Automatique vers OPERATIONAL dès `success_count >= 2`
- **Restauration** : Possible depuis archive si trouvé en fallback et validé

### 4.5 Règles de promotion AUTO → OPERATIONAL

```python
# Vérification à chaque mise à jour de success_count
if skill.priority == 4 and skill.success_count >= 2:
    skill.priority = 3  # Promotion
    skill.promoted_at = datetime.now().isoformat()
    skill.status = 'active'  # S'il était archivé, il revient actif
    # Notifier ADA pour qu'elle informe l'utilisateur :
    # "Le skill '{title}' a été promu en OPERATIONAL suite à 2 succès."
```

### 4.6 Règle d'archivage AUTO

```python
# À exécuter via tâche planifiée quotidienne (cron ou scheduler Python)
def archive_stale_auto_skills():
    threshold = datetime.now() - timedelta(days=30)
    # Archiver les AUTO jamais utilisés depuis 30 jours
    # UNIQUEMENT priority=4, JAMAIS priority 1, 2 ou 3
    db.execute("""
        UPDATE skills SET status = 'archived'
        WHERE priority = 4
        AND status = 'active'
        AND usage_count = 0
        AND (last_used IS NULL OR last_used < ?)
    """, (threshold.isoformat(),))
```

---

## 5. FORMAT DU CONTENU D'UN SKILL

Chaque skill est un fichier Markdown structuré. Le contenu est stocké tel quel dans la colonne `content`. Voici le format obligatoire :

### 5.1 Template skill CORE

```markdown
# [TITRE DU SKILL]

## Rôle
[Description en une phrase de ce que ce skill définit]

## Contenu
[Le contenu principal : instructions, personnalité, règles, etc.]

## Règles absolues
- [Règle 1]
- [Règle 2]
```

### 5.2 Template skill DOMAIN

```markdown
# [NOM SOCIÉTÉ / DOMAINE]

## Contexte
[Description de la société ou du domaine en 2-3 phrases]

## Périmètre ADA dans ce contexte
[Ce qu'ADA fait/gère pour ce domaine]

## Informations clés
- [Info 1 : IP, accès, nomenclature, etc.]
- [Info 2]

## Interlocuteurs
- [Nom : rôle]

## Points d'attention
- [Piège ou particularité à connaître]
```

### 5.3 Template skill OPERATIONAL

```markdown
# [TITRE DE LA PROCÉDURE]

## Objectif
[Ce que cette procédure accomplit en une phrase]

## Déclencheurs
[Dans quels cas appliquer ce skill]

## Prérequis
- [Accès ou condition nécessaire]

## Procédure
1. [Étape 1]
2. [Étape 2]
3. [Étape 3]

## Commandes / Paramètres
```
[commande exacte avec paramètres]
```

## Erreurs connues
- **[Erreur]** → [Solution]

## Validation
[Comment vérifier que la procédure a réussi]

## Temps estimé
[Durée approximative]
```

### 5.4 Template skill AUTO (généré par ADA)

```markdown
# [TITRE AUTO-GÉNÉRÉ]

## Source
Généré automatiquement depuis conversation [ID] le [DATE]

## Contexte d'apprentissage
[Résumé de la situation qui a généré ce skill]

## Ce qui a fonctionné
[Étapes ou approche ayant mené au succès]

## Erreurs rencontrées
- [Erreur] → [Correction appliquée]

## Résultat obtenu
[Description du résultat final validé]

## À vérifier
[Points d'incertitude ou à confirmer manuellement]
```

---

## 6. MODULE `skills_db.py`

Ce fichier gère l'initialisation et la connexion à la base de données.

```python
# ada/skills/skills_db.py

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'skills.db')

def get_connection() -> sqlite3.Connection:
    """
    Retourne une connexion SQLite avec row_factory pour accès par nom de colonne.
    Active le mode WAL pour les accès concurrents.
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    """
    Crée les tables, triggers et index si absents.
    Idempotent — peut être appelé à chaque démarrage sans risque.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Table principale
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS skills (
            id                      TEXT PRIMARY KEY,
            title                   TEXT NOT NULL,
            keywords                TEXT NOT NULL,
            domain                  TEXT NOT NULL DEFAULT 'global',
            priority                INTEGER NOT NULL DEFAULT 4,
            status                  TEXT NOT NULL DEFAULT 'active',
            content                 TEXT NOT NULL,
            usage_count             INTEGER NOT NULL DEFAULT 0,
            success_count           INTEGER NOT NULL DEFAULT 0,
            last_used               TEXT,
            created_at              TEXT NOT NULL,
            auto_generated          INTEGER NOT NULL DEFAULT 0,
            promoted_at             TEXT DEFAULT NULL,
            source_conversation_id  TEXT DEFAULT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_skills_priority
            ON skills(priority);
        CREATE INDEX IF NOT EXISTS idx_skills_status
            ON skills(status);
        CREATE INDEX IF NOT EXISTS idx_skills_domain
            ON skills(domain);
        CREATE INDEX IF NOT EXISTS idx_skills_priority_status
            ON skills(priority, status);

        CREATE VIRTUAL TABLE IF NOT EXISTS skills_fts
        USING fts5(
            id, title, keywords, content,
            content='skills',
            content_rowid='rowid'
        );

        CREATE TRIGGER IF NOT EXISTS skills_ai
        AFTER INSERT ON skills BEGIN
            INSERT INTO skills_fts(rowid, id, title, keywords, content)
            VALUES (new.rowid, new.id, new.title, new.keywords, new.content);
        END;

        CREATE TRIGGER IF NOT EXISTS skills_ad
        AFTER DELETE ON skills BEGIN
            INSERT INTO skills_fts(skills_fts, rowid, id, title, keywords, content)
            VALUES ('delete', old.rowid, old.id, old.title, old.keywords, old.content);
        END;

        CREATE TRIGGER IF NOT EXISTS skills_au
        AFTER UPDATE ON skills BEGIN
            INSERT INTO skills_fts(skills_fts, rowid, id, title, keywords, content)
            VALUES ('delete', old.rowid, old.id, old.title, old.keywords, old.content);
            INSERT INTO skills_fts(rowid, id, title, keywords, content)
            VALUES (new.rowid, new.id, new.title, new.keywords, new.content);
        END;
    """)

    conn.commit()
    conn.close()


def seed_from_files(seed_dir: str):
    """
    Charge les skills initiaux depuis les fichiers .md du dossier skills_seed/.
    À appeler une seule fois lors du premier démarrage.
    Vérifie l'existence de l'id avant insertion pour être idempotent.

    Structure attendue du répertoire :
        seed_dir/core/     → priority=1, domain='global'
        seed_dir/domain/   → priority=2, domain=nom_fichier_sans_extension
    """
    conn = get_connection()

    for subfolder, priority, domain_from_filename in [
        ('core', 1, False),
        ('domain', 2, True)
    ]:
        folder = os.path.join(seed_dir, subfolder)
        if not os.path.exists(folder):
            continue

        for filename in os.listdir(folder):
            if not filename.endswith('.md'):
                continue

            skill_id = filename.replace('.md', '')
            domain = skill_id if domain_from_filename else 'global'

            # Vérifier si déjà présent
            existing = conn.execute(
                "SELECT id FROM skills WHERE id = ?", (skill_id,)
            ).fetchone()
            if existing:
                continue

            with open(os.path.join(folder, filename), 'r', encoding='utf-8') as f:
                content = f.read()

            # Extraire le titre (première ligne H1)
            title = skill_id
            for line in content.splitlines():
                if line.startswith('# '):
                    title = line[2:].strip()
                    break

            # Générer keywords depuis le nom de fichier (basique — à affiner manuellement)
            keywords = skill_id.replace('_', ' ')

            conn.execute("""
                INSERT INTO skills
                (id, title, keywords, domain, priority, status, content,
                 usage_count, success_count, created_at, auto_generated)
                VALUES (?, ?, ?, ?, ?, 'active', ?, 0, 0, ?, 0)
            """, (
                skill_id, title, keywords, domain, priority,
                content, datetime.now().isoformat()
            ))

    conn.commit()
    conn.close()
```

---

## 7. MODULE `skills_manager.py`

Module principal. Toutes les opérations sur les skills passent par ce fichier.

```python
# ada/skills/skills_manager.py

import sqlite3
from datetime import datetime, timedelta
from typing import Optional
from .skills_db import get_connection

# ─────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────

MAX_SKILLS_IN_CONTEXT = 5
# Nombre maximum de skills chargés simultanément dans le prompt.
# Au-delà, on prend les N avec le meilleur score.

AUTO_ARCHIVE_DAYS = 30
# Nombre de jours sans usage avant archivage d'un skill AUTO (priority=4)

AUTO_PROMOTE_THRESHOLD = 2
# Nombre de succès avant promotion AUTO → OPERATIONAL

PRIORITY_WEIGHTS = {
    1: 1000,  # CORE
    2: 100,   # DOMAIN
    3: 10,    # OPERATIONAL
    4: 1,     # AUTO
}

# ─────────────────────────────────────────────
# RECHERCHE PRINCIPALE — CASCADE EN 4 NIVEAUX
# ─────────────────────────────────────────────

def search_skills(
    query: str,
    active_domain: Optional[str] = None,
    max_results: int = MAX_SKILLS_IN_CONTEXT
) -> dict:
    """
    Recherche les skills pertinents pour une requête donnée.
    Retourne un dictionnaire structuré avec le résultat de chaque niveau.

    Paramètres :
        query         : La requête utilisateur (texte libre)
        active_domain : Domaine actif ('maison', 'opentechno', 'uscss', 'margep', None)
                        Si None, les skills DOMAIN de tous les domaines sont candidats
        max_results   : Nombre max de skills à retourner (hors CORE qui est toujours inclus)

    Retour :
        {
            'core': [skill, ...],          # Toujours présents
            'domain': [skill, ...],        # Si domaine actif
            'operational': [skill, ...],   # Via FTS sur skills actifs priority=3
            'auto': [skill, ...],          # Via FTS sur skills actifs priority=4
            'archive': [],                 # Vide à ce stade — rempli par fallback si besoin
            'total_loaded': int,
            'fallback_needed': bool        # True si aucun skill de niveau 3/4 trouvé
        }
    """
    conn = get_connection()
    result = {
        'core': [],
        'domain': [],
        'operational': [],
        'auto': [],
        'archive': [],
        'total_loaded': 0,
        'fallback_needed': False
    }

    # ── NIVEAU 1 : CORE (toujours chargé) ──
    result['core'] = _fetch_all_active(conn, priority=1)

    # ── NIVEAU 2 : DOMAIN (si domaine actif) ──
    if active_domain:
        result['domain'] = _fetch_all_active(conn, priority=2, domain=active_domain)
    else:
        # Pas de domaine actif → charger tous les DOMAIN (résumés courts)
        result['domain'] = _fetch_all_active(conn, priority=2)

    # ── NIVEAU 3 : OPERATIONAL via FTS ──
    fts_query = _build_fts_query(query)
    operational = _fts_search(conn, fts_query, priority=3, status='active', limit=max_results)
    result['operational'] = operational

    # ── NIVEAU 4 : AUTO via FTS (si on n'a pas encore assez) ──
    remaining = max_results - len(operational)
    if remaining > 0:
        auto = _fts_search(conn, fts_query, priority=4, status='active', limit=remaining)
        result['auto'] = auto

    total = (len(result['core']) + len(result['domain']) +
             len(result['operational']) + len(result['auto']))
    result['total_loaded'] = total

    # Fallback nécessaire si aucun OPERATIONAL ni AUTO trouvé
    result['fallback_needed'] = (
        len(result['operational']) == 0 and
        len(result['auto']) == 0
    )

    conn.close()

    # Mettre à jour les compteurs d'usage
    all_skills = (result['core'] + result['domain'] +
                  result['operational'] + result['auto'])
    for skill in all_skills:
        _increment_usage(skill['id'])

    return result


def search_archive(query: str, max_results: int = 3) -> list:
    """
    Fallback : recherche dans les skills archivés.
    À appeler uniquement si search_skills() retourne fallback_needed=True.

    Retour : liste de skills archivés pertinents (peut être vide)
    """
    conn = get_connection()
    fts_query = _build_fts_query(query)

    # Chercher dans tous les niveaux archivés, priorité 4 d'abord puis 3
    results = []
    for priority in [3, 4]:
        found = _fts_search(
            conn, fts_query,
            priority=priority,
            status='archived',
            limit=max_results - len(results)
        )
        results.extend(found)
        if len(results) >= max_results:
            break

    conn.close()
    return results


# ─────────────────────────────────────────────
# CRUD SKILLS
# ─────────────────────────────────────────────

def get_skill(skill_id: str) -> Optional[dict]:
    """Retourne un skill par son id, ou None si inexistant."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM skills WHERE id = ?", (skill_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def save_skill(skill_data: dict) -> bool:
    """
    Crée ou met à jour un skill.
    Si l'id existe déjà, met à jour title, keywords, content et domain.
    Ne modifie JAMAIS priority, usage_count, success_count via cette fonction.
    Pour modifier la priorité, utiliser promote_skill() ou set_priority().

    Paramètres obligatoires dans skill_data :
        id, title, keywords, domain, priority, content

    Paramètres optionnels :
        auto_generated (défaut 0)
        source_conversation_id (défaut None)

    Retour : True si succès, False si erreur
    """
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM skills WHERE id = ?", (skill_data['id'],)
        ).fetchone()

        if existing:
            conn.execute("""
                UPDATE skills
                SET title=?, keywords=?, content=?, domain=?
                WHERE id=?
            """, (
                skill_data['title'],
                skill_data['keywords'],
                skill_data['content'],
                skill_data.get('domain', 'global'),
                skill_data['id']
            ))
        else:
            conn.execute("""
                INSERT INTO skills
                (id, title, keywords, domain, priority, status, content,
                 usage_count, success_count, created_at, auto_generated,
                 source_conversation_id)
                VALUES (?, ?, ?, ?, ?, 'active', ?, 0, 0, ?, ?, ?)
            """, (
                skill_data['id'],
                skill_data['title'],
                skill_data['keywords'],
                skill_data.get('domain', 'global'),
                skill_data.get('priority', 4),
                skill_data['content'],
                datetime.now().isoformat(),
                skill_data.get('auto_generated', 0),
                skill_data.get('source_conversation_id', None)
            ))

        conn.commit()
        return True
    except Exception as e:
        print(f"[SkillsManager] Erreur save_skill: {e}")
        return False
    finally:
        conn.close()


def delete_skill(skill_id: str, force: bool = False) -> bool:
    """
    Supprime définitivement un skill.

    RÈGLE DE SÉCURITÉ :
    - Sans force=True : refuse de supprimer les priority 1, 2, 3
    - Avec force=True : supprime quel que soit le niveau (admin uniquement)

    Retour : True si supprimé, False si refusé ou erreur
    """
    conn = get_connection()
    skill = conn.execute(
        "SELECT priority FROM skills WHERE id = ?", (skill_id,)
    ).fetchone()

    if not skill:
        conn.close()
        return False

    if skill['priority'] <= 3 and not force:
        print(f"[SkillsManager] Refus suppression skill protégé: {skill_id} (priority={skill['priority']}). Utiliser force=True.")
        conn.close()
        return False

    conn.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
    conn.commit()
    conn.close()
    return True


def archive_skill(skill_id: str) -> bool:
    """
    Archive un skill (status='archived').
    Fonctionne sur n'importe quel niveau SAUF priority 1 (CORE).
    """
    conn = get_connection()
    skill = conn.execute(
        "SELECT priority FROM skills WHERE id = ?", (skill_id,)
    ).fetchone()

    if not skill:
        conn.close()
        return False

    if skill['priority'] == 1:
        print(f"[SkillsManager] Refus archivage skill CORE: {skill_id}")
        conn.close()
        return False

    conn.execute(
        "UPDATE skills SET status='archived' WHERE id=?", (skill_id,)
    )
    conn.commit()
    conn.close()
    return True


def restore_skill(skill_id: str) -> bool:
    """Restaure un skill archivé en status='active'."""
    conn = get_connection()
    conn.execute(
        "UPDATE skills SET status='active' WHERE id=?", (skill_id,)
    )
    conn.commit()
    conn.close()
    return True


def promote_skill(skill_id: str) -> bool:
    """
    Promeut un skill AUTO (priority=4) en OPERATIONAL (priority=3).
    Ne fait rien si le skill est déjà priority <= 3.

    Retour : True si promotion effectuée, False sinon
    """
    conn = get_connection()
    skill = conn.execute(
        "SELECT priority, status FROM skills WHERE id = ?", (skill_id,)
    ).fetchone()

    if not skill or skill['priority'] != 4:
        conn.close()
        return False

    conn.execute("""
        UPDATE skills
        SET priority=3, promoted_at=?, status='active'
        WHERE id=?
    """, (datetime.now().isoformat(), skill_id))
    conn.commit()
    conn.close()
    return True


def set_priority(skill_id: str, new_priority: int) -> bool:
    """
    Modifie manuellement la priorité d'un skill (admin uniquement).
    new_priority doit être entre 1 et 4.
    """
    if new_priority not in (1, 2, 3, 4):
        return False
    conn = get_connection()
    conn.execute(
        "UPDATE skills SET priority=? WHERE id=?", (new_priority, skill_id)
    )
    conn.commit()
    conn.close()
    return True


# ─────────────────────────────────────────────
# COMPTEURS ET SCORING
# ─────────────────────────────────────────────

def record_success(skill_id: str):
    """
    Incrémente le success_count d'un skill.
    À appeler quand l'utilisateur confirme une action ou valide une réponse.
    Vérifie automatiquement si le skill AUTO doit être promu en OPERATIONAL.
    """
    conn = get_connection()
    conn.execute("""
        UPDATE skills
        SET success_count = success_count + 1
        WHERE id = ?
    """, (skill_id,))
    conn.commit()

    # Vérifier la promotion automatique
    skill = conn.execute(
        "SELECT priority, success_count, title FROM skills WHERE id=?",
        (skill_id,)
    ).fetchone()

    promoted = False
    if skill and skill['priority'] == 4 and skill['success_count'] >= AUTO_PROMOTE_THRESHOLD:
        conn.execute("""
            UPDATE skills
            SET priority=3, promoted_at=?, status='active'
            WHERE id=?
        """, (datetime.now().isoformat(), skill_id))
        conn.commit()
        promoted = True

    conn.close()

    if promoted:
        # Retourner l'info pour que ADA puisse notifier l'utilisateur
        return {
            'promoted': True,
            'skill_id': skill_id,
            'message': f"Le skill '{skill['title']}' a été promu en OPERATIONAL suite à {AUTO_PROMOTE_THRESHOLD} succès confirmés."
        }
    return {'promoted': False}


def _increment_usage(skill_id: str):
    """Incrémente usage_count et met à jour last_used. Usage interne."""
    conn = get_connection()
    conn.execute("""
        UPDATE skills
        SET usage_count = usage_count + 1,
            last_used = ?
        WHERE id = ?
    """, (datetime.now().isoformat(), skill_id))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# TÂCHE DE MAINTENANCE (à planifier quotidiennement)
# ─────────────────────────────────────────────

def run_maintenance() -> dict:
    """
    Tâche de maintenance quotidienne.
    - Archive les skills AUTO inactifs depuis AUTO_ARCHIVE_DAYS jours
    - NE TOUCHE PAS aux priority 1, 2, 3

    Retour : {"archived": [ids], "promoted": [ids]}
    """
    conn = get_connection()
    threshold = (datetime.now() - timedelta(days=AUTO_ARCHIVE_DAYS)).isoformat()

    # Trouver les AUTO archivables
    to_archive = conn.execute("""
        SELECT id FROM skills
        WHERE priority = 4
        AND status = 'active'
        AND usage_count = 0
        AND (last_used IS NULL OR last_used < ?)
    """, (threshold,)).fetchall()

    archived_ids = []
    for row in to_archive:
        conn.execute(
            "UPDATE skills SET status='archived' WHERE id=?", (row['id'],)
        )
        archived_ids.append(row['id'])

    conn.commit()
    conn.close()

    return {
        'archived': archived_ids,
        'archived_count': len(archived_ids)
    }


def list_skills(
    priority: Optional[int] = None,
    domain: Optional[str] = None,
    status: Optional[str] = None
) -> list:
    """
    Liste les skills avec filtres optionnels.
    Retourne les métadonnées sans le contenu complet (pour affichage).
    """
    conn = get_connection()
    query = "SELECT id, title, keywords, domain, priority, status, usage_count, success_count, last_used, auto_generated, promoted_at FROM skills WHERE 1=1"
    params = []

    if priority is not None:
        query += " AND priority=?"
        params.append(priority)
    if domain:
        query += " AND domain=?"
        params.append(domain)
    if status:
        query += " AND status=?"
        params.append(status)

    query += " ORDER BY priority ASC, success_count DESC, usage_count DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ─────────────────────────────────────────────
# FONCTIONS INTERNES
# ─────────────────────────────────────────────

def _fetch_all_active(conn, priority: int, domain: Optional[str] = None) -> list:
    """Charge tous les skills actifs d'une priorité (et domaine optionnel)."""
    if domain:
        rows = conn.execute("""
            SELECT * FROM skills
            WHERE priority=? AND status='active' AND domain=?
            ORDER BY usage_count DESC
        """, (priority, domain)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM skills
            WHERE priority=? AND status='active'
            ORDER BY usage_count DESC
        """, (priority,)).fetchall()
    return [dict(row) for row in rows]


def _fts_search(
    conn,
    fts_query: str,
    priority: int,
    status: str,
    limit: int
) -> list:
    """
    Recherche FTS5 dans skills_fts, filtrée par priority et status.
    Calcule un score composite : rank FTS + poids priorité + bonus usage.
    """
    try:
        rows = conn.execute("""
            SELECT s.*, skills_fts.rank as fts_rank
            FROM skills_fts
            JOIN skills s ON skills_fts.id = s.id
            WHERE skills_fts MATCH ?
            AND s.priority = ?
            AND s.status = ?
            ORDER BY
                (? + (skills_fts.rank * -1) + (s.usage_count * 0.1) + (s.success_count * 0.5)) DESC
            LIMIT ?
        """, (fts_query, priority, status, PRIORITY_WEIGHTS[priority], limit)).fetchall()
        return [dict(row) for row in rows]
    except sqlite3.OperationalError:
        # FTS query invalide → retourner liste vide sans planter
        return []


def _build_fts_query(query: str) -> str:
    """
    Construit une query FTS5 depuis un texte libre.
    - Découpe en tokens
    - Supprime les stop words français courants
    - Retourne une query FTS5 avec OR entre les tokens

    Exemple : "comment faire un backup proxmox ?"
              → "backup OR proxmox"
    """
    stop_words = {
        'le', 'la', 'les', 'de', 'du', 'des', 'un', 'une',
        'et', 'ou', 'est', 'en', 'au', 'aux', 'ce', 'se',
        'il', 'elle', 'on', 'je', 'tu', 'nous', 'vous', 'ils',
        'que', 'qui', 'quoi', 'comment', 'quel', 'quelle',
        'pour', 'par', 'sur', 'sous', 'avec', 'sans', 'dans',
        'faire', 'avoir', 'être', 'mon', 'ton', 'son', 'ma',
        'ta', 'sa', 'me', 'te', 'si', 'pas', 'ne', 'plus',
        'ada', 'peux', 'peut', 'faut', 'dois', 'doit'
    }

    import re
    # Nettoyer la query
    tokens = re.sub(r'[^\w\s]', ' ', query.lower()).split()
    meaningful = [t for t in tokens if t not in stop_words and len(t) > 2]

    if not meaningful:
        # Fallback : utiliser tous les tokens > 2 caractères
        meaningful = [t for t in query.lower().split() if len(t) > 2]

    if not meaningful:
        return '""'  # Query vide → FTS retournera rien sans planter

    return ' OR '.join(meaningful)
```

---

## 8. MODULE `skills_injector.py`

Construit le system prompt enrichi avec les skills sélectionnés.

```python
# ada/skills/skills_injector.py

from typing import Optional
from .skills_manager import search_skills, search_archive

FALLBACK_MESSAGE_TEMPLATE = """
⚠️ INFORMATION ADA : Aucun skill opérationnel trouvé pour cette demande.
J'ai effectué une recherche dans mes archives : {archive_result}
"""

def build_system_prompt(
    base_system_prompt: str,
    query: str,
    active_domain: Optional[str] = None,
    enable_archive_fallback: bool = True
) -> tuple[str, dict]:
    """
    Construit le system prompt final en injectant les skills pertinents.

    Paramètres :
        base_system_prompt    : Le system prompt de base d'ADA (sans skills)
        query                 : La requête de l'utilisateur
        active_domain         : Domaine actif dans l'interface ('maison', 'opentechno', etc.)
        enable_archive_fallback : Si True, recherche dans archives si fallback nécessaire

    Retour :
        (system_prompt_final: str, metadata: dict)

        metadata contient :
        {
            'skills_loaded': [ids chargés],
            'fallback_used': bool,
            'archive_results': [ids depuis archive],
            'promotion_notification': str ou None
        }
    """
    metadata = {
        'skills_loaded': [],
        'fallback_used': False,
        'archive_results': [],
        'promotion_notification': None
    }

    # Recherche principale
    search_result = search_skills(query, active_domain)

    # Construire les blocs de skills
    skill_blocks = []

    # CORE — toujours en premier
    for skill in search_result['core']:
        skill_blocks.append(_format_skill_block(skill, 'CORE'))
        metadata['skills_loaded'].append(skill['id'])

    # DOMAIN
    for skill in search_result['domain']:
        skill_blocks.append(_format_skill_block(skill, 'DOMAIN'))
        metadata['skills_loaded'].append(skill['id'])

    # OPERATIONAL
    for skill in search_result['operational']:
        skill_blocks.append(_format_skill_block(skill, 'OPÉRATIONNEL'))
        metadata['skills_loaded'].append(skill['id'])

    # AUTO
    for skill in search_result['auto']:
        skill_blocks.append(_format_skill_block(skill, 'AUTO'))
        metadata['skills_loaded'].append(skill['id'])

    # FALLBACK ARCHIVE si nécessaire
    if search_result['fallback_needed'] and enable_archive_fallback:
        archive_skills = search_archive(query)
        if archive_skills:
            metadata['fallback_used'] = True
            metadata['archive_results'] = [s['id'] for s in archive_skills]
            for skill in archive_skills:
                skill_blocks.append(_format_skill_block(skill, 'ARCHIVE'))

    # Assembler le prompt final
    if skill_blocks:
        skills_section = "\n\n---\n## SKILLS CHARGÉS\n\n" + "\n\n---\n\n".join(skill_blocks)
    else:
        skills_section = ""

    # Message de fallback archive
    archive_notice = ""
    if metadata['fallback_used']:
        if metadata['archive_results']:
            archive_notice = f"\n\n⚠️ Note : Réponse basée sur des skills archivés ({', '.join(metadata['archive_results'])}). Veux-tu les réactiver ?"
        else:
            archive_notice = "\n\n⚠️ Note : Aucun skill trouvé, même en archive. Je mémorise cette réponse comme nouveau skill."

    final_prompt = base_system_prompt + skills_section + archive_notice

    return final_prompt, metadata


def _format_skill_block(skill: dict, level_label: str) -> str:
    """Formate un skill pour injection dans le prompt."""
    return f"""### [{level_label}] {skill['title']}
**ID**: {skill['id']} | **Domaine**: {skill['domain']}

{skill['content']}"""
```

---

## 9. MODULE `skills_generator.py`

Génère automatiquement des skills depuis les conversations.

```python
# ada/skills/skills_generator.py

import re
import json
from datetime import datetime
from typing import Optional
from .skills_manager import save_skill, get_skill

MIN_TOOL_CALLS_FOR_SKILL = 5
# Nombre minimum de tool calls dans une conversation pour déclencher
# la génération automatique d'un skill

def should_generate_skill(conversation: dict) -> bool:
    """
    Détermine si une conversation mérite la génération d'un skill.

    Paramètres :
        conversation : dict avec au minimum :
            {
                'tool_calls_count': int,   # Nombre de tool calls dans la conversation
                'resolved': bool,          # True si la tâche a été complétée
                'user_confirmed': bool     # True si l'utilisateur a confirmé le résultat
            }

    Retour : True si on doit générer un skill
    """
    return (
        conversation.get('tool_calls_count', 0) >= MIN_TOOL_CALLS_FOR_SKILL
        and conversation.get('resolved', False)
    )


def generate_skill_from_conversation(
    conversation_id: str,
    conversation_history: list,
    llm_client,
    domain: str = 'global'
) -> Optional[dict]:
    """
    Utilise le LLM pour analyser une conversation et en extraire un skill.

    Paramètres :
        conversation_id      : ID unique de la conversation
        conversation_history : Liste de messages [{'role': str, 'content': str}]
        llm_client           : Client LLM d'ADA (doit avoir une méthode complete())
        domain               : Domaine de la conversation

    Retour : dict skill prêt pour save_skill(), ou None si génération échouée
    """

    # Préparer le résumé de la conversation pour le LLM
    convo_text = "\n".join([
        f"[{msg['role'].upper()}]: {msg['content']}"
        for msg in conversation_history[-20:]  # Limiter aux 20 derniers messages
    ])

    extraction_prompt = f"""Analyse cette conversation entre un utilisateur et ADA (assistant IA).
Extrais les informations pour créer un skill réutilisable.

CONVERSATION :
{convo_text}

Génère un JSON avec exactement ces champs :
{{
    "id": "snake_case_identifiant_court_sans_accents",
    "title": "Titre lisible en français",
    "keywords": "mots clés séparés par espaces sans accents en minuscules",
    "summary": "Ce que cette procédure accomplit en une phrase",
    "steps": ["étape 1", "étape 2", "étape 3"],
    "errors": ["erreur rencontrée → solution appliquée"],
    "result": "Description du résultat final",
    "uncertainties": ["point incertain à vérifier"]
}}

RÈGLES :
- L'id doit être court, unique, en snake_case, sans accents
- Les keywords doivent couvrir tous les termes techniques de la conversation
- Steps = uniquement les étapes qui ont FONCTIONNÉ
- Errors = uniquement les erreurs qui se sont produites avec leur solution
- Retourner UNIQUEMENT le JSON, sans texte avant ou après
"""

    try:
        response = llm_client.complete(extraction_prompt)
        # Nettoyer la réponse (enlever éventuels backticks)
        clean = re.sub(r'```json|```', '', response).strip()
        data = json.loads(clean)
    except (json.JSONDecodeError, Exception) as e:
        print(f"[SkillsGenerator] Erreur extraction JSON: {e}")
        return None

    # Vérifier que l'id n'existe pas déjà
    existing = get_skill(data['id'])
    if existing:
        # Ajouter un suffixe timestamp pour éviter la collision
        data['id'] = f"{data['id']}_{datetime.now().strftime('%Y%m%d_%H%M')}"

    # Construire le contenu Markdown
    content = _build_auto_skill_content(data, conversation_id)

    skill = {
        'id': data['id'],
        'title': data['title'],
        'keywords': data['keywords'],
        'domain': domain,
        'priority': 4,  # AUTO par défaut
        'content': content,
        'auto_generated': 1,
        'source_conversation_id': conversation_id
    }

    return skill


def _build_auto_skill_content(data: dict, conversation_id: str) -> str:
    """Construit le contenu Markdown d'un skill auto-généré."""
    steps_md = "\n".join([f"{i+1}. {s}" for i, s in enumerate(data.get('steps', []))])
    errors_md = "\n".join([f"- {e}" for e in data.get('errors', [])]) or "- Aucune erreur notée"
    uncertainties_md = "\n".join([f"- {u}" for u in data.get('uncertainties', [])]) or "- Aucune"

    return f"""# {data['title']}

## Source
Généré automatiquement depuis conversation `{conversation_id}` le {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Objectif
{data.get('summary', 'Non défini')}

## Ce qui a fonctionné
{steps_md}

## Erreurs rencontrées et corrections
{errors_md}

## Résultat obtenu
{data.get('result', 'Non documenté')}

## Points à vérifier
{uncertainties_md}
"""
```

---

## 10. INTÉGRATION DANS LE BACKEND ADA

### 10.1 Initialisation au démarrage

```python
# Dans le fichier principal d'ADA (app.py ou main.py)

from ada.skills.skills_db import init_db, seed_from_files
from ada.skills.skills_manager import run_maintenance
import os

# Au démarrage de l'application
def startup():
    # 1. Initialiser la DB (idempotent)
    init_db()

    # 2. Charger les skills initiaux depuis les fichiers .md
    seed_dir = os.path.join(os.path.dirname(__file__), 'skills_seed')
    seed_from_files(seed_dir)

    # 3. Lancer la maintenance (archiver les skills AUTO obsolètes)
    maintenance_result = run_maintenance()
    if maintenance_result['archived_count'] > 0:
        print(f"[ADA Skills] {maintenance_result['archived_count']} skills AUTO archivés")
```

### 10.2 Dans le handler de message

```python
# Dans le handler qui traite les messages entrants

from ada.skills.skills_injector import build_system_prompt

async def handle_message(user_message: str, session: dict) -> str:
    # Récupérer le domaine actif depuis la session
    active_domain = session.get('active_domain', None)

    # Construire le system prompt enrichi avec les skills
    enriched_prompt, skills_metadata = build_system_prompt(
        base_system_prompt=ADA_BASE_SYSTEM_PROMPT,
        query=user_message,
        active_domain=active_domain,
        enable_archive_fallback=True
    )

    # Appel LLM avec le prompt enrichi
    response = await llm_client.complete(
        system=enriched_prompt,
        messages=session['history']
    )

    # Stocker les skills chargés dans la session pour le suivi des succès
    session['last_skills_loaded'] = skills_metadata['skills_loaded']

    # Notifier si un skill a été promu
    if skills_metadata.get('promotion_notification'):
        response += f"\n\n💡 {skills_metadata['promotion_notification']}"

    return response
```

### 10.3 Enregistrement des succès

```python
# Quand l'utilisateur confirme une action (bouton "Confirmer" dans l'UI)

from ada.skills.skills_manager import record_success

def on_user_confirms_action(session: dict):
    """Appelé quand l'utilisateur clique sur "Confirmer" dans l'interface."""
    for skill_id in session.get('last_skills_loaded', []):
        result = record_success(skill_id)
        if result.get('promoted'):
            # Afficher notification dans l'UI
            notify_user(result['message'])
```

### 10.4 Génération automatique de skill en fin de conversation

```python
# En fin de conversation complexe

from ada.skills.skills_generator import should_generate_skill, generate_skill_from_conversation
from ada.skills.skills_manager import save_skill

def on_conversation_end(conversation: dict, session: dict):
    """Appelé quand une conversation se termine ou dépasse MIN_TOOL_CALLS."""
    if should_generate_skill(conversation):
        skill_data = generate_skill_from_conversation(
            conversation_id=conversation['id'],
            conversation_history=session['history'],
            llm_client=llm_client,
            domain=session.get('active_domain', 'global')
        )
        if skill_data:
            save_skill(skill_data)
            # Notifier ADA pour qu'elle informe l'utilisateur
            notify_user(f"💾 Nouveau skill mémorisé : '{skill_data['title']}'")
```

---

## 11. SEEDS — SKILLS INITIAUX À CRÉER

### Fichier `skills_seed/core/ada_identity.md`

```markdown
# Identité ADA

## Rôle
Tu es ADA, système de pilotage unifié d'Aurélien.

## Périmètre
Tu gères en une interface unifiée :
- La domotique de la maison
- L'infrastructure IT d'OpenTechno (MSP)
- La supervision USCSS
- Le suivi Marge Pro

## Caractère
Tu es directe, précise, proactive. Tu anticipes les problèmes.
Tu ne poses pas de question inutile. Si tu as besoin de contexte,
tu demandes une seule chose à la fois, clairement.
Tu confirmes toujours les actions irréversibles avant de les exécuter.

## Ton
Professionnel mais humain. Pas de formules creuses.
Tu t'adresses à Aurélien par son prénom uniquement si nécessaire.
```

### Fichier `skills_seed/core/ada_response_format.md`

```markdown
# Format de réponse ADA

## Règles de format

- Réponses courtes pour les statuts et confirmations (1-3 lignes)
- Réponses structurées pour les procédures (titres, étapes numérotées)
- Toujours indiquer la source d'une information technique (skill chargé, mémoire, inférence)
- Pour les actions critiques : résumer l'action, demander confirmation, puis exécuter
- Ne jamais inventer des valeurs techniques (IP, credentials, IDs) — demander si inconnu
- Signaler explicitement si la réponse vient d'un skill archivé
```

### Fichier `skills_seed/domain/opentechno.md`

```markdown
# OpenTechno — Contexte MSP

## Description
Société de services informatiques managés (MSP) gérée par Aurélien.

## Infrastructure propre
- Proxmox : 2 nodes, 12 VMs/LXC actives
- NAS sauvegarde : 20 TB (14.2 TB utilisés)
- Serveur téléphonie : 4 lignes SIP
- Reverse proxy nginx + TLS
- LLM Ollama local (Mistral)

## Clients RMM supervisés
- Dupont SA : surveillance disques, serveurs Windows
- Martin & Fils : surveillance services Windows, backups

## Nomenclature
- VMs Proxmox numérotées par VMID (ex: 112 = compta Martin & Fils)
- Backups : storage "nas-backup", compression zstd
- Alertes RMM : seuil disque 85%, services critiques

## Points d'attention
- Toujours confirmer l'identité du client avant une action RMM
- Ne jamais redémarrer un serveur client sans validation explicite
- Les backups tournent la nuit de 02:00 à ~04:15
```

### Fichier `skills_seed/domain/maison.md`

```markdown
# Maison — Domotique

## Description
Résidence principale d'Aurélien, pilotée via Domoticz/Home Assistant.

## Appareils actifs
- 144 appareils Zigbee/Z-Wave/WiFi
- Éclairage : salon (3), bureau (2), extérieur
- Accès : portail EXT, parking EXT, parking colonne
- Climat : thermostat (cible 21°C jour, 18°C nuit)
- Sécurité : alarme (désactivée par défaut)

## Scènes configurées
- Focus : bureau 100%, 20°C, notifications suspendues 2h
- Relax : lumières 40% chaleureuses, 21°C
- Nuit : tout éteint, 18°C, portail sécurisé, alarme armée

## Points d'attention
- Vérifier l'heure avant d'armer l'alarme
- Le switch salon redémarre occasionnellement (connu, non critique)
- Les capteurs extérieurs ont une latence de ~2 secondes
```

---

## 12. COMMANDES ADMIN ADA

ADA doit reconnaître et traiter ces commandes spéciales dans le chat :

```
/skills list                    → Liste tous les skills actifs avec métadonnées
/skills list archived           → Liste les skills archivés
/skills show [id]               → Affiche le contenu complet d'un skill
/skills promote [id]            → Promeut un skill AUTO en OPERATIONAL
/skills archive [id]            → Archive un skill
/skills restore [id]            → Restaure un skill archivé
/skills delete [id]             → Supprime (demande confirmation, refuse si priority < 4)
/skills delete force [id]       → Suppression forcée (tous niveaux)
/skills maintenance             → Lance la tâche de maintenance manuellement
/skills new                     → Ouvre le formulaire de création manuelle
```

---

## 13. POINTS D'ATTENTION POUR L'IMPLÉMENTATION

1. **FTS5 doit être activé dans SQLite** — vérifier avec `SELECT sqlite_version()` et que la compilation inclut FTS5. Sur la plupart des distributions modernes c'est le cas.

2. **Ne jamais modifier `usage_count` et `success_count` manuellement** — passer obligatoirement par `_increment_usage()` et `record_success()`.

3. **Les triggers FTS sont automatiques** — ne pas insérer directement dans `skills_fts`, toujours passer par la table `skills`.

4. **Thread safety** — SQLite en mode WAL supporte les lectures concurrentes. Pour les écritures, utiliser un verrou applicatif si plusieurs workers peuvent écrire simultanément.

5. **Le `seed_from_files()` est idempotent** — l'appeler à chaque démarrage est safe, il vérifie l'existence avant insertion.

6. **La génération AUTO de skills nécessite un accès au LLM** — si le LLM est indisponible, logger l'erreur mais ne pas bloquer le reste du système.

7. **Backup de `skills.db`** — inclure ce fichier dans les sauvegardes Proxmox. C'est la mémoire long terme d'ADA.

8. **Keywords sans accents** — toujours stocker et rechercher sans accents pour éviter les problèmes d'encodage FTS. Utiliser `unicodedata.normalize()` si nécessaire.

---

## 14. ARBORESCENCE FINALE

```
ada/
├── skills/
│   ├── __init__.py             # Exporte les fonctions principales
│   ├── skills_db.py            # init_db(), seed_from_files(), get_connection()
│   ├── skills_manager.py       # search_skills(), search_archive(), save_skill(), etc.
│   ├── skills_injector.py      # build_system_prompt()
│   └── skills_generator.py     # generate_skill_from_conversation()
├── data/
│   └── skills.db               # Créé automatiquement
└── skills_seed/
    ├── core/
    │   ├── ada_identity.md
    │   └── ada_response_format.md
    └── domain/
        ├── opentechno.md
        ├── maison.md
        ├── uscss.md
        └── margep.md
```

---

*Fin de spec — document complet et autonome pour implémentation sans ambiguïté.*
