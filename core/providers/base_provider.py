# core/providers/base_provider.py
"""
Abstract base class that all provider adapters must implement.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from core.entity_models import Provider, Entity


class BaseProvider(ABC):
    """
    Contract for all automation provider adapters.

    Implementations must be resilient — every public method must catch
    exceptions internally and return safe empty values on failure.
    """

    @property
    @abstractmethod
    def provider_info(self) -> Provider:
        """Return current Provider metadata (reads live from settings)."""
        ...

    @abstractmethod
    def fetch_entities(self) -> list[Entity]:
        """
        Discover and return all entities from this provider.
        Never raises — returns [] on any error.
        """
        ...

    @abstractmethod
    def test_connection(self) -> bool:
        """
        Test reachability of this provider.
        Updates provider_info.status as a side effect.
        Never raises.
        """
        ...

    @abstractmethod
    def toggle(self, provider_entity_id: str, on: bool) -> bool:
        """
        Turn an entity on or off.
        Returns True on success, False on any error.
        Never raises.
        """
        ...

    def set_brightness(self, provider_entity_id: str, value: int) -> bool:
        """
        Set brightness 0-100. Default no-op returns False.
        Override in providers that support brightness.
        """
        return False
