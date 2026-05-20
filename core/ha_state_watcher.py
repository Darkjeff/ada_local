"""
Generic HA entity state watcher — polls subscribed entities every N seconds
and fires callbacks when a target state is entered.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable

from core.ha_control import ha_manager


@dataclass
class _Subscription:
    entity_id: str
    trigger_states: list[str]
    callback: Callable


class HAStateWatcher:
    """
    Daemon thread that polls HA entity states at a fixed interval.
    Fires callback(entity_id, new_state) when a subscribed entity
    enters one of its trigger_states.
    """

    def __init__(self, poll_interval: float = 5.0):
        self._poll_interval = poll_interval
        self._subscriptions: list[_Subscription] = []
        self._last_states: dict[str, str] = {}
        self._running = False
        self._thread: threading.Thread | None = None

    def subscribe(self, entity_id: str, trigger_states: list[str], callback: Callable) -> None:
        if not entity_id:
            return
        self._subscriptions.append(_Subscription(entity_id, trigger_states, callback))

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="HAStateWatcher"
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            for sub in list(self._subscriptions):
                try:
                    self._check(sub)
                except Exception as e:
                    print(f"[HAStateWatcher] Error checking {sub.entity_id}: {e}")
            time.sleep(self._poll_interval)

    def _check(self, sub: _Subscription) -> None:
        state_dict = ha_manager.get_state(sub.entity_id)
        if not state_dict:
            return
        new_state = state_dict.get("state")
        if new_state is None:
            return
        prev = self._last_states.get(sub.entity_id)
        self._last_states[sub.entity_id] = new_state
        if prev == new_state:
            return
        if new_state in sub.trigger_states:
            try:
                sub.callback(sub.entity_id, new_state)
            except Exception as e:
                print(f"[HAStateWatcher] Callback error for {sub.entity_id}: {e}")


# Singleton
ha_state_watcher = HAStateWatcher()
