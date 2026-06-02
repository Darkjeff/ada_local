# Spécification complète — Skills opérationnels et AutoSkills adaptatifs pour ADA Web

## 1. Résumé exécutif

ADA doit disposer de deux couches de compétences complémentaires :

1. **Skills opérationnels** : compétences principales, stables, éditées manuellement, stockées sous forme de fichiers `skills/*/SKILL.md`. Elles constituent le socle fonctionnel et comportemental d’ADA.
2. **AutoSkills** : compétences adaptatives, générées et enrichies automatiquement à partir des discussions de chat, stockées en SQLite/FTS5, classées par priorité, domaine, statut et historique d’usage.

Le chat doit devenir le moteur d’évolution des AutoSkills : à chaque conversation pertinente, ADA doit pouvoir détecter un apprentissage réutilisable, créer une nouvelle AutoSkill ou enrichir une AutoSkill existante, puis la réutiliser dans les futures réponses.

L’objectif n’est pas de remplacer les skills existantes, mais de créer une **mémoire procédurale vivante**, organisée et exploitable.

---

## 2. Objectifs

### 2.1 Objectifs fonctionnels

- Conserver intégralement le système de skills opérationnels `SKILL.md`.
- Activer réellement les AutoSkills SQLite dans le pipeline de chat web.
- Injecter les AutoSkills pertinentes dans le prompt en complément des skills opérationnels.
- Créer automatiquement des AutoSkills depuis les conversations répétitives ou procédurales.
- Enrichir une AutoSkill existante plutôt que créer des doublons.
- Gérer les AutoSkills avec priorité, domaine, statut, historique, promotion et archivage.
- Exposer les AutoSkills dans l’interface web avec une vue dédiée.
- Ajouter des événements Radar pour diagnostiquer l’injection, la génération et l’évolution des AutoSkills.

### 2.2 Objectifs techniques

- Rester local-first.
- Minimiser l’impact sur la latence du chat.
- Éviter les créations intempestives de skills.
- Garantir l’auditabilité des créations/modifications automatiques.
- Séparer clairement :
  - skills opérationnels,
  - AutoSkills,
  - mémoire conversationnelle,
  - RAG documentaire.

---

## 3. État actuel observé

### 3.1 Skills opérationnels existants

Le système actuel `core/skill_manager.py` charge les fichiers `skills/*/SKILL.md`, avec frontmatter YAML, triggers et contenu injectable.

Ce système doit rester en place, car il représente les skills principaux d’ADA.

### 3.2 Module AutoSkills existant mais incomplet

Le dépôt contient déjà une couche `core/skills/*` avec :

- `skills_db.py` : base SQLite/FTS5, table `skills`, source `seed | manual | auto`, priorité, statut, compteurs.
- `skills_manager.py` : CRUD, recherche, promotion, archivage, maintenance.
- `skills_generator.py` : génération depuis une conversation.
- `skills_injector.py` : injection de skills SQLite dans le system prompt.

Cependant, le pipeline web actuel n’exploite pas complètement cette couche :

- il injecte les skills opérationnels via `core.skill_manager.skill_manager.inject(...)` ;
- il n’injecte pas encore les AutoSkills SQLite dans le prompt ;
- il sauvegarde les conversations en mémoire, mais ne déclenche pas la création ou l’enrichissement des AutoSkills ;
- l’interface web semble prévoir `/api/autoskills`, mais les endpoints doivent être vérifiés/complétés.

---

## 4. Terminologie

### 4.1 Skill opérationnel

Skill principal, structurant et stable.

Caractéristiques :

- Stockage : `skills/<nom>/SKILL.md`.
- Création : manuelle.
- Édition : interface ou fichier.
- Déclenchement : triggers YAML ou `always: true`.
- Rôle : donner à ADA ses capacités fondamentales.
- Priorité : haute par nature.
- Exemple : `proxmox`, `domotique`, `margepro`, `user_profile`, `programmation`.

### 4.2 AutoSkill

Skill adaptatif généré automatiquement depuis les conversations.

Caractéristiques :

- Stockage : SQLite `data/skills.db`.
- Table principale : `skills` avec `source='auto'`.
- Création : automatique ou manuelle assistée.
- Évolution : enrichissement automatique.
- Déclenchement : recherche FTS5 + domaine + priorité.
- Rôle : compléter les skills opérationnels avec l’expérience accumulée.
- Exemple : `Exploitation Proxmox OpenTechno`, `Procédure PBS`, `Préférences de réponse infrastructure`.

### 4.3 Mémoire conversationnelle

Historique brut ou consolidé des échanges.

Caractéristiques :

- Stockage : `data/memory.db`.
- Usage : contexte de fond.
- Rôle : rappeler des échanges passés.
- Ne doit pas remplacer les AutoSkills.

### 4.4 RAG documentaire

Base documentaire locale indexée.

