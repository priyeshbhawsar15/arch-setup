import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('gaming_profile', HERE / 'configure-gaming-profile.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class GamingProfileTests(unittest.TestCase):
    def test_manifest_has_current_choices(self):
        data = json.loads((m.PROFILE / 'games.json').read_text())
        games = {g['name']: g for g in data['games']}
        self.assertEqual(len(games), 13)
        self.assertFalse(games['TS4_x64.exe']['desktop'])
        for name in ('HS2', 'KS'):
            self.assertNotIn('artwork', games[name])
            self.assertIsNone(games[name]['year'])
            self.assertIn('3840', games[name]['config']['game']['args'])
        self.assertEqual(len([g for g in games.values() if g.get('upscaler')]), 5)
        for asset in data['assets']:
            self.assertEqual(len(asset['sha256']), 64)
            self.assertNotIn('/latest/', asset['url'])
        self.assertTrue({3425461811, 2395607006}.issubset(m.shortcut_ids(data)))

    def test_merge_preserves_unmanaged_and_removes_steam_launcher(self):
        original = {'game': {'appid': '123', 'steamless_binary': 'old', 'custom': 'keep'}, 'system': {'env': {'CUSTOM': 'yes'}}}
        desired = {'game': {'exe': '/game.exe'}, 'system': {'prefix_command': 'gamescope', 'env': {'WINEDLLOVERRIDES': 'dxgi=n,b'}}}
        result = m.merge_config(original, desired)
        self.assertNotIn('appid', result['game'])
        self.assertEqual(result['game']['custom'], 'keep')
        self.assertEqual(result['system']['env']['CUSTOM'], 'yes')
        self.assertEqual(result['system']['prefix_command'], 'gamescope')
        self.assertIn('appid', original['game'])
        self.assertEqual(result, m.merge_config(result, desired))

    def test_ini_settings_and_no_forced_fsr4update(self):
        for filename, vulkan in [('OptiScaler-0.9.4.ini', False), ('OptiScaler-fsr4vk-0.4.3.ini', True)]:
            ini = m.configured_ini((m.PROFILE / filename).read_text(), vulkan)
            self.assertIn('\nShortcutKey=0x08\n', ini)
            self.assertIn('UseHQFont=false', ini)
            self.assertNotIn('Fsr4Update=true', ini)
            self.assertIn('VulkanUpscaler=ffx' if vulkan else 'Fsr4ForceEnableInt8=true', ini)

    def test_utf16_setup_4k_idempotent(self):
        data = '<Setup><Width>1600</Width><Height>900</Height><FullScreen>false</FullScreen></Setup>'.encode('utf-16')
        updated = m.setup_4k(data)
        self.assertTrue(updated.startswith(b'\xff\xfe'))
        self.assertIn('<Width>3840</Width>', updated.decode('utf-16'))
        self.assertEqual(updated, m.setup_4k(updated))

    def test_checksum_rejects_download_without_replacing_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer = m.Installer(Path(tmp))
            def download(url, path):
                Path(path).write_bytes(b'untrusted')
            with patch.object(m.urllib.request, 'urlretrieve', side_effect=download):
                with self.assertRaisesRegex(ValueError, 'SHA256'):
                    installer.asset({'name': 'test.zip', 'url': 'https://example.org/test', 'sha256': '0' * 64})
            self.assertFalse((Path(tmp) / '.cache/arch-setups/gaming/test.zip').exists())

    def test_apply_twice_dynamic_ids_no_live_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Path(tmp)
            root = h / '.local/share/lutris'
            root.mkdir(parents=True)
            exe = h / 'game/game.exe'
            exe.parent.mkdir()
            exe.touch()
            with contextlib.closing(sqlite3.connect(root / 'pga.db')) as con, con:
                con.execute('CREATE TABLE games (id INTEGER PRIMARY KEY, name TEXT, slug TEXT, runner TEXT, executable TEXT, directory TEXT, installed INTEGER, installer_slug TEXT, year INTEGER, configpath TEXT, has_custom_banner INTEGER, has_custom_icon INTEGER, has_custom_coverart_big INTEGER)')
                con.execute("INSERT INTO games (id,name,slug) VALUES (99,'unrelated','unrelated')")
            appdir = h / '.local/share/applications'
            appdir.mkdir(parents=True)
            qbit = appdir / 'qBittorrent.desktop'
            qbit.write_text('[Desktop Entry]\nName=Old\nExec=keep-url\n')
            game = {'key': 'test', 'name': 'Test', 'slug': 'test', 'runner': 'wine', 'year': None, 'desktop': True,
                    'config': {'game': {'exe': '${HOME}/game/game.exe', 'working_dir': '${HOME}/game'}, 'system': {'env': {'WINEDLLOVERRIDES': 'dxgi=n,b'}}}}
            profile = {'games': [game], 'retired_shortcuts': [], 'assets': []}
            with patch.object(m.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)), patch.object(m.subprocess, 'check_output', return_value=''), contextlib.redirect_stdout(io.StringIO()) as output:
                m.apply(profile, h, False)
                before = {p: p.stat().st_mtime_ns for p in h.rglob('*') if p.is_file()}
                m.apply(profile, h, False)
                after = {p: p.stat().st_mtime_ns for p in h.rglob('*') if p.is_file()}
            self.assertEqual(before, after)
            self.assertIn('already installed', output.getvalue())
            self.assertIn('lutris:rungameid/100', (appdir / 'lutris-test.desktop').read_text())
            self.assertIn('Name=qBittorrent Web', qbit.read_text())
            self.assertIn('Exec=keep-url', qbit.read_text())
            with contextlib.closing(sqlite3.connect(root / 'pga.db')) as con:
                self.assertEqual(con.execute('SELECT count(*) FROM games').fetchone()[0], 2)

    def test_links_never_replace_user_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            inst = m.Installer(home)
            target = home / 'target'
            target.mkdir()
            link = home / 'games-links/game'
            inst.link(link, target)
            self.assertTrue(link.is_symlink())
            count = inst.changed
            inst.link(link, target)
            self.assertEqual(inst.changed, count)
            user_file = home / 'custom'
            user_file.write_text('preserve')
            with contextlib.redirect_stdout(io.StringIO()):
                inst.link(user_file, target)
            self.assertEqual(user_file.read_text(), 'preserve')

    def test_atomic_backup_and_idempotence(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            p = home / 'file'
            inst = m.Installer(home)
            inst.save(p, b'old')
            inst.save(p, b'new')
            self.assertEqual((inst.backup / 'files' / str(p).lstrip('/')).read_bytes(), b'old')
            count = inst.changed
            inst.save(p, b'new')
            self.assertEqual(inst.changed, count)


if __name__ == '__main__':
    unittest.main()
