"""Wrappers must execute mise's binary, never resolve themselves through PATH."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.local = self.home / ".local/bin"
        self.local.mkdir(parents=True)
        self.backend = self.bin / "backend"
        self.backend.write_text("#!/usr/bin/python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\nsys.exit(7)\n")
        self.backend.chmod(0o755)
        mise = self.bin / "mise"
        mise.write_text('''#!/bin/bash
case "$1" in
use)
  count=$(cat "$HOME/calls" 2>/dev/null || echo 0)
  count=$((count + 1)); echo "$count" > "$HOME/calls"
  echo "mise preparation"
  ((count < 5)) || exit 23
  ;;
which) printf '%s\n' "${RESOLVED_BINARY:-$HOME/bin/backend}" ;;
x) tool=$2; shift 4; exec "$HOME/.local/bin/$tool" "$@" ;;
*) exit 99 ;;
esac
''')
        mise.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home),
                        PATH=f"{self.local}:{self.bin}:/usr/bin")

    def wrapper(self, tool):
        source = ROOT / ("github/gh" if tool == "gh" else "t3/codex")
        target = self.local / tool
        shutil.copy2(source, target)
        target.chmod(0o755)
        return target

    def test_absolute_backend_preserves_arguments_protocol_and_exit(self):
        for tool in ("gh", "codex"):
            with self.subTest(tool=tool):
                (self.home / "calls").unlink(missing_ok=True)
                result = subprocess.run([str(self.wrapper(tool)), "argument with spaces", "--json"],
                                        env=self.env, capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 7, result.stderr)
                self.assertEqual(json.loads(result.stdout), ["argument with spaces", "--json"])
                self.assertFalse((self.home / "calls").exists(), 'runtime wrappers must not install or update tools')

    def test_self_resolution_is_rejected_including_symlink_alias(self):
        for tool in ("gh", "codex"):
            with self.subTest(tool=tool):
                wrapper = self.wrapper(tool)
                alias = self.bin / "alias"
                alias.unlink(missing_ok=True)
                alias.symlink_to(wrapper)
                (self.home / "calls").unlink(missing_ok=True)
                result = subprocess.run([str(wrapper)], env=dict(self.env, RESOLVED_BINARY=str(alias)),
                                        capture_output=True, text=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertFalse((self.home / "calls").exists())
                self.assertIn("executable", result.stderr)

    def test_known_mise_x_wrappers_are_upgraded_with_a_backup(self):
        comments = {
            "gh": "# Preserve mise setup, but reserve stdout for the actual GitHub CLI response.",
            "codex": "# Preserve mise setup, but reserve stdout for the Codex app-server protocol.",
        }
        for tool in ("gh", "codex"):
            with self.subTest(tool=tool):
                old = (f'#!/bin/bash\n{comments[tool]}\nexport MISE_MINIMUM_RELEASE_AGE=0\n'
                       f'mise use -g "{tool}" >&2 || exit 1\nexec mise x "{tool}" -- "{tool}" "$@"\n')
                target = self.local / tool
                target.write_text(old)
                target.chmod(0o755)
                installer = ROOT / ("install-github-cli.sh" if tool == "gh" else "install-codex.sh")
                result = subprocess.run(["bash", str(installer)], env=dict(self.env, XDG_STATE_HOME=str(self.home / "state")),
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                source = ROOT / ("github/gh" if tool == "gh" else "t3/codex")
                self.assertEqual(target.read_bytes(), source.read_bytes())
                backups = list((self.home / "state/arch-setups/backups").glob(f"{tool}-mise-*/{tool}"))
                self.assertEqual(len(backups), 1)
                self.assertEqual(backups[0].read_text(), old)

