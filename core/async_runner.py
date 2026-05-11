"""
Persistent asyncio event loop running in a background daemon thread.

Replaces asyncio.run() for Kasa calls — a single long-lived loop means
aiohttp sessions are never abruptly closed when a loop shuts down,
which eliminates the "Unclosed client session" warnings.
"""

import asyncio
import logging
import threading
from typing import Any, Coroutine

# python-kasa doesn't close its aiohttp sessions between calls — suppress
# the resulting noise since it's cosmetic and doesn't affect functionality.
logging.getLogger("aiohttp.client").setLevel(logging.CRITICAL)
logging.getLogger("aiohttp.connector").setLevel(logging.CRITICAL)

_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None
_lock = threading.Lock()


def _silent_exception_handler(loop, context):
    # Swallow "Unclosed client session / connector" noise from python-kasa
    msg = context.get("message", "")
    if "Unclosed" in msg or "unclosed" in msg:
        return
    loop.default_exception_handler(context)


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop, _thread
    with _lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            _loop.set_exception_handler(_silent_exception_handler)
            _thread = threading.Thread(
                target=_loop.run_forever,
                name="AsyncRunner",
                daemon=True,
            )
            _thread.start()
        return _loop


def run_async(coro: Coroutine, timeout: float = 30.0) -> Any:
    """
    Submit a coroutine to the persistent loop and block until it completes.
    Safe to call from any thread (including QThread workers).
    """
    loop = _get_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)
