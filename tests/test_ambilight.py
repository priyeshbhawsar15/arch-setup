"""Room ambilight helper: LED geometry, mapping switch and non-destructive HyperHDR database reconcile."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load():
    loader = importlib.machinery.SourceFileLoader('ambilight_helper', str(ROOT / 'ambilight/ambilight.py'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def quadrant(led):
    """Colour of a four-quadrant test image (R top-left, B top-right, G bottom-left, M bottom-right) at the area centre."""
    h = (led['hmin'] + led['hmax']) / 2
    v = (led['vmin'] + led['vmax']) / 2
    return {(True, True): 'R', (False, True): 'B', (True, False): 'G', (False, False): 'M'}[(h < 0.5, v < 0.5)]


def runs(sequence):
    out = []
    for item in sequence:
        if not out or out[-1] != item:
            out.append(item)
    return ''.join(out)


SCHEMA = '''
CREATE TABLE settings ( type TEXT , config TEXT, hyperhdr_instance INTEGER, updated_at TEXT);
CREATE TABLE instances ( instance INTEGER , friendly_name TEXT, enabled INTEGER DEFAULT 0, last_use TEXT);
CREATE TABLE auth ( user TEXT , password BLOB, token BLOB, salt BLOB, comment TEXT, portal_token TEXT, id TEXT, created_at TEXT, last_use TEXT);
'''


class Geometry(unittest.TestCase):
    def setUp(self):
        self.helper = load()
        self.helper.LAYOUT_FILE = ROOT / 'ambilight/layout.json'

    def test_led_counts_match_the_controllers(self):
        layouts = self.helper.layouts('spatial')
        self.assertEqual({k: len(v) for k, v in layouts.items()}, {'monitor': 169, 'window': 213, 'bed': 414})

    def test_spatial_order_follows_each_strip(self):
        layouts = self.helper.layouts('spatial')
        # Monitor from the chair: bottom-left, counter-clockwise; then 40 under-monitor LEDs left to right.
        self.assertEqual(runs(quadrant(l) for l in layouts['monitor'][:129]), 'GMBRG')
        self.assertEqual(runs(quadrant(l) for l in layouts['monitor'][129:]), 'GM')
        # Window (left of the desk): right side up, top right-to-left, left side down; left half of the image.
        self.assertEqual(runs(quadrant(l) for l in layouts['window']), 'GRG')
        # Bed curtain (right): left side up, top left-to-right, right side down; right half of the image.
        self.assertEqual(runs(quadrant(l) for l in layouts['bed'][:209]), 'MBM')

    def test_under_bed_is_always_one_screen_average_group(self):
        for mapping in ('spatial', 'average'):
            under = self.helper.layouts(mapping)['bed'][209:]
            self.assertEqual({l['group'] for l in under}, {2})
            covered = sum((l['hmax'] - l['hmin']) * (l['vmax'] - l['vmin']) for l in under)
            self.assertGreater(covered, 0.95)
            self.assertLessEqual(covered, 1.0 + 1e-6)

    def test_average_mapping_groups_room_zones_and_keeps_monitor_spatial(self):
        spatial, average = self.helper.layouts('spatial'), self.helper.layouts('average')
        self.assertEqual(spatial['monitor'], average['monitor'])
        self.assertEqual({l['group'] for l in average['window']}, {1})
        self.assertEqual({l['group'] for l in average['bed'][:209]}, {1})
        self.assertEqual({l['group'] for l in spatial['window']}, {0})


class DatabaseReconcile(unittest.TestCase):
    def setUp(self):
        self.helper = load()
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.helper.LAYOUT_FILE = ROOT / 'ambilight/layout.json'
        self.helper.STATE_FILE = base / 'state.json'
        self.helper.DB = base / 'hyperhdr.db'
        con = sqlite3.connect(self.helper.DB)
        con.executescript(SCHEMA)
        con.execute("insert into instances values (0, 'First LED instance', 1, '')")
        defaults = {
            'device': {'type': 'file', 'colorOrder': 'rgb', 'refreshTime': 0},
            'leds': [{'hmin': 0, 'hmax': 1, 'vmin': 0, 'vmax': 0.08, 'group': 0}],
            'smoothing': {'enable': True, 'type': 'HybridRgbInterpolator', 'time_ms': 150, 'updateFrequency': 50},
            'systemControl': {'systemInstanceEnable': False, 'systemInstancePriority': 245},
            'videoControl': {'videoInstanceEnable': True, 'videoInstancePriority': 240},
            'color': {'channelAdjustment': [{'gamma': 1.5}]},
        }
        for typ, cfg in defaults.items():
            con.execute('insert into settings values (?, ?, 0, "")', (typ, json.dumps(cfg)))
        con.execute('insert into settings values ("systemGrabber", ?, NULL, "")', (json.dumps({'fps': 20, 'hardware': True, 'cropTop': 0}),))
        con.commit()
        con.close()
        self.pgrep = mock.patch.object(self.helper.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1))
        self.pgrep.start()

    def tearDown(self):
        self.pgrep.stop()
        self.temp.cleanup()

    def rows(self):
        con = sqlite3.connect(self.helper.DB)
        rows = {(i, t): json.loads(c) for i, t, c in con.execute('select hyperhdr_instance, type, config from settings')}
        names = list(con.execute('select instance, friendly_name, enabled from instances order by instance'))
        con.close()
        return rows, names

    def test_creates_three_wled_instances_and_owns_capture_source(self):
        self.assertEqual(self.helper.verify_db(), 1)
        self.helper.setup_db()
        rows, names = self.rows()
        self.assertEqual(names, [(0, 'monitor', 1), (1, 'window', 1), (2, 'bed', 1)])
        self.assertEqual([rows[(i, 'device')]['host'] for i in range(3)], ['192.168.2.160', '192.168.2.161', '192.168.2.162'])
        self.assertEqual([len(rows[(i, 'leds')]) for i in range(3)], [169, 213, 414])
        self.assertTrue(all(rows[(i, 'systemControl')]['systemInstanceEnable'] for i in range(3)))
        self.assertFalse(any(rows[(i, 'videoControl')]['videoInstanceEnable'] for i in range(3)))
        self.assertEqual(rows[(None, 'systemGrabber')], {'fps': 30, 'hardware': False, 'cropTop': 0,
                         'device': 'Pipewire System Dialog selection', 'videoMode': 512,
                         'hdrToneMapping': False, 'signalDetection': False})
        self.assertEqual(self.helper.verify_db(), 0)

    def test_rerun_keeps_web_ui_edits_outside_owned_settings(self):
        self.helper.setup_db()
        con = sqlite3.connect(self.helper.DB)
        con.execute('update settings set config = ? where hyperhdr_instance = 1 and type = "color"',
                    (json.dumps({'channelAdjustment': [{'gamma': 2.2, 'temperatureRed': 1.1}]}),))
        smoothing = json.loads(con.execute('select config from settings where hyperhdr_instance = 2 and type = "smoothing"').fetchone()[0])
        smoothing['antiFlickeringFilter'] = False
        con.execute('update settings set config = ? where hyperhdr_instance = 2 and type = "smoothing"', (json.dumps(smoothing),))
        con.commit()
        con.close()
        self.assertEqual(self.helper.verify_db(), 0)
        self.helper.setup_db()
        rows, _ = self.rows()
        self.assertEqual(rows[(1, 'color')], {'channelAdjustment': [{'gamma': 2.2, 'temperatureRed': 1.1}]})
        self.assertFalse(rows[(2, 'smoothing')]['antiFlickeringFilter'])

    def test_mapping_change_is_detected_and_written(self):
        self.helper.setup_db()
        self.helper.save_state({'mapping': 'average', 'profile': 'movie', 'auto': True})
        self.assertEqual(self.helper.verify_db(), 1)
        self.helper.write_leds('average')
        self.assertEqual(self.helper.verify_db(), 0)
        rows, _ = self.rows()
        self.assertEqual({l['group'] for l in rows[(1, 'leds')]}, {1})


class CaptureCheck(unittest.TestCase):
    """hyperhdr.service ExecStartPost: fail (so systemd restarts HyperHDR) when screen capture never starts."""

    def setUp(self):
        self.helper = load()
        self.temp = tempfile.TemporaryDirectory()
        self.helper.DB = Path(self.temp.name) / 'hyperhdr.db'
        con = sqlite3.connect(self.helper.DB)
        con.executescript(SCHEMA)
        con.execute("insert into auth (user, portal_token) values ('Hyperhdr', 'EYsEDVx9MMAA')")
        con.commit()
        con.close()

    def tearDown(self):
        self.temp.cleanup()

    def serve(self, *infos):
        """Successive serverinfo replies; the last one repeats."""
        replies = list(infos)

        class FakeHyper:
            def call(_, msg):
                assert msg['command'] == 'serverinfo'
                return {'info': replies.pop(0) if len(replies) > 1 else replies[0]}
        return mock.patch.object(self.helper, 'Hyper', FakeHyper)

    @staticmethod
    def info(active=None, grabber_enabled=True):
        priorities = [] if active is None else [{'componentId': 'SYSTEMGRABBER', 'priority': 245, 'active': active}]
        return {'priorities': priorities, 'components': [{'name': 'SYSTEMGRABBER', 'enabled': grabber_enabled}]}

    def test_passes_once_the_capture_input_is_active(self):
        with self.serve(self.info(), self.info(active=False), self.info(active=True)):
            self.assertEqual(self.helper.capture_check(timeout=5, poll=0), 0)

    def test_fails_when_the_portal_session_never_delivers_frames(self):
        with self.serve(self.info(active=False)):
            self.assertEqual(self.helper.capture_check(timeout=0.05, poll=0), 1)

    def test_waits_for_the_api_to_come_up(self):
        calls = iter([OSError('refused'), OSError('refused'), self.info(active=True)])

        class FakeHyper:
            def __init__(_):
                item = next(calls)
                if isinstance(item, Exception):
                    raise item
                _.item = item

            def call(_, msg):
                return {'info': _.item}
        with mock.patch.object(self.helper, 'Hyper', FakeHyper):
            self.assertEqual(self.helper.capture_check(timeout=5, poll=0), 0)

    def test_skipped_while_no_screen_share_choice_is_saved(self):
        con = sqlite3.connect(self.helper.DB)
        con.execute("update auth set portal_token = ''")
        con.commit()
        con.close()
        with mock.patch.object(self.helper, 'Hyper', side_effect=AssertionError('must not wait for capture')):
            self.assertEqual(self.helper.capture_check(timeout=0.05, poll=0), 0)

    def test_skipped_when_screen_capture_is_switched_off(self):
        with self.serve(self.info(grabber_enabled=False)):
            self.assertEqual(self.helper.capture_check(timeout=0.05, poll=0), 0)


if __name__ == '__main__':
    unittest.main()
