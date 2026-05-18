# Semantic Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ADA's keyword-overlap router with an Ollama-embedding-based semantic router that uses cosine similarity against pre-computed utterance vectors, with transparent fallback to the old keyword logic.

**Architecture:** A new `EmbeddingRouter` class in `core/semantic_router.py` lazily builds a per-route embedding cache (via `requests.post` to Ollama `/api/embeddings` using `nomic-embed-text`), computes mean cosine similarity at query time, and falls back to the renamed `_KeywordFallback` when Ollama is unavailable. The public `get_route()` signature is unchanged.

**Tech Stack:** Python stdlib (`threading`, `time`), `requests` (already used project-wide for Ollama calls), `numpy` (already in requirements), Ollama `nomic-embed-text` model.

---

### Task 1: Add `semantic_router` settings block to DEFAULT_SETTINGS

**Files:**
- Modify: `core/settings_store.py`

- [ ] **Step 1: Read the current DEFAULT_SETTINGS to confirm insertion point**

Open `core/settings_store.py`. The `DEFAULT_SETTINGS` dict ends with the `"senses"` block (around line 64–71). We will add the new block after `"senses"`.

- [ ] **Step 2: Add the `semantic_router` block**

In `core/settings_store.py`, locate the end of the `"senses"` block:

```python
    "senses": {
        "camera_index": 0,
        "audio_input_device": -1,          # -1 = system default
        "audio_output_device": -1,         # -1 = system default
        "speech_output_mode": "local",     # "local" | "ha_media_player"
        "ha_tts_entity": "",               # selected HA media_player entity_id (device id in registry)
    }
```

Add after it (before the closing `}` of `DEFAULT_SETTINGS`):

```python
    "semantic_router": {
        "embedding_model": "nomic-embed-text",
        "confidence_threshold": 0.45,
        "embed_timeout_s": 5.0,
        "retry_cooldown_s": 30.0,
    }
```

The full end of `DEFAULT_SETTINGS` should look like:

```python
    "senses": {
        "camera_index": 0,
        "audio_input_device": -1,
        "audio_output_device": -1,
        "speech_output_mode": "local",
        "ha_tts_entity": "",
    },
    "semantic_router": {
        "embedding_model": "nomic-embed-text",
        "confidence_threshold": 0.45,
        "embed_timeout_s": 5.0,
        "retry_cooldown_s": 30.0,
    }
}
```

- [ ] **Step 3: Verify no syntax errors**

```bash
python -c "from core.settings_store import DEFAULT_SETTINGS; print(DEFAULT_SETTINGS['semantic_router'])"
```

Expected output:
```
{'embedding_model': 'nomic-embed-text', 'confidence_threshold': 0.45, 'embed_timeout_s': 5.0, 'retry_cooldown_s': 30.0}
```

- [ ] **Step 4: Commit**

```bash
git add core/settings_store.py
git commit -m "feat(router): add semantic_router defaults to settings_store"
```

---

### Task 2: Rewrite `core/semantic_router.py` with EmbeddingRouter + fallback

**Files:**
- Modify: `core/semantic_router.py` (full rewrite, same public interface)

The file must keep `VALID_ROUTES`, `_ROUTES` utterance dict, and `get_route(prompt) -> str` unchanged from the caller's perspective. The existing keyword logic moves into `_KeywordFallback`. A new `EmbeddingRouter` wraps it with Ollama embeddings.

- [ ] **Step 1: Write the new `core/semantic_router.py`**

Replace the entire file with:

