"""Exercise the real wallpaper installer against local Git and fake desktop IPC."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WallpaperTransactionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='wallpaper-transaction-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.source = self.root / 'source'
        self.source.mkdir()
        self.git('init', '-q', cwd=self.source)
        (self.source / 'manifest.json').write_text('{"id":"priyesh.wallpaper-controller"}')
        hook = self.source / 'install.sh'
        hook.write_text('#!/bin/bash\nexit 0\n')
        hook.chmod(0o755)
        self.commit('initial')
        self.old = self.git('rev-parse', 'HEAD', cwd=self.source)
        self.plugin = self.home / '.config/omarchy/plugins/priyesh.wallpaper-controller'
        self.plugin.parent.mkdir(parents=True)
        self.git('clone', '-q', str(self.source), str(self.plugin))
        hook.write_text('#!/bin/bash\nprintf "{\\"changed\\":true}" > "$HOME/.config/omarchy/shell.json"\nexit 37\n')
        self.commit('failed activation candidate')
        self.new = self.git('rev-parse', 'HEAD', cwd=self.source)
        self.shell = self.home / '.config/omarchy/shell.json'
        self.shell.write_text('{"keep":"original shell settings"}')
        self.env = dict(os.environ, HOME=str(self.home), XDG_STATE_HOME=str(self.home / 'state'), PATH=str(self.bin) + ':' + os.environ['PATH'])
        self.env.pop('HYPRLAND_INSTANCE_SIGNATURE', None)
        self.env.pop('ARCH_SETUPS_AUTOMATED', None)
        self.env.pop('ARCH_SETUPS_PROFILE', None)
        self.command('omarchy', '''printf '%s\n' "$*" >> "$HOME/ipc.log"
if [[ "$1 $2" == "plugin list" ]]; then
  if [[ -e "$HOME/disabled" ]]; then enabled=false; else enabled=true; fi
  printf '[{"id":"priyesh.wallpaper-controller","enabled":%s}]\n' "$enabled"
elif [[ "$1 $2" == "plugin disable" ]]; then touch "$HOME/disabled"
elif [[ "$1 $2" == "plugin enable" ]]; then rm -f "$HOME/disabled"
elif [[ "$1 $2" == "plugin remove" ]]; then rm -rf "$HOME/.config/omarchy/plugins/priyesh.wallpaper-controller"
fi
exit 0''')
        for name in ('omarchy-shell', 'linux-wallpaperengine', 'aether', 'magick', 'zenity', 'wallpaper-controller'):
            self.command(name, 'exit 0')

    def git(self, *args, cwd=None):
        return subprocess.check_output(['git', *args], cwd=cwd, text=True, stderr=subprocess.PIPE).strip()

    def commit(self, message):
        self.git('add', '.', cwd=self.source)
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', message, cwd=self.source)

    def command(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/bash\n' + body + '\n')
        path.chmod(0o755)

    def run_installer(self, pin, *args):
        text = (ROOT / 'install-wallpaper-controller.sh').read_text()
        lines = [('SCRIPT_DIR=' + shlex.quote(str(ROOT))) if line.startswith('SCRIPT_DIR=') else
                 ('plugin_url=' + shlex.quote(str(self.source))) if line.startswith('plugin_url=') else
                 ('plugin_commit=' + shlex.quote(pin)) if line.startswith('plugin_commit=') else line for line in text.splitlines()]
        path = self.root / 'install-wallpaper-controller.sh'
        path.write_text('\n'.join(lines) + '\n')
        return subprocess.run(['bash', str(path), *args], env=self.env, capture_output=True, text=True)

    def test_activation_failure_restores_previous_checkout_configuration_and_enabled_state(self):
        result = self.run_installer(self.new)
        self.assertEqual(result.returncode, 37, result.stdout + result.stderr)
        self.assertEqual(self.git('rev-parse', 'HEAD', cwd=self.plugin), self.old)
        self.assertEqual(self.shell.read_text(), '{"keep":"original shell settings"}')
        self.assertFalse((self.home / 'disabled').exists())
        self.assertFalse(list(self.plugin.parent.glob('.wallpaper-transaction.*')))

    def test_missing_commit_does_not_disable_or_archive_the_working_plugin(self):
        result = self.run_installer('0' * 40)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git('rev-parse', 'HEAD', cwd=self.plugin), self.old)
        self.assertNotIn('plugin disable', (self.home / 'ipc.log').read_text() if (self.home / 'ipc.log').exists() else '')
        self.assertFalse((self.home / 'disabled').exists())

    def test_remove_archives_original_state_privately_and_remembers_disabled(self):
        config = self.home / '.config/omarchy/wallpaper-controller.json'
        config.write_text('{"active":"chosen-by-user","wallpaperEnabled":true}')
        result = self.run_installer(self.old, '--remove')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.plugin.exists())
        self.assertFalse(config.exists())
        backups = list((self.home / 'state/arch-setups/backups').glob('wallpaper-controller-remove-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o700)
        self.assertEqual(next(backups[0].rglob('wallpaper-controller.json')).read_text(), '{"active":"chosen-by-user","wallpaperEnabled":true}')
        self.assertIs(json.loads((self.home / 'state/arch-setups/features.json').read_text())['install-wallpaper-controller.sh'], False)

    def test_multiline_menu_removal_preserves_comments_and_unrelated_settings(self):
        menu = self.home / '.config/omarchy/extensions/omarchy-menu.jsonc'
        menu.parent.mkdir(parents=True)
        menu.write_text('{\n// keep this comment\n"style.wallpaper-controller": {\n"label":"Wallpaper",\n"action":"controller"\n},\n"unrelated":{"action":"keep"}\n}\n')
        prefix = (ROOT / 'install-wallpaper-controller.sh').read_text().split('\ncase "${1:-}"', 1)[0]
        path = self.root / 'functions.sh'
        path.write_text(prefix.replace('SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"', 'SCRIPT_DIR=' + shlex.quote(str(ROOT))))
        result = subprocess.run(['bash', '-c', 'source "$1"; remove_menu_entry', 'test', str(path)], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('// keep this comment', menu.read_text())
        parsed = json.loads(menu.read_text().replace('// keep this comment', ''))
        self.assertEqual(parsed, {'unrelated': {'action': 'keep'}})


if __name__ == '__main__':
    unittest.main()
