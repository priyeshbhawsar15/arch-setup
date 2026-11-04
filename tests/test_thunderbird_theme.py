"""Fluentbird/Thunderbird deployment against fixture homes, local Git remotes and fake commands."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / 'thunderbird/fluentbird.py'
CUSTOM = ROOT / 'thunderbird/fluentbird-custom.css'
BLOCK_START = '// >>> arch-setups fluentbird'
PREF = 'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);'
CHANGED, UNCHANGED, NO_PROFILE = 0, 10, 11


class Fixture(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.home = self.base / 'home'
        self.thunderbird = self.home / '.config/thunderbird'
        self.profile = self.thunderbird / 'abc.default-release'
        self.profile.mkdir(parents=True)
        (self.thunderbird / 'old.default').mkdir()
        # The per-installation default must win over an older profile flagged Default=1.
        (self.thunderbird / 'profiles.ini').write_text(
            '[General]\nVersion=2\n\n[Profile0]\nName=default-release\nIsRelative=1\nPath=abc.default-release\n\n'
            '[Install111]\nDefault=abc.default-release\nLocked=1\n\n'
            '[Profile1]\nName=default\nIsRelative=1\nPath=old.default\nDefault=1\n')
        (self.profile / 'prefs.js').write_text('user_pref("extensions.activeThemeID", "default-theme@mozilla.org");\n')
        self.chrome = self.profile / 'chrome'
        self.env = dict(os.environ, HOME=str(self.home), XDG_CONFIG_HOME=str(self.home / '.config'),
                        XDG_STATE_HOME=str(self.home / 'state'), XDG_DATA_HOME=str(self.home / 'data'),
                        PYTHONDONTWRITEBYTECODE='1', ARCH_SETUPS_AUTOMATED='1')
        for name in ('ARCH_SETUPS_THUNDERBIRD_DIR', 'ARCH_SETUPS_THUNDERBIRD_PROFILE', 'ARCH_SETUPS_IGNORE_LOCAL',
                     'ARCH_SETUPS_PROFILE', 'FLUENTBIRD_SOURCE_URL', 'FLUENTBIRD_SOURCE_PIN'):
            self.env.pop(name, None)
        self.source = self.base / 'source'
        self.write_source(self.source, 'one')

    @staticmethod
    def write_source(directory, version, extra=None):
        for old in directory.iterdir() if directory.exists() else ():
            if old.name == '.git':
                continue
            shutil.rmtree(old) if old.is_dir() and not old.is_symlink() else old.unlink()
        (directory / 'Icons').mkdir(parents=True, exist_ok=True)
        (directory / 'Titlebar_Icons').mkdir(exist_ok=True)
        (directory / 'userChrome.css').write_text(f'@import url("custom.css");\n/* theme {version} */\n')
        (directory / 'custom.css').write_text('/* upstream stub must never be deployed */\n')
        (directory / 'Icons/mail.svg').write_text(f'<svg id="mail-{version}"/>')
        (directory / 'Titlebar_Icons/maximize.png').write_bytes(b'\x89PNG\r\n' + version.encode())
        (directory / 'LICENSE').write_text('MIT License\nCopyright (c) Danny\n')
        (directory / 'README.md').write_text('not deployed\n')
        for relative, text in (extra or {}).items():
            (directory / relative).write_text(text)

    def helper(self, *args, env=None):
        return subprocess.run(['python3', '-I', str(HELPER), *args], env=env or self.env, capture_output=True, text=True)

    def apply(self, revision='one', source=None, custom=CUSTOM):
        return self.helper('apply', '--source', str(source or self.source), '--revision', revision, '--custom', str(custom))

    def status(self, revision='one'):
        result = self.helper('status', '--json', '--revision', revision)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def backups(self):
        return sorted((self.home / 'state/arch-setups/backups').glob('fluentbird-*'))


class DeploymentTests(Fixture):
    def test_apply_deploys_owned_files_enables_stylesheets_and_is_idempotent(self):
        result = self.apply()
        self.assertEqual(result.returncode, CHANGED, result.stderr)
        self.assertIn('theme one', (self.chrome / 'userChrome.css').read_text())
        self.assertEqual((self.chrome / 'Icons/mail.svg').read_text(), '<svg id="mail-one"/>')
        self.assertEqual((self.chrome / 'custom.css').read_text(), CUSTOM.read_text())
        self.assertTrue((self.chrome / 'LICENSE.fluentbird').read_text().startswith('MIT License'))
        self.assertFalse((self.chrome / 'README.md').exists())
        self.assertIn(PREF, (self.profile / 'user.js').read_text())
        self.assertEqual(self.status()['state'], 'current')
        before = {path: path.stat().st_mtime_ns for path in self.profile.rglob('*') if path.is_file()}
        self.assertEqual(self.apply().returncode, UNCHANGED)
        self.assertEqual(before, {path: path.stat().st_mtime_ns for path in self.profile.rglob('*') if path.is_file()})
        self.assertEqual(self.backups(), [])

    def test_the_installation_default_profile_is_used_not_the_legacy_default(self):
        self.assertEqual(self.apply().returncode, CHANGED)
        self.assertFalse((self.thunderbird / 'old.default/chrome').exists())

    def test_existing_user_js_is_preserved_and_backed_up_then_only_the_block_is_removed(self):
        user = self.profile / 'user.js'
        user.write_text('user_pref("mail.spellcheck.inline", false);')
        self.assertEqual(self.apply().returncode, CHANGED)
        text = user.read_text()
        self.assertTrue(text.startswith('user_pref("mail.spellcheck.inline", false);\n' + BLOCK_START))
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual((self.backups()[0] / 'user.js').read_text(), 'user_pref("mail.spellcheck.inline", false);')
        self.assertEqual(self.helper('remove').returncode, CHANGED)
        self.assertEqual(user.read_text(), 'user_pref("mail.spellcheck.inline", false);\n')
        self.assertFalse(self.chrome.exists())

    def test_remove_deletes_a_user_js_the_theme_alone_created_and_second_remove_is_a_noop(self):
        self.apply()
        self.assertEqual(self.helper('remove').returncode, CHANGED)
        self.assertFalse((self.profile / 'user.js').exists())
        self.assertFalse(self.chrome.exists())
        self.assertEqual(self.helper('remove').returncode, UNCHANGED)

    def test_foreign_user_chrome_is_never_overwritten_and_nothing_else_changes(self):
        self.chrome.mkdir()
        (self.chrome / 'userChrome.css').write_text('/* my own theme */\n')
        result = self.apply()
        self.assertEqual(result.returncode, 1)
        self.assertIn('userChrome.css', result.stderr)
        self.assertEqual((self.chrome / 'userChrome.css').read_text(), '/* my own theme */\n')
        self.assertEqual(sorted(path.name for path in self.chrome.iterdir()), ['userChrome.css'])
        self.assertFalse((self.profile / 'user.js').exists())

    def test_identical_preexisting_files_are_adopted_not_treated_as_conflicts(self):
        self.chrome.mkdir()
        shutil.copy2(self.source / 'userChrome.css', self.chrome / 'userChrome.css')
        self.assertEqual(self.apply().returncode, CHANGED)
        self.assertEqual(self.status()['state'], 'current')

    def test_locally_edited_owned_file_is_backed_up_then_restored(self):
        self.apply()
        (self.chrome / 'custom.css').write_text('/* hand edit */\n')
        self.assertEqual(self.status()['state'], 'modified')
        self.assertEqual(self.apply().returncode, CHANGED)
        self.assertEqual((self.chrome / 'custom.css').read_text(), CUSTOM.read_text())
        self.assertEqual((self.backups()[0] / 'chrome/custom.css').read_text(), '/* hand edit */\n')

    def test_update_replaces_files_drops_stale_owned_files_and_keeps_foreign_ones(self):
        self.write_source(self.source, 'one', {'Icons/old.svg': '<svg/>'})
        self.apply()
        (self.chrome / 'mine.css').write_text('/* unrelated */\n')
        self.write_source(self.source, 'two')
        self.assertEqual(self.status('two')['state'], 'stale')
        self.assertEqual(self.apply('two').returncode, CHANGED)
        self.assertIn('theme two', (self.chrome / 'userChrome.css').read_text())
        self.assertFalse((self.chrome / 'Icons/old.svg').exists())
        self.assertEqual((self.chrome / 'mine.css').read_text(), '/* unrelated */\n')
        self.assertEqual(self.status('two')['state'], 'current')

    def test_remove_keeps_foreign_files_and_backs_up_edited_owned_ones(self):
        self.apply()
        (self.chrome / 'mine.css').write_text('/* unrelated */\n')
        (self.chrome / 'custom.css').write_text('/* personal */\n')
        self.assertEqual(self.helper('remove').returncode, CHANGED)
        self.assertEqual(sorted(path.name for path in self.chrome.iterdir()), ['mine.css'])
        self.assertEqual((self.backups()[0] / 'chrome/custom.css').read_text(), '/* personal */\n')

    def test_symlinked_chrome_directory_and_user_js_are_refused(self):
        elsewhere = self.base / 'elsewhere'
        elsewhere.mkdir()
        self.chrome.symlink_to(elsewhere)
        result = self.apply()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(list(elsewhere.iterdir()), [])
        self.chrome.unlink()
        target = self.base / 'managed-user.js'
        target.write_text('// owned by dotfiles\n')
        (self.profile / 'user.js').symlink_to(target)
        self.assertEqual(self.apply().returncode, 1)
        self.assertEqual(target.read_text(), '// owned by dotfiles\n')

    def test_symlink_in_theme_source_is_rejected_before_any_write(self):
        (self.source / 'Icons/escape.svg').symlink_to('/etc/hostname')
        self.assertEqual(self.apply().returncode, 1)
        self.assertFalse(self.chrome.exists())

    def test_no_profile_yet_is_reported_not_created(self):
        shutil.rmtree(self.thunderbird)
        self.assertEqual(self.apply().returncode, NO_PROFILE)
        self.assertFalse(self.thunderbird.exists())
        report = self.status()
        self.assertEqual(report['state'], 'no-profile')

    def test_status_is_read_only_and_warns_about_a_non_system_theme(self):
        (self.profile / 'prefs.js').write_text('user_pref("extensions.activeThemeID", "thunderbird-compact-dark@mozilla.org");\n')
        report = self.status()
        self.assertEqual(report['state'], 'not-applied')
        self.assertTrue(any('System theme' in warning for warning in report['warnings']))
        self.assertFalse(self.chrome.exists())
        self.assertFalse((self.profile / 'user.js').exists())


class InstallerTests(Fixture):
    """Run the real installers against a local Git remote and a fake Thunderbird."""

    def setUp(self):
        super().setUp()
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        fake = self.bin / 'thunderbird'
        fake.write_text('#!/bin/bash\nexit 0\n')
        fake.chmod(0o755)
        self.remote = self.base / 'remote'
        self.write_source(self.remote, 'one')
        self.git('init', '-q')
        self.git('add', '.')
        self.git('-c', 'user.name=Tests', '-c', 'user.email=tests@example.invalid', 'commit', '-qm', 'one')
        self.pin = self.git('rev-parse', 'HEAD').strip()
        self.env.update(PATH=str(self.bin) + os.pathsep + os.environ['PATH'], FLUENTBIRD_SOURCE_URL=str(self.remote),
                        FLUENTBIRD_SOURCE_PIN=self.pin)
        self.checkout = self.home / 'data/arch-setups/fluentbird'

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.remote, text=True)

    def installer(self, *args, env=None):
        return subprocess.run(['bash', str(ROOT / 'install-fluentbird.sh'), *args], env=env or self.env,
                              capture_output=True, text=True)

    def test_install_is_pinned_idempotent_and_reports_already_installed(self):
        result = self.installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Fluentbird installed', result.stdout)
        self.assertEqual(subprocess.check_output(['git', '-C', str(self.checkout), 'rev-parse', 'HEAD'], text=True).strip(), self.pin)
        self.assertIn('theme one', (self.chrome / 'userChrome.css').read_text())
        again = self.installer()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn('already installed', again.stdout)
        self.assertEqual(self.installer('--status').returncode, 0)

    def test_a_pin_change_updates_the_theme_to_the_exact_new_commit(self):
        self.installer()
        self.write_source(self.remote, 'two')
        self.git('add', '-A')
        self.git('-c', 'user.name=Tests', '-c', 'user.email=tests@example.invalid', 'commit', '-qm', 'two')
        result = self.installer(env=dict(self.env, FLUENTBIRD_SOURCE_PIN=self.git('rev-parse', 'HEAD').strip()))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('theme two', (self.chrome / 'userChrome.css').read_text())

    def test_disable_remove_and_reenable_manage_profile_checkout_and_remembered_choice(self):
        lifecycle = {key: value for key, value in self.env.items() if key != 'ARCH_SETUPS_AUTOMATED'}
        self.assertEqual(self.installer(env=lifecycle).returncode, 0)
        choices = self.home / 'state/arch-setups/features.json'
        self.assertTrue(json.loads(choices.read_text())['install-fluentbird.sh'])
        disabled = self.installer('--disable', env=lifecycle)
        self.assertEqual(disabled.returncode, 0, disabled.stderr)
        self.assertFalse(self.chrome.exists())
        self.assertFalse((self.profile / 'user.js').exists())
        self.assertTrue((self.checkout / '.git').is_dir(), '--disable keeps the reproducible checkout')
        self.assertFalse(json.loads(choices.read_text())['install-fluentbird.sh'])
        self.assertEqual(self.installer(env=lifecycle).returncode, 0)
        self.assertTrue((self.chrome / 'userChrome.css').is_file())
        removed = self.installer('--remove', env=lifecycle)
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertFalse(self.chrome.exists())
        self.assertFalse(self.checkout.exists())

    def test_remove_keeps_a_checkout_it_does_not_own(self):
        self.installer()
        subprocess.check_call(['git', '-C', str(self.checkout), 'remote', 'set-url', 'origin', 'https://example.invalid/other.git'])
        result = self.installer('--remove')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Keeping', result.stdout)
        self.assertTrue(self.checkout.is_dir())

    def test_foreign_checkout_origin_fails_closed_without_touching_the_profile(self):
        self.installer()
        shutil.rmtree(self.chrome)
        (self.profile / 'user.js').unlink()
        subprocess.check_call(['git', '-C', str(self.checkout), 'remote', 'set-url', 'origin', 'https://example.invalid/other.git'])
        self.assertNotEqual(self.installer().returncode, 0)
        self.assertFalse(self.chrome.exists())

    def test_fresh_thunderbird_without_a_profile_defers_instead_of_failing(self):
        shutil.rmtree(self.thunderbird)
        result = self.installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('no profile yet', result.stdout)
        self.assertFalse(self.thunderbird.exists())

    def stubbed(self, name, body):
        """Copy an installer next to a stub lib.sh so package/command presence is deterministic."""
        directory = Path(tempfile.mkdtemp(prefix='stub-' + name + '-', dir=self.base))
        shutil.copytree(ROOT / 'thunderbird', directory / 'thunderbird')
        (directory / 'lib.sh').write_text(body)
        shutil.copy2(ROOT / f'install-{name}.sh', directory / f'install-{name}.sh')
        return directory / f'install-{name}.sh'

    STUB = ('log() { printf "%s\\n" "$*"; }\n'
            'is_command_available() { [[ "$1" != thunderbird ]] && command -v "$1" >/dev/null 2>&1; }\n'
            'desktop_file_exists() { return 1; }\n'
            'require_omarchy() { :; }\n'
            'omarchy() { printf "omarchy %s\\n" "$*"; }\n'
            'feature_lifecycle() { :; }\n'
            'install_pinned_git_checkout() { printf "unexpected checkout\\n"; }\n')

    def test_thunderbird_installer_uses_omarchy_only_when_missing(self):
        script = self.stubbed('thunderbird', self.STUB)
        missing = subprocess.run(['bash', str(script)], env=self.env, capture_output=True, text=True)
        self.assertEqual(missing.returncode, 0, missing.stderr)
        self.assertIn('omarchy pkg add thunderbird', missing.stdout)
        present = self.stubbed('thunderbird', self.STUB.replace('[[ "$1" != thunderbird ]] && ', ''))
        result = subprocess.run(['bash', str(present)], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('already installed', result.stdout)
        self.assertNotIn('omarchy', result.stdout)

    def test_fluentbird_requires_thunderbird_and_changes_nothing_without_it(self):
        script = self.stubbed('fluentbird', self.STUB)
        result = subprocess.run(['bash', str(script)], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('install-thunderbird.sh', result.stdout)
        self.assertNotIn('unexpected checkout', result.stdout)
        self.assertFalse(self.chrome.exists())


class RegistrationTests(Fixture):
    def test_registry_dependency_source_lock_and_safe_profile_agree(self):
        registry = json.loads((ROOT / 'config/features.json').read_text())
        self.assertEqual(registry['install-fluentbird.sh']['requires'], ['install-thunderbird.sh'])
        source = json.loads((ROOT / 'config/plugin-sources.json').read_text())['install-fluentbird.sh']
        text = (ROOT / 'install-fluentbird.sh').read_text()
        self.assertIn('theme_url="' + source['source'] + '"', text)
        self.assertIn('theme_commit="' + source['pin'] + '"', text)
        safe = json.loads((ROOT / 'features.json').read_text())['enabledInstallers']
        self.assertIn('install-thunderbird.sh', safe)
        self.assertIn('install-fluentbird.sh', safe)

    def test_doctor_reports_pending_before_first_run_then_ok_when_current(self):
        profile = self.base / 'features.json'
        profile.write_text(json.dumps({'enabledInstallers': ['install-thunderbird.sh', 'install-fluentbird.sh']}))

        def readiness():
            result = subprocess.run(['python3', str(ROOT / 'config/doctor.py'), '--json', '--profile', str(profile)],
                                    env=self.env, capture_output=True, text=True)
            rows = {row['name']: row for row in json.loads(result.stdout)['checks']}
            return rows['readiness:fluentbird']

        shutil.rmtree(self.thunderbird)
        self.assertEqual(readiness()['status'], 'pending')
        self.thunderbird.mkdir(parents=True)
        (self.thunderbird / 'profiles.ini').write_text('[Profile0]\nName=x\nIsRelative=1\nPath=p\nDefault=1\n')
        (self.thunderbird / 'p').mkdir()
        self.assertEqual(readiness()['status'], 'error')
        pin = json.loads((ROOT / 'config/plugin-sources.json').read_text())['install-fluentbird.sh']['pin']
        self.assertEqual(self.apply(revision=pin).returncode, CHANGED)
        self.assertEqual(readiness()['status'], 'ok')


if __name__ == '__main__':
    unittest.main()
