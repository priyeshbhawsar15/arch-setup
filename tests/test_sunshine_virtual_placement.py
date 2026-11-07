"""Placement of the Sunshine virtual output by the rendered monitors.lua."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('placement_monitor_layout', REPO / 'hypr/scripts/monitor-layout.py')
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)

VIRTUAL = 'SUNSHINE-VIRTUAL-1080P'
# The real desk: two rotated 1080p side monitors to the right of a 4K OLED at 1.5x.
OLED = {'name': 'DP-6', 'x': 0, 'y': 0, 'width': 3840, 'height': 2160, 'scale': 1.5, 'transform': 0}
LEFT = {'name': 'DP-5', 'x': 2560, 'y': 0, 'width': 1920, 'height': 1080, 'scale': 1, 'transform': 1}
RIGHT = {'name': 'DP-4', 'x': 3640, 'y': 0, 'width': 1920, 'height': 1080, 'scale': 1, 'transform': 3}

# Records hl.monitor rules for the virtual output and the events subscribed to.
HARNESS = '''
local monitors = MONITORS
local rules, events = {}, {}
hl = {
  env = function() end,
  workspace_rule = function() end,
  get_monitors = function() return monitors end,
  on = function(event) events[#events + 1] = event end,
  monitor = function(rule)
    if rule.output == "%s" then rules[#rules + 1] = rule.position .. "@" .. rule.scale end
  end,
}
dofile(os.getenv("HOME") .. "/.config/hypr/monitors.lua")
print(table.concat(rules, ","))
print(table.concat(events, ","))
''' % VIRTUAL


def lua_monitors(monitors):
    fields = []
    for m in monitors:
        m = dict({'is_mirror': False}, **m)
        fields.append('{' + ', '.join(f'{k} = {json.dumps(v)}' for k, v in m.items()) + '}')
    return '{' + ', '.join(fields) + '}'


@unittest.skipUnless(shutil.which('lua'), 'Lua interpreter required')
class VirtualPlacementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        config = self.home / '.config/hypr'
        config.mkdir(parents=True)
        (config / 'monitors.lua').write_text(
            layout.render(layout.load_config(REPO / 'monitor-layout.json'), REPO / 'hypr/monitors.lua'))

    def place(self, *monitors):
        script = HARNESS.replace('MONITORS', lua_monitors(monitors))
        out = subprocess.run(['lua', '-'], input=script, env=dict(os.environ, HOME=str(self.home)),
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        rules, events = (out.stdout.split('\n') + [''])[:2]
        return rules, events.split(',')

    def virtual(self, x, y, scale=2):
        return {'name': VIRTUAL, 'x': x, 'y': y, 'width': 1920, 'height': 1080, 'scale': scale, 'transform': 0}

    def test_takes_origin_when_the_left_monitor_is_off(self):
        # Sunshine measures from 0,0; without this the stream cursor drifts.
        rules, _ = self.place(LEFT, RIGHT, self.virtual(4720, 0))
        self.assertEqual(rules, '0x0@1')

    def test_sits_right_of_everything_when_origin_is_used(self):
        # Logical sizes: OLED 2560 wide at 1.5x, rotated side monitors 1080 wide.
        rules, _ = self.place(OLED, LEFT, RIGHT, self.virtual(0, 0))
        self.assertEqual(rules, '4720x0@1')

    def test_goes_below_when_a_monitor_overlaps_the_origin_area(self):
        near = {'name': 'HDMI-A-1', 'x': 1000, 'y': 0, 'width': 1920, 'height': 1080, 'scale': 1, 'transform': 0}
        rules, _ = self.place(near, self.virtual(2920, 0))
        self.assertEqual(rules, '0x1080@1')

    def test_unscaled_output_already_in_place_is_left_alone(self):
        # An identical rule still fires layout events, which would loop.
        rules, _ = self.place(LEFT, RIGHT, self.virtual(0, 0, scale=1))
        self.assertEqual(rules, '')

    def test_wrong_scale_is_corrected_in_place(self):
        rules, _ = self.place(LEFT, RIGHT, self.virtual(0, 0, scale=2))
        self.assertEqual(rules, '0x0@1')

    def test_rule_exists_before_the_output_is_created(self):
        rules, events = self.place(LEFT, RIGHT)
        self.assertEqual(rules, '0x0@1')
        for event in ('config.reloaded', 'monitor.added', 'monitor.removed', 'monitor.layout_changed'):
            self.assertIn(event, events)


if __name__ == '__main__':
    unittest.main()
