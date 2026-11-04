import argparse
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('export_lutris', Path(__file__).with_name('export-lutris-steam.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ExportTests(unittest.TestCase):
    def game(self):
        return dict(id=7, name='A game', slug='a-game', configpath='steam-shortcut-3681072528-123', runner='wine')

    def test_preserves_existing_id_tags_and_unrelated_fields(self):
        entries = {'0': dict(appid=m.signed(3681072528), AppName='Old', Exe='game.exe',
                             LaunchOptions='gamescope %command%', tags={'0': 'Favorites'}, LastPlayTime=123)}
        aid = m.merge_game(self.game(), entries, '/icon.png')
        self.assertEqual(aid, 3681072528)
        self.assertEqual(entries['0']['LastPlayTime'], 123)
        self.assertEqual(entries['0']['tags']['0'], 'Favorites')
        self.assertEqual(entries['0']['LaunchOptions'], 'lutris:rungameid/7')
        self.assertEqual(entries['0']['Exe'], '"/usr/bin/lutris"')
        again = json.dumps(entries)
        m.merge_game(self.game(), entries, '/icon.png')
        self.assertEqual(json.dumps(entries), again)

    def test_metadata_exclusion_restores_source_name_and_empty_icon(self):
        game = dict(self.game(), slug='ts4_x64exe', name='TS4_x64.exe')
        entries = {'0': dict(appid=m.signed(3681072528), AppName='The Sims 4', icon='/new/cover.jpg',
                             tags={'0': 'Favorites', '1': 'Lutris backend'})}
        m.merge_game(game, entries, '/new/cover.jpg')
        self.assertEqual(entries['0']['AppName'], 'TS4_x64.exe')
        self.assertEqual(entries['0']['icon'], '')
        self.assertEqual(entries['0']['tags'], {'0': 'Favorites'})
        self.assertEqual(entries['0']['LaunchOptions'], 'lutris:rungameid/7')

    def test_owned_art_removal_preserves_user_changes(self):
        import hashlib
        with tempfile.TemporaryDirectory() as td, patch.object(m, 'STATE', Path(td) / 'state'):
            grid = Path(td) / 'grid'
            grid.mkdir()
            owned_file = grid / '123p.jpg'
            modified_file = grid / '123_hero.jpg'
            owned_file.write_bytes(b'generated')
            modified_file.write_bytes(b'user changed')
            owned = {str(owned_file): hashlib.sha256(b'generated').hexdigest(),
                     str(modified_file): hashlib.sha256(b'old').hexdigest()}
            writer = m.Writer()
            m.remove_owned_art(writer, 123, grid, owned)
            self.assertFalse(owned_file.exists())
            self.assertTrue(modified_file.exists())
            self.assertIn(str(modified_file), owned)
            self.assertEqual((writer.backup / str(owned_file).lstrip('/')).read_bytes(), b'generated')

    def test_new_entry_is_stable_without_duplicates(self):
        game = dict(self.game(), configpath='local-game')
        entries = {}
        aid = m.merge_game(game, entries, '')
        self.assertGreaterEqual(aid, 0x80000000)
        self.assertEqual(m.merge_game(game, entries, ''), aid)
        self.assertEqual(len(entries), 1)
        self.assertEqual(m.vdf.binary_loads(m.vdf.binary_dumps({'shortcuts': entries})), {'shortcuts': entries})

    def test_duplicate_matching_entries_rejected(self):
        entries = {'0': dict(appid=m.signed(3681072528)),
                   '1': dict(appid=m.signed(4000000000), LaunchOptions='lutris:rungameid/7')}
        with self.assertRaises(ValueError):
            m.merge_game(self.game(), entries, '')

    def test_compat_removal_is_scoped(self):
        config = {'InstallConfigStore': {'Software': {'Valve': {'Steam': {
            'CompatToolMapping': {'3681072528': {'name': 'proton'}, '813780': {'name': 'keep'}}}}}}}
        m.remove_compat(config, {3681072528})
        mapping = config['InstallConfigStore']['Software']['Valve']['Steam']['CompatToolMapping']
        self.assertEqual(mapping, {'813780': {'name': 'keep'}})

    STORE = ('"UserLocalConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n\t\t\t"Steam"\n\t\t\t{\n'
             '\t\t\t\t"apps"\n\t\t\t\t{\n\t\t\t\t\t"4217488047"\n\t\t\t\t\t{\n\t\t\t\t\t\t"Nested"\t\t"keep"\n\t\t\t\t\t}\n'
             '\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n\t"SteamController_XBoxSupport"\t\t"1"\n')

    def apps(self, text):
        return m.vdf.loads(text)['UserLocalConfigStore'].get('apps', {})

    def test_steam_input_disabled_adds_missing_apps_block_and_entries(self):
        text = self.STORE + '}\n'
        updated = m.disable_steam_input(text, {4217488047, 3681072528})
        apps = self.apps(updated)
        self.assertEqual(apps['4217488047']['UseSteamControllerConfig'], '0')
        self.assertEqual(apps['3681072528']['UseSteamControllerConfig'], '0')
        # The similarly named nested Software/Valve/Steam/apps block is untouched.
        nested = m.vdf.loads(updated)['UserLocalConfigStore']['Software']['Valve']['Steam']['apps']
        self.assertEqual(nested, {'4217488047': {'Nested': 'keep'}})
        self.assertEqual(m.disable_steam_input(updated, {4217488047, 3681072528}), updated)

    def test_steam_input_disabled_updates_existing_entry_and_keeps_other_keys(self):
        text = (self.STORE + '\t"apps"\n\t{\n\t\t"413080"\n\t\t{\n\t\t\t"UseSteamControllerConfig"\t\t"0"\n\t\t}\n'
                '\t\t"3681072528"\n\t\t{\n\t\t\t"UseSteamControllerConfig"\t\t"1"\n\t\t\t"SteamControllerRumble"\t\t"-1"\n\t\t}\n'
                '\t\t"2623494187"\n\t\t{\n\t\t\t"SteamControllerRumble"\t\t"-1"\n\t\t}\n\t}\n}\n')
        updated = m.disable_steam_input(text, {3681072528, 2623494187, 2314256998})
        apps = self.apps(updated)
        self.assertEqual(apps['413080'], {'UseSteamControllerConfig': '0'})
        self.assertEqual(apps['3681072528'], {'UseSteamControllerConfig': '0', 'SteamControllerRumble': '-1'})
        self.assertEqual(apps['2623494187'], {'SteamControllerRumble': '-1', 'UseSteamControllerConfig': '0'})
        self.assertEqual(apps['2314256998'], {'UseSteamControllerConfig': '0'})
        self.assertEqual(m.disable_steam_input(updated, {3681072528, 2623494187, 2314256998}), updated)

    def test_steam_input_edit_preserves_unrelated_text_byte_for_byte(self):
        text = self.STORE.replace('"keep"', '"Shift\tKEY"') + '}\n'
        updated = m.disable_steam_input(text, {1})
        # Only the new apps block is added; every original byte stays exactly in place.
        self.assertEqual(updated, text[:-2] + '\t"apps"\n\t{\n\t\t"1"\n\t\t{\n\t\t\t"UseSteamControllerConfig"\t\t"0"\n\t\t}\n\t}\n}\n')

    def test_steam_input_edit_requires_user_store(self):
        with self.assertRaises(ValueError):
            m.disable_steam_input('"Other"\n{\n}\n', {1})

    def test_uri_uses_64bit_nonsteam_id(self):
        aid = 3681072528
        self.assertEqual(m.steam_uri(aid), 'steam://rungameid/' + str((aid << 32) | 0x02000000))
        self.assertEqual(m.steam_uri(813780, native=True), 'steam://rungameid/813780')

    def test_mask_only_main_desktop_section(self):
        text = '[Desktop Entry]\nName=Game\nExec=lutris lutris:rungameid/7\n\n[Desktop Action X]\nName=X\n'
        updated = m.hide_desktop(text)
        self.assertIn('Hidden=true\n\n[Desktop Action X]', updated)
        self.assertEqual(m.hide_desktop(updated), updated)

    def test_lutris_visibility_and_aoe_cleanup_are_persistent(self):
        with tempfile.TemporaryDirectory() as td, patch.object(m, 'STATE', Path(td) / 'state'):
            apps = Path(td) / 'applications'
            apps.mkdir()
            lutris = apps / 'net.lutris.Lutris.desktop'
            lutris.write_text('[Desktop Entry]\nName=Lutris\nExec=lutris %U\nHidden=true\n')
            handler = apps / 'net.lutris.Lutris1.desktop'
            handler.write_text('[Desktop Entry]\nName=Lutris\nExec=lutris --install %f\nNoDisplay=true\nHidden=true\n')
            canonical = apps / 'steam-library-813780.desktop'
            canonical.write_text(m.desktop('AoE', m.steam_uri(813780, native=True), 'steam'))
            duplicate = apps / 'Age of Empires.desktop'
            duplicate.write_text('[Desktop Entry]\nName=AoE\nExec=steam steam://rungameid/813780\n')
            profile = apps / 'aoe2-some-account.desktop'
            profile.write_text('[Desktop Entry]\nName=AoE profile\nExec=/home/example/.local/bin/launch-aoe2-account example\n')
            unknown = apps / 'aoe2-custom.desktop'
            unknown.write_text('[Desktop Entry]\nName=Custom\nExec=/custom/other-game\n')
            writer = m.Writer()
            m.reconcile_launcher_policy(writer, apps)
            self.assertIn('Hidden=false', lutris.read_text())
            self.assertIn('NoDisplay=true', handler.read_text())
            self.assertNotIn('Hidden=true', canonical.read_text())
            self.assertIn('Hidden=true', duplicate.read_text())
            self.assertFalse(profile.exists())
            self.assertTrue(unknown.exists())
            self.assertTrue((writer.backup / str(profile).lstrip('/')).exists())
            again = m.Writer()
            m.reconcile_launcher_policy(again, apps)
            self.assertEqual(again.changes, 0)

    def lutris_game(self, gid, slug, name, runner='wine'):
        return dict(id=gid, name=name, slug=slug, runner=runner, configpath=slug)

    def test_game_launchers_are_single_direct_lutris_entries(self):
        with tempfile.TemporaryDirectory() as td, patch.object(m, 'STATE', Path(td) / 'state'), \
             patch.object(m, 'HOME', Path(td) / 'home'):
            apps = Path(td) / 'applications'
            apps.mkdir()
            hidden = apps / 'lutris-ghost.desktop'
            hidden.write_text('[Desktop Entry]\nName=Ghost\nExec=lutris lutris:rungameid/8\nCategories=Game;\nHidden=true\n')
            nonsteam = apps / 'steam-library-4217488047.desktop'
            nonsteam.write_text(m.desktop('Ghost', m.steam_uri(4217488047), 'steam'))
            native = apps / 'steam-library-813780.desktop'
            native.write_text(m.desktop('AoE', m.steam_uri(813780, native=True), 'steam'))
            foreign = apps / 'steam-library-123456789.desktop'
            foreign.write_text('[Desktop Entry]\nName=Mine\nExec=/usr/bin/steam ' + m.steam_uri(123456789) + '\n')
            games = [self.lutris_game(8, 'ghost-of-tsushima', 'Ghost'),
                     self.lutris_game(5, 'aoe', 'AoE', runner='steam')]
            writer = m.Writer()
            m.reconcile_game_launchers(writer, apps, games)
            self.assertNotIn('Hidden=true', hidden.read_text())
            self.assertFalse(nonsteam.exists())
            self.assertTrue((writer.backup / str(nonsteam).lstrip('/')).exists())
            self.assertTrue(native.exists())
            self.assertTrue(foreign.exists())
            self.assertFalse((apps / 'lutris-aoe.desktop').exists())
            again = m.Writer()
            m.reconcile_game_launchers(again, apps, games)
            self.assertEqual(again.changes, 0)

    def test_missing_direct_launcher_is_created_without_clobbering_foreign_files(self):
        with tempfile.TemporaryDirectory() as td, patch.object(m, 'STATE', Path(td) / 'state'), \
             patch.object(m, 'HOME', Path(td) / 'home'):
            apps = Path(td) / 'applications'
            apps.mkdir()
            icons = Path(td) / 'home/.local/share/icons/hicolor/128x128/apps'
            icons.mkdir(parents=True)
            (icons / 'lutris_epic-games-store.png').write_bytes(b'png')
            games = [self.lutris_game(1, 'epic-games-store', 'Epic Games Store'),
                     self.lutris_game(6, 'ts4_x64exe', 'TS4_x64.exe'),
                     self.lutris_game(9, 'cyberpunk-2077', 'Cyberpunk 2077')]
            foreign = apps / 'lutris-cyberpunk-2077.desktop'
            foreign.write_text('[Desktop Entry]\nName=Custom\nExec=/opt/other-launcher\n')
            writer = m.Writer()
            m.reconcile_game_launchers(writer, apps, games)
            epic = (apps / 'lutris-epic-games-store.desktop').read_text()
            self.assertIn('Name=Epic Games Store\n', epic)
            self.assertIn('Exec=lutris lutris:rungameid/1\n', epic)
            self.assertIn(f'Icon={icons / "lutris_epic-games-store.png"}\n', epic)
            self.assertIn('X-ArchSetups-LutrisLauncher=true', epic)
            self.assertNotIn('Hidden', epic)
            sims = (apps / 'lutris-ts4_x64exe.desktop').read_text()
            self.assertIn('Name=TS4_x64.exe\n', sims)  # metadata policy keeps the source title
            self.assertIn('Icon=lutris\n', sims)
            self.assertEqual(foreign.read_text(), '[Desktop Entry]\nName=Custom\nExec=/opt/other-launcher\n')
            again = m.Writer()
            m.reconcile_game_launchers(again, apps, games)
            self.assertEqual(again.changes, 0)

    def test_profile_launcher_is_kept_if_no_standard_aoe_entry_exists(self):
        with tempfile.TemporaryDirectory() as td, patch.object(m, 'STATE', Path(td) / 'state'):
            apps = Path(td) / 'apps'
            apps.mkdir()
            p = apps / 'aoe2-example.desktop'
            p.write_text('[Desktop Entry]\nExec=launch-aoe2-account example\n')
            m.reconcile_launcher_policy(m.Writer(), apps)
            self.assertTrue(p.exists())

    def test_writer_backs_up_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td, patch.object(m, 'STATE', Path(td) / 'state'):
            p = Path(td) / 'config'
            p.write_bytes(b'original')
            writer = m.Writer()
            writer.write(p, b'new')
            self.assertEqual((writer.backup / str(p).lstrip('/')).read_bytes(), b'original')
            writer.write(p, b'new')
            self.assertEqual(writer.changes, 1)
            link = Path(td) / 'link'
            link.symlink_to(p)
            with self.assertRaises(ValueError):
                writer.write(link, b'other')

    def test_fixture_migration_preserves_yaml_and_second_account(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            steam = home / '.local/share/Steam'
            base = steam / 'userdata/100/config'
            base.mkdir(parents=True)
            second = steam / 'userdata/200/config/shortcuts.vdf'
            second.parent.mkdir(parents=True)
            second.write_bytes(b'untouched account')
            (steam / 'config').mkdir()
            (steam / 'config/config.vdf').write_text(m.vdf.dumps({'InstallConfigStore': {'Software': {'Valve': {'Steam': {}}}}}, pretty=True))
            games = home / 'lutris-games'
            games.mkdir()
            yaml = b'game:\n  exe: /missing/Game.exe\n  prefix: /existing/prefix\nwine:\n  version: custom-runner\nsystem:\n  env:\n    CUSTOM: keep\n'
            (games / 'local.yml').write_bytes(yaml)
            dbpath = home / 'lutris.db'
            db = sqlite3.connect(dbpath)
            db.execute('CREATE TABLE games (id INTEGER,name TEXT,slug TEXT,runner TEXT,configpath TEXT,installed INTEGER)')
            db.execute("INSERT INTO games VALUES(1,'Local','local','wine','local',1)")
            db.execute("INSERT INTO games VALUES(17,'HS2','hs2','wine','removed-config',1)")
            db.commit()
            db.close()
            (base / 'shortcuts.vdf').write_bytes(m.vdf.binary_dumps({'shortcuts': {'0': {
                'appid': m.signed(3509545727), 'AppName': 'Honey Select 2 DX',
                'Exe': '"/usr/bin/lutris"', 'LaunchOptions': 'lutris:rungameid/17'}}}))
            (base / 'localconfig.vdf').write_text(self.STORE + '}\n')
            applications = home / '.local/share/applications'
            applications.mkdir(parents=True)
            removed_launcher = applications / 'steam-library-3509545727.desktop'
            removed_launcher.write_text('[Desktop Entry]\nX-ArchSetups-SteamLibrary=true\n')
            args = argparse.Namespace(if_enabled=False, apply=True, enable=True, artwork=False, account='100')
            with patch.object(m, 'HOME', home), patch.object(m, 'STATE', home / 'state'), \
                 patch.object(m, 'PREFERENCE', home / '.config/pref.json'), \
                 patch.object(m.settings, 'DB_PATH', str(dbpath)), \
                 patch.object(m.settings, 'GAME_CONFIG_DIR', str(games)), \
                 patch.object(m, 'process_running', return_value=False), \
                 patch.object(m.shutil, 'which', return_value=None), \
                 patch.dict(m.os.environ, XDG_DATA_HOME=str(home / '.local/share')):
                m.migrate(args)
                before = (base / 'shortcuts.vdf').read_bytes()
                localconfig_before = (base / 'localconfig.vdf').read_bytes()
                m.migrate(args)
                self.assertEqual((base / 'shortcuts.vdf').read_bytes(), before)
                self.assertEqual((base / 'localconfig.vdf').read_bytes(), localconfig_before)
            # Steam Input is disabled only for the exported Lutris shortcut, not the removed entry.
            apps = self.apps((base / 'localconfig.vdf').read_text())
            self.assertEqual(apps, {'3225172075': {'UseSteamControllerConfig': '0'}})
            self.assertEqual((games / 'local.yml').read_bytes(), yaml)
            self.assertEqual(second.read_bytes(), b'untouched account')
            entries = m.vdf.binary_loads(before)['shortcuts']
            self.assertEqual(len(entries), 1)
            self.assertIn('lutris:rungameid/1', next(iter(entries.values()))['LaunchOptions'])
            self.assertFalse(removed_launcher.exists())
            # The exported Lutris game gets one direct Lutris launcher and no Steam launcher.
            self.assertIn('Exec=lutris lutris:rungameid/1\n', (applications / 'lutris-local.desktop').read_text())
            self.assertFalse((applications / 'steam-library-3225172075.desktop').exists())