Caractéristiques :

- Sources : fichiers Markdown ou documents montés.
- Usage : injection de sources documentaires pertinentes.
- Rôle : fournir des connaissances longues et structurées.
- Ne doit pas être mélangé avec les AutoSkills.

---

## 5. Architecture cible

### 5.1 Couches de connaissance

Ordre logique de priorité :

```text
1. System prompt de base ADA
2. Capacités plugins actifs
3. Skills opérationnels SKILL.md
4. AutoSkills SQLite pertinents
5. RAG documentaire
6. Mémoire conversationnelle passée
7. Conversation courante
8. Message utilisateur
```

### 5.2 Rôle de chaque couche

| Couche | Source | Rôle | Stabilité | Priorité |
|---|---|---|---|---|
| System ADA | code | identité, règles globales | très stable | très haute |
| Plugins | code/config | capacités actives | stable | haute |
| Skills opérationnels | `SKILL.md` | compétences principales | stable | haute |
| AutoSkills | SQLite | apprentissages adaptatifs | évolutif | variable |
| RAG documentaire | documents | connaissance source | stable/volumineux | contextuelle |
| Mémoire | SQLite | contexte historique | évolutif | faible à moyenne |

### 5.3 Flux cible simplifié

```text
Message utilisateur
   ↓
Préparation contexte
   ↓
Injection skills opérationnels
   ↓
Recherche + injection AutoSkills
   ↓
Injection RAG documentaire
   ↓
Injection mémoire conversationnelle
   ↓
Réponse LLM / tool calling
   ↓
Sauvegarde conversation
   ↓
Analyse post-réponse
   ↓
Création ou enrichissement AutoSkill
   ↓
Événements Radar + historique
```

---

## 6. Règles de cohabitation

### 6.1 Règle fondamentale

Les AutoSkills ne remplacent jamais les skills opérationnels.

Une AutoSkill doit être considérée comme une couche d’ajustement ou d’expérience, jamais comme une vérité structurelle supérieure.

### 6.2 Priorité effective

La priorité finale d’injection doit respecter :

```text
SKILL.md always
> SKILL.md déclenché par trigger
> AutoSkill priorité 1 à 3
> AutoSkill priorité 4 à 6
> AutoSkill priorité 7 à 10
> mémoire conversationnelle
```

### 6.3 Conflits

En cas de contradiction :

1. Le message utilisateur courant prévaut.
2. Les règles système ADA prévalent.
3. Les skills opérationnels prévalent sur les AutoSkills.
4. Les AutoSkills récentes et mieux priorisées prévalent sur les AutoSkills anciennes.
5. Les documents RAG sourcés prévalent pour les faits documentaires.

### 6.4 Domaines

Les AutoSkills doivent être associées à un domaine :

- `core` : connaissances générales ADA.
- `auto` : domaine par défaut.
- `home` : domotique / maison.
- `opent` : OpenTechno / infrastructure.
- `margep` : MargePro.
- `societe` ou `company_id` : contexte société.
- Tout `context_id` actif transmis par le pipeline.

---

## 7. Modèle de données

### 7.1 Table existante `skills`

La table existante doit rester la base principale des AutoSkills.

Champs clés :

```sql
id TEXT PRIMARY KEY,
name TEXT NOT NULL,
domain TEXT NOT NULL DEFAULT 'core',
source TEXT NOT NULL DEFAULT 'manual',
content TEXT NOT NULL,
summary TEXT,
priority INTEGER NOT NULL DEFAULT 5,
status TEXT NOT NULL DEFAULT 'active',
success_count INTEGER NOT NULL DEFAULT 0,
usage_count INTEGER NOT NULL DEFAULT 0,
last_used TEXT,
created_at TEXT NOT NULL DEFAULT (datetime('now')),
updated_at TEXT NOT NULL DEFAULT (datetime('now'))
```

Pour les AutoSkills :

```sql
source = 'auto'
```

### 7.2 Nouvelle table recommandée `autoskill_observations`

But : conserver les observations conversationnelles qui ont servi à créer ou enrichir une AutoSkill.

```sql
CREATE TABLE IF NOT EXISTS autoskill_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id TEXT,
    session_id TEXT NOT NULL,
    domain TEXT,
    user_text TEXT NOT NULL,
    assistant_text TEXT NOT NULL,
    extracted_summary TEXT,
    confidence REAL NOT NULL DEFAULT 0,
    action TEXT NOT NULL, -- 'created' | 'updated' | 'skipped' | 'candidate'
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### 7.3 Nouvelle table recommandée `autoskill_feedback`

But : stocker les retours explicites ou implicites.

```sql
CREATE TABLE IF NOT EXISTS autoskill_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id TEXT NOT NULL,
    session_id TEXT,
    request_id TEXT,
    feedback TEXT NOT NULL, -- 'positive' | 'negative' | 'neutral'
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### 7.4 Nouvelle table recommandée `autoskill_injections`

