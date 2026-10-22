"""Installer effects use fixture homes and fake privileged/package commands."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


class DotfilesTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which("stow"):
            self.skipTest("GNU Stow is required")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.setup = self.base / "arch-setups"
        self.setup.mkdir()
        shutil.copy2(ROOT / "install-dotfiles.sh", self.setup / "install-dotfiles.sh")
        self.dots = self.base / "dotfiles"
        self.targets = [".config/nvim", ".config/starship.toml", ".config/tmux", ".zshrc"]
        for package, relative in {"nvim": ".config/nvim/init.lua", "starship": ".config/starship.toml",
                                  "tmux": ".config/tmux/tmux.conf", "zsh": ".zshrc"}.items():
            source = self.dots / package / relative
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("managed fixture\n")
        for relative in self.targets:
            target = self.home / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("original user fixture\n")
        self.env = dict(os.environ, HOME=str(self.home), XDG_STATE_HOME=str(self.home / "state"))

    def run_installer(self, env=None):
        return subprocess.run(["bash", str(self.setup / "install-dotfiles.sh")],
                              env=env or self.env, capture_output=True, text=True)

    def assert_originals(self):
        for relative in self.targets:
            target = self.home / relative
            self.assertTrue(target.is_file() and not target.is_symlink(), f"Original target changed: {target}")
            self.assertEqual(target.read_text(), "original user fixture\n")

    def test_stow_conflict_preserves_existing_configuration(self):
        (self.dots / "zsh/.zprofile").write_text("managed profile\n")
        (self.home / ".zprofile").write_text("unrelated profile\n")
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assert_originals()
        self.assertEqual((self.home / ".zprofile").read_text(), "unrelated profile\n")

    def test_failed_apply_preserves_existing_directory_data_and_managed_symlinks(self):
        nvim = self.home / ".config/nvim"
        nvim.unlink()
        nvim.mkdir()
        (nvim / "init.lua").write_text("original init\n")
        (nvim / "extra.lua").write_text("unrelated config\n")
        zsh = self.home / ".zshrc"
        zsh.unlink()
        zsh.symlink_to(self.dots / "zsh/.zshrc")
        (self.dots / "zsh/.zprofile").write_text("managed profile\n")
        (self.home / ".zprofile").write_text("conflicting profile\n")
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((nvim / "init.lua").read_text(), "original init\n")
        self.assertEqual((nvim / "extra.lua").read_text(), "unrelated config\n")
        self.assertTrue(zsh.is_symlink())
        self.assertEqual(zsh.resolve(), self.dots / "zsh/.zshrc")

    def test_success_keeps_backups_and_second_run_is_idempotent(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.home / ".config/nvim/init.lua").read_text(), "managed fixture\n")
        backups = list((self.home / "state/arch-setups/backups").glob("dotfiles-*"))
        self.assertEqual(len(backups), 1)
        for relative in self.targets:
            self.assertEqual((backups[0] / relative).read_text(), "original user fixture\n")
        second = self.run_installer()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(len(list((self.home / "state/arch-setups/backups").glob("dotfiles-*"))), 1)

    def test_missing_package_does_not_change_targets(self):
        shutil.rmtree(self.dots / "zsh")
        self.assertNotEqual(self.run_installer().returncode, 0)
        self.assert_originals()

    def test_failed_apply_rolls_back_created_links_and_originals(self):
        (self.dots / "zsh/.zprofile").write_text("managed profile\n")
        fake = self.base / "bin"
        fake.mkdir()
        stow = fake / "stow"
        stow.write_text('#!/bin/bash\n' + shutil.which("stow") + ' "$@" || exit $?\n'
                        'for arg in "$@"; do [[ "$arg" == --simulate || "$arg" == -n ]] && exit 0; done\nexit 23\n')
        stow.chmod(0o755)
        result = self.run_installer(dict(self.env, PATH=str(fake) + ":" + os.environ["PATH"]))
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assert_originals()
        self.assertFalse((self.home / ".zprofile").is_symlink())


class ServiceInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.etc = self.home / "etc/keyd"
        self.etc.mkdir(parents=True)
        self.env = dict(os.environ, HOME=str(self.home), XDG_STATE_HOME=str(self.home / "state"),
                        PATH=str(self.bin) + ":/usr/bin")
        self.command("pacman", "exit 0")
        self.command("tailscale", "exit 0")
        self.command("steam", "exit 0")
        self.command("gamescope", "exit 0")
        self.command("keyd", '[[ "$1" == reload ]] && cp "$HOME/etc/keyd/default.conf" "$HOME/live-keyd.conf"\nexit 0')
        remap = r'args=(); for a in "$@"; do args+=("${a/\/etc\/keyd\//$HOME/etc/keyd/}"); done'
        self.command("cmp", remap + '\nexec /usr/bin/cmp "${args[@]}"')
        self.command("sudo", remap + '\nexec "${args[@]}"')
        self.command("systemctl", '''case "$1" in
is-active) [[ -f "$HOME/service-active-$3" ]] ;;
is-enabled) [[ -f "$HOME/service-enabled-$3" ]] ;;
enable) touch "$HOME/service-active-$3" "$HOME/service-enabled-$3" ;;
*) exit 99 ;;
esac''')

    def command(self, name, source):
        path = self.bin / name
        path.write_text("#!/bin/bash\n" + source + "\n")
        path.chmod(0o755)

    def run_installer(self, name):
        return subprocess.run(["bash", str(ROOT / name)], env=self.env,
                              capture_output=True, text=True)

    def test_existing_tailscale_repairs_service(self):
        result = self.run_installer("install-tailscale.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.home / "service-active-tailscaled").exists())
        self.assertTrue((self.home / "service-enabled-tailscaled").exists())

    def test_keyd_changed_configuration_is_backed_up_and_live(self):
        (self.etc / "default.conf").write_text("user keyd configuration\n")
        (self.home / "live-keyd.conf").write_text("user keyd configuration\n")
        (self.home / "service-active-keyd").touch()
        (self.home / "service-enabled-keyd").touch()
        result = self.run_installer("install-keyd.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.home / "live-keyd.conf").read_bytes(), (ROOT / "keyd/default.conf").read_bytes())
        backups = list((self.home / "state/arch-setups/backups").glob("keyd-*/default.conf"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "user keyd configuration\n")
        self.assertEqual(backups[0].parent.stat().st_mode & 0o777, 0o700)

    def test_matching_steam_wrapper_regains_executable_mode(self):
        target = self.home / ".local/bin/steam-gamescope-hdr"
        target.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / "steam/gamescope-hdr", target)
        target.chmod(0o644)
        selection = self.home / 'games.json'
        selection.write_text('{"schemaVersion":1,"games":{},"libraries":{},"steamHdr":true}')
        self.env['ARCH_SETUPS_GAMING_PROFILE'] = str(selection)
        result = self.run_installer("install-steam.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.access(target, os.X_OK))

