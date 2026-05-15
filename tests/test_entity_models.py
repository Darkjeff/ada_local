# tests/test_entity_models.py
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestInferZone(unittest.TestCase):

    def test_bureau_keyword(self):
        from core.entity_models import infer_zone
        self.assertEqual(infer_zone("Bureau Desk Light"), "Bureau")

    def test_chambre_keyword(self):
        from core.entity_models import infer_zone
        self.assertEqual(infer_zone("Bedroom Ceiling"), "Chambre")

    def test_cuisine_keyword(self):
        from core.entity_models import infer_zone
        self.assertEqual(infer_zone("Cafetière cuisine"), "Cuisine")

    def test_chillout_keyword(self):
        from core.entity_models import infer_zone
        self.assertEqual(infer_zone("Salon TV"), "Chillout")

    def test_unknown_returns_other(self):
        from core.entity_models import infer_zone
        self.assertEqual(infer_zone("Somewhere Unknown"), "Other")

    def test_case_insensitive(self):
        from core.entity_models import infer_zone
        self.assertEqual(infer_zone("OFFICE LAMP"), "Bureau")


class TestInferCapabilities(unittest.TestCase):

    def test_light_no_extras(self):
        from core.entity_models import infer_capabilities
        caps = infer_capabilities("light", {})
        self.assertIn("read", caps)
        self.assertIn("control", caps)
        self.assertNotIn("brightness", caps)
        self.assertNotIn("color", caps)

    def test_light_with_brightness(self):
        from core.entity_models import infer_capabilities
        caps = infer_capabilities("light", {"brightness": 128})
        self.assertIn("brightness", caps)

    def test_light_with_color(self):
        from core.entity_models import infer_capabilities
        caps = infer_capabilities("light", {"rgb_color": [255, 0, 0]})
        self.assertIn("color", caps)

    def test_read_only_no_control(self):
        from core.entity_models import infer_capabilities
        caps = infer_capabilities("sensor", {}, read_only=True)
        self.assertIn("read", caps)
        self.assertNotIn("control", caps)

    def test_sensor_temperature(self):
        from core.entity_models import infer_capabilities
        caps = infer_capabilities("sensor", {"device_class": "temperature"}, read_only=True)
        self.assertIn("temperature", caps)

    def test_sensor_humidity(self):
        from core.entity_models import infer_capabilities
        caps = infer_capabilities("sensor", {"device_class": "humidity"}, read_only=True)
        self.assertIn("humidity", caps)

    def test_media_player_has_tts(self):
        from core.entity_models import infer_capabilities
        caps = infer_capabilities("media_player", {})
        self.assertIn("tts", caps)

    def test_media_player_volume(self):
        from core.entity_models import infer_capabilities
        caps = infer_capabilities("media_player", {"volume_level": 0.5})
        self.assertIn("volume", caps)

    def test_camera_snapshot(self):
        from core.entity_models import infer_capabilities
        caps = infer_capabilities("camera", {}, read_only=True)
        self.assertIn("snapshot", caps)


class TestHaDomainToEntityType(unittest.TestCase):

    def test_light(self):
        from core.entity_models import ha_domain_to_entity_type
        self.assertEqual(ha_domain_to_entity_type("light"), "light")

    def test_binary_sensor(self):
        from core.entity_models import ha_domain_to_entity_type
        self.assertEqual(ha_domain_to_entity_type("binary_sensor"), "binary_sensor")

    def test_unknown_domain(self):
        from core.entity_models import ha_domain_to_entity_type
        self.assertEqual(ha_domain_to_entity_type("vacuum"), "unknown")

    def test_media_player(self):
        from core.entity_models import ha_domain_to_entity_type
        self.assertEqual(ha_domain_to_entity_type("media_player"), "media_player")


class TestEntityDataclass(unittest.TestCase):

    def test_entity_creation(self):
        from core.entity_models import Entity
        e = Entity(
            id="kasa.192.168.1.1",
            provider="kasa",
            provider_entity_id="192.168.1.1",
            name="Office Light",
            type="light",
            zone="Bureau",
            state="on",
        )
        self.assertEqual(e.id, "kasa.192.168.1.1")
        self.assertEqual(e.zone, "Bureau")
        self.assertFalse(e.read_only)
        self.assertTrue(e.available)

    def test_provider_creation(self):
        from core.entity_models import Provider
        p = Provider(id="kasa", name="Kasa", enabled=True, type="kasa")
        self.assertEqual(p.status, "unknown")
        self.assertEqual(p.capabilities, [])


if __name__ == "__main__":
    unittest.main()
