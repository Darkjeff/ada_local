"""
Tests for core/intent_bridge.py — intent normalization.

Run: python -m pytest tests/test_intent_bridge.py -v
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestNormalizeIntent(unittest.TestCase):

    def setUp(self):
        from core.intent_bridge import IntentBridge
        self.ib = IntentBridge()

    def test_home_assistant_source_extracts_text(self):
        """HA payload uses key 'text'."""
        result = self.ib.normalize_intent("home_assistant", {"text": "turn on the lights"})
        self.assertEqual(result, "turn on the lights")

    def test_alexa_flat_payload_extracts_query(self):
        """Flat Alexa payload uses key 'query'."""
        result = self.ib.normalize_intent("alexa", {"query": "set a timer"})
        self.assertEqual(result, "set a timer")

    def test_alexa_nested_payload_extracts_slot_value(self):
        """Nested Alexa payload traverses request.intent.slots.query.value."""
        payload = {
            "request": {
                "intent": {
                    "slots": {
                        "query": {"value": "play jazz music"}
                    }
                }
            }
        }
        result = self.ib.normalize_intent("alexa", payload)
        self.assertEqual(result, "play jazz music")

    def test_google_home_extracts_query_text(self):
        """Google Home payload uses key 'queryText'."""
        result = self.ib.normalize_intent("google_home", {"queryText": "what is the weather?"})
        self.assertEqual(result, "what is the weather?")

    def test_unknown_source_falls_back_to_text(self):
        """Unknown source tries 'text' key first."""
        result = self.ib.normalize_intent("unknown_source", {"text": "hello ada"})
        self.assertEqual(result, "hello ada")

    def test_unknown_source_falls_back_to_query(self):
        """Unknown source falls back to 'query' if 'text' is absent."""
        result = self.ib.normalize_intent("unknown_source", {"query": "hello ada"})
        self.assertEqual(result, "hello ada")

    def test_returns_none_for_empty_ha_payload(self):
        """Returns None when HA payload has no 'text' key."""
        result = self.ib.normalize_intent("home_assistant", {})
        self.assertIsNone(result)

    def test_returns_none_for_malformed_alexa_payload(self):
        """Returns None for Alexa payload with no 'query' and malformed nested dict."""
        result = self.ib.normalize_intent("alexa", {"request": {}})
        self.assertIsNone(result)


class TestRouteIntent(unittest.TestCase):

    def test_route_intent_does_not_raise(self):
        """route_intent() runs without error (placeholder implementation)."""
        from core.intent_bridge import IntentBridge
        ib = IntentBridge()
        ib.route_intent("turn on the kitchen light")

    def test_route_intent_singleton_does_not_raise(self):
        """Global intent_bridge singleton works without error."""
        from core.intent_bridge import intent_bridge
        intent_bridge.route_intent("test intent")


if __name__ == '__main__':
    unittest.main()
