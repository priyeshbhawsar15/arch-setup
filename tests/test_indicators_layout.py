import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'indicators/layout.py'

class IndicatorsLayoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.shell = self.home / '.config/omarchy/shell.json'
        self.shell.parent.mkdir(parents=True)
        self.state = self.home / '.local/state/arch-setups/indicators-layout.json'
        self.config = {'bar': {'id': 'omarchy.bar', 'layout': {'left': [], 'center': [{'id':'local.clock'}], 'right': [{'id':'omarchy.indicators','alwaysShow':True}, {'id':'local.weather'}]}}, 'plugins': [{'id':'local.service'}]}
        self.shell.write_text(json.dumps(self.config))

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, action):
        result = subprocess.run(['python3', str(SCRIPT), action, str(self.shell), str(self.state)], env=dict(os.environ, HOME=str(self.home), XDG_STATE_HOME=str(self.home / '.local/state')), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_enable_disable_restores_original_settings_and_unrelated_entries(self):
        self.call('enable')
        installed = json.loads(self.shell.read_text())
        self.assertEqual(installed['bar']['layout']['right'][0]['id'], 'priyesh.indicators')
        self.assertTrue(installed['bar']['layout']['right'][0]['alwaysShow'])
        self.assertEqual(installed['bar']['layout']['right'][1], {'id':'local.weather'})
        before = self.shell.read_bytes()
        self.call('enable')
        self.assertEqual(self.shell.read_bytes(), before)
        self.call('disable')
        self.assertEqual(json.loads(self.shell.read_text()), self.config)

    def test_disable_does_not_restore_stale_slot_after_bar_change(self):
        self.call('enable')
        updated = json.loads(self.shell.read_text())
        updated['bar']['id'] = 'local.new-bar'
        updated['bar']['layout']['right'] = [{'id':'local.new-widget'}]
        self.shell.write_text(json.dumps(updated))
        self.call('disable')
        self.assertEqual(json.loads(self.shell.read_text()), updated)

    def test_absent_original_slot_is_removed_without_inventing_default_widget(self):
        self.config['bar']['id'] = 'hancore.shibumi.bar'
        self.config['bar']['layout']['right'] = [{'id':'local.weather'}]
        self.shell.write_text(json.dumps(self.config))
        self.call('enable')
        self.assertTrue(json.loads(self.shell.read_text())['bar']['layout']['right'][0]['shibumiModule'])
        self.call('disable')
        self.assertEqual(json.loads(self.shell.read_text()), self.config)

if __name__ == '__main__':
    unittest.main()
