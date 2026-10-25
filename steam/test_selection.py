"""Portable game-selection contracts; no mount, network, GPU or user data required."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from gaming_profile import load_selection, owned_shortcuts

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('selected_game_installer', HERE / 'configure-gaming-profile.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class SelectionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='selected-games-')
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name) / 'home with spaces'
        self.home.mkdir()
        self.selection = self.home / 'selection.json'

    def resolve(self, values):
        self.selection.write_text(json.dumps(values))
        return load_selection(self.selection, self.home)

    def profile(self, **options):
        return {'schemaVersion': 1, 'libraries': {'primary': str(self.home / 'library')},
                'games': {'cyberpunk-2077': {'library': 'primary', 'path': 'Cyberpunk 2077', **options}}}

    def test_default_empty_selection_never_creates_personal_launchers(self):
        with patch.dict(os.environ, {}, clear=True):
            resolved = load_selection(home=self.home)
        self.assertEqual(resolved['games'], [])
        with contextlib.redirect_stdout(io.StringIO()):
            installer.apply(resolved, self.home, True)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_steam_export_is_opt_in_and_cannot_reverse_sync(self):
        self.assertFalse(self.resolve({'schemaVersion': 1})['exportSteam'])
        self.assertTrue(self.resolve({'schemaVersion': 1, 'exportSteam': True})['exportSteam'])
        with self.assertRaises(ValueError):
            self.resolve({'schemaVersion': 1, 'exportSteam': True, 'importSteam': True})
        with self.assertRaises(ValueError):
            self.resolve({'schemaVersion': 1, 'exportSteam': 'yes'})

    def test_library_root_and_prefix_do_not_depend_on_username_or_steam_ids(self):
        game = self.resolve(self.profile())['games'][0]
        self.assertEqual(game['config']['game']['exe'], str(self.home / 'library/Cyberpunk 2077/bin/x64/Cyberpunk2077.exe'))
        self.assertTrue(game['config']['game']['prefix'].endswith('/wineprefixes/arch-setups/cyberpunk-2077'))
        self.assertNotIn('upscaler', game)
        self.assertNotIn('artwork', game)
        self.assertNotIn('prefix_command', game['config']['system'])
        self.assertNotIn('WINEDLLOVERRIDES', game['config']['system']['env'])

    def test_disabled_game_needs_no_mount_and_owns_no_generic_import(self):
        result = self.resolve({'schemaVersion': 1, 'games': {'cyberpunk-2077': {'enabled': False}}})
        self.assertEqual(result['games'], [])
        self.assertEqual(owned_shortcuts(result), set())

    def test_unavailable_selected_game_does_not_suppress_steam_import(self):
        result = self.resolve(self.profile())
        self.assertEqual(owned_shortcuts(result), set())
        game = result['games'][0]
        path = Path(game['config']['game']['exe'])
        path.parent.mkdir(parents=True)
        path.touch()
        self.assertEqual(owned_shortcuts(result), {game['shortcut_id']})

    def test_hdr_and_mods_require_explicit_per_game_opt_in(self):
        with self.assertRaisesRegex(ValueError, 'resolution'):
            self.resolve(self.profile(hdr=True))
        game = self.resolve(self.profile(hdr=True, resolution=[2560, 1440], upscaler='optiscaler-094'))['games'][0]
        self.assertEqual(game['config']['system']['env']['ARCH_SETUPS_GAME_WIDTH'], '2560')
        self.assertEqual(game['config']['system']['prefix_command'], 'steam-gamescope-hdr')
        self.assertEqual(game['upscaler'], 'optiscaler-094')
        self.assertFalse(game['allowModReplacement'])

    def test_selected_halo_without_display_opt_in_does_not_force_hdr_or_engine_settings(self):
        profile = self.profile()
        profile['games'] = {'halo-campaign-evolved': {'library': 'primary', 'path': 'Halo'}}
        game = self.resolve(profile)['games'][0]
        self.assertNotIn('display_settings', game)
        self.assertNotIn('prefix_command', game['config']['system'])
        for key in ('PROTON_ENABLE_HDR', 'ENABLE_HDR_WSI', 'DXVK_HDR'):
            self.assertNotIn(key, game['config']['system']['env'])

    def test_halo_retains_upstream_capture_and_hdr_at_the_selected_resolution(self):
        profile = self.profile()
        profile['games'] = {'halo-campaign-evolved': {'library': 'primary', 'path': 'Halo', 'hdr': True, 'resolution': [2560, 1440]}}
        game = self.resolve(profile)['games'][0]
        self.assertEqual(game['config']['system']['env']['HALO_GAMESCOPE_CAPTURE'], '1')
        self.assertEqual(game['config']['system']['env']['PROTON_ENABLE_WAYLAND'], '0')
        self.assertEqual(game['config']['system']['env']['PROTON_ENABLE_HDR'], '1')
        self.assertEqual(game['display_settings']['ResolutionSizeX'], '2560')
        self.assertEqual(game['display_settings']['ResolutionSizeY'], '1440')
        self.assertEqual(game['display_settings']['bUseHDRDisplayOutput'], 'True')
        profile['games']['halo-campaign-evolved']['hdr'] = False
        game = self.resolve(profile)['games'][0]
        self.assertEqual(game['display_settings']['ResolutionSizeX'], '2560')
        self.assertNotIn('bUseHDRDisplayOutput', game['display_settings'])
        self.assertNotIn('PROTON_ENABLE_HDR', game['config']['system']['env'])

    def test_invalid_selection_fails_closed(self):
        for update in ({'path': '../outside'}, {'library': 'missing'}, {'hdr': 'yes'}, {'resolution': [0, 0]}, {'unknown': 1}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.resolve(self.profile(**update))

    def test_foreign_mod_is_refused_before_any_file_changes(self):
        game = self.resolve(self.profile(upscaler='optiscaler-094'))['games'][0]
        target = Path(game['config']['game']['exe']).parent
        target.mkdir(parents=True)
        existing = target / 'dxgi.dll'
        existing.write_bytes(b'user-mod')
        manager = installer.Installer(self.home)
        def extract(args, **kwargs):
            directory = Path(next(arg[2:] for arg in args if arg.startswith('-o')))
            (directory / 'OptiScaler.dll').write_bytes(b'new-mod')
            return subprocess.CompletedProcess(args, 0)
        assets = [{'name': 'fixture', 'url': 'https://example.invalid', 'sha256': '0' * 64}]
        with patch.object(manager, 'asset', return_value=self.home / 'archive'), patch.object(installer.subprocess, 'run', side_effect=extract):
            with self.assertRaisesRegex(ValueError, 'Foreign/modified'):
                manager.upscaler(game, assets)
        self.assertEqual(existing.read_bytes(), b'user-mod')
        self.assertEqual(list(target.iterdir()), [existing])

    def test_hdr_wrapper_uses_requested_dimensions_not_four_k(self):
        binary = self.home / 'bin'
        binary.mkdir()
        fake = binary / 'gamescope'
        fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
        fake.chmod(0o755)
        env = dict(os.environ, PATH=str(binary) + ':/usr/bin', ARCH_SETUPS_GAME_WIDTH='1920', ARCH_SETUPS_GAME_HEIGHT='1080', HALO_GAMESCOPE_CAPTURE='0')
        result = subprocess.run(['bash', str(HERE / 'gamescope-hdr'), 'a game.exe', '--argument'], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('3840', result.stdout)
        self.assertIn('--nested-width\n1920\n', result.stdout)
        self.assertIn('a game.exe\n--argument', result.stdout)
        self.assertNotIn('--force-grab-cursor', result.stdout)
        env['HALO_GAMESCOPE_CAPTURE'] = '1'
        captured = subprocess.run(['bash', str(HERE / 'gamescope-hdr'), 'a game.exe'], env=env, capture_output=True, text=True)
        self.assertEqual(captured.returncode, 0, captured.stderr)
        self.assertEqual(captured.stdout.splitlines().count('--force-grab-cursor'), 1)
        self.assertIn('--nested-width\n1920\n', captured.stdout)


if __name__ == '__main__':
    unittest.main()