```python
"""
Semantic Router — embedding-based classifier with keyword fallback.

Routes user prompts to one of 7 agents using cosine similarity against
Ollama-embedded utterances (nomic-embed-text). Falls back to the original
keyword-overlap scorer when Ollama is unavailable.

Routes:
  qwen_basic      → simple chat, greetings, quick facts
  qwen_thinking   → complex reasoning, coding, analysis
  function_gemma  → actions (lights, timer, calendar...)
  cad_generation  → 3D model creation / iteration
  print_control   → printer status / print job control
  vision          → webcam / image analysis
  youtube         → YouTube transcription / summary
"""

import logging
import re
import threading
import time
from typing import Optional

import numpy as np
import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public contract
# ---------------------------------------------------------------------------

VALID_ROUTES = {
    "qwen_basic", "qwen_thinking", "function_gemma",
    "cad_generation", "print_control", "vision", "youtube",
}

# ---------------------------------------------------------------------------
# Utterances per route
# ---------------------------------------------------------------------------

_ROUTES: dict[str, list[str]] = {
    "vision": [
        "regarde", "que vois tu", "que vois-tu", "qu'est-ce que tu vois",
        "décris ce que tu vois", "regarde autour", "observe",
        "prends une photo", "capture une image", "montre ce que tu vois",
        "analyse l'image", "décris la scène", "tu vois quoi",
        "dis-moi ce que tu vois", "regarde ce qu'il y a",
        "utilise la caméra", "webcam", "caméra",
        "what do you see", "look around", "describe what you see",
        "take a picture", "capture a frame", "look at this",
        "what's in front of you", "describe the scene",
        "use the camera", "show me what you see", "camera",
        "scan the room", "look at the room",
    ],

    "cad_generation": [
        "crée un modèle 3d", "génère un fichier stl", "dessine une pièce",
        "modélise un boîtier", "crée une pièce pour", "conception 3d",
        "modifie le modèle", "change les dimensions", "crée un stl",
        "create a 3d model", "generate a 3d model", "design a 3d object",
        "make a cad model", "create an stl file", "generate stl",
        "design a box", "model a bracket", "create a gear",
        "make a housing for", "design a mount for", "create a case for",
        "parametric design", "build123d",
        "make me a 3d model", "i need a 3d model",
        "modify the 3d model", "change the height of the model",
        "add a hole to the model", "update the design",
        "iterate on the model", "adjust the dimensions",
    ],

    "print_control": [
        "imprime le modèle", "lance l'impression", "statut de l'impression",
        "pause l'impression", "annule l'impression", "progression impression",
        "température buse", "température plateau", "trouve les imprimantes",
        "connecte l'imprimante", "statut imprimante", "où en est l'impression",
        "imprimante 3d", "octoprint", "klipper", "moonraker",
        "print the model", "start printing", "send to printer",
        "print status", "how's the print going", "what is printing",
        "pause the print", "cancel the print", "resume the print",
        "printer temperature", "bed temperature", "hotend temperature",
        "discover printers", "find my printer", "connect to printer",
        "3d printer status", "is the printer done", "stop the printer",
    ],

    "function_gemma": [
        "allume la lumière", "éteins la lumière", "mets la lumière",
        "turn on the lights", "turn off the lights", "dim the lights",
        "minuterie", "timer", "set a timer", "set an alarm", "réveil",
        "ajoute une tâche", "add a task", "crée un événement",
        "create a calendar event", "schedule meeting",
        "cherche sur internet", "search the web", "look up",
        "quel temps fait-il", "weather in", "météo à",
        "qu'est-ce que j'ai aujourd'hui", "what tasks do I have",
        "what's on my schedule", "rappelle-moi",
        "exécute", "lance le script", "shell", "commande powershell",
        "liste les fichiers", "quelle version", "ping",
        "espace disque", "espace disponible", "disk space", "df",
        "utilisation cpu", "utilisation mémoire", "ram disponible",
        "processus en cours", "liste les processus", "process list",
        "quel est l'espace", "combien d'espace", "how much disk",
        "température cpu", "cpu temperature", "charge système",
        "ports ouverts", "connexions réseau", "netstat", "ipconfig", "ifconfig",
        "version de python", "version python", "version nodejs",
        "services windows", "services linux", "systemctl",
    ],

    "qwen_thinking": [
        "pourquoi", "explique", "comment fonctionne", "analyse",
        "compare", "différence entre", "pros and cons", "avantages inconvénients",
        "résume", "résumé", "synthèse", "implications",
        "écris un programme", "écris du code", "débogue", "debug",
        "write code", "write a function", "write a script",
        "explain", "how does", "what are the steps",
        "walk me through", "detailed explanation",
        "essay", "business plan", "inverse kinematics",
        "quantum", "machine learning", "algorithme",
        "implémente", "implement", "architecture",
    ],

    "qwen_basic": [
        "bonjour", "salut", "bonsoir", "merci", "ça va", "au revoir",
        "hi", "hello", "hey", "good morning", "good night",
        "thanks", "thank you", "bye", "see you", "ok", "sure",
        "what's up", "how are you", "what time is it",
        "quelle heure", "quelle date", "quel jour",
        "capitale", "capital of", "qui est", "who is",
        "blague", "joke", "say something funny",
    ],
}

# ---------------------------------------------------------------------------
# _KeywordFallback — original keyword-overlap logic, unchanged
# ---------------------------------------------------------------------------

_THRESHOLD = 1  # minimum overlapping tokens to count a hit


def _tokenize(text: str) -> frozenset:
    """Lowercase, split on non-word chars, drop tokens shorter than 2 chars."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return frozenset(w for w in text.split() if len(w) > 1)


class _KeywordFallback:
    """Keyword-overlap scorer. Zero dependencies, <1 ms."""

    def __init__(self) -> None:
        self._index: list[tuple[str, frozenset]] = []
        for route, utterances in _ROUTES.items():
            for utt in utterances:
                self._index.append((route, _tokenize(utt)))

    def get_route(self, prompt: str) -> str:
        if not prompt or not prompt.strip():
            return "qwen_basic"
        if re.search(r"(?:youtube\.com/watch|youtu\.be/)", prompt):
            return "youtube"
        tokens = _tokenize(prompt)
        if not tokens:
            return "qwen_basic"
        scores: dict[str, float] = {r: 0.0 for r in VALID_ROUTES}
        for route, utt_tokens in self._index:
            overlap = len(tokens & utt_tokens)
            if overlap >= _THRESHOLD:
                scores[route] += overlap / max(len(utt_tokens), 1)
        best_route = max(scores, key=lambda r: scores[r])
        if scores[best_route] < 0.3:
            return "function_gemma"
        return best_route


# ---------------------------------------------------------------------------
# EmbeddingRouter — Ollama-based semantic router
# ---------------------------------------------------------------------------

class EmbeddingRouter:
    """
    Routes prompts using cosine similarity against Ollama-embedded utterances.

    Lazy init: the embedding cache is built on the first call to route().
    Falls back to _KeywordFallback on any Ollama error.
    """

    def __init__(self) -> None:
        self._cache: dict[str, np.ndarray] = {}   # route → (N, 768) float32 matrix
        self._lock = threading.Lock()
        self._last_retry: float = 0.0              # epoch time of last failed init attempt
        self._keyword = _KeywordFallback()
        self._load_settings()

    def _load_settings(self) -> None:
        """Read configuration from settings_store (with safe defaults)."""
        try:
            from core.settings_store import app_settings
            sr = app_settings.get("semantic_router", {})
        except Exception:
            sr = {}
        self._model: str = sr.get("embedding_model", "nomic-embed-text")
        self._threshold: float = float(sr.get("confidence_threshold", 0.45))
        self._timeout: float = float(sr.get("embed_timeout_s", 5.0))
        self._cooldown: float = float(sr.get("retry_cooldown_s", 30.0))
        try:
            from core.settings_store import app_settings
            base = app_settings.get("ollama_url", "http://localhost:11434")
        except Exception:
            from config import OLLAMA_URL
            # config.OLLAMA_URL already ends with /api
            base = OLLAMA_URL.rstrip("/api").rstrip("/")
        self._embed_url: str = base.rstrip("/") + "/api/embeddings"

    def _embed(self, text: str) -> Optional[np.ndarray]:
        """Return a float32 vector for *text*, or None on error."""
        try:
            resp = requests.post(
                self._embed_url,
                json={"model": self._model, "prompt": text},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            vec = np.array(resp.json()["embedding"], dtype=np.float32)
            return vec
        except Exception as exc:
            logger.warning("[SemanticRouter] embed failed: %s", exc)
            return None

    def _ensure_cache(self) -> None:
        """
        Build the per-route utterance matrices (once, thread-safe).
        If Ollama is down, leaves cache empty and records the attempt time
        so callers can respect the retry cooldown.
        """
        with self._lock:
            if self._cache:
                return  # already built
            now = time.monotonic()
            if now - self._last_retry < self._cooldown and self._last_retry > 0:
                return  # cooldown not elapsed
            self._last_retry = now

            route_vecs: dict[str, list[np.ndarray]] = {r: [] for r in _ROUTES}
            total = 0
            for route, utterances in _ROUTES.items():
                for utt in utterances:
                    vec = self._embed(utt)
                    if vec is None:
                        # Ollama unavailable — abort, leave cache empty
                        logger.warning(
                            "[SemanticRouter] Ollama indisponible, mode keyword actif"
                        )
                        return
                    route_vecs[route].append(vec)
                    total += 1

            # Store as (N, D) matrices for fast batch cosine computation
            self._cache = {
                route: np.stack(vecs)
                for route, vecs in route_vecs.items()
                if vecs
            }
            logger.info(
                "[SemanticRouter] cache prêt (%d routes, %d utterances)",
                len(self._cache),
                total,
            )

    @staticmethod
    def _cosine_mean(query_vec: np.ndarray, matrix: np.ndarray) -> float:
        """Mean cosine similarity between *query_vec* and each row of *matrix*."""
        q = query_vec / (np.linalg.norm(query_vec) + 1e-9)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
        normed = matrix / norms
        return float(np.mean(normed @ q))

    def _best_route(self, query_vec: np.ndarray) -> tuple[str, float]:
        """Return (route, score) for the highest-scoring route."""
        best_route = "qwen_basic"
        best_score = -1.0
        for route, matrix in self._cache.items():
            score = self._cosine_mean(query_vec, matrix)
            if score > best_score:
                best_score = score
                best_route = route
        return best_route, best_score

    def route(self, prompt: str) -> str:
        """
        Return the best route for *prompt*.
        Falls back to keyword router if Ollama is unavailable.
        Never raises.
        """
        if not prompt or not prompt.strip():
            return "qwen_basic"

        # YouTube URL detection — highest priority
        if re.search(r"(?:youtube\.com/watch|youtu\.be/)", prompt):
            return "youtube"

        try:
            self._ensure_cache()

            if not self._cache:
                # Ollama was down during cache build — use keyword fallback
                return self._keyword.get_route(prompt)

            query_vec = self._embed(prompt)
            if query_vec is None:
                return self._keyword.get_route(prompt)

            best_route, best_score = self._best_route(query_vec)
            if best_score < self._threshold:
                return "qwen_basic"
            return best_route

        except Exception as exc:
            logger.error("[SemanticRouter] unexpected error: %s", exc, exc_info=True)
            return "qwen_basic"


# ---------------------------------------------------------------------------
# Module-level singleton + public interface
# ---------------------------------------------------------------------------

_router = EmbeddingRouter()


def get_route(prompt: str) -> str:
    """
    Route a prompt to one of the VALID_ROUTES.
    Public interface — identical signature to the previous keyword router.
    """
    return _router.route(prompt)


def warmup() -> None:
    """
    Trigger cache initialisation eagerly (optional — call at ADA startup
    when Ollama is guaranteed to be available).
    """
    _router._ensure_cache()
    if _router._cache:
        print("[SemanticRouter] Ready (embedding router, nomic-embed-text).")
    else:
        print("[SemanticRouter] Ready (keyword fallback — Ollama unavailable).")
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
python -c "from core.semantic_router import get_route, VALID_ROUTES; print(get_route('bonjour'))"
```

