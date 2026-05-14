r"""
Tests that senses defaults are present in DEFAULT_SETTINGS.

Run: C:\Users\Darkjeff\AppData\Roaming\uv\python\cpython-3.14-windows-x86_64-none\python.exe -m unittest tests.test_senses_settings -v
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestSensesDefaults(unittest.TestCase):

    def _get_defaults(self) -> dict:
        # Extract DEFAULT_SETTINGS dict from settings_store.py
        # without executing the module (which requires PySide6, etc.)
        import ast

        settings_file = os.path.join(os.path.dirname(__file__), '..', 'core', 'settings_store.py')
        with open(settings_file, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())

        # Find the DEFAULT_SETTINGS assignment
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == 'DEFAULT_SETTINGS':
                        # Evaluate the dict literal
                        return ast.literal_eval(node.value)

        raise RuntimeError("DEFAULT_SETTINGS not found in settings_store.py")

    def test_senses_key_exists(self):
        """DEFAULT_SETTINGS has a 'senses' top-level key."""
        defaults = self._get_defaults()
        self.assertIn('senses', defaults)

    def test_camera_index_default(self):
        """senses.camera_index defaults to 0 (first/only webcam)."""
        defaults = self._get_defaults()
        self.assertEqual(defaults['senses']['camera_index'], 0)

    def test_audio_input_device_default(self):
        """senses.audio_input_device defaults to -1 (system default)."""
        defaults = self._get_defaults()
        self.assertEqual(defaults['senses']['audio_input_device'], -1)

    def test_audio_output_device_default(self):
        """senses.audio_output_device defaults to -1 (system default)."""
        defaults = self._get_defaults()
        self.assertEqual(defaults['senses']['audio_output_device'], -1)

    def test_all_values_are_integers(self):
        """All senses defaults are integers."""
        defaults = self._get_defaults()
        for key, val in defaults['senses'].items():
            self.assertIsInstance(val, int, f"senses.{key} should be int, got {type(val)}")


if __name__ == '__main__':
    unittest.main()
