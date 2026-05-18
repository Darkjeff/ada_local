"""Tests that the n8n settings block is present and readable via SettingsStore."""
import os
import tempfile
import unittest
from unittest.mock import patch

from core.settings_store import SettingsStore


class TestN8NSettings(unittest.TestCase):
    def setUp(self):
        """Create a SettingsStore pointing at a temp directory (no real disk state)."""
        self.tmp = tempfile.mkdtemp()
        with patch.object(SettingsStore, '__init__', lambda s: None):
            self.store = SettingsStore.__new__(SettingsStore)
        # Reinitialise properly with temp path
        import threading
        from pathlib import Path
        from core.settings_store import DEFAULT_SETTINGS
        self.store._lock = threading.RLock()
        self.store._settings = DEFAULT_SETTINGS.copy()
        self.store._settings_dir = Path(self.tmp)
        self.store._settings_file = Path(self.tmp) / "settings.json"

    def test_n8n_block_exists(self):
        cfg = self.store.get("n8n")
        self.assertIsNotNone(cfg)
        self.assertIsInstance(cfg, dict)

    def test_n8n_url_default(self):
        self.assertEqual(self.store.get("n8n.url"), "http://localhost:5678")

    def test_n8n_timeout_default(self):
        self.assertEqual(self.store.get("n8n.timeout_s"), 10.0)

    def test_n8n_fallback_default(self):
        self.assertIs(self.store.get("n8n.fallback_enabled"), True)

    def test_n8n_cooldown_default(self):
        self.assertEqual(self.store.get("n8n.cooldown_s"), 30.0)


if __name__ == "__main__":
    unittest.main()