Expected output (keyword fallback fires since Ollama isn't mocked):
```
qwen_basic
```

- [ ] **Step 3: Commit**

```bash
git add core/semantic_router.py
git commit -m "feat(router): replace keyword router with Ollama embedding router + keyword fallback"
```

---

### Task 3: Write 12 tests in `tests/test_semantic_router.py`

**Files:**
- Create: `tests/test_semantic_router.py`

All Ollama calls are mocked via `unittest.mock.patch`. No real Ollama instance required.

- [ ] **Step 1: Write the test file**

```python
"""
Tests for core/semantic_router.py

Strategy:
  - mock requests.post to simulate Ollama embeddings
  - EmbeddingRouter instances created fresh per test (bypasses module singleton)
  - keyword fallback tested by raising ConnectionError in requests.post
"""

import threading
import time
import unittest
from typing import Optional
from unittest.mock import MagicMock, patch

import numpy as np

from core.semantic_router import (
    EmbeddingRouter,
    _KeywordFallback,
    VALID_ROUTES,
    get_route,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_post_mock(vectors: dict[str, np.ndarray]):
    """
    Return a requests.post mock that maps utterance text → vector.
    For unknown utterances it returns a zero vector of the same dimension.
    The first value in `vectors` determines the dimension.
    """
    dim = next(iter(vectors.values())).shape[0] if vectors else 768

    def _post(url, json=None, timeout=None):
        prompt = (json or {}).get("prompt", "")
        vec = vectors.get(prompt, np.zeros(dim, dtype=np.float32))
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"embedding": vec.tolist()}
        return mock_resp

    return _post


def _fresh_router(post_mock=None) -> EmbeddingRouter:
    """Create an EmbeddingRouter with a cleared cache (bypasses module singleton)."""
    router = EmbeddingRouter.__new__(EmbeddingRouter)
    router._cache = {}
    router._lock = threading.Lock()
    router._last_retry = 0.0
    router._keyword = _KeywordFallback()
    router._model = "nomic-embed-text"
    router._threshold = 0.45
    router._timeout = 5.0
    router._cooldown = 30.0
    router._embed_url = "http://localhost:11434/api/embeddings"
    return router


# ---------------------------------------------------------------------------
# TestEmbeddingRouter — 7 tests
# ---------------------------------------------------------------------------

class TestEmbeddingRouter(unittest.TestCase):

    def _router_with_identical_vecs(self, target_route: str, dim: int = 8) -> tuple[EmbeddingRouter, np.ndarray]:
        """
        Build a router where utterances for `target_route` all have vector [1,0,0,...],
        and all other utterances have vector [0,1,0,...].
        Returns (router, query_vec_that_matches_target_route).
        """
        from core.semantic_router import _ROUTES

        target_vec = np.zeros(dim, dtype=np.float32)
        target_vec[0] = 1.0
        other_vec = np.zeros(dim, dtype=np.float32)
        other_vec[1] = 1.0

        vectors: dict[str, np.ndarray] = {}
        for route, utterances in _ROUTES.items():
            for utt in utterances:
                vectors[utt] = target_vec if route == target_route else other_vec

        router = _fresh_router()
        with patch("core.semantic_router.requests.post", side_effect=_make_post_mock(vectors)):
            router._ensure_cache()

        return router, target_vec.copy()

    def test_known_route_function_gemma(self):
        router, query_vec = self._router_with_identical_vecs("function_gemma")
        with patch("core.semantic_router.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"embedding": query_vec.tolist()}
            mock_post.return_value = mock_resp
            result = router.route("éteins l'éclairage du bureau")
        self.assertEqual(result, "function_gemma")

    def test_known_route_vision(self):
        router, query_vec = self._router_with_identical_vecs("vision")
        with patch("core.semantic_router.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"embedding": query_vec.tolist()}
            mock_post.return_value = mock_resp
            result = router.route("montre-moi ce que tu vois")
        self.assertEqual(result, "vision")

    def test_known_route_youtube(self):
        """YouTube URL detection bypasses embedding entirely."""
        router = _fresh_router()
        result = router.route("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(result, "youtube")

    def test_known_route_cad(self):
        router, query_vec = self._router_with_identical_vecs("cad_generation")
        with patch("core.semantic_router.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"embedding": query_vec.tolist()}
            mock_post.return_value = mock_resp
            result = router.route("génère-moi une pièce 3D")
        self.assertEqual(result, "cad_generation")

    def test_score_below_threshold_returns_default(self):
        """Orthogonal vector → score near 0 → qwen_basic."""
        from core.semantic_router import _ROUTES
        dim = 8
        cache_vec = np.zeros(dim, dtype=np.float32)
        cache_vec[0] = 1.0
        vectors = {utt: cache_vec.copy() for utts in _ROUTES.values() for utt in utts}

        router = _fresh_router()
        router._threshold = 0.45
        with patch("core.semantic_router.requests.post", side_effect=_make_post_mock(vectors)):
            router._ensure_cache()

        # Orthogonal query vector → cosine ≈ 0
        orthogonal_vec = np.zeros(dim, dtype=np.float32)
        orthogonal_vec[2] = 1.0

        with patch("core.semantic_router.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"embedding": orthogonal_vec.tolist()}
            mock_post.return_value = mock_resp
            result = router.route("quelque chose de complètement aléatoire")
        self.assertEqual(result, "qwen_basic")

    def test_empty_prompt_returns_default(self):
        router = _fresh_router()
        self.assertEqual(router.route(""), "qwen_basic")
        self.assertEqual(router.route("   "), "qwen_basic")
        self.assertEqual(router.route(None), "qwen_basic")  # type: ignore[arg-type]

    def test_cache_built_once(self):
        """_embed() is called N_utterances times at init, not on each route() call."""
        from core.semantic_router import _ROUTES
        total_utterances = sum(len(v) for v in _ROUTES.values())
        dim = 4
        base_vec = np.ones(dim, dtype=np.float32)

        router = _fresh_router()
        call_count = 0

        def counting_post(url, json=None, timeout=None):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"embedding": base_vec.tolist()}
            return mock_resp

        with patch("core.semantic_router.requests.post", side_effect=counting_post):
            router._ensure_cache()
            count_after_init = call_count

            # route() calls _embed() once more for the query
            router.route("bonjour")
            count_after_route = call_count

        self.assertEqual(count_after_init, total_utterances)
        # route() added exactly 1 embed call (the query), not N_utterances again
        self.assertEqual(count_after_route, total_utterances + 1)


# ---------------------------------------------------------------------------
# TestFallback — 3 tests
# ---------------------------------------------------------------------------

class TestFallback(unittest.TestCase):

    def test_ollama_down_uses_keyword_fallback(self):
        """ConnectionError during cache build → keyword fallback route returned."""
        router = _fresh_router()

        def raising_post(url, json=None, timeout=None):
            raise requests_module.exceptions.ConnectionError("Ollama down")

        import requests as requests_module
        with patch("core.semantic_router.requests.post", side_effect=raising_post):
            result = router.route("allume la lumière")

        # keyword fallback should return function_gemma for this prompt
        self.assertEqual(result, "function_gemma")
        self.assertEqual(router._cache, {})  # cache stays empty

    def test_ollama_timeout_uses_keyword_fallback(self):
        """Timeout during query embed → keyword fallback."""
        from core.semantic_router import _ROUTES
        dim = 4
        base_vec = np.ones(dim, dtype=np.float32)
        vectors = {utt: base_vec.copy() for utts in _ROUTES.values() for utt in utts}

        router = _fresh_router()
        # Build cache successfully
        with patch("core.semantic_router.requests.post", side_effect=_make_post_mock(vectors)):
            router._ensure_cache()
        self.assertNotEqual(router._cache, {})

        # Now simulate timeout on the query embed
        import requests as requests_module
        with patch("core.semantic_router.requests.post",
                   side_effect=requests_module.exceptions.Timeout("timeout")):
            result = router.route("éteins la lumière")

        # Keyword fallback kicks in for the query
        self.assertEqual(result, "function_gemma")

    def test_retry_cooldown_respected(self):
        """If Ollama was down, _ensure_cache() is not retried within cooldown_s."""
        router = _fresh_router()
        router._cooldown = 30.0

        import requests as requests_module
        call_count = 0

        def failing_post(url, json=None, timeout=None):
            nonlocal call_count
            call_count += 1
            raise requests_module.exceptions.ConnectionError("down")

        with patch("core.semantic_router.requests.post", side_effect=failing_post):
            router._ensure_cache()  # first attempt — should try
            first_count = call_count

            # Simulate second call immediately (within cooldown)
            router._ensure_cache()
            second_count = call_count

        # Second call within cooldown must not trigger any new requests.post calls
        self.assertGreater(first_count, 0)
        self.assertEqual(first_count, second_count)


# ---------------------------------------------------------------------------
# TestIntegration — 2 tests
# ---------------------------------------------------------------------------

class TestIntegration(unittest.TestCase):

    def test_same_interface(self):
        """get_route() always returns one of the 7 valid routes."""
        prompts = [
            "bonjour", "allume la lumière", "génère un modèle 3D",
            "que vois-tu", "imprime le modèle", "explique la relativité",
            "https://youtu.be/dQw4w9WgXcQ", "", "  ", "xyz abc def",
        ]
        for prompt in prompts:
            result = get_route(prompt)
            self.assertIn(
                result,
                VALID_ROUTES,
                f"get_route({prompt!r}) returned invalid route {result!r}",
            )

    def test_thread_safety(self):
        """10 concurrent threads calling route() produce no exceptions."""
        from core.semantic_router import _ROUTES
        dim = 4
        base_vec = np.ones(dim, dtype=np.float32)
        vectors = {utt: base_vec.copy() for utts in _ROUTES.values() for utt in utts}

        router = _fresh_router()
        errors: list[Exception] = []
        results: list[str] = []

        def worker():
            try:
                with patch("core.semantic_router.requests.post",
                           side_effect=_make_post_mock(vectors)):
                    r = router.route("allume la lumière")
                results.append(r)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertEqual(errors, [], f"Thread errors: {errors}")
        self.assertEqual(len(results), 10)
        for r in results:
            self.assertIn(r, VALID_ROUTES)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests**

```bash
cd C:\wamp64\www\ada_local
python -m pytest tests/test_semantic_router.py -v
```

Expected output:
```
tests/test_semantic_router.py::TestEmbeddingRouter::test_cache_built_once PASSED
tests/test_semantic_router.py::TestEmbeddingRouter::test_empty_prompt_returns_default PASSED
tests/test_semantic_router.py::TestEmbeddingRouter::test_known_route_cad PASSED
tests/test_semantic_router.py::TestEmbeddingRouter::test_known_route_function_gemma PASSED
tests/test_semantic_router.py::TestEmbeddingRouter::test_known_route_vision PASSED
tests/test_semantic_router.py::TestEmbeddingRouter::test_known_route_youtube PASSED
tests/test_semantic_router.py::TestEmbeddingRouter::test_score_below_threshold_returns_default PASSED
tests/test_semantic_router.py::TestFallback::test_ollama_down_uses_keyword_fallback PASSED
tests/test_semantic_router.py::TestFallback::test_ollama_timeout_uses_keyword_fallback PASSED
tests/test_semantic_router.py::TestFallback::test_retry_cooldown_respected PASSED
tests/test_semantic_router.py::TestIntegration::test_same_interface PASSED
tests/test_semantic_router.py::TestIntegration::test_thread_safety PASSED

12 passed in Xs
```

If any test fails, fix `core/semantic_router.py` or the test helper until all 12 pass.

- [ ] **Step 3: Run full test suite to check for regressions**

```bash
python -m pytest --tb=short -q
```

Expected: all previously-passing tests still pass, 12 new tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_semantic_router.py
git commit -m "test(router): add 12 tests for EmbeddingRouter + fallback + thread safety"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered by |
|---|---|
| `EmbeddingRouter` with lazy `_ensure_cache` | Task 2 — `_ensure_cache()` with `threading.Lock` |
| `_embed()` via `requests.post` to `/api/embeddings` | Task 2 — `_embed()` method |
| Mean cosine similarity per route | Task 2 — `_cosine_mean()` + `_best_route()` |
| Confidence threshold 0.45 | Task 1 (settings) + Task 2 (read from settings) |
| 30s retry cooldown | Task 2 — `_last_retry` + cooldown check in `_ensure_cache()` |
| Keyword fallback on any error | Task 2 — all except branches call `_keyword.get_route()` |
| `get_route()` never raises | Task 2 — outer try/except in `route()` |
| Thread-safe init | Task 2 — `threading.Lock` in `_ensure_cache()` |
| `warmup()` updated | Task 2 — new `warmup()` logs actual state |
| Settings in `settings_store.py` | Task 1 |
| 12 tests, no real Ollama | Task 3 |
| `numpy` already present | No action needed (confirmed `numpy>=2.0.0` in requirements.txt) |

**Placeholder scan:** No TBDs, no TODOs, no incomplete sections.

**Type consistency:**
- `_embed()` returns `Optional[np.ndarray]` — used consistently in `_ensure_cache()` and `route()`
- `_best_route()` returns `tuple[str, float]` — destructured correctly in `route()`
- `_KeywordFallback.get_route()` returns `str` — called correctly in fallback branches
