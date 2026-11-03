import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SunshineConfigTests(unittest.TestCase):
    def test_existing_config_is_hardened_without_losing_display_or_pairing(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            config = home / '.config/sunshine'
            config.mkdir(parents=True)
            path = config / 'sunshine.conf'
            original = '# personal\noutput_name = DP-5\nupnp = enabled\nupnp = enabled\ncsrf_allowed_origins = https://old-host\n'
            path.write_text(original)
            credentials = config / 'sunshine_state.json'
            credentials.write_text('private pairing data')
            env = dict(os.environ, HOME=tmp, XDG_CONFIG_HOME=str(home / '.config'), XDG_STATE_HOME=str(home / 'state'))
            command = ['python3', str(ROOT / 'sunshine/configure.py')]
            first = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            content = path.read_text()
            self.assertIn('output_name = DP-5', content)
            self.assertIn('upnp = disabled', content)
            self.assertNotIn('upnp = enabled', content)
            self.assertNotIn('https://old-host', content)
            self.assertIn('bind_address = 127.0.0.1', content)
            self.assertEqual(credentials.read_text(), 'private pairing data')
            backups = list((home / 'state/arch-setups/backups').glob('sunshine-*/sunshine.conf'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), original)
            self.assertEqual(backups[0].parent.stat().st_mode & 0o777, 0o700)
            second = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(content, path.read_text())
            self.assertEqual(len(list((home / 'state/arch-setups/backups').glob('sunshine-*'))), 1)


class PairingRepairTests(unittest.TestCase):
    def test_duplicate_identity_is_reduced_without_changing_other_devices(self):
        import importlib.util
        import json
        spec = importlib.util.spec_from_file_location('repair', ROOT / 'sunshine/repair-pairing.py')
        repair = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(repair)
        # Distinct PEM bodies exercise certificate identity grouping independently
        # of formatting; the repair never grants trust to a new certificate.
        a = '-----BEGIN CERTIFICATE-----\nY2VydC1h\n-----END CERTIFICATE-----\n'
        b = '-----BEGIN CERTIFICATE-----\nY2VydC1i\n-----END CERTIFICATE-----\n'
        state = {'password': 'untouched', 'root': {'uniqueid': 'host', 'named_devices': [
            {'name': 'phone', 'uuid': 'old', 'cert': a, 'enabled': 'true'},
            {'name': 'laptop', 'uuid': 'other', 'cert': b, 'enabled': 'true'},
            {'name': 'phone', 'uuid': 'new', 'cert': a, 'enabled': 'true'},
        ]}}
        original = json.dumps(state)
        updated, count = repair.deduplicate(state)
        self.assertEqual(count, 1)
        self.assertEqual(updated['password'], 'untouched')
        self.assertEqual(updated['root']['uniqueid'], 'host')
        self.assertEqual([d['uuid'] for d in updated['root']['named_devices']], ['other', 'new'])
        self.assertEqual(json.dumps(state), original)
        self.assertEqual(repair.deduplicate(updated), (updated, 0))
        state['root']['named_devices'][0]['enabled'] = 'false'
        with self.assertRaisesRegex(ValueError, 'disabled'):
            repair.deduplicate(state)


class PairingResetTests(unittest.TestCase):
    def test_reset_removes_host_and_client_certificates_but_preserves_admin(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            config = home / 'config/sunshine'
            (config / 'credentials').mkdir(parents=True)
            old = {'username': 'admin', 'password': 'hash', 'salt': 'salt',
                   'root': {'uniqueid': 'old-host', 'named_devices': [{'cert': 'old-client'}],
                            'devices': [{'certs': ['old-legacy-client']}]}}
            state = config / 'sunshine_state.json'
            state.write_text(json.dumps(old))
            (config / 'credentials/cacert.pem').write_text('old-host-cert')
            (config / 'credentials/cakey.pem').write_text('old-private-key')
            env = dict(os.environ, HOME=tmp, XDG_CONFIG_HOME=str(home / 'config'), XDG_STATE_HOME=str(home / 'state'))
            result = subprocess.run(['python3', str(ROOT / 'sunshine/reset-pairing.py')], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(state.read_text()), {'username': 'admin', 'password': 'hash', 'salt': 'salt'})
            self.assertFalse((config / 'credentials/cacert.pem').exists())
            self.assertFalse((config / 'credentials/cakey.pem').exists())
            backups = list((home / 'state/arch-setups/backups').glob('sunshine-reset-*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].stat().st_mode & 0o777, 0o700)
            self.assertEqual(json.loads((backups[0] / state.name).read_text()), old)
            self.assertEqual((backups[0] / 'credentials/cakey.pem').read_text(), 'old-private-key')


class NetworkBindingTests(unittest.TestCase):
    def test_binding_is_available_without_lan_or_tailscale_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for command in ('ip', 'tailscale'):
                path = base / command
                path.write_text('#!/bin/sh\nexit 1\n')
                path.chmod(0o755)
            result = subprocess.run(['bash', str(ROOT / 'sunshine/start.sh'), '--print-address'],
                                    env=dict(os.environ, PATH=tmp + ':/usr/bin'), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), '0.0.0.0')


class SunshineInstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.log = self.home / 'calls.log'
        self.choices = self.home / 'state/arch-setups/features.json'
        binaries = self.home / 'bin'
        binaries.mkdir()
        for name in ('sunshine', 'pacman'):
            path = binaries / name
            path.write_text('#!/bin/bash\nexit 0\n')
            path.chmod(0o755)
        path = binaries / 'systemctl'
        path.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$SUNSHINE_TEST_LOG"\n'
                        'if [[ "$*" == *" cat "* ]]; then [[ -n "${SUNSHINE_TEST_UNITS:-}" ]] || exit 1; fi\n')
        path.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home), XDG_CONFIG_HOME=str(self.home / 'config'),
                        XDG_STATE_HOME=str(self.home / 'state'), XDG_RUNTIME_DIR=str(self.home),
                        SUNSHINE_TEST_LOG=str(self.log), PYTHONDONTWRITEBYTECODE='1',
                        PATH=f"{binaries}:{os.environ['PATH']}")

    def run_installer(self, *args, **env):
        self.log.write_text('')
        result = subprocess.run(['bash', str(ROOT / 'install-sunshine.sh'), *args], env={**self.env, **env},
                                capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_unchanged_rerun_does_not_restart_a_live_stream(self):
        self.run_installer()
        self.assertIn('restart app-dev.lizardbyte.app.Sunshine.service', self.log.read_text())
        result = self.run_installer()
        self.assertNotIn('restart', self.log.read_text())
        self.assertIn('start app-dev.lizardbyte.app.Sunshine.service', self.log.read_text())
        self.assertIn('already installed', result.stdout)

    def test_automated_run_does_not_record_a_user_choice(self):
        self.run_installer(ARCH_SETUPS_AUTOMATED='1')
        self.assertFalse(self.choices.exists())

    def test_disable_without_installed_units_succeeds(self):
        self.run_installer('--disable', ARCH_SETUPS_AUTOMATED='1')
        self.assertNotIn('--now', self.log.read_text())
