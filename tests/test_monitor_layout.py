import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import importlib.util
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / 'hypr/scripts/window-span-dp6-dp4-toggle.sh'
spec = importlib.util.spec_from_file_location('monitor_layout', REPO / 'hypr/scripts/monitor-layout.py')
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)


def monitors():
    return [
        dict(name='DP-6', description='Microstep MAG321UP OLED', width=3840,
             height=2160, scale=1.5, transform=0, x=0, y=0, disabled=False),
        dict(name='DP-5', description='Lenovo Group Limited LEN S22e-19 0x01010101',
             width=1920, height=1080, scale=1, transform=1, x=2560, y=0, disabled=False),
        dict(name='DP-4', description='Lenovo Group Limited LEN S22e-19 0x59333830',
             width=1920, height=1080, scale=1, transform=3, x=3640, y=0, disabled=False),
    ]


class SpanShortcutTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        scripts = self.home / '.config/hypr/scripts'
        scripts.mkdir(parents=True)
        helper = REPO / 'hypr/scripts/monitor-layout.py'
        (scripts / 'monitor-layout.py').write_bytes(helper.read_bytes())
        (scripts / SCRIPT.name).write_bytes(SCRIPT.read_bytes())
        self.script = scripts / SCRIPT.name
        config = REPO / 'monitor-layout.json'
        if config.exists():
            target = self.home / '.config/omarchy/monitor-layout.json'
            target.parent.mkdir(parents=True)
            target.write_bytes(config.read_bytes())
        self.bin = self.home / 'bin'
        self.bin.mkdir()
        stub = self.bin / 'hyprctl'
        stub.write_text('''#!/usr/bin/env python3
import json, os, pathlib, re, sys
h = pathlib.Path(os.environ['HOME'])
args = sys.argv[1:]
state = h / 'window.json'
if not state.exists():
 state.write_text(json.dumps(dict(address='0x123', workspace=dict(name='side:1'),
     floating=os.environ.get('TEST_FLOATING') == '1', pinned=False, fullscreen=0,
     fullscreenClient=0, at=[2560,0], size=[500,700])))
if 'activewindow' in args:
 print(state.read_text())
elif 'monitors' in args:
 print((h / 'monitors.json').read_text())
else:
 with (h / 'dispatches').open('a') as f: f.write(' '.join(args) + '\\n')
 window = json.loads(state.read_text())
 command = ' '.join(args)
 xy = re.search(r'x = (-?\\d+), y = (-?\\d+)', command)
 if xy and 'window.resize' in command:
  size = [int(xy[1]), int(xy[2])]
  window['at'] = [window['at'][i] - (size[i] - window['size'][i]) // 2 for i in range(2)]
  window['size'] = size
 elif xy and 'window.move' in command:
  window['at'] = [int(xy[1]), int(xy[2])]
 elif 'window.float' in command:
  window['floating'] = not window['floating']
 elif 'window.pin' in command:
  window['pinned'] = not window['pinned']
 state.write_text(json.dumps(window))
 print('ok')
''')
        stub.chmod(0o755)
        notify = self.bin / 'notify-send'
        notify.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >&2\n')
        notify.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home), XDG_STATE_HOME=str(self.home / 'state'),
                        PATH=str(self.bin) + ':' + os.environ['PATH'])

    def run_span(self, outputs):
        (self.home / 'monitors.json').write_text(json.dumps(outputs))
        return subprocess.run(['bash', str(self.script)], env=self.env, text=True, capture_output=True)

    def test_current_layout_spans_portrait_pair(self):
        result = self.run_span(monitors())
        self.assertEqual(result.returncode, 0, result.stderr)
        dispatches = (self.home / 'dispatches').read_text()
        self.assertIn('x = 2560, y = 0', dispatches)
        self.assertIn('x = 2160, y = 1920', dispatches)
        window = json.loads((self.home / 'window.json').read_text())
        self.assertEqual(window['at'], [2560, 0])
        self.assertEqual(window['size'], [2160, 1920])
        self.assertTrue(window['floating'])

    def test_floating_window_spans_and_restores_exact_geometry(self):
        self.env['TEST_FLOATING'] = '1'
        result = self.run_span(monitors())
        self.assertEqual(result.returncode, 0, result.stderr)
        window = json.loads((self.home / 'window.json').read_text())
        self.assertEqual(window['at'], [2560, 0])
        self.assertEqual(window['size'], [2160, 1920])
        self.assertTrue(window['floating'])
        self.assertTrue(window['pinned'])
        result = self.run_span([])
        self.assertEqual(result.returncode, 0, result.stderr)
        restored = json.loads((self.home / 'window.json').read_text())
        self.assertEqual(restored['at'], [2560, 0])
        self.assertEqual(restored['size'], [500, 700])
        self.assertTrue(restored['floating'])
        self.assertFalse(restored['pinned'])

    def test_changed_ports_and_reversed_positions(self):
        outputs = monitors()
        outputs[0]['name'] = 'DP-4'
        outputs[1].update(name='DP-9', x=3640)
        outputs[2].update(name='HDMI-A-1', x=2560)
        result = self.run_span(outputs)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('x = 2160, y = 1920', (self.home / 'dispatches').read_text())

    def test_gap_is_rejected_without_moving_window(self):
        outputs = monitors()
        outputs[2]['x'] += 30
        result = self.run_span(outputs)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('adjacent', result.stderr)
        self.assertFalse((self.home / 'dispatches').exists())

    def test_missing_side_is_reported_without_moving_window(self):
        result = self.run_span(monitors()[:2])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('side_right', result.stderr)
        self.assertFalse((self.home / 'dispatches').exists())

    def test_restore_does_not_require_monitors(self):
        state = self.home / 'state/omarchy/window-span-dp6-dp4/123.json'
        state.parent.mkdir(parents=True)
        state.write_text(json.dumps(dict(workspace='side:1', floating=False, pinned=False,
                                        fullscreen=0, fullscreenClient=0, at=[2560,0], size=[500,700])))
        result = self.run_span([])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(state.exists())


