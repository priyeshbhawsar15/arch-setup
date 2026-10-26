"""Supported media backend demand must not add a second visible widget."""
import importlib.util
import json
import os
from unittest.mock import patch
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('shibumi_settings', ROOT / 'config/shibumi-settings.py')
settings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(settings)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        environment = patch.dict(os.environ, {'XDG_STATE_HOME': str(Path(self.temp.name) / 'state')})
        environment.start()
        self.addCleanup(environment.stop)
        self.shell = Path(self.temp.name) / 'shell.json'
        self.policy = Path(self.temp.name) / 'policy.json'
        self.policy.write_text(json.dumps({'barMain': 'main', 'monitors': {'main': {'description': 'OLED'}}}))
        self.data = {'bar': {'id': 'hancore.shibumi.bar', 'layout': {'left': ['other']}},
                     'plugins': [{'id': 'hancore.shibumi.state', 'shibumi': {
                         'presentation': {'shellStyle': 'shibumi'}, 'widgets': {'G9': {'enabled': False}}}}],
                     'disabledPlugins': [], 'unrelated': {'keep': True}}
        self.save()

    def save(self):
        self.shell.write_text(json.dumps(self.data))

    def test_backend_only_preserves_every_other_value(self):
        settings.main(self.shell, media_backend_only=True)
        result = json.loads(self.shell.read_text())
        self.assertEqual(result['plugins'].pop(), {'id': 'hancore.shibumi.media'})
        self.assertEqual(result, self.data)

    def test_backend_only_idempotent(self):
        settings.main(self.shell, media_backend_only=True)
        original = self.shell.read_bytes()
        settings.main(self.shell, media_backend_only=True)
        self.assertEqual(self.shell.read_bytes(), original)

    def test_existing_backend_options_preserved(self):
        self.data['plugins'].append({'id': 'hancore.shibumi.media', 'custom': True})
        self.save()
        settings.main(self.shell, media_backend_only=True)
        self.assertEqual(json.loads(self.shell.read_text()), self.data)

    def test_explicit_disable_not_overridden(self):
        self.data['disabledPlugins'].append('hancore.shibumi.media')
        self.save()
        with self.assertRaises(ValueError):
            settings.main(self.shell, media_backend_only=True)
        self.assertEqual(json.loads(self.shell.read_text()), self.data)

    def test_normal_install_keeps_g9_hidden_and_loads_backend(self):
        settings.main(self.shell, self.policy)
        result = json.loads(self.shell.read_text())
        state = result['plugins'][0]['shibumi']
        self.assertFalse(state['widgets']['G9']['enabled'])
        self.assertEqual(state['presentation']['mainMonitorDescription'], 'OLED')
        self.assertEqual(result['bar'], self.data['bar'])
        self.assertEqual(result['plugins'][-1], {'id': 'hancore.shibumi.media'})

    def test_missing_suite_rejected(self):
        self.data['plugins'] = []
        self.save()
        with self.assertRaises(ValueError):
            settings.main(self.shell, media_backend_only=True)


if __name__ == '__main__':
    unittest.main()