But : tracer quand une AutoSkill est injectée.

```sql
CREATE TABLE IF NOT EXISTS autoskill_injections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id TEXT NOT NULL,
    session_id TEXT,
    request_id TEXT,
    query TEXT NOT NULL,
    domain TEXT,
    score REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### 7.5 Utilisation de `skills_history`

La table existante `skills_history` doit continuer à tracer :

- `save`
- `auto_create`
- `auto_update`
- `auto_merge`
- `auto_promote`
- `archive`
- `restore`
- `feedback_positive`
- `feedback_negative`

---

## 8. Paramètres de configuration

Ajouter dans `DEFAULT_SETTINGS` :

```python
"autoskills": {
    "enabled": True,
    "inject_enabled": True,
    "generate_enabled": True,
    "update_enabled": True,
    "min_turns": 4,
    "min_content_len": 100,
    "min_confidence": 0.62,
    "max_injected": 5,
    "max_generation_history": 20,
    "cooldown_minutes": 10,
    "default_domain": "auto",
    "allow_core_domain_auto_write": False,
    "archive_after_days": 30,
    "auto_promote_threshold": 2,
    "generation_model": "",
    "merge_model": "",
    "debug": False
}
```

Règles :

- `generation_model` vide signifie utiliser le modèle de chat courant.
- `allow_core_domain_auto_write=False` évite de polluer le domaine `core`.
- Le domaine `core` doit rester principalement réservé aux seeds et aux skills structurantes.

---

## 9. Injection des AutoSkills dans le pipeline

### 9.1 Emplacement

Dans `web/pipeline.py`, après :

```python
messages = skill_manager.inject(messages, user_text)
```

Ajouter l’injection AutoSkills SQLite.

### 9.2 Helper proposé

Créer `core/skills/autoskills_runtime.py`.

Responsabilités :

- `inject_autoskills(messages, query, domain, request_id, session_id)`
- `maybe_update_autoskill(history, user_text, assistant_text, domain, request_id, session_id)`
- `record_injected_usage(skill_ids, request_id, session_id)`

### 9.3 Pseudo-code injection

```python
def inject_autoskills(messages, query, domain=None, request_id=None, session_id=None):
    from core.settings_store import settings
    if not settings.get("autoskills.enabled", True):
        return messages, {"skills_injected": [], "skills_count": 0}
    if not settings.get("autoskills.inject_enabled", True):
        return messages, {"skills_injected": [], "skills_count": 0}

    from core.skills.skills_injector import build_system_prompt

    base_prompt = messages[0]["content"] if messages and messages[0].get("role") == "system" else ""
    max_skills = settings.get("autoskills.max_injected", 5)

    final_prompt, meta = build_system_prompt(
        base_prompt=base_prompt,
        query=query,
        active_domain=domain,
        max_skills=max_skills,
    )

    if messages and messages[0].get("role") == "system":
        messages[0] = {"role": "system", "content": final_prompt}
    else:
        messages.insert(0, {"role": "system", "content": final_prompt})

    return messages, meta
```

### 9.4 Métadonnées à conserver

Le pipeline doit conserver les IDs injectés :

```python
_autoskill_meta = {
    "skills_injected": [...],
    "skills_count": 2,
    "domain": "opent"
}
```

Ces IDs serviront à :

- tracer l’injection ;
- incrémenter `usage_count` ;
- permettre un feedback utilisateur ;
- détecter quelles AutoSkills ont influencé une réponse.

---

## 10. Création et enrichissement automatique

### 10.1 Emplacement

Après la production de la réponse et après sauvegarde en mémoire :

```python
memory_store.save(session_id, "user", user_text)
memory_store.save(session_id, "assistant", response)
```

Ajouter :

```python
await maybe_update_autoskill(
    history=history,
    user_text=user_text,
    assistant_text=response,
    domain=_effective_ctx or plugin_context or "auto",
    request_id=_req_id,
    session_id=session_id,
)
```

### 10.2 Détection

Ne pas générer une AutoSkill sur chaque message.

Déclencheurs possibles :

- plusieurs échanges sur un même sujet ;
- présence de procédures ;
- répétition de questions similaires ;
- corrections ou préférences explicites de l’utilisateur ;
- configuration locale ;
- usage d’un domaine/plugin identifiable ;
- réponse contenant des étapes, commandes, règles ou conventions.

### 10.3 Scoring recommandé

Créer une fonction :

```python
def score_autoskill_candidate(conversation, user_text, assistant_text, domain=None) -> dict:
    return {
        "score": 0.0,
        "topic": "",
        "reasons": [],
        "should_generate": False,
    }
