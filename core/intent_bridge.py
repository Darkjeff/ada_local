"""
IntentBridge — normalizes and routes external voice assistant intents to ADA.

This is a placeholder implementation. External voice assistants (Alexa, Google Home,
Home Assistant automations) forward text commands to ADA after their own transcription.
ADA never receives raw audio from these sources.

Privacy guarantee: IntentBridge only ever handles text strings — never audio data.
"""
from __future__ import annotations


class IntentBridge:
    """
    Normalize raw intent payloads from external sources and route to ADA's pipeline.

    Supported payload formats per source:
      home_assistant — {"text": "..."}
      alexa          — {"query": "..."} or nested Alexa request envelope
      google_home    — {"queryText": "..."}
      unknown        — tries "text", then "query"
    """

    def normalize_intent(self, source: str, raw_payload: dict) -> str | None:
        """
        Extract the intent text string from a source-specific payload.

        Returns the intent text, or None if the payload is unrecognized.
        """
        if source == "home_assistant":
            return raw_payload.get("text")

        elif source == "alexa":
            # Support flat {"query": "..."} or nested Alexa request envelope
            if "query" in raw_payload:
                return raw_payload["query"]
            try:
                return raw_payload["request"]["intent"]["slots"]["query"]["value"]
            except (KeyError, TypeError):
                return None

        elif source == "google_home":
            return raw_payload.get("queryText")

        else:
            # Unknown source: try common text keys
            return raw_payload.get("text") or raw_payload.get("query")

    def route_intent(self, intent_text: str) -> None:
        """
        Route a normalized text intent to ADA's processing pipeline.

        Placeholder: logs the intent. Real implementation will invoke the
        function router or chat engine once those APIs are stable.
        """
        print(f"[IntentBridge] Routing intent: {intent_text!r}")


# Global singleton
intent_bridge = IntentBridge()
