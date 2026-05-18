# Semantic Router — Design Spec

**Date:** 2026-05-15  
**Projet:** ADA — Phase 1 de l'évolution multi-agents  
**Statut:** Approuvé

---

## Objectif

Remplacer le `semantic_router.py` actuel (keyword-overlap classifier) par un routeur basé sur des embeddings sémantiques via Ollama, tout en conservant une interface publique identique et un fallback transparent vers l'ancienne logique.

---

## Contexte

### Système actuel

`core/semantic_router.py` utilise un score de chevauchement de tokens pour router les messages vers 7 routes :

| Route | Usage |
|---|---|
| `qwen_basic` | Chat simple, salutations, questions rapides |
| `qwen_thinking` | Raisonnement, code, analyse |
| `function_gemma` | Actions : lumières, timer, calendrier, etc. |
| `cad_generation` | Génération de modèles 3D |
| `print_control` | Contrôle d'imprimantes 3D |
| `vision` | Webcam / analyse d'images |
| `youtube` | Transcription et résumé YouTube |

**Problème :** "éteins la lumière" route correctement, mais "désactive l'éclairage du bureau" échoue car aucun token ne matche les utterances de `function_gemma`. La précision est dégradée sur les paraphrases et le français naturel.

### Contrainte critique

Un précédent système ML (`FunctionGemmaRouter` avec `transformers`/`loky`) a été désactivé à cause de fuites de sémaphores POSIX et d'un segfault au shutdown sur Ubuntu. Toute nouvelle dépendance ML doit éviter ce stack.

**Solution retenue :** embeddings via l'API HTTP Ollama (`nomic-embed-text`) — zéro nouvelle dépendance ML Python, aucun processus loky.

---

## Architecture

### Structure du module

```
core/semantic_router.py
│
├── EmbeddingRouter                     ← nouveau cœur sémantique
│   ├── _cache: dict[str, np.ndarray]  # utterances pré-calculées (route → matrice)
│   ├── _lock: threading.Lock          # thread-safety init cache
│   ├── _last_retry: float             # cooldown retry si Ollama down
│   ├── _ensure_cache()                # init lazy, idempotent
│   ├── _embed(text) → np.ndarray      # appel POST /api/embeddings
│   ├── _best_route(vec) → (str,float) # cosine similarity contre cache
│   └── route(prompt) → str            # méthode principale
│
├── _KeywordRouter                      ← ancienne logique renommée, intacte
│   └── get_route(prompt) → str
│
└── get_route(prompt: str) → str        ← interface publique (inchangée)
    ├── délègue à EmbeddingRouter
    └── fallback → _KeywordRouter si erreur
```

### Fichiers touchés

| Fichier | Action |
|---|---|
| `core/semantic_router.py` | Réécriture complète (interface publique préservée) |
| `tests/test_semantic_router.py` | Nouveau fichier (12 tests) |
| `requirements.txt` | Ajout `numpy>=1.24` si absent |

**Aucun autre fichier modifié.** `voice_assistant.py`, `handlers.py`, et tout autre appelant de `get_route()` restent intacts.

---

## Flux de données

```
get_route("éteins la lumière du bureau")
          │
          ▼
    EmbeddingRouter.route()
          │
          ├─ _ensure_cache()  [lazy, une seule fois, thread-safe]
          │   ├─ Ollama OK  → calcule embeddings des utterances → stocke en cache
          │   └─ Ollama KO  → cache vide, fallback keyword silencieux
          │
          ├─ Ollama disponible ?
          │   YES → POST /api/embeddings {"model":"nomic-embed-text","prompt":"..."}
          │               ↓ vecteur float32[768]
          │         _best_route(query_vec)
          │               ↓ mean cosine similarity par route
          │         score >= 0.45 → return "function_gemma"
          │         score <  0.45 → return "qwen_basic"
          │
          └─ NO (ConnectionError / timeout) → _KeywordRouter.get_route(prompt)
```

### Calcul de similarité

Pour chaque route, le score est la **mean cosine similarity** entre le vecteur de la requête et la matrice d'utterances de la route :

```python
scores[route] = mean(cosine(query_vec, utterance_matrix))
```

La route avec le score moyen le plus élevé gagne, si ce score dépasse le seuil de confiance.

---

## Modèle d'embedding

**Modèle :** `nomic-embed-text`  
**Dimension vecteur :** 768  
**Taille :** ~274 MB  
**Installation :** `ollama pull nomic-embed-text`  
**Endpoint :** `POST http://localhost:11434/api/embeddings`

