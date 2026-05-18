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

# Note: "youtube" is not in _ROUTES — it is detected by URL regex in route() and
# _KeywordFallback.get_route() before any scoring occurs.

# ---------------------------------------------------------------------------
# _KeywordFallback — original keyword-overlap logic, unchanged
# ---------------------------------------------------------------------------

_KEYWORD_OVERLAP_THRESHOLD = 1  # minimum overlapping tokens to count a hit


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
            if overlap >= _KEYWORD_OVERLAP_THRESHOLD:
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
        self._cache: dict[str, np.ndarray] = {}   # route → (N, D) float32 matrix, D = embedding dimension
        self._lock = threading.Lock()
        self._last_retry: float = 0.0              # epoch time of last failed init attempt
        self._keyword = _KeywordFallback()
        self._load_settings()

    def _load_settings(self) -> None:
        """Read configuration from settings_store (with safe defaults)."""
        sr: dict = {}
        base_url = "http://localhost:11434"
        try:
            from core.settings_store import app_settings
            sr = app_settings.get("semantic_router", {})
            base_url = app_settings.get("ollama_url", base_url)
        except Exception:
            try:
                from config import OLLAMA_URL
                base = OLLAMA_URL.rstrip("/")
                if base.endswith("/api"):
                    base = base[:-4]
                base_url = base
            except Exception:
                pass
        self._model: str = sr.get("embedding_model", "nomic-embed-text")
        self._threshold: float = float(sr.get("confidence_threshold", 0.45))
        self._timeout: float = float(sr.get("embed_timeout_s", 5.0))
        self._cooldown: float = float(sr.get("retry_cooldown_s", 30.0))
        self._embed_url: str = base_url.rstrip("/") + "/api/embeddings"

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
                            "[SemanticRouter] Ollama indisponible (failed on route=%s), mode keyword actif",
                            route,
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

    def _get_cache_snapshot(self) -> dict:
        """Return the current cache under the lock (empty dict if not built)."""
        with self._lock:
            return dict(self._cache)

    def _best_route(self, query_vec: np.ndarray, cache: dict) -> tuple[str, float]:
        """Return (route, score) for the highest-scoring route."""
        best_route = "qwen_basic"
        best_score = -1.0
        for route, matrix in cache.items():
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
        if re.search(r"(?:youtube\.com/watch|youtu\.be/)", prompt):
            return "youtube"
        try:
            self._ensure_cache()
            cache = self._get_cache_snapshot()
            if not cache:
                return self._keyword.get_route(prompt)
            query_vec = self._embed(prompt)
            if query_vec is None:
                return self._keyword.get_route(prompt)
            best_route, best_score = self._best_route(query_vec, cache)
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
    with _router._lock:
        ready = bool(_router._cache)
    if ready:
        logger.info("[SemanticRouter] Ready (embedding router, nomic-embed-text).")
    else:
        logger.warning("[SemanticRouter] Ready (keyword fallback — Ollama unavailable).")
