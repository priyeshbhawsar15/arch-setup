import os
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]

class OmalandMenuTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / 'home'
        self.work = Path(self.tmp.name) / 'setup'
        self.work.mkdir()
        self.home.mkdir()
        shutil.copy2(REPO / 'lib.sh', self.work / 'lib.sh')
        shutil.copytree(REPO / 'config', self.work / 'config')
        src = (REPO / 'install-omaland.sh').read_text().split('\ncase "${1:-}"', 1)[0]
        (self.work / 'functions.sh').write_text(src)
        self.bin = self.work / 'bin'
        self.bin.mkdir()
        for name in ('omarchy', 'omarchy-shell'):
            path = self.bin / name
            path.write_text('#!/bin/sh\nexit 0\n')
            path.chmod(0o755)
        self.menu = self.home / '.config/omarchy/extensions/omarchy-menu.jsonc'
        self.menu.parent.mkdir(parents=True)
        self.env = dict(os.environ, HOME=str(self.home), PATH=str(self.bin) + ':' + os.environ['PATH'])

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, fn):
        subprocess.run(['bash', '-c', 'source "$1"; "$2"', 'test', str(self.work / 'functions.sh'), fn], env=self.env, check=True, capture_output=True)

    def test_existing_jsonc_accepts_editor_and_keeps_siblings(self):
        self.menu.write_text('{\n// custom user choice\n"style.hyprland.custom": {"action": "my-tool"},\n}\n')
        self.call('install_menu_entry')
        check = subprocess.run(['python3', str(REPO / 'config/managed-config.py'), 'check-menu', str(self.menu), '{"style.hyprland.omaland":{"icon":"󰸌","label":"Omaland Visual Editor","aliases":["omaland"],"action":"omarchy-shell shell toggle bobbynicholas.omaland"}}'], capture_output=True)
        self.assertEqual(check.returncode, 0, check.stderr.decode())
        self.assertIn('// custom user choice', self.menu.read_text())
        self.assertIn('"style.hyprland.custom": {"action": "my-tool"}', self.menu.read_text())
        before = self.menu.read_bytes()
        self.call('install_menu_entry')
        self.assertEqual(self.menu.read_bytes(), before)

    def test_disable_removes_only_owned_entries(self):
        self.menu.write_text('{\n"style.hyprland.custom": {"action": "my-tool"},\n"style.hyprland.omaland": {},\n"style.hyprland.edit": {},\n"retained": {}\n}\n')
        self.call('remove_menu_entry')
        result = self.menu.read_text()
        self.assertIn('"style.hyprland.custom": {"action": "my-tool"}', result)
        self.assertNotIn('"style.hyprland.omaland"', result)
        self.assertNotIn('"style.hyprland.edit"', result)

    def test_custom_desktop_entry_survives_install_and_disable(self):
        plugin = self.home / '.config/omarchy/plugins/bobbynicholas.omaland'
        plugin.mkdir(parents=True)
        (plugin / 'omaland.desktop').write_text('[Desktop Entry]\nX-Omaland-Managed=true\nIcon=@ICON@\n')
        desktop = self.home / '.local/share/applications/omaland.desktop'
        desktop.parent.mkdir(parents=True)
        desktop.write_text('[Desktop Entry]\nExec=my-private-editor\n')
        original = desktop.read_bytes()
        self.call('install_desktop_entry')
        self.assertEqual(desktop.read_bytes(), original)
        self.call('remove_desktop_entry')
        self.assertEqual(desktop.read_bytes(), original)


class ShibumiSettingsTests(OmalandMenuTests):
    # Avoid inherited menu tests: this fixture exercises a separate installer.
    test_existing_jsonc_accepts_editor_and_keeps_siblings = None
    test_disable_removes_only_owned_entries = None
    test_custom_desktop_entry_survives_install_and_disable = None

    def setUp(self):
        super().setUp()
        src = (REPO / 'install-shibumi-shell.sh').read_text().split('\ncase "${1:-}"', 1)[0]
        (self.work / 'functions.sh').write_text(src)
        (self.work / 'shibumi').mkdir()
        (self.work / 'shibumi/Bar.qml').write_text('historical copied override')
        (self.work / 'monitor-layout.json').write_text(json.dumps({'barMain':'main','monitors':{'main':{'description':'Fixture main'}}}))

    def test_supported_configuration_does_not_replace_managed_payload(self):
        target = self.home / '.config/omarchy/plugins/hancore.shibumi.bar/Bar.qml'
        target.parent.mkdir(parents=True)
        target.write_text('transactionally managed payload')
        shell = self.home / '.config/omarchy/shell.json'
        original = {'bar':{'id':'hancore.shibumi.bar','layout':{'center':[{'id':'local.clock'}]}}, 'plugins':[{'id':'hancore.shibumi.state','shibumi':{'version':1,'presentation':{'radius':'small'}}}, {'id':'local.service'}]}
        shell.write_text(json.dumps(original))
        self.call('deploy_overrides')
        self.assertEqual(target.read_text(), 'transactionally managed payload')
        updated = json.loads(shell.read_text())
        self.assertEqual(updated['bar'], original['bar'])
        state = updated['plugins'][0]['shibumi']
        self.assertEqual(state['presentation']['mainMonitorDescription'], 'Fixture main')
        self.assertEqual(state['presentation']['radius'], 'small')
        self.assertTrue(state['widgets']['G15']['enabled'])

if __name__ == '__main__':
    unittest.main()