class MonitorPolicyTest(unittest.TestCase):
    def setUp(self):
        state = tempfile.TemporaryDirectory(prefix='monitor-test-state-')
        self.addCleanup(state.cleanup)
        environment = patch.dict(os.environ, {'XDG_STATE_HOME': state.name})
        environment.start()
        self.addCleanup(environment.stop)
        self.config = layout.load_config(REPO / 'monitor-layout.json')

    def test_duplicate_display_identity_is_rejected(self):
        outputs = monitors()
        outputs.append(dict(outputs[1], name='DP-9'))
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            layout.resolve(self.config, outputs)

    def test_single_monitor_rules_do_not_disable_main(self):
        text = layout.single_monitor_lua(self.config, monitors())
        self.assertNotIn('DP-', text)
        self.assertNotIn(self.config['monitors']['main']['description'], text)
        self.assertIn(self.config['monitors']['side_left']['description'], text)
        with self.assertRaisesRegex(ValueError, 'main'):
            layout.single_monitor_lua(self.config, monitors()[1:])

    def test_install_preserves_settings_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            omarchy = home / '.config/omarchy'
            (omarchy / 'plugins/priyesh.system-metrics').mkdir(parents=True)
            core = omarchy / 'plugins/hancore.shibumi.bar/core'
            core.mkdir(parents=True)
            (core / 'GroupSlot.qml').write_text('old')
            (core / 'BarSection.qml').write_text('old')
            (omarchy / 'obsidian-tasks.json').write_text(json.dumps(dict(targetScreen='DP-6', token='secret')))
            (omarchy / 'wallpaper-controller.json').write_text(json.dumps(dict(spanGroups=[['old']], wallpaperEnabled=False, active='video')))
            shell = dict(plugins=[dict(id='unrelated', secret='keep'),
                         dict(id='hancore.shibumi.state', shibumi=dict(presentation=dict(other='keep'))),
                         dict(id='io.github.sirjul1337.lock-explorer',
                              phasedPower=dict(main='old', sides=['old'], sideTint=42), video='keep')])
            (omarchy / 'shell.json').write_text(json.dumps(shell))
            outputs = monitors()
            outputs[0]['name'] = 'HDMI-A-1'
            outputs[1]['name'] = 'DP-9'
            outputs[2]['name'] = 'DP-8'
            with patch.object(Path, 'home', return_value=home), patch.object(layout, 'live_monitors', return_value=outputs):
                first = layout.install(self.config, REPO / 'monitor-layout.json', REPO)
                second = layout.install(self.config, REPO / 'monitor-layout.json', REPO)
            self.assertTrue(first['changed'])
            self.assertTrue(first['wallpaperChanged'])
            self.assertFalse(second['changed'])
            self.assertEqual(json.loads((omarchy / 'system-metrics.json').read_text())['targetScreen'], 'DP-8')
            tasks = json.loads((omarchy / 'obsidian-tasks.json').read_text())
            self.assertEqual(tasks, dict(targetScreen='DP-9', token='secret'))
            wallpaper = json.loads((omarchy / 'wallpaper-controller.json').read_text())
            self.assertFalse(wallpaper['wallpaperEnabled'])
            self.assertEqual(wallpaper['active'], 'video')
            self.assertEqual(wallpaper['spanGroups'], [['DP-9', 'DP-8']])
            plugins = json.loads((omarchy / 'shell.json').read_text())['plugins']
            self.assertEqual(plugins[0], shell['plugins'][0])
            self.assertEqual(plugins[2]['phasedPower']['sideTint'], 42)
            self.assertEqual(plugins[2]['phasedPower']['main'], 'HDMI-A-1')
            self.assertEqual(plugins[2]['video'], 'keep')
            self.assertEqual((core / 'GroupSlot.qml').read_text(), 'old')
            self.assertEqual((core / 'BarSection.qml').read_text(), 'old')
            self.assertEqual(plugins[1]['shibumi']['presentation'], dict(other='keep', mainMonitorDescription='Microstep MAG321UP OLED'))
            self.assertNotIn('@monitor:', (home / '.config/hypr/monitors.lua').read_text())

    def test_disconnected_roles_preserve_plugin_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = home / '.config/omarchy/obsidian-tasks.json'
            config.parent.mkdir(parents=True)
            config.write_text('{"targetScreen":"last-known"}')
            with patch.object(Path, 'home', return_value=home), patch.object(layout, 'live_monitors', return_value=[]):
                layout.install(self.config, REPO / 'monitor-layout.json', REPO)
            self.assertEqual(json.loads(config.read_text())['targetScreen'], 'last-known')

    def test_standalone_widget_target_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            with patch.object(Path, 'home', return_value=home), patch.object(layout, 'live_monitors', return_value=monitors()):
                self.assertTrue(layout.configure_widget(self.config, '.config/omarchy/system-metrics.json'))
                self.assertFalse(layout.configure_widget(self.config, '.config/omarchy/system-metrics.json'))
            data = json.loads((home / '.config/omarchy/system-metrics.json').read_text())
            self.assertEqual(data['targetScreen'], 'DP-4')


if __name__ == '__main__':
    unittest.main()
