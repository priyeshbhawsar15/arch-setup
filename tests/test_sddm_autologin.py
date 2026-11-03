import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SddmConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        session = self.root / 'usr/share/wayland-sessions/hyprland-uwsm.desktop'
        session.parent.mkdir(parents=True)
        session.write_text('[Desktop Entry]\nExec=uwsm start hyprland.desktop\n')
        self.config = load('sddm_config', 'sddm/configure-autologin.py')
        self.path = self.root / 'etc/sddm.conf.d/90-arch-setups-autologin.conf'

    def test_enable_disable_are_idempotent_and_preserve_other_configuration(self):
        theme = self.root / 'etc/sddm.conf.d/10-theme.conf'
        theme.parent.mkdir(parents=True)
        theme.write_text('[Theme]\nCurrent=personal\n')
        self.assertTrue(self.config.configure(True, 'alice', self.root))
        self.assertIn('User=alice', self.path.read_text())
        self.assertIn('Session=hyprland-uwsm.desktop', self.path.read_text())
        self.assertIn('Relogin=false', self.path.read_text())
        self.assertFalse(self.config.configure(True, 'alice', self.root))
        self.assertTrue(self.config.configure(False, 'alice', self.root))
        self.assertIn('User=\n', self.path.read_text())
        self.assertFalse(self.config.configure(False, 'alice', self.root))
        self.assertEqual(theme.read_text(), '[Theme]\nCurrent=personal\n')
        backup = list((self.root / 'var/lib/arch-setups/backups').glob('sddm-autologin-*'))
        self.assertEqual(len(backup), 1)
        self.assertEqual(backup[0].stat().st_mode & 0o777, 0o700)
        self.assertIn('User=alice', (backup[0] / self.path.name).read_text())

    def test_disable_without_managed_file_does_not_override_other_autologin(self):
        other = self.root / 'etc/sddm.conf.d/50-autologin.conf'
        other.parent.mkdir(parents=True)
        other.write_text('[Autologin]\nUser=alice\n')
        self.assertFalse(self.config.configure(False, 'alice', self.root, check_only=True))
        self.assertFalse(self.config.configure(False, 'alice', self.root))
        self.assertFalse(self.path.exists())

    def test_read_only_check_does_not_create_configuration(self):
        self.assertTrue(self.config.configure(True, 'alice', self.root, check_only=True))
        self.assertFalse(self.path.exists())
        self.assertFalse((self.root / 'var').exists())
        self.config.configure(True, 'alice', self.root)
        self.assertFalse(self.config.configure(True, 'alice', self.root, check_only=True))

    def test_foreign_file_and_higher_priority_overrides_are_refused(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('[Autologin]\nUser=bob\n')
        with self.assertRaisesRegex(ValueError, 'foreign'):
            self.config.configure(True, 'alice', self.root)
        self.path.unlink()
        override = self.root / 'etc/sddm.conf'
        override.write_text('[Theme]\nCurrent=personal\n[Autologin]\nUser=bob\n')
        with self.assertRaisesRegex(ValueError, 'override'):
            self.config.configure(True, 'alice', self.root)
        self.assertFalse(self.path.exists())
        self.assertIn('User=bob', override.read_text())


class StartupLockTests(unittest.TestCase):
    def setUp(self):
        self.lock = load('startup_lock', 'sddm/lock-after-login.py')

    def test_waits_for_secure_lock_rather_than_accepting_a_request(self):
        replies = iter(['{"passwordPam":true,"secure":false}', '{"passwordPam":true,"secure":true}'])
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, next(replies) if args[-1] == 'status' else 'ok', '')
        self.assertEqual(self.lock.lock_session(run=run, sleep=lambda _: None), 0)
        self.assertEqual(sum(args[-1] == 'status' for args in calls), 2)
        self.assertNotIn(['uwsm', 'stop'], calls)

    def test_lock_failure_requests_session_shutdown(self):
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, '{"secure":false}', '')
        clock = iter([0, 0, 99])
        self.assertEqual(self.lock.lock_session(run=run, sleep=lambda _: None, monotonic=lambda: next(clock)), 1)
        self.assertIn(['uwsm', 'stop'], calls)


@unittest.skipUnless(Path('/usr/share/wayland-sessions/hyprland-uwsm.desktop').is_file(), 'needs the UWSM session file')
class SddmInstallerTests(unittest.TestCase):
    def run_failing_enable(self, enabled_before):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            binaries = home / 'bin'
            binaries.mkdir()
            log = home / 'calls.log'
            commands = {
                'sddm': 'exit 0', 'uwsm': 'exit 0',
                'omarchy-shell': 'echo \'{"passwordPam": true}\'',
                'systemctl': 'printf "%s\\n" "$*" >> "$SDDM_TEST_LOG"; [[ "$*" != *is-enabled* ]] || exit "$SDDM_TEST_ENABLED"',
                'python3': '[[ "$1" != *configure-autologin.py ]] || exit 2; exec /usr/bin/python3 "$@"',
            }
            for name, body in commands.items():
                path = binaries / name
                path.write_text('#!/bin/bash\n' + body + '\n')
                path.chmod(0o755)
            result = subprocess.run(['bash', str(ROOT / 'install-sddm-autologin.sh'), '--enable'],
                                    capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                    env={'HOME': tmp, 'XDG_CONFIG_HOME': str(home / 'config'), 'XDG_STATE_HOME': str(home / 'state'),
                                         'XDG_RUNTIME_DIR': tmp, 'SDDM_TEST_LOG': str(log), 'SDDM_TEST_ENABLED': '0' if enabled_before else '1',
                                         'ARCH_SETUPS_AUTOMATED': '1', 'PATH': f'{binaries}:/usr/bin:/bin'})
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            return log.read_text()

    def test_failed_enable_removes_a_guard_it_added(self):
        self.assertIn('--user disable arch-sddm-autolock.service', self.run_failing_enable(False))

    def test_failed_enable_keeps_a_guard_protecting_existing_autologin(self):
        self.assertNotIn('--user disable', self.run_failing_enable(True))
