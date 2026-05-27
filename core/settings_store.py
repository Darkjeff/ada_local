"""
Centralized settings storage with persistence.
Saves settings to ~/.pocket_ai/settings.json
"""

import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, Signal


# Default settings - used when no settings file exists
DEFAULT_SETTINGS = {
    "theme": "Dark",
    "ollama_url": "http://localhost:11434",
    "models": {
        "chat": "qwen3:1.7b",
        "web_agent": "qwen3-vl:4b",
    },
    "web_agent_params": {
        "temperature": 1.0,
        "top_k": 20,
        "top_p": 0.95
    },
    "tts": {
        "voice": "en_GB-alba-medium"
    },
    "general": {
        "max_history": 20,
        "auto_fetch_news": True
    },
    "weather": {
        "latitude": 40.7128,
        "longitude": -74.0060,
        "city": "New York, NY"
    },
    "home_assistant": {
        "url": "",
        "token": "",
        "enabled": False,
        "tts_service": "tts.piper",        # HA TTS engine entity (e.g. tts.piper, tts.google_translate)
        "tts_target_entity": "",           # Reserved: future Settings-tab HA TTS config (distinct from runtime senses.ha_tts_entity)
        "hidden_entities": [],
        "door_entity": "",
        "door_message": "🚪 Ciel un client !",
        "door_alert_enabled": False,
    },
    "kasa": {
        "enabled": True,
        "priority": 50,
    },
    "k1": {
        "ip": "",
        "password": ""
    },
    "telegram": {
        "enabled": False,
        "token": "",
        "owner_chat_id": "",
        "allowed_users": []
    },
    "briefing": {
        "enabled": False,
        "hour": 7
    },
    "senses": {
        "camera_index": 0,
        "audio_input_device": -1,          # -1 = system default
        "audio_output_device": -1,         # -1 = system default
        "speech_output_mode": "local",     # "local" | "ha_media_player"
        "ha_tts_entity": "",               # selected HA media_player entity_id (device id in registry)
    },
    "semantic_router": {
        "embedding_model": "nomic-embed-text",
        "confidence_threshold": 0.45,
        "embed_timeout_s": 5.0,
        "retry_cooldown_s": 30.0,
    },
    "n8n": {
        "url": "http://localhost:5678",
        "timeout_s": 10.0,
        "fallback_enabled": True,
        "cooldown_s": 30.0,
    },
    "navidrome": {
        "url": "http://localhost:4533",
        "user": "",
        "password": "",
    },
    "music": {
        "default_player": "",
        "room_players": {},
        "playlist_server_host": "192.168.1.70",
        "playlist_server_port": 8765,
    },
    "calibre": {
        "url": "",
        "username": "",
        "password": "",
        "db_path": "",   # Chemin local vers metadata.db (optionnel, plus fiable)
    },
    "shell_exec": {
        "enabled": True,
        # If True, only READ_ONLY allowlist + ADMIN_CONFIRM patterns are accepted.
        # Unknown commands are BLOCKED.  Set False to allow any non-blocked command
        # with confirmation.
        "allowlist_enabled": True,
        # If True, only owner chat_id (telegram.owner_chat_id) can trigger shell_exec.
        "require_owner": False,
        # Additional patterns that require confirmation (on top of hard-coded ones).
        # Each entry is a Python regex string.
        "confirm_required_patterns": [],
        # Additional patterns that are always blocked (on top of hard-coded ones).
        "blocked_patterns": [],
    },
}


class SettingsStore(QObject):
    """
    Thread-safe settings manager with Qt signals for reactive updates.
    """
    
    # Emit when any setting changes: (key_path, new_value)
    setting_changed = Signal(str, object)
    
    def __init__(self):
        super().__init__()
        self._lock = threading.RLock()
        self._settings: Dict[str, Any] = {}
        self._settings_dir = Path.home() / ".pocket_ai"
        self._settings_file = self._settings_dir / "settings.json"
        
        self._load()
    
    def _load(self):
        """Load settings from disk, or initialize defaults."""
        with self._lock:
            if self._settings_file.exists():
                try:
                    with open(self._settings_file, 'r', encoding='utf-8') as f:
                        loaded = json.load(f)
                    # Merge with defaults to handle new settings in updates
                    self._settings = self._deep_merge(DEFAULT_SETTINGS.copy(), loaded)
                except (json.JSONDecodeError, IOError) as e:
                    print(f"[Settings] Error loading settings: {e}. Using defaults.")
                    self._settings = DEFAULT_SETTINGS.copy()
            else:
                self._settings = DEFAULT_SETTINGS.copy()
                self._save()  # Create the file with defaults
    
    def _save(self):
        """Persist settings to disk."""
        with self._lock:
            try:
                self._settings_dir.mkdir(parents=True, exist_ok=True)
                with open(self._settings_file, 'w', encoding='utf-8') as f:
                    json.dump(self._settings, f, indent=2)
            except IOError as e:
                print(f"[Settings] Error saving settings: {e}")
    
    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Recursively merge override into base."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get a setting by dot-notation path.
        Example: get("models.chat") returns the chat model name.
        """
        with self._lock:
            keys = key_path.split('.')
            value = self._settings
            try:
                for k in keys:
                    value = value[k]
                return value
            except (KeyError, TypeError):
                return default
    
    def set(self, key_path: str, value: Any):
        """
        Set a setting by dot-notation path and save.
        Example: set("models.chat", "qwen3:8b")
        """
        with self._lock:
            keys = key_path.split('.')
            target = self._settings
            for k in keys[:-1]:
                if k not in target:
                    target[k] = {}
                target = target[k]
            target[keys[-1]] = value
            self._save()
        
        # Emit signal (outside lock to prevent deadlock)
        self.setting_changed.emit(key_path, value)
    
    def get_all(self) -> Dict[str, Any]:
        """Return a copy of all settings."""
        with self._lock:
            return self._settings.copy()
    
    def reset_to_defaults(self):
        """Reset all settings to defaults."""
        with self._lock:
            self._settings = DEFAULT_SETTINGS.copy()
            self._save()
        self.setting_changed.emit("*", None)


# Global singleton instance
settings = SettingsStore()
