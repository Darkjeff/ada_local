# core package
# Lazy imports: wrapped in try/except so individual modules can be imported
# in test environments that lack heavy optional dependencies (numpy, sounddevice, etc.)
try:
    from core.tts import PiperTTS, SentenceBuffer, tts
    from core.llm import route_query, execute_function, should_bypass_router, preload_models, http_session
except ImportError:
    pass

__all__ = [
    "PiperTTS", "SentenceBuffer", "tts",
    "route_query", "execute_function", "should_bypass_router", "preload_models", "http_session"
]