```

Critères :

| Signal | Points |
|---|---:|
| Au moins 4 tours user/assistant | +0.20 |
| Mots procéduraux : procédure, étape, configurer, installer, résoudre | +0.15 |
| Répétition d’un domaine/plugin | +0.20 |
| Contient commandes, routes API ou paramètres techniques | +0.15 |
| L’utilisateur corrige ou précise une règle | +0.15 |
| Sujet déjà vu dans mémoire récente | +0.10 |
| Réponse assistant structurée en actions | +0.10 |
| Contient secrets/tokens/mots de passe | -1.00 |
| Conversation trop courte ou bavardage | -0.50 |

Seuil recommandé :

```text
score >= 0.62 → génération ou enrichissement
```

### 10.4 Recherche d’une AutoSkill existante

Avant création, rechercher une AutoSkill proche :

```sql
SELECT * FROM skills
WHERE source='auto'
  AND status='active'
  AND (domain=? OR domain='auto')
  AND skills_fts MATCH ?
ORDER BY priority ASC, bm25(skills_fts) ASC
LIMIT 5;
```

Règle :

- Si une AutoSkill proche existe : enrichir.
- Sinon : créer.

### 10.5 Création

Créer une AutoSkill avec :

```python
save_skill(
    skill_id="auto_<hash>",
    name="...",
    summary="...",
    content="...",
    domain=domain,
    source="auto",
    priority=5,
)
```

### 10.6 Enrichissement

Enrichir signifie :

- conserver les règles déjà présentes ;
- ajouter les nouvelles procédures ;
- corriger les informations obsolètes ;
- fusionner les doublons ;
- ne pas écraser une AutoSkill avec une conversation faible.

Le LLM doit recevoir :

```text
AutoSkill existante
+ conversation récente
+ objectif : fusionner en une version meilleure
+ format JSON strict
```

---

## 11. Prompts LLM recommandés

### 11.1 Prompt de génération

```text
Tu es un extracteur de compétences procédurales pour ADA.
Analyse la conversation et détermine s’il existe une connaissance réutilisable.

Tu dois produire une AutoSkill concise, opérationnelle et exploitable.
Ne stocke jamais de secret, token, mot de passe, clé API ou donnée sensible.
Si la conversation ne justifie pas d’AutoSkill, réponds avec {"action":"skip"}.

Réponds uniquement en JSON strict :
{
  "action": "create" | "skip",
  "name": "titre court",
  "summary": "résumé en une phrase",
  "domain": "domaine",
  "content": "contenu complet de la skill",
  "confidence": 0.0,
  "triggers": ["mot1", "mot2"]
}
```

### 11.2 Prompt d’enrichissement

```text
Tu es chargé de maintenir une AutoSkill ADA.
Fusionne l’AutoSkill existante avec les nouveaux apprentissages de la conversation.

Contraintes :
- conserve ce qui est toujours vrai ;
- ajoute les nouvelles règles utiles ;
- supprime les doublons ;
- marque les incertitudes ;
- ne stocke aucun secret ;
- ne transforme pas la skill en historique de conversation ;
- écris une skill directement exploitable.

Réponds uniquement en JSON strict :
{
  "action": "update" | "skip",
  "name": "titre court",
  "summary": "résumé mis à jour",
  "content": "contenu fusionné",
  "confidence": 0.0,
  "change_summary": "ce qui a changé"
}
```

### 11.3 Format conseillé du contenu AutoSkill

```markdown
## Objectif
Décrire ce que cette AutoSkill aide ADA à faire.

## Contexte
Domaine, client, système ou contexte concerné.

## Règles de réponse
- Règle 1
- Règle 2

## Procédures connues
### Procédure A
1. Étape
2. Étape

## Points de vigilance
- Confirmation obligatoire pour actions destructives.
- Ne jamais exposer de secrets.

