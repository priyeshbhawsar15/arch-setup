import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WidgetInstallerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / 'home'
        self.home.mkdir()
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        for name, body in {
            'omarchy': '#!/bin/bash\nif [[ "$1 $2" == "plugin list" ]]; then printf \'[{"id":"%s","enabled":true}]\\n\' "$TEST_PLUGIN_ID"; fi\n',
            'omarchy-shell': '#!/bin/bash\nexit 0\n',
            'obsidian': '#!/bin/bash\nexit 0\n',
        }.items():
            target = self.bin / name
            target.write_text(body)
            target.chmod(0o755)
        self.env = {**os.environ, 'HOME': str(self.home), 'XDG_STATE_HOME': str(self.home / '.local/state'),
                    'PATH': str(self.bin) + ':' + os.environ['PATH'], 'PYTHONDONTWRITEBYTECODE': '1'}

    def git(self, *args, cwd=None):
        return subprocess.check_output(['git', *args], cwd=cwd, text=True, stderr=subprocess.PIPE).strip()

    def fixture(self, feature, command):
        upstream = self.base / 'upstream'
        upstream.mkdir()
        self.git('init', '-q', cwd=upstream)
        (upstream / 'manifest.json').write_text(json.dumps({'id': 'priyesh.' + feature}))
        (upstream / 'bin').mkdir()
        (upstream / 'bin' / command).write_text('#!/bin/bash\nexit 0\n')
        (upstream / 'bin' / command).chmod(0o755)
        (upstream / 'install.sh').write_text('#!/bin/bash\nexit 0\n')
        (upstream / 'install.sh').chmod(0o755)
        self.git('add', '.', cwd=upstream)
        self.git('-c', 'user.name=Tests', '-c', 'user.email=tests@example.invalid', 'commit', '-qm', 'initial', cwd=upstream)
        old = self.git('rev-parse', 'HEAD', cwd=upstream)
        target = self.home / '.config/omarchy/plugins' / ('priyesh.' + feature)
        target.parent.mkdir(parents=True)
        self.git('clone', '-q', str(upstream), str(target))
        return upstream, target, old

    def run_installer(self, filename, feature, upstream, revision):
        source = (ROOT / filename).read_text()
        lines = source.splitlines()
        lines = [('SCRIPT_DIR=' + shlex.quote(str(ROOT))) if line.startswith('SCRIPT_DIR=') else
                 ('plugin_url=' + shlex.quote(str(upstream))) if line.startswith('plugin_url=') else
                 ('plugin_commit=' + shlex.quote(revision)) if line.startswith('plugin_commit=') else line
                 for line in lines]
        script = self.base / filename
        script.write_text('\n'.join(lines) + '\n')
        return subprocess.run(['bash', str(script)], capture_output=True, text=True,
                              env={**self.env, 'TEST_PLUGIN_ID': 'priyesh.' + feature})

    def test_existing_weather_checkout_updates_without_undefined_stage(self):
        upstream, target, old = self.fixture('weather-widget', 'weather-widget')
        (upstream / 'new').write_text('new payload')
        self.git('add', '.', cwd=upstream)
        self.git('-c', 'user.name=Tests', '-c', 'user.email=tests@example.invalid', 'commit', '-qm', 'update', cwd=upstream)
        new = self.git('rev-parse', 'HEAD', cwd=upstream)
        result = self.run_installer('install-weather-widget.sh', 'weather-widget', upstream, new)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git('rev-parse', 'HEAD', cwd=target), new)

    def test_matching_quota_checkout_repairs_cli_and_secret_permissions(self):
        upstream, target, revision = self.fixture('omniroute-quota', 'omniroute-quota')
        config = self.home / '.config/omarchy/omniroute-quota.json'
        config.write_text('{"token":"test-token","custom":42}')
        config.chmod(0o644)
        result = self.run_installer('install-omniroute-quota.sh', 'omniroute-quota', upstream, revision)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(config.read_text())['custom'], 42)
        self.assertTrue((self.home / '.local/bin/omniroute-quota').is_symlink())
        self.assertEqual((self.home / '.local/bin/omniroute-quota').resolve(), target / 'bin/omniroute-quota')


if __name__ == '__main__':
    unittest.main()
