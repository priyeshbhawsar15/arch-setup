import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('gaming_mode', Path(__file__).with_name('gaming-mode.py'))
gm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gm)

MONITOR = dict(name='DP-6', description='OLED', width=3840, height=2160,
               refreshRate=119.999, x=0, y=0, scale=1.5, transform=0,
               currentFormat='XRGB2101010', colorManagementPreset='hdr',
               sdrBrightness=1.75, sdrSaturation=1, sdrMinLuminance=.2,
               sdrMaxLuminance=80, vrr=False)


class GamingModeTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(gm, 'plugin_states', return_value={})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_versioned_decorations_hint_and_optout(self):
        with tempfile.TemporaryDirectory() as td, patch.object(gm, 'STATE', Path(td)), \
             patch.object(gm, 'monitor', return_value=MONITOR), patch.object(gm, 'read', return_value={}), \
             patch.object(gm, 'set_vrr'):
            session = gm.enter({'monitor': 'DP-6', 'pausePlugins': []})
            self.assertEqual(session['schemaVersion'], 1)
            self.assertTrue(session['pauseDecorations'])
            gm.leave(session)
            session = gm.enter({'monitor': 'DP-6', 'pausePlugins': [], 'pauseDecorations': False})
            self.assertFalse(session['pauseDecorations'])
            gm.leave(session)
            with self.assertRaises(RuntimeError):
                gm.enter({'monitor': 'DP-6', 'pauseDecorations': 'false'})

    def test_overlay_enable_does_not_require_catalog_active_bar_flag(self):
        a = gm.DEFAULT_PAUSE_PLUGINS[0]
        with patch.object(gm, 'run') as call, patch.object(gm, 'plugin_states', return_value={a: {'enabled': True, 'active': False}}):
            gm.set_plugin_enabled(a, True)
            call.assert_called_once_with('omarchy', 'plugin', 'enable', a, timeout=5)
        with patch.object(gm, 'run') as call:
            with self.assertRaises(RuntimeError):
                gm.set_plugin_enabled('omarchy.lock', False)
            call.assert_not_called()

    def test_pause_candidates_only_reviewed_enabled_widgets(self):
        a, b, c = gm.DEFAULT_PAUSE_PLUGINS
        states = {a: {'enabled': True}, b: {'enabled': False}, c: {'enabled': True, 'canDisable': False}}
        self.assertEqual(gm.pause_candidates({}, states), [a])
        self.assertEqual(gm.pause_candidates({'pausePlugins': []}, states), [])
        with self.assertRaises(RuntimeError):
            gm.pause_candidates({'pausePlugins': ['omarchy.lock']}, states)
        with self.assertRaises(RuntimeError):
            gm.pause_candidates({'pausePlugins': [a, a]}, states)

    def test_widget_pause_and_restore_only_originally_enabled_plugins(self):
        a, b, _ = gm.DEFAULT_PAUSE_PLUGINS
        with tempfile.TemporaryDirectory() as td, patch.object(gm, 'STATE', Path(td)), \
             patch.object(gm, 'monitor', return_value=MONITOR), patch.object(gm, 'read', return_value={}), \
             patch.object(gm, 'set_vrr'), patch.object(gm, 'set_plugin_enabled') as toggle, \
             patch.object(gm, 'plugin_states', return_value={a: {'enabled': True}, b: {'enabled': False}}):
            session = gm.enter({'monitor': 'DP-6'})
            self.assertEqual(session['pausedPlugins'], [a])
            toggle.assert_called_once_with(a, False)
            with patch.object(gm, 'plugin_states', return_value={a: {'enabled': False}, b: {'enabled': False}}):
                gm.leave(session)
            self.assertEqual(toggle.call_args.args, (a, True))
            self.assertNotIn(unittest.mock.call(b, True), toggle.call_args_list)

    def test_partial_widget_pause_failure_rolls_back(self):
        a, b, _ = gm.DEFAULT_PAUSE_PLUGINS
        with tempfile.TemporaryDirectory() as td, patch.object(gm, 'STATE', Path(td)), \
             patch.object(gm, 'monitor', return_value=MONITOR), patch.object(gm, 'read', return_value={}), \
             patch.object(gm, 'set_vrr'), \
             patch.object(gm, 'plugin_states', side_effect=[{a: {'enabled': True}, b: {'enabled': True}},
                                                          {a: {'enabled': False}, b: {'enabled': True}}]), \
             patch.object(gm, 'set_plugin_enabled', side_effect=[None, RuntimeError('disable failed'), None]) as toggle:
            with self.assertRaisesRegex(RuntimeError, 'disable failed'):
                gm.enter({'monitor': 'DP-6'})
            self.assertEqual(toggle.call_args.args, (a, True))
            self.assertFalse((Path(td) / 'session.json').exists())

    def test_manual_resume_and_removed_plugins_are_not_reenabled(self):
        a, b, _ = gm.DEFAULT_PAUSE_PLUGINS
        with patch.object(gm, 'plugin_states', return_value={a: {'enabled': True}}), \
             patch.object(gm, 'set_plugin_enabled') as toggle:
            gm.restore_plugins({'pausedPlugins': [a, b]})
            toggle.assert_not_called()

    def test_widget_restore_failure_retains_recovery_journal(self):
        a = gm.DEFAULT_PAUSE_PLUGINS[0]
        with tempfile.TemporaryDirectory() as td, patch.object(gm, 'STATE', Path(td)), \
             patch.object(gm, 'monitor', return_value=MONITOR), patch.object(gm, 'set_vrr'), \
             patch.object(gm, 'read', return_value={}), \
             patch.object(gm, 'plugin_states', return_value={a: {'enabled': False}}), \
             patch.object(gm, 'set_plugin_enabled', side_effect=RuntimeError('enable failed')):
            session = {'signature': gm.os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'), 'monitor': 'DP-6',
                       'previousVrr': 0, 'wallpaper': None, 'pausedPlugins': [a]}
            gm.save(Path(td) / 'session.json', session)
            with self.assertRaises(RuntimeError):
                gm.leave(session)
            self.assertTrue((Path(td) / 'session.json').exists())

    def test_big_picture_and_generic_gamescope_no_longer_activate(self):
        clients = [{'class': 'steam', 'title': 'Steam Big Picture Mode'},
                   {'class': 'gamescope', 'title': 'Not necessarily a game'}]
        with patch.object(gm, 'leases', return_value=False), patch.object(gm, 'running_games', return_value=False):
            self.assertFalse(gm.gaming_requested(clients))
        self.assertTrue(gm.game_windows([{'class': 'steam_app_813780', 'title': 'Game'}]))
        self.assertFalse(gm.game_windows([{'class': 'steam_app_0'}]))
        self.assertFalse(gm.game_windows([{'class': 'steam_app_431960'}]))

    def test_new_steam_and_lutris_games_need_no_catalog(self):
        self.assertEqual(gm.process_game_source('new-game', {'SteamAppId': '123456789'}), 'Steam')
        self.assertEqual(gm.process_game_source('new-game', {'SteamGameId': '123456789123456789'}), 'Steam')
        self.assertEqual(gm.process_game_source('python-game', {'GAME_NAME': 'A newly installed Lutris game'}), 'Lutris')
        self.assertIsNone(gm.process_game_source('new-game', {'SteamAppId': '0'}))
        self.assertIsNone(gm.process_game_source('new-game', {}))

    def test_background_helpers_and_wallpapers_do_not_hold_mode(self):
        for name in ['steam', 'steamwebhelper', 'lutris', 'wineserver', 'services.exe',
                     'explorer.exe', 'winedevice.exe', 'linux-wallpaper', 'fossilize_repla']:
            self.assertIsNone(gm.process_game_source(name, {'SteamAppId': '123', 'GAME_NAME': 'Game'}))
        self.assertIsNone(gm.process_game_source('wallpaper.exe', {'SteamAppId': '431960'}))
        self.assertIsNone(gm.process_game_source('wallpaper.exe', {'GAME_NAME': 'Wallpaper Engine'}))

    def fake_process(self, root, pid, comm, environment):
        p = root / str(pid)
        p.mkdir()
        (p / 'comm').write_text(comm)
        (p / 'environ').write_bytes(b'\0'.join(k.encode() + b'=' + v.encode() for k, v in environment.items()))
        return p

    def test_process_detection_multiple_games_and_exit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a = self.fake_process(root, 100, 'game-one', {'SteamAppId': '123'})
            b = self.fake_process(root, 200, 'game-two', {'GAME_NAME': 'New Lutris Game'})
            self.assertTrue(gm.running_games(root))
            (a / 'environ').write_bytes(b'')
            self.assertTrue(gm.running_games(root))
            (b / 'environ').unlink()  # An exiting process is not an error.
            self.assertFalse(gm.running_games(root))

    def test_process_scan_filters_uid_session_and_private_environment(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(gm.os.environ, HYPRLAND_INSTANCE_SIGNATURE='session-a'):
            root = Path(td)
            p = self.fake_process(root, 100, 'game', {'GAME_NAME': 'Game', 'API_KEY': 'private',
                                                   'HYPRLAND_INSTANCE_SIGNATURE': 'session-b'})
            self.assertFalse(gm.running_games(root))
            (p / 'environ').write_bytes(b'GAME_NAME=Game\0API_KEY=private')
            self.assertFalse(gm.running_games(root, uid=gm.os.getuid() + 1))
            with patch.object(gm, 'process_game_source', wraps=gm.process_game_source) as classify:
                self.assertTrue(gm.running_games(root))
                self.assertNotIn('API_KEY', classify.call_args.args[1])

    def test_runtime_markers_and_explicit_leases_activate_without_windows(self):
        with patch.object(gm, 'leases', return_value=False), patch.object(gm, 'running_games', return_value=True):
            self.assertTrue(gm.gaming_requested([]))
        with patch.object(gm, 'leases', return_value=True), patch.object(gm, 'running_games', return_value=False):
            self.assertTrue(gm.gaming_requested([]))

    def test_complete_monitor_spec_preserves_native_hdr_and_layout(self):
        s = gm.monitor_spec(MONITOR, 1)
        self.assertEqual(s['mode'], '3840x2160@119.99900')
        for key, value in dict(position='0x0', scale=1.5, bitdepth=10, cm='hdr',
                               sdrbrightness=1.75, vrr=1).items():
            self.assertEqual(s[key], value)
        with patch.object(gm, 'run', return_value='ok') as call:
            gm.set_vrr(MONITOR, 0)
            self.assertIn('vrr=0', call.call_args.args[2])
            self.assertIn('cm="hdr"', call.call_args.args[2])

    def test_only_selected_monitor(self):
        with patch.object(gm, 'hypr', return_value=[MONITOR, dict(MONITOR, name='DP-4', description='Other')]):
            self.assertEqual(gm.monitor({'monitor': 'desc:OLED'})['name'], 'DP-6')
            with self.assertRaises(RuntimeError):
                gm.monitor({'monitor': 'missing'})

    def test_wallpaper_ownership(self):
        s = {'wallpaper': 'we:123'}
        self.assertTrue(gm.wallpaper_owned(s, {'active': 'we:123', 'wallpaperEnabled': False}))
        self.assertFalse(gm.wallpaper_owned(s, {'active': 'we:456', 'wallpaperEnabled': False}))
        self.assertFalse(gm.wallpaper_owned(s, {'active': 'we:123', 'wallpaperEnabled': True}))
        self.assertFalse(gm.wallpaper_owned({'wallpaper': None}, {'active': 'we:123'}))

    def test_entry_journal_precedes_effects_and_exit_restores(self):
        with tempfile.TemporaryDirectory() as td, patch.object(gm, 'STATE', Path(td)), \
             patch.object(gm, 'monitor', return_value=MONITOR), \
             patch.object(gm, 'set_vrr') as vrr, patch.object(gm, 'read', return_value={
                 'active': 'we:123', 'wallpaperEnabled': True}):
            def effect(*args):
                self.assertTrue((Path(td) / 'session.json').is_file())
                return ''
            with patch.object(gm, 'run', side_effect=effect):
                s = gm.enter({'monitor': 'DP-6', 'restoreVrr': 0})
            self.assertEqual(s['wallpaper'], 'we:123')
            vrr.assert_called_with(MONITOR, 1)
            with patch.object(gm, 'read', return_value={'active': 'we:123', 'wallpaperEnabled': False}), \
                 patch.object(gm, 'run') as run:
                gm.leave(s)
                self.assertEqual(run.call_args.args[-2:], ('apply', 'we:123'))
            vrr.assert_called_with(MONITOR, 0)
            self.assertFalse((Path(td) / 'session.json').exists())

    def test_already_stopped_wallpaper_is_never_restarted(self):
        with tempfile.TemporaryDirectory() as td, patch.object(gm, 'STATE', Path(td)), \
             patch.object(gm, 'monitor', return_value=MONITOR), patch.object(gm, 'set_vrr'), \
             patch.object(gm, 'read', return_value={'active': 'we:123', 'wallpaperEnabled': False}), \
             patch.object(gm, 'run') as run:
            session = gm.enter({'monitor': 'DP-6'})
            gm.leave(session)
            run.assert_not_called()

    def test_failed_entry_rolls_back(self):
        with tempfile.TemporaryDirectory() as td, patch.object(gm, 'STATE', Path(td)), \
             patch.object(gm, 'monitor', return_value=MONITOR), \
             patch.object(gm, 'read', side_effect=[{'active': 'we:123'},
                                                 {'active': 'we:123', 'wallpaperEnabled': False}]), \
             patch.object(gm, 'set_vrr', side_effect=[RuntimeError('VRR failed'), None]), \
             patch.object(gm, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'VRR failed'):
                gm.enter({'monitor': 'DP-6'})
            self.assertEqual(run.call_args.args[-2:], ('apply', 'we:123'))
            self.assertFalse((Path(td) / 'session.json').exists())

    def test_failed_restore_retains_journal(self):
        with tempfile.TemporaryDirectory() as td, patch.object(gm, 'STATE', Path(td)), \
             patch.object(gm, 'monitor', side_effect=RuntimeError('disconnected')):
            s = {'signature': gm.os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'),
                 'monitor': 'DP-6', 'previousVrr': 0, 'wallpaper': None}
            gm.save(Path(td) / 'session.json', s)
            with self.assertRaises(RuntimeError):
                gm.leave(s)
            self.assertTrue((Path(td) / 'session.json').exists())

    def test_stale_pid_lease_removed(self):
        with tempfile.TemporaryDirectory() as td, patch.object(gm, 'STATE', Path(td)), \
             patch.object(gm, 'birth', return_value='new-process'):
            p = Path(td) / 'lease-123.json'
            gm.save(p, {'pid': 123, 'birth': 'old-process'})
            self.assertFalse(gm.leases())
            self.assertFalse(p.exists())

    def test_launch_native_resolution_and_preserves_other_preloads(self):
        with tempfile.TemporaryDirectory() as td, patch.object(gm, 'STATE', Path(td)), \
             patch.object(gm, 'monitor', return_value=MONITOR), \
             patch.object(gm, 'read', return_value={'monitor': 'DP-6'}), \
             patch.object(gm, 'run', return_value='ok'), patch.dict(gm.os.environ, LD_PRELOAD='/steam/gameoverlayrenderer.so:/custom/mod.so'), \
             patch.object(gm.subprocess, 'call', return_value=0) as call:
            self.assertEqual(gm.launch(['game', '--option'], hdr=True), 0)
            args = call.call_args.args[0]
            self.assertEqual(args[args.index('-w') + 1], '3840')
            self.assertEqual(args[args.index('-W') + 1], '3840')
            self.assertIn('--hdr-enabled', args)
            self.assertEqual(call.call_args.kwargs['env']['LD_PRELOAD'], '/custom/mod.so')
            self.assertEqual(list(Path(td).glob('lease-*.json')), [])
            with self.assertRaises(RuntimeError):
                gm.launch(['steam-gamescope-hdr', 'game'])


if __name__ == '__main__':
    unittest.main()
