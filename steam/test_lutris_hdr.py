"""Blanket Lutris HDR: python3 -m unittest discover -s steam -p 'test_lutris_hdr.py'."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

SCRIPT = Path(__file__).with_name('configure-lutris-hdr.py')
LEGACY = 'gamescope -w 3840 -h 2160 -W 3840 -H 2160 -r 120 -f --hdr-enabled --hdr-sdr-content-nits 203 --'


class LutrisHdrTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.games, self.state = root / 'games', root / 'state'
        self.games.mkdir()
        bin_dir = root / 'bin'
        bin_dir.mkdir()
        (bin_dir / 'pgrep').write_text('#!/bin/sh\nexit 1\n')  # Lutris is closed
        (bin_dir / 'pgrep').chmod(0o755)
        self.env = dict(os.environ, XDG_STATE_HOME=str(self.state), PATH=f'{bin_dir}:/usr/bin')
        self.write('plain', {'game': {'exe': '/g/Game.exe', 'prefix': '/p'}, 'system': {'env': {'KEEP': '1'}}})
        self.write('legacy', {'game': {'exe': '/g/Launcher.exe'}, 'system': {'prefix_command': LEGACY}})
        self.write('custom', {'game': {'exe': '/g/Other.exe'}, 'system': {'prefix_command': 'gamemoderun'}})
        self.write('steam', {'game': {'appid': '322330'}, 'system': {}})
        self.write('native', {'game': {'exe': '/g/launch.sh'}})
        self.write('store', {'game': {'exe': '/g/EpicGamesLauncher.exe'}})
        self.write('wrapped', {'game': {'exe': '/g/Done.exe'}, 'system': {'prefix_command': 'steam-gamescope-hdr'}})
        self.originals = {path.name: path.read_bytes() for path in self.games.glob('*.yml')}

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, name, config):
        (self.games / f'{name}.yml').write_text(yaml.safe_dump(config, sort_keys=False))

    def read(self, name):
        return yaml.safe_load((self.games / f'{name}.yml').read_text())

    def run_script(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), '--games-dir', str(self.games), *args],
                              env=self.env, capture_output=True, text=True)

    def test_wraps_windows_games_only_and_round_trips(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read('plain')['system'], {'env': {'KEEP': '1'}, 'prefix_command': 'steam-gamescope-hdr'})
        self.assertEqual(self.read('legacy')['system']['prefix_command'], 'steam-gamescope-hdr')
        self.assertIn('Kept user-owned prefix command', result.stdout)
        for untouched in ('custom', 'steam', 'native', 'store', 'wrapped'):
            self.assertEqual((self.games / f'{untouched}.yml').read_bytes(), self.originals[f'{untouched}.yml'])
        self.assertEqual(len(list(self.games.glob('*.bak-hdr-*'))), 2)
        ledger = json.loads((self.state / 'arch-setups/games/lutris-hdr.json').read_text())
        self.assertEqual(ledger, {'legacy.yml': {'previous': LEGACY}, 'plain.yml': {'previous': None}})
        again = self.run_script()
        self.assertIn('already match', again.stdout)
        self.assertEqual(len(list(self.games.glob('*.bak-hdr-*'))), 2)
        removed = self.run_script('--remove')
        self.assertEqual(removed.returncode, 0, removed.stderr)
        for name, content in self.originals.items():
            self.assertEqual(yaml.safe_load((self.games / name).read_bytes()), yaml.safe_load(content))
        self.assertFalse((self.state / 'arch-setups/games/lutris-hdr.json').exists())

    def test_remove_keeps_user_changes_and_running_lutris_blocks_edits(self):
        self.run_script()
        self.write('plain', {'game': {'exe': '/g/Game.exe'}, 'system': {'prefix_command': 'mine'}})
        self.run_script('--remove')
        self.assertEqual(self.read('plain')['system']['prefix_command'], 'mine')
        self.assertEqual(self.read('legacy')['system']['prefix_command'], LEGACY)
        (Path(self.env['PATH'].split(':')[0]) / 'pgrep').write_text('#!/bin/sh\nexit 0\n')
        blocked = self.run_script()
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn('close Lutris', blocked.stderr)
        self.assertEqual(self.read('legacy')['system']['prefix_command'], LEGACY)


if __name__ == '__main__':
    unittest.main()
