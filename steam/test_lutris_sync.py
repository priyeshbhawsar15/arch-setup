"""Use installed Lutris APIs with isolated user data; never start its GUI."""
import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("hdr_fixture", ROOT / "steam/configure-gamescope-hdr.py")
hdr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hdr)


@unittest.skipUnless(importlib.util.find_spec("lutris"), "System Lutris libraries are required")
class LutrisSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.data = self.home / "data"
        self.env = dict(os.environ, HOME=str(self.home), XDG_DATA_HOME=str(self.data),
                        XDG_CONFIG_HOME=str(self.home / "config"), XDG_CACHE_HOME=str(self.home / "cache"),
                        PYTHONDONTWRITEBYTECODE="1")
        self.env.pop("STEAM_EXTRA_COMPAT_TOOLS_PATHS", None)
        commands = self.home / "bin"
        commands.mkdir()
        pgrep = commands / "pgrep"
        pgrep.write_text('#!/bin/bash\n[[ -e "$HOME/active-lutris" ]]\n')
        pgrep.chmod(0o755)
        self.env["PATH"] = str(commands) + ":/usr/bin"
        self.steam = self.home / ".local/share/Steam"
        (self.steam / "steamapps").mkdir(parents=True)

    def python(self, *args):
        return subprocess.run(["/usr/bin/python3", *args], env=self.env, capture_output=True, text=True, timeout=30)

    def sync(self):
        return self.python(str(ROOT / "steam/sync-lutris-steam.py"))

    def test_fresh_profile_initializes_database_before_importing_games(self):
        (self.steam / "steamapps/appmanifest_123.acf").write_text(
            '"AppState"\n{\n"appid" "123"\n"name" "Fixture Game"\n"StateFlags" "4"\n}\n')
        result = self.sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        with sqlite3.connect(self.data / "lutris/pga.db") as connection:
            self.assertEqual(connection.execute("select name from games where installer_slug='steam-123'").fetchone(),
                             ("Fixture Game",))

    def test_selected_profile_loads_through_lutris_in_both_directory_layouts(self):
        import json
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                root = self.home / ('legacy' if legacy else 'modern')
                env = dict(self.env, HOME=str(root), XDG_CONFIG_HOME=str(root / 'config'),
                           XDG_DATA_HOME=str(root / 'data'), XDG_STATE_HOME=str(root / 'state'),
                           XDG_CACHE_HOME=str(root / 'cache'))
                if legacy:
                    (root / 'config/lutris').mkdir(parents=True)
                executable = root / 'library/game/bin/x64/Cyberpunk2077.exe'
                executable.parent.mkdir(parents=True)
                executable.touch()
                selection = root / 'selection.json'
                selection.write_text(json.dumps({'schemaVersion': 1, 'libraries': {'primary': str(root / 'library')},
                    'games': {'cyberpunk-2077': {'library': 'primary', 'path': 'game', 'desktop': legacy}}}))
                env['ARCH_SETUPS_GAMING_PROFILE'] = str(selection)
                for args in ([str(ROOT / 'steam/sync-lutris-steam.py'), '--initialize-only'],
                             [str(ROOT / 'steam/configure-gaming-profile.py'), '--apply']):
                    result = subprocess.run(['/usr/bin/python3', *args], env=env, capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                result = subprocess.run(['/usr/bin/python3', '-c', '''from lutris import settings
from lutris.config import LutrisConfig
from pathlib import Path
config = LutrisConfig(runner_slug='wine', game_config_id='arch-profile-steam-shortcut-3013353202')
assert config.game_config['exe'].endswith('/game/bin/x64/Cyberpunk2077.exe'), config.game_config
print(settings.GAME_CONFIG_DIR)
'''], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(str(root / ('config/lutris/games' if legacy else 'data/lutris/games')), result.stdout)

    def test_active_lutris_refuses_sync_before_creating_user_state(self):
        (self.home / "active-lutris").touch()
        result = self.sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Close Lutris", result.stderr)
        self.assertFalse((self.data / "lutris/pga.db").exists())

    def seed_shortcut(self):
        path = self.steam / "userdata/1/config/shortcuts.vdf"
        path.parent.mkdir(parents=True)
        tree = {"shortcuts": (0, {"0": (0, {"AppName": (1, "Example"), "Exe": (1, "/games/example.exe"),
                  "appid": (2, 123), "LaunchOptions": (1, "PROTON_LOG=1 %command% -dx11")})})}
        path.write_bytes(hdr.serialize_binary_vdf(tree) + b"\x08")
        seed = self.python("-c", '''from lutris import settings
from lutris.database.schema import syncdb
from lutris.database.games import add_game
from lutris.util.system import create_folder
for directory in (settings.DATA_DIR, settings.CONFIG_DIR, settings.GAME_CONFIG_DIR):
    create_folder(directory)
syncdb()
add_game(name='Example', runner='steam', slug='example', installed=1,
         installer_slug='steam-shortcut-123', configpath='existing', platform='Windows')
''')
        self.assertEqual(seed.returncode, 0, seed.stderr)
        self.path = self.data / "lutris/games/existing.yml"
        self.original = ('game:\n  working_dir: /custom/workdir\nsystem:\n  gamemode: false\n'
                         '  env:\n    CUSTOM_SETTING: preserved\nsteam:\n  start_in_big_picture: true\n')
        self.path.write_text(self.original)

    def test_existing_game_preserves_unmanaged_fields_and_backs_up_changes(self):
        import yaml
        self.seed_shortcut()
        result = self.sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        content = yaml.safe_load(self.path.read_text())
        self.assertEqual(content["game"].get("working_dir"), "/custom/workdir")
        self.assertIs(content["system"].get("gamemode"), False)
        self.assertEqual(content["system"]["env"], {"CUSTOM_SETTING": "preserved", "PROTON_LOG": "1"})
        self.assertTrue(content["steam"]["start_in_big_picture"])
        self.assertEqual(content["game"]["args"], "-dx11")
        backups = list(self.path.parent.glob("existing.yml.bak-steam-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), self.original)
        unchanged = self.path.stat().st_mtime_ns
        second = self.sync()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.path.stat().st_mtime_ns, unchanged)
        self.assertEqual(len(list(self.path.parent.glob("existing.yml.bak-steam-*"))), 1)

    def test_malformed_existing_yaml_is_preserved_and_failure_is_visible(self):
        self.seed_shortcut()
        self.path.write_text("game: [unterminated")
        result = self.sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.path.read_text(), "game: [unterminated")

