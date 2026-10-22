import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'config/feature-profile.py'


class FeaturePreferencesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.profile = self.base / 'features.json'
        self.profile.write_text('{"disabledInstallers":[]}')
        self.env = {**os.environ, 'XDG_STATE_HOME': str(self.base / 'state')}

    def run_profile(self, *args):
        return subprocess.run(['python3', str(SCRIPT), '--profile', str(self.profile), *args],
                              env=self.env, capture_output=True, text=True)

    def test_disabled_choice_survives_automatic_install_and_can_be_exported(self):
        self.assertEqual(self.run_profile('remember', 'install-weather-widget.sh', 'false').returncode, 0)
        self.assertEqual(self.run_profile('enabled', 'install-weather-widget.sh').returncode, 1)
        self.assertEqual(self.run_profile('enabled', 'install-system-metrics.sh').returncode, 0)
        result = self.run_profile('export')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'disabledInstallers': ['install-weather-widget.sh']})
        self.assertEqual((self.base / 'state/arch-setups/features.json').stat().st_mode & 0o777, 0o600)

    def test_explicit_reenable_overrides_profile_disable(self):
        self.profile.write_text('{"disabledInstallers":["install-weather-widget.sh"]}')
        self.assertEqual(self.run_profile('enabled', 'install-weather-widget.sh').returncode, 1)
        self.assertEqual(self.run_profile('remember', 'install-weather-widget.sh', 'true').returncode, 0)
        self.assertEqual(self.run_profile('enabled', 'install-weather-widget.sh').returncode, 0)

    def test_workspace_feature_is_skipped_when_required_suite_disabled(self):
        self.profile.write_text('{"disabledInstallers":["install-shibumi-shell.sh"]}')
        self.assertEqual(self.run_profile('enabled', 'install-per-monitor-workspaces.sh').returncode, 1)

    def test_explicit_selection_cannot_omit_required_installers(self):
        self.profile.write_text('{"enabledInstallers":["install-dotfiles.sh"]}')
        result = self.run_profile('plan')
        self.assertEqual(result.returncode, 2)
        self.assertIn('required installer', result.stderr)
        self.assertFalse((self.base / 'state').exists())

    def test_corrupt_preferences_do_not_get_overwritten(self):
        state = self.base / 'state/arch-setups/features.json'
        state.parent.mkdir(parents=True)
        state.write_text('{broken')
        result = self.run_profile('remember', 'install-weather-widget.sh', 'true')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(state.read_text(), '{broken')


if __name__ == '__main__':
    unittest.main()
