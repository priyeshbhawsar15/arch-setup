"""Regression checks: python3 -m unittest discover -s steam -p 'test_*.py'."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('config', Path(__file__).with_name('configure-gamescope-hdr.py'))
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


class LaunchTests(unittest.TestCase):
    def test_wrap_and_idempotency(self):
        for val in ('', 'PROTON_LOG=1 %command% -vulkan',
                    'env -u XMODIFIERS steam-gamescope-hdr %command%',
                    'DXVK_HDR=1 gamescope -w 1280 -h 720 -W 1920 -H 1080 -r 120 -f -F fsr --fsr-sharpness 2 -- %command% -vulkan'):
            result = config.wrap_launch_options(val)
            self.assertEqual(result, config.wrap_launch_options(result))
            self.assertEqual(result.count('%command%'), 1)
            if 'gamescope -' in result:
                self.assertIn('-w 3840 -h 2160 -W 3840 -H 2160', result)
                self.assertNotIn('fsr', result)
                self.assertIn('-r 120', result)
                self.assertTrue(result.endswith('%command% -vulkan'))

    def test_shortcuts_backup_preservation(self):
        tree = {'shortcuts': (0, {'0': (0, {'AppName': (1, 'Test Game'),
                'Exe': (1, '"/games/Game.exe"'), 'appid': (2, 123),
                'LaunchOptions': (1, 'PROTON_LOG=1 %command%')}),
                '1': (0, {'Exe': (1, '/usr/bin/tool'), 'LaunchOptions': (1, '')})})}
        original = config.serialize_binary_vdf(tree) + b'\x08'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'shortcuts.vdf'
            path.write_bytes(original)
            self.assertTrue(config.process_shortcuts_vdf(path)[0])
            updated = config.parse_binary_vdf(path.read_bytes())['shortcuts'][1]
            self.assertEqual(updated['0'][1]['appid'], (2, 123))
            self.assertEqual(updated['1'], tree['shortcuts'][1]['1'])
            self.assertEqual(next(path.parent.glob('*.bak-4k-*')).read_bytes(), original)
            self.assertFalse(config.process_shortcuts_vdf(path)[0])

    def test_halo_proton_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shortcuts = root / 'userdata/1/config/shortcuts.vdf'
            shortcuts.parent.mkdir(parents=True)
            tree = {'shortcuts': (0, {'0': (0, {'Exe': (1, '/games/HaloCampaignEvolved.exe'),
                                               'appid': (2, 3834757053)})})}
            shortcuts.write_bytes(config.serialize_binary_vdf(tree) + b'\x08')
            settings = root / 'config/config.vdf'
            settings.parent.mkdir()
            settings.write_text('"Root"\n{\n"CompatToolMapping"\n{\n}\n}\n')
            self.assertTrue(config.configure_halo_proton(root))
            self.assertIn('proton_experimental', settings.read_text())
            self.assertFalse(config.configure_halo_proton(root))
            self.assertEqual(settings.read_text().count('3834757053'), 1)

    def test_bad_vdf_not_written(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'shortcuts.vdf'
            path.write_bytes(b'\x01unterminated')
            with self.assertRaises(ValueError):
                config.process_shortcuts_vdf(path)
            self.assertEqual(path.read_bytes(), b'\x01unterminated')
