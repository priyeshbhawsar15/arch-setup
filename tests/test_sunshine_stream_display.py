"""Landscape side monitors while the main Sunshine host streams."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / 'sunshine/stream-display.py'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


display = load('stream_display', HELPER)
layout = load('stream_monitor_layout', REPO / 'hypr/scripts/monitor-layout.py')

LEFT = 'Lenovo Group Limited LEN S22e-19 0x01010101'
RIGHT = 'Lenovo Group Limited LEN S22e-19 0x59333830'


def edid(name, serial, serial_text=''):
    data = bytearray(128)
    data[:8] = b'\x00\xff\xff\xff\xff\xff\xff\x00'
    data[12:16] = struct.pack('<I', serial)
    data[54:72] = b'\x00\x00\x00\xfc\x00' + (name.encode() + b'\n').ljust(13, b' ')
    if serial_text:
        data[72:90] = b'\x00\x00\x00\xff\x00' + (serial_text.encode() + b'\n').ljust(13, b' ')
    return bytes(data)


class PolicyTests(unittest.TestCase):
    def test_desk_policy_puts_both_side_monitors_landscape_side_by_side(self):
        rendered = display.render_config(layout.load_config(REPO / 'monitor-layout.json'))
        self.assertEqual(rendered['capture'], LEFT)
        self.assertEqual([(d['description'], d['x'], d['y']) for d in rendered['landscape']],
                         [(LEFT, 2560, 0), (RIGHT, 4480, 0)])

    def test_hosts_without_the_setting_render_nothing(self):
        self.assertIsNone(display.render_config(layout.load_config(REPO / 'profiles/laptop.json')))

    def test_invalid_settings_are_rejected(self):
        base = json.loads((REPO / 'monitor-layout.json').read_text())
        for stream in ({'capture': 'main', 'landscape': ['side_left']},
                       {'capture': 'side_left', 'landscape': ['side_left', 'side_left']},
                       {'capture': 'side_left', 'landscape': ['side_left', 'nope']},
                       {'capture': 'side_left'}):
            policy = dict(base, sunshineStream=stream)
            with tempfile.NamedTemporaryFile('w', suffix='.json') as file:
                json.dump(policy, file)
                file.flush()
                with self.assertRaises(ValueError, msg=stream):
                    layout.load_config(file.name)

    def test_a_display_needs_a_fixed_mode_and_position(self):
        policy = json.loads((REPO / 'monitor-layout.json').read_text())
        policy['monitors']['side_right']['position'] = 'auto'
        with tempfile.NamedTemporaryFile('w', suffix='.json') as file:
            json.dump(policy, file)
            file.flush()
            with self.assertRaises(ValueError):
                layout.load_config(file.name)


HARNESS = '''
local rules = {}
hl = {
  get_monitors = function() return MONITORS end,
  monitor = function(rule) rules[#rules + 1] = rule.output .. "|" .. rule.position .. "|" .. rule.transform end,
}
dofile(arg[1])
print(table.concat(rules, ","))
'''
SIDES = '{ description = "%s" }, { description = "%s" }' % (LEFT, RIGHT)
OLED = '{ description = "Microstep MAG321UP OLED", name = "DP-6" }'
VIRTUAL = '{ description = "Headless", name = "SUNSHINE-VIRTUAL-1080P" }'


@unittest.skipUnless(shutil.which('lua'), 'Lua interpreter required')
class ToggleTests(unittest.TestCase):
    def evaluate(self, signature, session, monitors=SIDES + ', ' + OLED):
        config = display.render_config(layout.load_config(REPO / 'monitor-layout.json'))
        with tempfile.TemporaryDirectory() as tmp:
            toggle = Path(tmp) / 'toggle.lua'
            toggle.write_text(display.toggle_lua(config, signature))
            out = subprocess.run(['lua', '-', str(toggle)], input=HARNESS.replace('MONITORS', '{ ' + monitors + ' }'),
                                 capture_output=True, text=True,
                                 env=dict(os.environ, HYPRLAND_INSTANCE_SIGNATURE=session))
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout.strip()

    def test_rotates_both_monitors_in_the_session_that_wrote_it(self):
        self.assertEqual(self.evaluate('abc', 'abc'),
                         f'desc:{LEFT}|2560x0|0,desc:{RIGHT}|4480x0|0')

    def test_starts_at_the_origin_when_no_other_monitor_is_on(self):
        # Otherwise the stream cursor drifts: Sunshine measures from 0,0.
        for monitors in (SIDES, SIDES + ', ' + VIRTUAL):
            self.assertEqual(self.evaluate('abc', 'abc', monitors),
                             f'desc:{LEFT}|0x0|0,desc:{RIGHT}|1920x0|0')

    def test_a_new_login_ignores_a_leftover_toggle(self):
        self.assertEqual(self.evaluate('abc', 'other'), '')


class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def connector(self, name, data, status='connected'):
        path = self.root / f'card2-{name}'
        path.mkdir()
        (path / 'status').write_text(status + '\n')
        (path / 'edid').write_bytes(data)

    def test_finds_the_monitor_by_serial_whatever_its_connector_is(self):
        self.connector('DP-4', edid('LEN S22e-19', 0x59333830))
        self.connector('DP-6', edid('LEN S22e-19', 0x01010101))
        self.connector('DP-5', b'', status='disconnected')
        self.assertEqual(display.connector_for(LEFT, self.root), 'DP-6')
        self.assertEqual(display.connector_for(RIGHT, self.root), 'DP-4')

    def test_a_serial_string_takes_precedence_like_hyprland(self):
        self.connector('HDMI-A-1', edid('DELL U2720Q', 1, 'ABC123'))
        self.assertEqual(display.connector_for('Dell Inc. DELL U2720Q ABC123', self.root), 'HDMI-A-1')

    def test_missing_or_ambiguous_monitors_keep_the_configured_output(self):
        self.assertIsNone(display.connector_for(LEFT, self.root))
        self.connector('DP-1', edid('LEN S22e-19', 0x01010101))
        self.connector('DP-2', edid('LEN S22e-19', 0x01010101))
        self.assertIsNone(display.connector_for(LEFT, self.root))


class WatcherTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.watcher = display.Watcher(grace=120, clock=lambda: self.now)

    def test_restores_only_after_the_client_stays_away(self):
        self.watcher.line('[x]: Info: CLIENT CONNECTED')
        self.watcher.line('[x]: Info: CLIENT DISCONNECTED')
        self.now = 119
        self.assertFalse(self.watcher.expired())
        self.now = 120
        self.assertTrue(self.watcher.expired())
        self.assertFalse(self.watcher.expired())

    def test_a_quick_reconnect_keeps_landscape(self):
        self.watcher.line('CLIENT DISCONNECTED')
        self.now = 60
        self.watcher.line('CLIENT CONNECTED')
        self.now = 500
        self.assertFalse(self.watcher.expired())

    def expire(self, running, config=True):
        restarts, finished = [], []
        saved = display.finish, display.app_running, display.load_config, display.restart_host
        display.finish = lambda: finished.append(True)
        display.app_running = lambda: running
        display.load_config = lambda: {'landscape': []} if config else None
        display.restart_host = restarts.append
        try:
            display.on_grace_expired()
        finally:
            display.finish, display.app_running, display.load_config, display.restart_host = saved
        return finished, restarts

    def test_an_app_left_running_is_ended_so_the_next_connection_launches(self):
        finished, restarts = self.expire(running=True)
        self.assertEqual(finished, [True])
        self.assertEqual(len(restarts), 1)

    def test_nothing_is_restarted_without_an_app_or_a_policy(self):
        self.assertEqual(self.expire(running=False)[1], [])
        self.assertEqual(self.expire(running=True, config=False)[1], [])

    def test_other_log_lines_change_nothing(self):
        self.watcher.line('Info: Executing [Desktop]')
        self.now = 1000
        self.assertFalse(self.watcher.expired())


FAKE_HYPRCTL = '''#!/bin/sh
# Reports the side monitors rotated unless the landscape toggle exists.
echo "$@" >> "$HOME/hyprctl.log"
if [ "$1" = monitors ]; then
  t=1; [ -f "$XDG_STATE_HOME/omarchy/toggles/hypr/sunshine-stream-landscape.lua" ] && t=0
  printf '[{"description": "%s", "transform": %s}, {"description": "%s", "transform": %s}]' "$LEFT" "$t" "$RIGHT" "$t"
fi
'''


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        (self.home / 'bin').mkdir()
        (self.home / 'run').mkdir()
        hyprctl = self.home / 'bin/hyprctl'
        hyprctl.write_text(FAKE_HYPRCTL)
        hyprctl.chmod(0o755)
        self.config = self.home / 'stream.json'
        self.config.write_text(json.dumps(display.render_config(layout.load_config(REPO / 'monitor-layout.json'))))
        self.toggle = self.home / 'state/omarchy/toggles/hypr/sunshine-stream-landscape.lua'
        self.env = dict(os.environ, HOME=str(self.home), XDG_STATE_HOME=str(self.home / 'state'),
                        XDG_RUNTIME_DIR=str(self.home / 'run'), HYPRLAND_INSTANCE_SIGNATURE='session',
                        ARCH_SETUPS_STREAM_DISPLAY_CONFIG=str(self.config), LEFT=LEFT, RIGHT=RIGHT,
                        PATH=f'{self.home / "bin"}:{os.environ["PATH"]}', PYTHONDONTWRITEBYTECODE='1')

    def run_helper(self, command, **env):
        return subprocess.run([sys.executable, str(HELPER), command], capture_output=True, text=True,
                              env=dict(self.env, **env), timeout=30)

    def test_prepare_rotates_and_finish_restores(self):
        prepared = self.run_helper('prepare')
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        self.assertIn('landscape applied', prepared.stderr)
        self.assertIn('"session"', self.toggle.read_text())
        finished = self.run_helper('finish')
        self.assertEqual(finished.returncode, 0, finished.stderr)
        self.assertFalse(self.toggle.exists())
        self.assertEqual((self.home / 'hyprctl.log').read_text().count('reload'), 2)

    def test_prepare_never_fails_a_stream_launch(self):
        # Sunshine aborts the launch if a prep command fails.
        for env in ({'PATH': '/nonexistent'}, {'ARCH_SETUPS_STREAM_DISPLAY_CONFIG': str(self.home / 'none.json')}):
            result = self.run_helper('prepare', **env)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_an_unowned_toggle_is_left_alone(self):
        self.toggle.parent.mkdir(parents=True)
        self.toggle.write_text('-- personal\n')
        self.assertEqual(self.run_helper('prepare').returncode, 0)
        self.assertEqual(self.run_helper('finish').returncode, 0)
        self.assertEqual(self.toggle.read_text(), '-- personal\n')

    def test_finish_without_a_stream_does_nothing(self):
        self.assertEqual(self.run_helper('finish').returncode, 0)
        self.assertFalse((self.home / 'hyprctl.log').exists())


class SunshinePrepTests(unittest.TestCase):
    def test_host_runs_the_helper_around_every_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = dict(os.environ, HOME=tmp, XDG_CONFIG_HOME=str(home / '.config'), XDG_STATE_HOME=str(home / 'state'))
            result = subprocess.run(['python3', str(REPO / 'sunshine/configure.py')], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            line = next(l for l in (home / '.config/sunshine/sunshine.conf').read_text().splitlines()
                        if l.startswith('global_prep_cmd = '))
            [command] = json.loads(line.split(' = ', 1)[1])
            helper = '"$(HOME)/.local/lib/arch-setups/sunshine-stream-display.py"'
            self.assertEqual(command, {'do': helper + ' prepare', 'undo': helper + ' finish', 'elevated': False})


if __name__ == '__main__':
    unittest.main()
