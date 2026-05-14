"""
Tests for core/device_enumerator.py

Run: python -m pytest tests/test_device_enumerator.py -v
  or: python -m unittest tests.test_device_enumerator -v
"""
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Add core directory to path to bypass package init (avoids loading tts/sounddevice)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../core')))


class TestListCameras(unittest.TestCase):

    def test_returns_list(self):
        """list_cameras() always returns a list, even with no cameras."""
        from device_enumerator import list_cameras
        result = list_cameras()
        self.assertIsInstance(result, list)

    def test_returns_empty_when_cv2_absent(self):
        """list_cameras() returns [] when cv2 is not installed."""
        original = sys.modules.pop('device_enumerator', None)
        with patch.dict('sys.modules', {'cv2': None}):
            if 'device_enumerator' in sys.modules:
                del sys.modules['device_enumerator']
            from device_enumerator import list_cameras
            result = list_cameras()
        # Restore original module if it existed
        if original:
            sys.modules['device_enumerator'] = original
        self.assertIsInstance(result, list)

    def test_structure_with_mocked_camera(self):
        """Each entry has 'index' (int) and 'name' (str)."""
        mock_cv2 = MagicMock()
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True

        def make_cap(idx):
            c = MagicMock()
            # Only camera index 0 opens successfully
            c.isOpened.return_value = (idx == 0)
            return c

        mock_cv2.VideoCapture.side_effect = make_cap

        # Reload module with mock
        if 'device_enumerator' in sys.modules:
            del sys.modules['device_enumerator']
        with patch.dict('sys.modules', {'cv2': mock_cv2}):
            from device_enumerator import list_cameras
            result = list_cameras()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['index'], 0)
        self.assertIsInstance(result[0]['name'], str)
        self.assertIn('0', result[0]['name'])  # "Camera 0"

    def test_releases_each_capture(self):
        """list_cameras() calls cap.release() for each opened camera."""
        mock_cv2 = MagicMock()
        released = []

        def make_cap(idx):
            c = MagicMock()
            c.isOpened.return_value = (idx == 0)
            c.release.side_effect = lambda: released.append(idx)
            return c

        mock_cv2.VideoCapture.side_effect = make_cap

        if 'device_enumerator' in sys.modules:
            del sys.modules['device_enumerator']
        with patch.dict('sys.modules', {'cv2': mock_cv2}):
            from device_enumerator import list_cameras
            list_cameras()

        self.assertIn(0, released)


class TestListAudioInputs(unittest.TestCase):

    def test_returns_list(self):
        """list_audio_inputs() always returns a list."""
        from device_enumerator import list_audio_inputs
        result = list_audio_inputs()
        self.assertIsInstance(result, list)

    def test_filters_input_devices_only(self):
        """Only devices with max_input_channels > 0 are returned."""
        mock_sd = MagicMock()
        mock_sd.query_devices.return_value = [
            {"name": "Microphone", "max_input_channels": 2, "max_output_channels": 0},
            {"name": "Speakers",   "max_input_channels": 0, "max_output_channels": 2},
            {"name": "Headset In", "max_input_channels": 1, "max_output_channels": 1},
        ]
        if 'device_enumerator' in sys.modules:
            del sys.modules['device_enumerator']
        with patch.dict('sys.modules', {'sounddevice': mock_sd}):
            from device_enumerator import list_audio_inputs
            result = list_audio_inputs()

        names = [d['name'] for d in result]
        self.assertIn('Microphone', names)
        self.assertIn('Headset In', names)
        self.assertNotIn('Speakers', names)

    def test_structure(self):
        """Each entry has 'index' (int) and 'name' (str)."""
        mock_sd = MagicMock()
        mock_sd.query_devices.return_value = [
            {"name": "Mic", "max_input_channels": 1, "max_output_channels": 0},
        ]
        if 'device_enumerator' in sys.modules:
            del sys.modules['device_enumerator']
        with patch.dict('sys.modules', {'sounddevice': mock_sd}):
            from device_enumerator import list_audio_inputs
            result = list_audio_inputs()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['index'], 0)
        self.assertEqual(result[0]['name'], 'Mic')

    def test_returns_empty_when_sounddevice_absent(self):
        """list_audio_inputs() returns [] when sounddevice raises."""
        from device_enumerator import list_audio_inputs
        with patch('device_enumerator._query_audio_devices',
                   side_effect=Exception("no sounddevice")):
            result = list_audio_inputs()
        self.assertEqual(result, [])


class TestListAudioOutputs(unittest.TestCase):

    def test_returns_list(self):
        """list_audio_outputs() always returns a list."""
        from device_enumerator import list_audio_outputs
        result = list_audio_outputs()
        self.assertIsInstance(result, list)

    def test_filters_output_devices_only(self):
        """Only devices with max_output_channels > 0 are returned."""
        mock_sd = MagicMock()
        mock_sd.query_devices.return_value = [
            {"name": "Microphone", "max_input_channels": 2, "max_output_channels": 0},
            {"name": "Speakers",   "max_input_channels": 0, "max_output_channels": 2},
            {"name": "Headset",    "max_input_channels": 1, "max_output_channels": 1},
        ]
        if 'device_enumerator' in sys.modules:
            del sys.modules['device_enumerator']
        with patch.dict('sys.modules', {'sounddevice': mock_sd}):
            from device_enumerator import list_audio_outputs
            result = list_audio_outputs()

        names = [d['name'] for d in result]
        self.assertIn('Speakers', names)
        self.assertIn('Headset', names)
        self.assertNotIn('Microphone', names)


if __name__ == '__main__':
    unittest.main()