Le modèle est multilingue (français/anglais). Il est déjà utilisé comme standard embedding dans l'écosystème Ollama.

---

## Initialisation

**Stratégie : lazy au premier appel** (pas au démarrage d'ADA).

Raison : Ollama peut ne pas être prêt quand ADA démarre. L'init lazy évite tout blocage au boot.

```
Premier get_route() appelé
    → _ensure_cache() [protected by threading.Lock]
        → Ollama up ? → calcule N_routes × N_utterances embeddings (~2s)
                         log: "[SemanticRouter] cache prêt (7 routes, 68 utterances)"
        → Ollama KO  → cache vide
                         log: "WARNING [SemanticRouter] Ollama indisponible, mode keyword actif"
    → route() procède normalement
```

**Retry cooldown :** si le cache est vide (Ollama était down), chaque appel re-tente `_ensure_cache()` avec un cooldown de **30 secondes** pour éviter de spammer l'API.

---

## Gestion d'erreurs

| Situation | Comportement | Log niveau |
|---|---|---|
| Ollama down au démarrage | Cache vide → keyword fallback | WARNING |
| Ollama timeout sur query embed | `except` → keyword fallback | WARNING |
| Score < seuil de confiance | Return `qwen_basic` | silent |
| Prompt vide ou None | Return `qwen_basic` | silent |
| Exception inattendue | Return `qwen_basic` | ERROR |

**Invariant :** `get_route()` ne lève jamais d'exception. Comportement identique à l'actuel.

---

## Configuration

Paramètres ajoutés dans `core/settings_store.py` (bloc `semantic_router`) :

```python
"semantic_router": {
    "embedding_model": "nomic-embed-text",
    "confidence_threshold": 0.45,
    "embed_timeout_s": 5.0,
    "retry_cooldown_s": 30.0,
}
```

---

## Thread Safety

`get_route()` est appelé depuis des QThread séparés (`voice_assistant.py`, `handlers.py`).

- `_ensure_cache()` est protégé par `threading.Lock` — une seule initialisation
- `_embed()` instancie un client Ollama par appel (pas de singleton partagé) — safe
- Le cache `_cache` est en lecture seule après initialisation — safe

---

## Tests (12 tests)

**Fichier :** `tests/test_semantic_router.py`  
**Stratégie :** `ollama.Client.embeddings()` mocké via `unittest.mock.patch` — aucun Ollama réel requis.

### TestEmbeddingRouter (7 tests)

| Test | Vérifie |
|---|---|
| `test_known_route_function_gemma` | Vecteur proche des utterances function_gemma → "function_gemma" |
| `test_known_route_vision` | Vecteur proche vision → "vision" |
| `test_known_route_youtube` | Vecteur proche youtube → "youtube" |
| `test_known_route_cad` | Vecteur proche cad → "cad_generation" |
| `test_score_below_threshold_returns_default` | Vecteur orthogonal → "qwen_basic" |
| `test_empty_prompt_returns_default` | `""` → "qwen_basic" |
| `test_cache_built_once` | `_embed()` appelé N_utterances fois à l'init, pas à chaque `route()` |

### TestFallback (3 tests)

| Test | Vérifie |
|---|---|
| `test_ollama_down_uses_keyword_fallback` | `ConnectionError` → résultat keyword |
| `test_ollama_timeout_uses_keyword_fallback` | `TimeoutError` → résultat keyword |
| `test_retry_cooldown_respected` | Pas de retry avant 30s si Ollama down |

### TestIntegration (2 tests)

| Test | Vérifie |
|---|---|
| `test_same_interface` | `get_route()` retourne toujours une des 7 routes valides |
| `test_thread_safety` | 10 threads concurrents → aucune exception, résultats valides |

---

## Dépendances

| Paquet | Déjà présent ? | Rôle |
|---|---|---|
| `ollama` | Oui | Client HTTP Ollama |
| `numpy>=1.24` | Probable (via transformers) | Cosine similarity matricielle |

Si `numpy` absent : ajouter à `requirements.txt`.

---

## Non-périmètre (hors scope)

- `SkillManager` et ses keyword-triggers : **inchangés**
- `FunctionGemmaRouter` (9 fonctions) : **inchangé**
- `IntentBridge` (payloads externes) : **inchangé**
- Ajout de nouvelles routes : **hors scope**
- Interface utilisateur : **aucun impact**
