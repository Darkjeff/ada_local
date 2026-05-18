"""
Tests for core/semantic_router.py

Strategy:
  - mock requests.post to simulate Ollama embeddings
  - EmbeddingRouter instances created fresh per test (bypasses module singleton)
  - keyword fallback tested by raising ConnectionError in requests.post
"""

import threading
import unittest
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

def _make_post_mock(vectors: dict):
    """
    Return a side_effect callable for requests.post that maps utterance → vector.
    Unknown utterances get a zero vector of the same dimension as the first entry.
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


def _fresh_router() -> EmbeddingRouter:
    """Create an EmbeddingRouter with cleared state, bypassing module singleton."""
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


def _build_cache_for_route(target_route: str, dim: int = 8):
    """
    Build a router whose cache has:
      - target_route utterances → vector [1, 0, 0, ...]
      - all other utterances    → vector [0, 1, 0, ...]
    Returns (router, target_vector).
    """
    from core.semantic_router import _ROUTES

    target_vec = np.zeros(dim, dtype=np.float32)
    target_vec[0] = 1.0
    other_vec = np.zeros(dim, dtype=np.float32)
    other_vec[1] = 1.0

    vectors = {}
    for route, utterances in _ROUTES.items():
        for utt in utterances:
            vectors[utt] = target_vec if route == target_route else other_vec

    router = _fresh_router()
    with patch("core.semantic_router.requests.post", side_effect=_make_post_mock(vectors)):
        router._ensure_cache()

    return router, target_vec.copy()


# ---------------------------------------------------------------------------
# TestEmbeddingRouter — 7 tests
# ---------------------------------------------------------------------------

class TestEmbeddingRouter(unittest.TestCase):

    def _route_with_query(self, router: EmbeddingRouter, query_vec: np.ndarray, prompt: str) -> str:
        """Helper: call router.route() with a mocked query embed returning query_vec."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"embedding": query_vec.tolist()}
        with patch("core.semantic_router.requests.post", return_value=mock_resp):
            return router.route(prompt)

    def test_known_route_function_gemma(self):
        router, query_vec = _build_cache_for_route("function_gemma")
        result = self._route_with_query(router, query_vec, "éteins l'éclairage du bureau")
        self.assertEqual(result, "function_gemma")

    def test_known_route_vision(self):
        router, query_vec = _build_cache_for_route("vision")
        result = self._route_with_query(router, query_vec, "montre-moi ce que tu vois")
        self.assertEqual(result, "vision")

    def test_known_route_youtube(self):
        """YouTube URL detection bypasses embedding entirely — no requests.post called."""
        router = _fresh_router()
        result = router.route("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(result, "youtube")

    def test_known_route_cad(self):
        router, query_vec = _build_cache_for_route("cad_generation")
        result = self._route_with_query(router, query_vec, "génère-moi une pièce 3D")
        self.assertEqual(result, "cad_generation")

    def test_score_below_threshold_returns_default(self):
        """Orthogonal query vector → cosine ≈ 0 → score < 0.45 → qwen_basic."""
        from core.semantic_router import _ROUTES
        dim = 8
        cache_vec = np.zeros(dim, dtype=np.float32)
        cache_vec[0] = 1.0
        vectors = {utt: cache_vec.copy() for utts in _ROUTES.values() for utt in utts}

        router = _fresh_router()
        with patch("core.semantic_router.requests.post", side_effect=_make_post_mock(vectors)):
            router._ensure_cache()

        # Orthogonal to cache vectors → cosine similarity ≈ 0 → below threshold
        orthogonal = np.zeros(dim, dtype=np.float32)
        orthogonal[2] = 1.0

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"embedding": orthogonal.tolist()}
        with patch("core.semantic_router.requests.post", return_value=mock_resp):
            result = router.route("quelque chose de complètement aléatoire xyz")

        self.assertEqual(result, "qwen_basic")

    def test_empty_prompt_returns_default(self):
        router = _fresh_router()
        self.assertEqual(router.route(""), "qwen_basic")
        self.assertEqual(router.route("   "), "qwen_basic")

    def test_cache_built_once(self):
        """_embed() is called exactly N_utterances times during init, then once per route() call."""
        from core.semantic_router import _ROUTES
        total_utterances = sum(len(v) for v in _ROUTES.values())
        dim = 4
        base_vec = np.ones(dim, dtype=np.float32)
        call_count = 0

        def counting_post(url, json=None, timeout=None):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"embedding": base_vec.tolist()}
            return mock_resp

        router = _fresh_router()
        with patch("core.semantic_router.requests.post", side_effect=counting_post):
            router._ensure_cache()
            count_after_init = call_count

            router.route("bonjour")
            count_after_first_route = call_count

            router.route("allume la lumière")
            count_after_second_route = call_count

        self.assertEqual(count_after_init, total_utterances)
        self.assertEqual(count_after_first_route, total_utterances + 1)
        self.assertEqual(count_after_second_route, total_utterances + 2)


