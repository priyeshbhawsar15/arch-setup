import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


def noisy_wrapper(tool):
    return (f'#!/bin/bash\nexport MISE_MINIMUM_RELEASE_AGE=0\n'
            f'mise use -g "{tool}" || exit 1\nexec mise x "{tool}" -- "{tool}" "$@"\n')


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.bin = self.home / 'fake-bin'
        self.bin.mkdir()
        mise = self.bin / 'mise'
        mise.write_text('''#!/bin/bash
set -eu
case "$1" in
  which)
    if [[ "${FAKE_MISSING:-0}" == 1 && ! -f "$HOME/installed-$2" ]]; then exit 1; fi
    printf '%s/fake-bin/tool\\n' "$HOME"
    ;;
  use)
    echo "mise setup announcement"
    [[ "${FAKE_SETUP_FAIL:-0}" != 1 ]] || exit 12
    touch "$HOME/installed-$3"
    ;;
  x)
    [[ "$3" == -- ]] || exit 99
    shift 4
    exec "$HOME/fake-bin/tool" "$@"
    ;;
  *) exit 99 ;;
esac
''')
        mise.chmod(0o755)
        tool = self.bin / 'tool'
        tool.write_text('''#!/usr/bin/env python3
import json, os, sys
print(json.dumps({"args": sys.argv[1:], "backend": "mise"}))
sys.exit(int(os.environ.get("FAKE_TOOL_EXIT", "0")))
''')
        tool.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home), XDG_STATE_HOME=str(self.home / 'state'),
                        PATH=str(self.bin) + ':' + os.environ['PATH'])

    def installer(self, tool):
        return ROOT / ('install-github-cli.sh' if tool == 'gh' else 'install-codex.sh')

    def source(self, tool):
        return ROOT / ('github/gh' if tool == 'gh' else 't3/codex')

    def target(self, tool):
        path = self.home / '.local/bin' / tool
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def run_installer(self, tool):
        return subprocess.run(['bash', str(self.installer(tool))], env=self.env,
                              capture_output=True, text=True, check=True).stdout

    def backups(self, tool):
        return list((self.home / 'state').glob(f'arch-setups/backups/{tool}-mise-*/{tool}'))

    def test_fresh_and_idempotent(self):
        for tool in ('gh', 'codex'):
            with self.subTest(tool=tool):
                self.run_installer(tool)
                self.assertEqual(self.target(tool).read_bytes(), self.source(tool).read_bytes())
                self.assertTrue(os.access(self.target(tool), os.X_OK))
                self.assertIn('already installed', self.run_installer(tool))
                self.assertFalse(self.backups(tool))

    def test_noisy_wrapper_backed_up(self):
        for tool in ('gh', 'codex'):
            with self.subTest(tool=tool):
                self.target(tool).write_text(noisy_wrapper(tool))
                self.run_installer(tool)
                self.assertEqual(self.target(tool).read_bytes(), self.source(tool).read_bytes())
                self.assertEqual(len(self.backups(tool)), 1)
                self.assertEqual(self.backups(tool)[0].read_text(), noisy_wrapper(tool))
                self.assertIn('already installed', self.run_installer(tool))
                self.assertEqual(len(self.backups(tool)), 1)

    def test_system_gh_wrapper_replaced(self):
        old = '#!/bin/bash\n# Keep GitHub CLI stdout machine-readable for T3 and other integrations.\nexec /usr/bin/gh "$@"\n'
        self.target('gh').write_text(old)
        self.run_installer('gh')
        self.assertEqual(self.target('gh').read_bytes(), self.source('gh').read_bytes())
        self.assertEqual(self.backups('gh')[0].read_text(), old)

    def test_custom_wrapper_preserved(self):
        for tool in ('gh', 'codex'):
            custom = noisy_wrapper(tool) + '# custom behavior\n'
            self.target(tool).write_text(custom)
            self.assertIn('Preserving custom', self.run_installer(tool))
            self.assertEqual(self.target(tool).read_text(), custom)

    def test_symlink_preserved(self):
        for tool in ('gh', 'codex'):
            self.target(tool).symlink_to(self.bin / 'tool')
            self.run_installer(tool)
            self.assertTrue(self.target(tool).is_symlink())
            self.assertEqual(os.readlink(self.target(tool)), str(self.bin / 'tool'))

    def test_managed_wrapper_permissions_repaired(self):
        for tool in ('gh', 'codex'):
            self.target(tool).write_bytes(self.source(tool).read_bytes())
            self.target(tool).chmod(0o644)
            self.run_installer(tool)
            self.assertTrue(os.access(self.target(tool), os.X_OK))
            self.assertEqual(len(self.backups(tool)), 1)

    def test_missing_mise_tool_installed(self):
        self.env['FAKE_MISSING'] = '1'
        for tool in ('gh', 'codex'):
            self.run_installer(tool)
            self.assertTrue((self.home / f'installed-{tool}').exists())
            self.assertIn('already installed', self.run_installer(tool))

    def test_wrappers_keep_stdout_clean_and_preserve_arguments(self):
        for tool in ('gh', 'codex'):
            self.run_installer(tool)
            args = ['auth' if tool == 'gh' else 'app-server', 'argument with spaces', '--json']
            result = subprocess.run([str(self.target(tool)), *args], env=self.env,
                                    capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout), {'args': args, 'backend': 'mise'})
            self.assertIn('mise setup announcement', result.stderr)
            self.env['FAKE_TOOL_EXIT'] = '7'
            result = subprocess.run([str(self.target(tool))], env=self.env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 7)
            del self.env['FAKE_TOOL_EXIT']

    def test_setup_failure_does_not_start_tool(self):
        for tool in ('gh', 'codex'):
            self.run_installer(tool)
            env = dict(self.env, FAKE_SETUP_FAIL='1')
            result = subprocess.run([str(self.target(tool))], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, '')
            self.assertIn('mise setup announcement', result.stderr)


if __name__ == '__main__':
    unittest.main()
