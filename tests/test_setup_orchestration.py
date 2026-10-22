"""End-to-end entrypoint/profile tests with only logging installers, never a live system."""
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EntrypointTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='setup-contract-')
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        self.home = self.base / 'home with spaces'
        self.home.mkdir()
        for name in ('install-all.sh', 'lib.sh', 'features.json', 'monitor-layout.json'):
            shutil.copy2(ROOT / name, self.repo / name)
        for name in ('config', 'profiles'):
            shutil.copytree(ROOT / name, self.repo / name)
        for name in ('steam/gaming_profile.py', 'steam/profile/games.json', 'gaming/selection.json'):
            target = self.repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        self.names = re.findall(r'^  (install-[a-z0-9-]+\.sh)$', (self.repo / 'install-all.sh').read_text(), re.M)
        for name in self.names + ['preflight.sh', 'doctor.sh']:
            target = self.repo / name
            target.write_text('#!/bin/bash\nprintf "%s\\n" "' + name + '" >> "$HOME/invocations"\n[[ "${FAIL_INSTALLER:-}" != "' + name + '" ]]\n')
            target.chmod(0o755)
        # Never inspect or update the host package state, even on a cold host.
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        self.database = self.base / 'pacman/sync'
        self.database.mkdir(parents=True)
        (self.database / 'core.db').write_text('fixture index')
        command = self.bin / 'pacman-conf'
        command.write_text('#!/bin/bash\nif [[ "$1" == --repo-list ]]; then echo core; else printf "%s\\n" "$TEST_PACMAN_DB"; fi\n')
        command.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home), XDG_STATE_HOME=str(self.home / 'state'),
                        XDG_CONFIG_HOME=str(self.home / 'config'), XDG_DATA_HOME=str(self.home / 'data'),
                        XDG_CACHE_HOME=str(self.home / 'cache'), ARCH_SETUPS_IGNORE_LOCAL='1',
                        PATH=str(self.bin) + os.pathsep + os.environ['PATH'], TEST_PACMAN_DB=str(self.database.parent))
        for name in ('ARCH_SETUPS_PROFILE', 'ARCH_SETUPS_SETTINGS', 'ARCH_SETUPS_GAMING_PROFILE', 'ARCH_SETUPS_MONITOR_LAYOUT'):
            self.env.pop(name, None)

    def run_setup(self, *args):
        return subprocess.run(['bash', str(self.repo / 'install-all.sh'), *args], env=self.env, capture_output=True, text=True)

    def test_registry_and_order_are_complete_and_topological(self):
        registry = json.loads((ROOT / 'config/features.json').read_text())
        self.assertEqual(set(self.names), set(registry))
        self.assertEqual(len(self.names), len(set(self.names)))
        for name, metadata in registry.items():
            for dependency in metadata.get('requires', []):
                self.assertLess(self.names.index(dependency), self.names.index(name))

    def test_default_plan_is_read_only_and_has_no_private_or_desktop_features(self):
        self.env.pop('PYTHONDONTWRITEBYTECODE', None)  # Exercise a stock user's shell.
        result = self.run_setup('--plan')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('RUN  install-steam.sh', result.stdout)
        self.assertIn('SKIP install-home-assistant.sh', result.stdout)
        self.assertIn('SKIP install-t3-planner-executor.sh', result.stdout)
        self.assertFalse((self.home / 'invocations').exists())
        self.assertFalse((self.home / 'state').exists())
        self.assertEqual(list(self.repo.rglob('__pycache__')), [], 'a plan must not write bytecode into its source tree')

    def test_disabled_installers_never_execute(self):
        profile = self.repo / 'disabled.json'
        profile.write_text(json.dumps({'enabledInstallers': ['install-stow.sh'], 'disabledInstallers': []}))
        result = self.run_setup('--profile', str(profile))
        if os.geteuid() == 0:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('not root', result.stderr)
            self.assertFalse((self.home / 'invocations').exists())
            return
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.home / 'invocations').read_text().splitlines(), ['preflight.sh', 'install-stow.sh', 'doctor.sh'])

    def test_cold_noninteractive_apply_requires_approval_before_any_installer(self):
        (self.database / 'core.db').unlink()
        result = self.run_setup()
        self.assertNotEqual(result.returncode, 0)
        if os.geteuid() != 0:
            self.assertIn('--approve-system-update', result.stderr)
            self.assertEqual((self.home / 'invocations').read_text().splitlines(), ['preflight.sh'])
        self.assertFalse((self.home / 'state/arch-setups/initial-system-update.json').exists())

    def test_invalid_profile_fails_before_preflight_and_preserves_bytes(self):
        profile = self.repo / 'broken.json'
        profile.write_text('{"enabledInstallers":["install-typo.sh"]}')
        result = self.run_setup('--profile', str(profile))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.home / 'invocations').exists())
        self.assertEqual(profile.read_text(), '{"enabledInstallers":["install-typo.sh"]}')

    def test_readiness_failure_is_not_reported_as_success(self):
        if os.geteuid() == 0:
            self.assertNotEqual(self.run_setup().returncode, 0)
            return
        self.env['FAIL_INSTALLER'] = 'doctor.sh'
        result = self.run_setup()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('All selected features passed', result.stdout)


class SourceAndLockContracts(unittest.TestCase):
    def test_every_plugin_pin_is_published_format_and_matches_installer(self):
        sources = json.loads((ROOT / 'config/plugin-sources.json').read_text())
        registry = json.loads((ROOT / 'config/features.json').read_text())
        for name, source in sources.items():
            with self.subTest(name=name):
                text = (ROOT / name).read_text()
                self.assertRegex(source['pin'], r'^[a-f0-9]{40}$')
                self.assertIn('="' + source['source'] + '"', text)
                self.assertIn('="' + source['pin'] + '"', text)
                if 'plugin' in registry[name]:
                    self.assertIn('plugin_id="' + registry[name]['plugin'] + '"', text)

    def test_lifecycle_helpers_have_no_undefined_backup_name(self):
        for installer in ROOT.glob('install-*.sh'):
            self.assertNotRegex(installer.read_text(), r'\bbackup_paths\b')

    def test_json_lock_response_is_validated_and_unknown_states_fail_closed(self):
        doctor = load('setup_doctor_contract', 'config/doctor.py')
        self.assertFalse(doctor.unlocked('{"locked":true,"requested":false,"sessionLocked":false}'))
        self.assertFalse(doctor.unlocked('{}'))
        self.assertFalse(doctor.unlocked('false'))
        self.assertFalse(doctor.unlocked('unavailable'))
        self.assertTrue(doctor.unlocked('{"locked":false,"requested":false,"sessionLocked":false}'))

    def test_appearance_is_not_replaced_after_gui_edits(self):
        # The real deployment fixture covers SDDM and generated rules as well.
        from test_hypr_deployment import DeploymentTests
        case = DeploymentTests('test_matching_helper_content_repairs_executable_permission')
        case.setUp()
        try:
            result = case.run_install()
            self.assertEqual(result.returncode, 0, result.stderr)
            path = case.config / 'looknfeel.lua'
            path.write_text('-- user/Omaland appearance\n')
            result = case.run_install()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(path.read_text(), '-- user/Omaland appearance\n')
        finally:
            case.doCleanups()


if __name__ == '__main__':
    unittest.main()
