import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PinnedDeploymentTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.upstream = self.base / 'upstream'
        self.target = self.base / 'plugins/example.widget'
        self.upstream.mkdir()
        self.git('init', '-q', cwd=self.upstream)
        (self.upstream / 'manifest.json').write_text('{"id":"example.widget"}')
        (self.upstream / 'payload').write_text('old')
        self.git('add', '.', cwd=self.upstream)
        self.git('-c', 'user.name=Tests', '-c', 'user.email=tests@example.invalid', 'commit', '-qm', 'old', cwd=self.upstream)
        self.old = self.git('rev-parse', 'HEAD', cwd=self.upstream).strip()
        self.target.parent.mkdir()
        self.git('clone', '-q', str(self.upstream), str(self.target))
        (self.upstream / 'payload').write_text('new')
        self.git('add', '.', cwd=self.upstream)
        self.git('-c', 'user.name=Tests', '-c', 'user.email=tests@example.invalid', 'commit', '-qm', 'new', cwd=self.upstream)
        self.new = self.git('rev-parse', 'HEAD', cwd=self.upstream).strip()

    def git(self, *args, cwd=None):
        return subprocess.check_output(['git', *args], cwd=cwd, text=True, stderr=subprocess.PIPE)

    def deploy(self, revision, validation='return 0', source=None, reviewed_origin=None):
        script = f'''set -euo pipefail
source {shlex.quote(str(ROOT / 'lib.sh'))}
omarchy() {{ {validation}; }}
install_pinned_plugin {shlex.quote(str(self.target))} {shlex.quote(str(source or self.upstream))} {revision} example.widget {shlex.quote(str(reviewed_origin or ''))}
'''
        return subprocess.run(['bash', '-c', script], capture_output=True, text=True)

    def test_updates_validated_checkout_to_exact_commit(self):
        result = self.deploy(self.new)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git('rev-parse', 'HEAD', cwd=self.target).strip(), self.new)
        self.assertEqual((self.target / 'payload').read_text(), 'new')

    def test_reviewed_origin_migration_installs_fork_and_retains_unknown_origins(self):
        fork = self.base / 'fork'
        self.git('clone', '-q', str(self.upstream), str(fork))
        refused = self.deploy(self.new, source=fork)
        self.assertNotEqual(refused.returncode, 0)
        result = self.deploy(self.new, source=fork, reviewed_origin=self.upstream)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git('remote', 'get-url', 'origin', cwd=self.target).strip(), str(fork))

    def test_validation_failure_retains_working_revision_and_cleans_stage(self):
        result = self.deploy(self.new, 'return 42')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('validation failed', result.stderr)
        self.assertEqual(self.git('rev-parse', 'HEAD', cwd=self.target).strip(), self.old)
        self.assertEqual(list(self.target.parent.glob('.*.install.*')), [])

    def test_dirty_checkout_is_not_overwritten(self):
        (self.target / 'payload').write_text('my custom changes')
        result = self.deploy(self.new)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('local changes', result.stderr)
        self.assertEqual((self.target / 'payload').read_text(), 'my custom changes')

    def test_untracked_file_is_preserved(self):
        (self.target / 'notes').write_text('local notes')
        result = self.deploy(self.new)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('local changes', result.stderr)
        self.assertEqual((self.target / 'notes').read_text(), 'local notes')

    def test_bad_manifest_id_retains_working_revision(self):
        (self.upstream / 'manifest.json').write_text('{"id":"foreign.widget"}')
        self.git('add', '.', cwd=self.upstream)
        self.git('-c', 'user.name=Tests', '-c', 'user.email=tests@example.invalid', 'commit', '-qm', 'wrong id', cwd=self.upstream)
        bad = self.git('rev-parse', 'HEAD', cwd=self.upstream).strip()
        result = self.deploy(bad)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unexpected plugin ID', result.stderr)
        self.assertEqual(self.git('rev-parse', 'HEAD', cwd=self.target).strip(), self.old)


class BackupTest(unittest.TestCase):
    def test_backup_preserves_original_data_in_private_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / 'custom.lua'
            source.write_text('personal settings')
            script = f'source {shlex.quote(str(ROOT / "lib.sh"))}; backup_feature_paths config-test {shlex.quote(str(source))}'
            result = subprocess.run(['bash', '-c', script], capture_output=True, text=True,
                                    env={**os.environ, 'XDG_STATE_HOME': str(base / 'state')})
            self.assertEqual(result.returncode, 0, result.stderr)
            backup = Path(result.stdout.strip())
            self.assertEqual(backup.stat().st_mode & 0o777, 0o700)
            self.assertEqual((backup / source.relative_to('/')).read_text(), 'personal settings')
            self.assertEqual(source.read_text(), 'personal settings')


if __name__ == '__main__':
    unittest.main()