## Exemples de formulations utilisateur
- "..."
- "..."
```

---

## 12. Gestion de la priorité

### 12.1 Valeurs

| Priorité | Signification |
|---:|---|
| 1 | Critique / toujours prioritaire |
| 2 | Très important |
| 3 | Protégé / quasi permanent |
| 4 | AutoSkill fortement utile |
| 5 | AutoSkill normale nouvellement créée |
| 6-7 | AutoSkill secondaire |
| 8-10 | Rare / faible priorité |

### 12.2 Création

Toute nouvelle AutoSkill doit commencer à :

```text
priority = 5
```

### 12.3 Promotion

Promouvoir automatiquement si :

- l’AutoSkill est injectée plusieurs fois ;
- le feedback est positif ;
- le même domaine revient souvent ;
- elle produit une réponse utile.

Règle minimale :

```text
success_count >= 2 et priority == 4 → priority = 3
```

La priorité 3 protège contre l’archivage automatique.

### 12.4 Dépromotion

Dépromouvoir si :

- feedback négatif ;
- contradiction détectée ;
- absence d’utilisation prolongée ;
- contenu trop générique.

### 12.5 Archivage

Archiver automatiquement les AutoSkills :

- `source='auto'`,
- `status='active'`,
- `priority > 3`,
- non utilisées depuis `archive_after_days`,
- non modifiées depuis `archive_after_days`.

---

## 13. API Web AutoSkills

Créer ou compléter les endpoints suivants.

### 13.1 Liste

```http
GET /api/autoskills?status=active&domain=opent
```

Réponse :

```json
{
  "count": 2,
  "skills": [
    {
      "id": "auto_xxx",
      "name": "Exploitation Proxmox OpenTechno",
      "domain": "opent",
      "source": "auto",
      "summary": "...",
      "priority": 5,
      "status": "active",
      "usage_count": 3,
      "success_count": 1,
      "last_used": "...",
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

### 13.2 Détail

```http
GET /api/autoskills/{skill_id}
```

Inclure :

- contenu complet ;
- historique ;
- injections récentes ;
- observations ;
- feedback.

### 13.3 Création manuelle

```http
POST /api/autoskills
```

Body :

```json
{
  "name": "...",
  "domain": "opent",
  "summary": "...",
  "content": "...",
  "priority": 5
}
```

### 13.4 Mise à jour

```http
PATCH /api/autoskills/{skill_id}
```

Body partiel :

```json
{
  "name": "...",
  "summary": "...",
  "content": "...",
  "priority": 4,
  "domain": "opent"
}
```

### 13.5 Archivage

```http
PATCH /api/autoskills/{skill_id}/archive
```

### 13.6 Restauration

```http
PATCH /api/autoskills/{skill_id}/restore
```

### 13.7 Promotion

```http
PATCH /api/autoskills/{skill_id}/promote
```

### 13.8 Suppression

```http
DELETE /api/autoskills/{skill_id}
```

Règle : refuser suppression si `priority <= 3`, sauf paramètre admin explicite.

### 13.9 Feedback

```http
POST /api/autoskills/{skill_id}/feedback
```

Body :

```json
{
  "feedback": "positive",
  "reason": "réponse pertinente",
  "request_id": "req_xxx"
}
```

### 13.10 Maintenance

```http
POST /api/autoskills/maintenance
```

---

## 14. Interface utilisateur

### 14.1 Vue Compétences

Séparer clairement trois onglets :

1. **Skills opérationnels**
   - source : `SKILL.md`
   - édition manuelle
   - triggers
   - always

2. **AutoSkills actifs**
   - source : SQLite `source='auto'`
   - priorité
   - domaine
   - usage
   - succès
   - contenu
   - historique
   - actions : voir, éditer, promouvoir, archiver, supprimer

3. **AutoSkills archivés**
   - restauration
   - suppression si autorisée

### 14.2 Fiche AutoSkill

Afficher :

- titre ;
- domaine ;
- résumé ;
- contenu complet ;
- priorité ;
- statut ;
- nombre d’utilisations ;
- nombre de succès ;
- dernière utilisation ;
- dernières modifications ;
- conversations ayant contribué ;
- actions possibles.

### 14.3 Indicateur dans le chat

Optionnel, en mode debug :

```text
AutoSkills injectées : Proxmox PBS, Procédures backups
```

Ne pas afficher par défaut pour ne pas polluer l’expérience.

---

## 15. Événements Radar

Ajouter des événements pour rendre le système observable.

### 15.1 Injection

```text
autoskills.search.started
autoskills.search.completed
autoskills.injected
autoskills.context.empty
```

Metadata :

```json
{
  "query_preview": "...",
  "domain": "opent",
  "skills_count": 2,
  "skill_ids": ["auto_xxx"]
}
```

### 15.2 Génération

```text
autoskills.generation.started
autoskills.generation.skipped
autoskills.generation.created
autoskills.generation.updated
autoskills.generation.error
```

Metadata :

```json
{
  "domain": "opent",
  "score": 0.78,
  "action": "updated",
  "skill_id": "auto_xxx",
  "reason": "repeated procedural Proxmox discussion"
}
```

### 15.3 Maintenance

```text
autoskills.maintenance.started
autoskills.maintenance.completed
```

---

## 16. Sécurité et confidentialité

### 16.1 Données interdites dans une AutoSkill

Ne jamais stocker automatiquement :

- mots de passe ;
- tokens API ;
- secrets ;
- cookies ;
- clés privées ;
- valeurs d’authentification ;
- informations personnelles sensibles non nécessaires.

### 16.2 Sanitization

Avant génération ou sauvegarde, appliquer une fonction :

```python
def sanitize_autoskill_text(text: str) -> str:
    # masquer tokens, Authorization, password, secret, api_key, cookie, private_key, etc.
    return sanitized
```

Réutiliser la logique Radar si elle existe déjà pour masquer les champs sensibles.

### 16.3 Actions dangereuses

Les AutoSkills peuvent mémoriser des règles, mais ne doivent pas supprimer les confirmations obligatoires.

Pour Proxmox par exemple :

- reboot node ;
- stop VM ;
- restore backup ;
- delete snapshot ;
- poweroff ;
- modification réseau.

Ces actions doivent toujours demander confirmation, même si une AutoSkill dit qu’elles sont fréquentes.

---

## 17. Implémentation technique recommandée

### 17.1 Nouveau fichier `core/skills/autoskills_runtime.py`

Contenu recommandé :

```python
from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

from core.settings_store import settings
from core.skills.skills_manager import (
    search_skills,
    save_skill,
    record_success,
)
from core.skills.skills_generator import (
    should_generate_skill,
    generate_skill_from_conversation,
)
from core.skills.skills_injector import build_system_prompt

logger = logging.getLogger(__name__)


def normalize_autoskill_domain(domain: Optional[str]) -> str:
    if not domain:
        return settings.get("autoskills.default_domain", "auto")
    if domain == "core" and not settings.get("autoskills.allow_core_domain_auto_write", False):
        return settings.get("autoskills.default_domain", "auto")
    return domain


def inject_autoskills(messages, query: str, domain: Optional[str], request_id: str = "", session_id: str = ""):
    if not settings.get("autoskills.enabled", True):
        return messages, {"skills_injected": [], "skills_count": 0, "domain": domain}
    if not settings.get("autoskills.inject_enabled", True):
        return messages, {"skills_injected": [], "skills_count": 0, "domain": domain}

    domain = normalize_autoskill_domain(domain)
    max_skills = settings.get("autoskills.max_injected", 5)

    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": ""})

    final_prompt, meta = build_system_prompt(
        base_prompt=messages[0]["content"],
        query=query,
        active_domain=domain,
        max_skills=max_skills,
    )
    messages[0] = {"role": "system", "content": final_prompt}

    # TODO: insert into autoskill_injections
    return messages, meta


class RuntimeLLMClient:
    def __init__(self, call_llm):
        self._call_llm = call_llm

    async def chat(self, messages: list[dict]) -> str:
        return await self._call_llm(messages, thinking=False)


async def maybe_update_autoskill(
    history: list[dict],
    user_text: str,
    assistant_text: str,
    domain: Optional[str],
    request_id: str,
    session_id: str,
    call_llm,
) -> Optional[str]:
    if not settings.get("autoskills.enabled", True):
        return None
    if not settings.get("autoskills.generate_enabled", True):
        return None

    domain = normalize_autoskill_domain(domain)

    conversation = [
        m for m in history[-settings.get("autoskills.max_generation_history", 20):]
        if m.get("role") in ("user", "assistant")
    ]
    conversation.append({"role": "user", "content": user_text})
    conversation.append({"role": "assistant", "content": assistant_text})

    if not should_generate_skill(conversation):
        return None

    # Identifiant stable basé sur domaine + sujet récent.
    raw_key = domain + "\n" + "\n".join(m.get("content", "")[:500] for m in conversation[-8:])
    skill_id = "auto_" + hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:10]

    llm_client = RuntimeLLMClient(call_llm)
    generated = await generate_skill_from_conversation(
        skill_id=skill_id,
        history=conversation,
        llm_client=llm_client,
        domain=domain,
    )
    if not generated:
        return None

    save_skill(
        skill_id=generated["id"],
        name=generated["name"],
        content=generated["content"],
        summary=generated.get("summary", ""),
        domain=generated.get("domain", domain),
        source="auto",
        priority=generated.get("priority", 5),
    )

    return generated["id"]
```

Cette version minimale crée des AutoSkills. Une version complète doit aussi rechercher une AutoSkill existante et fusionner.

### 17.2 Modification `web/pipeline.py`

Après injection des skills opérationnels :

```python
messages = skill_manager.inject(messages, user_text)

try:
    from core.skills.autoskills_runtime import inject_autoskills
    messages, _autoskill_meta = inject_autoskills(
        messages,
        query=user_text,
        domain=_effective_ctx or plugin_context or "auto",
        request_id=_req_id,
        session_id=session_id,
    )
except Exception:
    _autoskill_meta = {"skills_injected": [], "skills_count": 0}
```

Après sauvegarde de la réponse :

```python
try:
    from core.skills.autoskills_runtime import maybe_update_autoskill
    await maybe_update_autoskill(
        history=history,
        user_text=user_text,
        assistant_text=response,
        domain=_effective_ctx or plugin_context or "auto",
        request_id=_req_id,
        session_id=session_id,
        call_llm=_call_llm,
    )
except Exception as exc:
    # ne jamais casser le chat pour une erreur AutoSkill
    pass
```

Même logique pour la branche streaming avec `full_response`.

---

## 18. Évolution intelligente : enrichir plutôt que dupliquer

La version minimale ci-dessus crée une AutoSkill. La version cible doit enrichir une AutoSkill existante.

### 18.1 Recherche existante

```python
def find_existing_autoskill(topic_text: str, domain: str) -> dict | None:
    rows = search_skills(topic_text, active_domain=domain, limit=5)
    candidates = [r for r in rows if r.get("source") == "auto"]
    return candidates[0] if candidates else None
```

### 18.2 Fusion

Si `existing` existe :

```python
merged = await merge_autoskill_with_conversation(
    existing_skill=existing,
    conversation=conversation,
    llm_client=llm_client,
)
```

Puis :

```python
save_skill(
    skill_id=existing["id"],
    name=merged["name"],
    content=merged["content"],
    summary=merged["summary"],
    domain=existing["domain"],
    source="auto",
    priority=existing["priority"],
)
```

### 18.3 Historisation

Chaque fusion doit ajouter une entrée :

```text
skills_history.action = 'auto_merge'
skills_history.detail = change_summary
```

---

## 19. Exemple attendu : Proxmox

Après plusieurs échanges sur Proxmox/PBS, ADA doit produire une AutoSkill proche de :

```markdown
# Exploitation Proxmox / PBS OpenTechno

## Objectif
Aider ADA à répondre aux demandes récurrentes liées à l’infrastructure Proxmox et PBS du contexte OpenTechno.

## Contexte
Domaine : opent.
Les demandes concernent principalement les instances Proxmox, les VMs, les nodes, les snapshots, les backups et PBS.

## Règles de réponse
- Répondre en français.
- Être concis pour les états simples.
- Demander confirmation avant toute action destructive.
- Si plusieurs instances sont disponibles, demander laquelle utiliser.

## Actions sensibles
Toujours demander confirmation avant :
- arrêt ou reboot de VM ;
- reboot de node ;
- restauration de backup ;
- suppression de snapshot ;
- lancement d’un backup impactant.

## Requêtes typiques
- "Liste les VMs"
- "État du PBS"
- "Dernier backup réussi"
- "Espace disque datastores"
```

---

## 20. Tests

### 20.1 Tests unitaires

Créer :

```text
tests/test_autoskills_runtime.py
tests/test_autoskills_api.py
tests/test_autoskills_generation.py
tests/test_autoskills_injection.py
```

### 20.2 Cas de test : injection

1. Créer une AutoSkill `source='auto'`, domaine `opent`, contenu contenant `PBS`.
2. Envoyer une question `Quel est l’état du PBS ?`.
3. Vérifier que l’AutoSkill est injectée dans le prompt.
4. Vérifier que `usage_count` augmente.

### 20.3 Cas de test : création

1. Simuler 4 échanges sur Proxmox.
2. Appeler `maybe_update_autoskill`.
3. Vérifier qu’une entrée `source='auto'` est créée.
4. Vérifier `domain='opent'`.
5. Vérifier `priority=5`.

### 20.4 Cas de test : enrichissement

1. Créer une AutoSkill Proxmox existante.
2. Simuler une nouvelle conversation sur PBS.
3. Appeler `maybe_update_autoskill`.
4. Vérifier qu’aucun doublon n’est créé.
5. Vérifier que le contenu existant est enrichi.

### 20.5 Cas de test : sécurité

1. Conversation contenant `token_value`, `password`, `Authorization`.
2. Appeler génération.
3. Vérifier que le secret est absent du contenu sauvegardé.

### 20.6 Cas de test : archivage

1. AutoSkill `source='auto'`, `priority=5`, non utilisée depuis 31 jours.
2. Lancer maintenance.
3. Vérifier `status='archived'`.

### 20.7 Cas de test : protection

1. AutoSkill `priority=3`.
2. Lancer maintenance.
3. Vérifier qu’elle reste active.

---

## 21. Plan d’implémentation

### Phase 1 — Stabiliser le modèle

- Valider que les skills opérationnels restent dans `core/skill_manager.py`.
- Valider que les AutoSkills restent dans `core/skills/*`.
- Ajouter la configuration `autoskills` dans `settings_store.py`.

### Phase 2 — API AutoSkills

- Ajouter les endpoints `/api/autoskills`.
- Brancher liste, détail, création, édition, archive, restore, promote, delete, feedback.
- Vérifier que l’UI existante consomme bien ces endpoints.

### Phase 3 — Injection runtime

- Créer `core/skills/autoskills_runtime.py`.
- Ajouter `inject_autoskills` dans `web/pipeline.py` après les skills opérationnels.
- Ajouter événements Radar.

### Phase 4 — Génération minimale

- Ajouter `maybe_update_autoskill` après sauvegarde de réponse.
- Créer une AutoSkill si conversation qualifiée.
- Ne pas encore fusionner, ou fusion simple par ID stable.

### Phase 5 — Fusion intelligente

- Ajouter recherche d’AutoSkill existante.
- Ajouter prompt de merge.
- Éviter les doublons.
- Historiser les modifications.

### Phase 6 — Feedback et promotion

- Ajouter feedback chat/UI.
- Relier feedback positif à `record_success`.
- Dépromotion ou archivage en cas de feedback négatif.

### Phase 7 — Tests et observabilité

- Tests unitaires.
- Tests intégration pipeline.
- Logs Radar.
- Vue debug dans l’UI.

---

## 22. Critères d’acceptation

Le système est considéré fonctionnel si :

1. Les skills opérationnels `SKILL.md` continuent de fonctionner sans régression.
2. Une AutoSkill manuelle SQLite peut être injectée dans le chat.
3. Après une conversation procédurale répétée, une AutoSkill `source='auto'` est créée.
4. Une conversation ultérieure sur le même thème injecte cette AutoSkill.
5. Une nouvelle conversation sur le même thème enrichit l’AutoSkill au lieu de créer un doublon.
6. L’UI affiche séparément : skills opérationnels, AutoSkills actifs, AutoSkills archivés.
7. Les événements Radar permettent de voir : recherche, injection, création, mise à jour, skip, erreur.
8. Aucun secret évident n’est sauvegardé dans une AutoSkill.
9. Les actions dangereuses restent soumises à confirmation.
10. Une erreur AutoSkill ne casse jamais la réponse chat.

---

## 23. Points de vigilance

### 23.1 Risque de pollution

Sans seuil strict, ADA pourrait créer trop d’AutoSkills. Il faut donc :

- seuil de confiance ;
- cooldown ;
- fusion avant création ;
- archivage automatique ;
- UI de contrôle.

### 23.2 Risque de doublons

Le système doit toujours rechercher une AutoSkill existante avant création.

### 23.3 Risque de sur-injection

Limiter à `max_injected=5`, idéalement moins selon longueur.

### 23.4 Risque de conflit avec SKILL.md

Les skills opérationnels doivent rester prioritaires.

### 23.5 Risque de fuite de secrets

La sanitization est obligatoire avant sauvegarde.

---

## 24. Tâches concrètes pour un agent de développement

### Tâche A — Configuration

Modifier `core/settings_store.py` pour ajouter le bloc `autoskills` dans `DEFAULT_SETTINGS`.

### Tâche B — Runtime

Créer `core/skills/autoskills_runtime.py` avec :

- `normalize_autoskill_domain`
- `inject_autoskills`
- `maybe_update_autoskill`
- `find_existing_autoskill`
- `merge_autoskill_with_conversation`
- `sanitize_autoskill_text`

### Tâche C — Pipeline

Modifier `web/pipeline.py` :

- injection AutoSkills après `skill_manager.inject` ;
- génération/enrichissement après sauvegarde réponse ;
- événements Radar ;
- non-blocage en cas d’erreur.

### Tâche D — API

Modifier `web/server.py` ou créer `web/router_autoskills.py`.

Endpoints :

- `GET /api/autoskills`
- `GET /api/autoskills/{id}`
- `POST /api/autoskills`
- `PATCH /api/autoskills/{id}`
- `PATCH /api/autoskills/{id}/archive`
- `PATCH /api/autoskills/{id}/restore`
- `PATCH /api/autoskills/{id}/promote`
- `DELETE /api/autoskills/{id}`
- `POST /api/autoskills/{id}/feedback`
- `POST /api/autoskills/maintenance`

### Tâche E — UI

Adapter `web/static/views/skills/index.js` pour :

- garder l’onglet `Skills opérationnels` alimenté par `/api/page/skills` ;
- utiliser `/api/autoskills` pour les AutoSkills ;
- afficher priorité, domaine, source, statut, compteurs ;
- permettre édition et archivage.

### Tâche F — Tests

Ajouter tests unitaires et intégration.

### Tâche G — Documentation

Créer `docs/ADA_AUTOSKILLS_SPEC.md` avec cette spécification et un guide d’exploitation.

---

## 25. Conclusion

La bonne architecture ADA est :

```text
Skills opérationnels = socle stable.
AutoSkills = expérience adaptative.
Chat = moteur d’apprentissage.
SQLite/FTS5 = mémoire procédurale structurée.
Radar = observabilité.
UI = contrôle humain.
```

Le système ne doit pas simplement stocker des conversations : il doit extraire, condenser, fusionner, prioriser et réutiliser les apprentissages utiles.

La priorité immédiate est donc de câbler les AutoSkills dans `web/pipeline.py` :

1. avant réponse : injection AutoSkills ;
2. après réponse : création/enrichissement AutoSkills.

Une fois ce câblage en place, ADA pourra réellement apprendre progressivement des usages récurrents, notamment sur Proxmox, PBS, les pratiques OpenTechno et les procédures métier.