# ---------------------------------------------------------------------------
# TestFallback — 3 tests
# ---------------------------------------------------------------------------

class TestFallback(unittest.TestCase):

    def test_ollama_down_uses_keyword_fallback(self):
        """ConnectionError during cache build → cache stays empty → keyword fallback used."""
        import requests as req_module

        router = _fresh_router()

        with patch("core.semantic_router.requests.post",
                   side_effect=req_module.exceptions.ConnectionError("Ollama down")):
            result = router.route("allume la lumière")

        self.assertEqual(result, "function_gemma")
        self.assertEqual(router._cache, {})

    def test_ollama_timeout_uses_keyword_fallback(self):
        """Timeout on query embed (cache built OK) → keyword fallback used for that call."""
        import requests as req_module
        from core.semantic_router import _ROUTES

        dim = 4
        base_vec = np.ones(dim, dtype=np.float32)
        vectors = {utt: base_vec.copy() for utts in _ROUTES.values() for utt in utts}

        router = _fresh_router()
        with patch("core.semantic_router.requests.post", side_effect=_make_post_mock(vectors)):
            router._ensure_cache()
        self.assertTrue(bool(router._cache))  # cache was built

        with patch("core.semantic_router.requests.post",
                   side_effect=req_module.exceptions.Timeout("timeout")):
            result = router.route("éteins la lumière")

        self.assertEqual(result, "function_gemma")

    def test_retry_cooldown_respected(self):
        """After a failed cache build, _ensure_cache() skips retry within cooldown_s."""
        import requests as req_module

        router = _fresh_router()
        router._cooldown = 30.0
        call_count = 0

        def failing_post(url, json=None, timeout=None):
            nonlocal call_count
            call_count += 1
            raise req_module.exceptions.ConnectionError("down")

        with patch("core.semantic_router.requests.post", side_effect=failing_post):
            router._ensure_cache()  # first attempt — hits the network
            count_after_first = call_count

            router._ensure_cache()  # second call — should be suppressed by cooldown
            count_after_second = call_count

        self.assertGreater(count_after_first, 0)
        self.assertEqual(count_after_first, count_after_second)


# ---------------------------------------------------------------------------
# TestIntegration — 2 tests
# ---------------------------------------------------------------------------

class TestIntegration(unittest.TestCase):

    def test_same_interface(self):
        """get_route() always returns one of the 7 valid routes, never raises."""
        prompts = [
            "bonjour", "allume la lumière", "génère un modèle 3D",
            "que vois-tu", "imprime le modèle", "explique la relativité",
            "https://youtu.be/dQw4w9WgXcQ", "", "  ", "xyz abc def 123",
        ]
        for prompt in prompts:
            result = get_route(prompt)
            self.assertIn(
                result,
                VALID_ROUTES,
                f"get_route({prompt!r}) returned invalid route {result!r}",
            )

    def test_thread_safety(self):
        """10 concurrent threads calling route() on a fresh router produce no exceptions."""
        from core.semantic_router import _ROUTES

        dim = 4
        base_vec = np.ones(dim, dtype=np.float32)
        vectors = {utt: base_vec.copy() for utts in _ROUTES.values() for utt in utts}

        router = _fresh_router()
        errors: list = []
        results: list = []
        lock = threading.Lock()

        def worker():
            try:
                with patch("core.semantic_router.requests.post",
                           side_effect=_make_post_mock(vectors)):
                    r = router.route("allume la lumière")
                with lock:
                    results.append(r)
            except Exception as exc:
                with lock:
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
