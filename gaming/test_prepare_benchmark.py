import importlib.util
from pathlib import Path
import stat
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('benchmark', Path(__file__).with_name('prepare-cyberpunk-benchmark.py'))
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class PrepareTests(unittest.TestCase):
    def test_private_opt_in_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = benchmark.prepare(Path(temporary) / 'benchmark')
            target = Path(result['profile'])
            text = target.read_text()
            self.assertIn('log_interval=0\n', text)
            self.assertIn('permit_upload=0\n', text)
            self.assertIn('no_display\n', text)
            self.assertNotIn('fps_limit=', text)
            self.assertFalse(result['activated'])
            self.assertFalse(result['game_settings_changed'])
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(target.parent.stat().st_mode), 0o700)
            self.assertIn('steam-gamescope-hdr env MANGOHUD=1', result['proposed_prefix'])
            self.assertFalse(benchmark.prepare(target.parent)['changed'])

    def test_foreign_profile_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'MangoHud.conf'
            target.write_text('custom profile')
            with self.assertRaises(ValueError):
                benchmark.prepare(Path(temporary))
            self.assertEqual(target.read_text(), 'custom profile')

    def test_symlink_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'MangoHud.conf'
            other = Path(temporary) / 'other'
            other.write_text('keep')
            target.symlink_to(other)
            with self.assertRaises(ValueError):
                benchmark.prepare(Path(temporary))
            self.assertEqual(other.read_text(), 'keep')

    def test_invalid_output_path(self):
        for path in ['relative', '/tmp/bad\npath']:
            with self.assertRaises(ValueError):
                benchmark.profile_text(path)


if __name__ == '__main__':
    unittest.main()
