"""
Persistent asyncio event loop running in a background daemon thread.

Replaces asyncio.run() for Kasa calls — a single long-lived loop means
aiohttp sessions are never abruptly closed when a loop shuts down,
which eliminates the "Unclosed client session" warnings.
"""

import asyncio
import threading
from typing import Any, Coroutine

_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None
_lock = threading.Lock()


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop, _thread
    with _lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
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
