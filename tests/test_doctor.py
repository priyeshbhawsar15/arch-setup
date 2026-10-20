import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'config/doctor.py'


class DoctorTest(unittest.TestCase):
    def test_read_only_checks_report_bad_permissions_without_exposing_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            config = home / '.config/omarchy/omniroute-quota.json'
            config.parent.mkdir(parents=True)
            config.write_text('{"token":"VERY_PRIVATE_TEST_TOKEN"}')
            config.chmod(0o644)
            before = config.read_bytes(), config.stat().st_mtime_ns, config.stat().st_mode
            result = subprocess.run(['python3', str(SCRIPT), '--json'], capture_output=True, text=True,
                                    env={**os.environ, 'HOME': tmp, 'XDG_STATE_HOME': str(home / 'state')})
            self.assertTrue(result.stdout.startswith('{'), result.stderr)
            payload = json.loads(result.stdout)
            self.assertNotIn('VERY_PRIVATE_TEST_TOKEN', result.stdout + result.stderr)
            self.assertTrue(any(row['status'] == 'error' and row['name'] == 'credentials:omniroute-quota'
                                for row in payload['checks']))
            self.assertEqual((config.read_bytes(), config.stat().st_mtime_ns, config.stat().st_mode), before)

    def test_preflight_checks_dotfiles_before_any_installer_can_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            result = subprocess.run(['python3', str(SCRIPT), '--preflight', '--dotfiles', str(home / 'missing'), '--json'],
                                    capture_output=True, text=True,
                                    env={**os.environ, 'HOME': tmp, 'XDG_STATE_HOME': str(home / 'state')})
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(result.stdout.startswith('{'), result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(any(row['name'] == 'dotfiles' and row['status'] == 'error' for row in payload['checks']))
            self.assertFalse((home / '.config').exists())


if __name__ == '__main__':
    unittest.main()
