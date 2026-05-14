"""
SensesManager — central registry of all ADA voice input/output endpoints.

Device types:
  raw_audio    — direct microphone access (local hardware only)
  intent_input — external voice assistant that sends normalized text intents
                 (Alexa, Google Home via HA automation — NO raw mic access)
  speech_output — TTS output target (local speaker, HA media_player)

Privacy levels:
  local                    — stays on device
  cloud_dependent          — requires cloud service (Amazon, Google)
  local_or_cloud_dependent — HA device (depends on user's HA configuration)

Privacy guarantee: intent_input devices never expose raw audio to ADA.
External assistants transcribe locally then forward text only.
"""
from __future__ import annotations

from typing import Literal

from core.settings_store import settings

DeviceType = Literal["raw_audio", "intent_input", "speech_output"]
PrivacyLevel = Literal["local", "cloud_dependent", "local_or_cloud_dependent"]
DeviceSource = Literal["local", "home_assistant", "google_home", "alexa", "ada_satellite"]


class SensesDevice(dict):
    """
    Typed dict representing one sensory endpoint.

    Required keys:
      id          (str)  — unique identifier within this registry
      name        (str)  — human-readable display name
      device_type (str)  — "raw_audio" | "intent_input" | "speech_output"
      source      (str)  — "local" | "home_assistant" | "google_home" | "alexa" | "ada_satellite"
      privacy     (str)  — "local" | "cloud_dependent" | "local_or_cloud_dependent"
      enabled     (bool) — whether the device is active
      entity_id   (str|None) — HA entity_id for home_assistant devices, else None
    """


class SensesManager:
    """
    Registry of all sensory endpoints. Manages speech dispatch and intent routing.

    Usage:
        from core.senses_manager import senses_manager
        senses_manager.send_speech("Hello!")
        senses_manager.register_device({...})
    """

    def __init__(self):
        self._devices: list[SensesDevice] = []
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register built-in local devices present in every ADA installation."""
        self.register_device({
            "id": "local_mic",
            "name": "Local Microphone",
            "device_type": "raw_audio",
            "source": "local",
            "privacy": "local",
            "enabled": True,
            "entity_id": None,
        })
        self.register_device({
            "id": "local_speaker",
            "name": "Local Speaker",
            "device_type": "speech_output",
            "source": "local",
            "privacy": "local",
            "enabled": True,
            "entity_id": None,
        })

    # ── Registry ───────────────────────────────────────────────────────────

    def register_device(self, device: SensesDevice) -> None:
        """Add or replace a device by id."""
        self._devices = [d for d in self._devices if d["id"] != device["id"]]
        self._devices.append(device)

    def get_devices(self, device_type: DeviceType | None = None) -> list[SensesDevice]:
        """Return all registered devices, optionally filtered by type."""
        if device_type is None:
            return list(self._devices)
        return [d for d in self._devices if d["device_type"] == device_type]

    def get_speech_outputs(self) -> list[SensesDevice]:
        """Return all speech_output devices."""
        return self.get_devices("speech_output")

    def get_intent_inputs(self) -> list[SensesDevice]:
        """Return all intent_input devices."""
        return self.get_devices("intent_input")

    def get_raw_audio_inputs(self) -> list[SensesDevice]:
        """Return all raw_audio devices."""
        return self.get_devices("raw_audio")

    # ── Capability checks ──────────────────────────────────────────────────

    def can_receive_intent(self) -> bool:
        """True if at least one enabled intent_input device is registered."""
        return any(d["enabled"] for d in self.get_intent_inputs())

    def can_send_speech(self) -> bool:
        """True if at least one enabled speech_output device is registered."""
        return any(d["enabled"] for d in self.get_speech_outputs())

    # ── Speech dispatch ────────────────────────────────────────────────────

    def send_speech(self, text: str, target_id: str | None = None) -> bool:
        """
        Dispatch TTS text to an output device.

        If target_id is None, the configured speech_output_mode from settings
        determines the target:
          - "local"          → "local_speaker"
          - "ha_media_player" → device id from settings key "senses.ha_tts_entity"

        Returns True if dispatched successfully, False otherwise.
        """
        if target_id is None:
            mode = settings.get("senses.speech_output_mode", "local")
            if mode == "ha_media_player":
                target_id = settings.get("senses.ha_tts_entity", "")
                if not target_id:
                    target_id = "local_speaker"
            else:
                target_id = "local_speaker"

        devices = [d for d in self._devices if d["id"] == target_id]
        if not devices:
            print(f"[SensesManager] Unknown target device: {target_id!r}")
            return False

        device = devices[0]
        if not device["enabled"]:
            print(f"[SensesManager] Target device is disabled: {target_id!r}")
            return False

        if device["source"] == "local":
            return self._send_local_speech(text)
        elif device["source"] == "home_assistant":
            return self._send_ha_speech(text, device["entity_id"])
        else:
            print(f"[SensesManager] Unsupported source for speech: {device['source']!r}")
            return False

    def _send_local_speech(self, text: str) -> bool:
        """Dispatch to local TTS engine."""
        try:
            from core.tts import tts
            tts.queue_sentence(text)
            return True
        except Exception as e:
            print(f"[SensesManager] Local TTS failed: {e}")
            return False

    def _send_ha_speech(self, text: str, entity_id: str | None) -> bool:
        """Dispatch to HA media_player via tts.speak service."""
        if not entity_id:
            print("[SensesManager] No HA entity_id configured for speech output")
            return False
        try:
            from core.ha_control import ha_manager
            tts_service = settings.get("home_assistant.tts_service", "tts.piper")
            return ha_manager.speak_to_media_player(entity_id, text, tts_service=tts_service)
        except Exception as e:
            print(f"[SensesManager] HA TTS dispatch failed: {e}")
            return False

    # ── Intent routing ─────────────────────────────────────────────────────

    def receive_external_intent(self, source: str, intent_text: str) -> None:
        """
        Called when an external voice assistant sends a text intent.

        Validates that the source is a registered, enabled intent_input device.
        If valid, routes to IntentBridge for processing.

        Privacy: this method only accepts text — never raw audio.
        """
        valid_sources = {d["source"] for d in self.get_intent_inputs() if d["enabled"]}
        if source not in valid_sources:
            print(f"[SensesManager] Rejected intent from unregistered source: {source!r}")
            return
        try:
            from core.intent_bridge import intent_bridge
            intent_bridge.route_intent(intent_text)
        except ImportError:
            print(f"[SensesManager] IntentBridge not available yet — intent dropped: {intent_text!r}")


# Global singleton
senses_manager = SensesManager()
