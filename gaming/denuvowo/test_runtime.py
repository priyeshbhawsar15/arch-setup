"""Offline shared-runtime setup/launch tests: no real games, packages or downloads."""
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


config = load('denuvowo_config', HERE / 'configure.py')
launcher = load('denuvowo_launcher', HERE / 'launch-denuvowo')


def archive(entries):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as tar:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.mode = 0o755 if name.endswith('/proton') else 0o644
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return stream.getvalue()


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.home = self.base / 'home'
        self.home.mkdir()
        self.version = 'GE-Proton-fixture'
        self.library = b'\x7fELF\x02\x01' + b'\0' * 10 + b'\x03\x00\x3e\x00' + b'fixture'
        self.proton_files = {self.version + '/' + key: value for key, value in {
            'proton': b'#!/bin/sh\nexit 0\n', 'version': b'fixture\n',
            'compatibilitytool.vdf': b'fixture\n'}.items()}
        self.payloads = {'https://fixture/library': self.library,
                         'https://fixture/proton': archive(self.proton_files)}
        self.assets = {key: {'version': version, 'url': url, 'sha256': hashlib.sha256(self.payloads[url]).hexdigest()}
                       for key, version, url in [('linuwux', 'fixture', 'https://fixture/library'),
                                                  ('proton', self.version, 'https://fixture/proton')]}
        self.downloads = []

    def fetch(self, url, target):
        self.downloads.append(url)
        target.write_bytes(self.payloads[url])

    def install(self):
        return config.install(self.home, self.assets, self.fetch)

    def change_proton(self, payload):
        self.payloads['https://fixture/proton'] = payload
        self.assets['proton']['sha256'] = hashlib.sha256(payload).hexdigest()

    def test_fresh_install_and_no_network_no_rewrite_rerun(self):
        result = self.install()
        self.assertEqual(result.changed, 5)
        self.assertEqual(len(self.downloads), 2)
        before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()}
        self.downloads.clear()
        self.assertEqual(self.install().changed, 0)
        after = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(self.downloads, [])
        self.assertFalse((self.home / '.local/share/wineprefixes').exists())
        self.assertFalse((self.home / '.local/share/Steam').exists())

    def test_existing_files_are_backed_up_and_unrelated_files_preserved(self):
        old = {'.local/bin/linuwux': b'old wrapper',
               '.local/share/linuwux/LinUwUx.so': b'old runtime'}
        for relative, payload in old.items():
            path = self.home / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            path.chmod(0o700)
        untouched = self.home / 'game-save'
        untouched.write_bytes(b'keep')
        result = self.install()
        for relative, payload in old.items():
            backup = result.backup / relative
            self.assertEqual(backup.read_bytes(), payload)
            self.assertEqual(backup.stat().st_mode & 0o777, 0o700)
        self.assertEqual(untouched.read_bytes(), b'keep')

    def test_bad_download_keeps_existing_wrapper(self):
        wrapper = self.home / '.local/bin/linuwux'
        wrapper.parent.mkdir(parents=True)
        wrapper.write_bytes(b'original')
        self.payloads['https://fixture/library'] = b'tampered'
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            self.install()
        self.assertEqual(wrapper.read_bytes(), b'original')
        self.assertFalse((self.home / '.local/bin/launch-denuvowo').exists())

    def test_wrong_elf_architecture_rejected_even_with_matching_hash(self):
        self.payloads['https://fixture/library'] = b'not ELF'
        self.assets['linuwux']['sha256'] = hashlib.sha256(b'not ELF').hexdigest()
        with self.assertRaisesRegex(ValueError, 'x86-64 ELF'):
            self.install()

    def test_archive_checksum_failure_does_not_replace_runtime(self):
        self.payloads['https://fixture/proton'] = b'bad archive'
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            self.install()
        self.assertFalse((self.home / '.local/share/linuwux/LinUwUx.so').exists())

    def test_archive_traversal_rejected(self):
        self.change_proton(archive({'../../escape': b'bad'}))
        with self.assertRaises(tarfile.FilterError):
            self.install()
        self.assertFalse((self.home / '.local/bin/linuwux').exists())
        self.assertFalse((self.base / 'escape').exists())

    def test_archive_escaping_symlink_rejected(self):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w:gz') as tar:
            info = tarfile.TarInfo(self.version + '/proton')
            info.type = tarfile.SYMTYPE
            info.linkname = '/tmp/outside-proton'
            tar.addfile(info)
        self.change_proton(stream.getvalue())
        with self.assertRaises(tarfile.FilterError):
            self.install()
        self.assertFalse((self.home / '.local/bin/linuwux').exists())

    def test_archive_missing_runner_files_rejected(self):
        self.change_proton(archive({self.version + '/version': b'fixture'}))
        with self.assertRaisesRegex(ValueError, 'missing proton'):
            self.install()

    def test_unmanaged_proton_directory_refused(self):
        proton = self.home / '.local/share/arch-setups/denuvowo' / self.version
        proton.mkdir(parents=True)
        (proton / 'mine').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'unmanaged'):
            self.install()
        self.assertEqual(self.downloads, [])
        self.assertEqual((proton / 'mine').read_text(), 'keep')

    def test_symlinked_managed_path_refused_without_following_it(self):
        destination = self.home / 'custom'
        destination.write_bytes(b'keep')
        wrapper = self.home / '.local/bin/linuwux'
        wrapper.parent.mkdir(parents=True)
        wrapper.symlink_to(destination)
        with self.assertRaisesRegex(ValueError, 'symlinked'):
            self.install()
        self.assertEqual(destination.read_bytes(), b'keep')
        self.assertEqual(self.downloads, [])

    def test_repairs_wrapper_executable_mode_without_downloads(self):
        self.install()
        wrapper = self.home / '.local/bin/linuwux'
        wrapper.chmod(0o644)
        self.downloads.clear()
        self.assertEqual(self.install().changed, 1)
        self.assertTrue(os.access(wrapper, os.X_OK))
        self.assertEqual(self.downloads, [])

    def test_whitespace_home_and_unsupported_architecture_refused(self):
        with self.assertRaisesRegex(ValueError, 'HOME'):
            config.install(self.base / 'has spaces', self.assets, self.fetch)
        with patch.object(config.platform, 'machine', return_value='aarch64'):
            with self.assertRaisesRegex(ValueError, 'x86-64'):
                self.install()
        self.assertEqual(self.downloads, [])

    def plan(self, slug='first-game', executable=None, args=None, env=None):
        bin_dir = self.home / 'fake-bin'
        bin_dir.mkdir(exist_ok=True)
        umu = bin_dir / 'umu-run'
        umu.write_text('#!/bin/sh\nexit 0\n')
        umu.chmod(0o755)
        exe = executable or self.home / 'Game Folder/Game.exe'
        exe.parent.mkdir(exist_ok=True)
        exe.touch()
        environ = {'PATH': str(bin_dir), 'WINEPREFIX': '/inherited',
                   'SteamAppId': 'wrong', 'SteamGameId': 'wrong',
                   'STEAM_COMPAT_DATA_PATH': '/wrong', 'KEEP_ME': 'yes'}
        environ.update(env or {})
        return launcher.launch_plan(slug, str(exe), args or [], self.home, environ)

    def test_game_prefixes_are_distinct_and_steam_ids_do_not_leak(self):
        self.install()
        cwd, env, command = self.plan(args=['--name', 'a b', ';not-shell'])
        other = self.plan('second-game')[1]
        self.assertNotEqual(env['WINEPREFIX'], other['WINEPREFIX'])
        self.assertTrue(env['WINEPREFIX'].endswith('/denuvowo/first-game'))
        self.assertEqual(env['GAMEID'], 'umu-default')
        self.assertNotIn('SteamAppId', env)
        self.assertNotIn('SteamGameId', env)
        self.assertNotIn('STEAM_COMPAT_DATA_PATH', env)
        self.assertEqual(env['KEEP_ME'], 'yes')
        self.assertEqual(cwd.name, 'Game Folder')
        self.assertEqual(command[-3:], ['--name', 'a b', ';not-shell'])
        self.assertFalse(Path(env['WINEPREFIX']).exists())

    def test_explicit_proton_and_umu_gameid_overrides(self):
        self.install()
        override = self.home / 'other-proton'
        override.mkdir()
        (override / 'proton').write_text('#!/bin/sh\nexit 0\n')
        (override / 'proton').chmod(0o755)
        env = self.plan(env={'PROTONPATH': str(override), 'DENUWOWO_GAMEID': 'umu-test'})[1]
        self.assertEqual(env['PROTONPATH'], str(override))
        self.assertEqual(env['GAMEID'], 'umu-test')

    def test_invalid_game_ids_rejected(self):
        for slug in ('../escape', '', '/absolute', 'has spaces', 'A', 'a' * 65):
            with self.subTest(slug=slug), self.assertRaisesRegex(ValueError, 'Game ID'):
                launcher.launch_plan(slug, '/unused.exe', [], self.home, {})

    def test_missing_executable_and_missing_umu_fail_actionably(self):
        self.install()
        with self.assertRaisesRegex(ValueError, 'executable not found'):
            launcher.launch_plan('game', '/missing.exe', [], self.home, {})
        exe = self.home / 'game.exe'
        exe.touch()
        with self.assertRaisesRegex(ValueError, 'umu-run is missing'):
            launcher.launch_plan('game', str(exe), [], self.home, {'PATH': '/missing'})

    def test_generic_wrapper_preserves_arguments_and_filters_only_gamescope_overlay(self):
        # bash is exec'd with a clean preload environment; inspect export before exec
        # with an in-process function, so no fake ELF is loaded into a real process.
        library = self.home / '.local/share/linuwux/LinUwUx.so'
        library.parent.mkdir(parents=True)
        library.touch()
        script = HERE / 'linuwux'
        for command in ('gamescope', 'some-game'):
            code = ('exec() { printf "%s\\n" "$LD_PRELOAD"; printf "[%s]\\n" "$@"; }; '
                    f'LD_PRELOAD="{library}:/other.so /gameoverlayrenderer.so"; '
                    f'set -- {command} "one two" ";literal"; source "$WRAPPER"')
            result = subprocess.run(['bash', '-c', code], env=dict(os.environ, HOME=str(self.home), WRAPPER=str(script), LD_PRELOAD=''),
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = result.stdout.splitlines()
            self.assertEqual(lines[0].count(str(library)), 1)
            self.assertIn('/other.so', lines[0])
            self.assertEqual('/gameoverlayrenderer.so' in lines[0], command != 'gamescope')
            self.assertEqual(lines[-2:], ['[one two]', '[;literal]'])

    def test_generic_launcher_cli_preserves_exit_status_arguments_and_prefix(self):
        self.install()
        cwd, env, command = self.plan()
        wrapper = self.home / '.local/bin/linuwux'
        wrapper.write_text('#!/usr/bin/python3\nimport json,os,sys\nfrom pathlib import Path\n'
                           'Path(os.environ["CAPTURE"]).write_text(json.dumps({'
                           '"argv":sys.argv[1:],"prefix":os.environ["WINEPREFIX"],'
                           '"cwd":os.getcwd()}))\nsys.exit(17)\n')
        capture = self.base / 'capture.json'
        env.update(HOME=str(self.home), CAPTURE=str(capture))
        env.pop('LD_PRELOAD', None)
        cli = self.home / '.local/bin/launch-denuvowo'
        result = subprocess.run(['/usr/bin/python3', str(cli), 'cli-game', command[2], 'a b', ';literal'],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 17, result.stderr)
        captured = json.loads(capture.read_text())
        self.assertEqual(captured['argv'][-2:], ['a b', ';literal'])
        self.assertEqual(captured['cwd'], str(cwd))
        self.assertTrue(captured['prefix'].endswith('/denuvowo/cli-game'))
        self.assertEqual(Path(captured['prefix']).stat().st_mode & 0o777, 0o700)
        redirected = self.home / '.local/share/wineprefixes/denuvowo/redirected'
        redirected.symlink_to(Path(captured['prefix']), target_is_directory=True)
        result = subprocess.run(['/usr/bin/python3', str(cli), 'redirected', command[2]],
                                env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('symlinked game prefix', result.stderr)

    def test_installer_registered_once_and_documented(self):
        self.assertEqual((ROOT / 'install-all.sh').read_text().count('  install-linuwux.sh\n'), 1)
        self.assertIn('**`install-linuwux.sh`**', (ROOT / 'SCRIPTS.md').read_text())


class InstallerShellTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.repo = self.home / 'repo'
        self.repo.mkdir()
        shutil.copy2(ROOT / 'install-linuwux.sh', self.repo)
        shutil.copy2(ROOT / 'lib.sh', self.repo)
        configure = self.repo / 'gaming/denuvowo/configure.py'
        configure.parent.mkdir(parents=True)
        configure.write_text('import os\nfrom pathlib import Path\n'
                             'Path(os.environ["CONFIGURED"]).write_text("configured")\n'
                             'print("LinUwUx support is already installed.")\n')
        self.bin = self.home / 'bin'
        self.bin.mkdir()
        (self.bin / 'dirname').symlink_to('/usr/bin/dirname')
        self.log = self.home / 'packages'
        self.configured = self.home / 'configured'
        self.env = dict(os.environ, HOME=str(self.home), PATH=str(self.bin),
                        PACKAGES=str(self.log), CONFIGURED=str(self.configured))

    def command(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/bash\n' + body + '\n')
        path.chmod(0o755)

    def run_installer(self):
        return subprocess.run(['/bin/bash', str(self.repo / 'install-linuwux.sh')],
                              env=self.env, capture_output=True, text=True)

    def test_existing_umu_does_not_invoke_package_manager(self):
        self.command('umu-run', 'exit 0')
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.configured.exists())
        self.assertFalse(self.log.exists())
        self.assertIn('already installed', result.stdout)

    def test_missing_umu_uses_omarchy_package_install(self):
        self.command('omarchy', 'printf "%s\\n" "$*" > "$PACKAGES"')
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text(), 'pkg add umu-launcher\n')
        self.assertTrue(self.configured.exists())

    def test_failed_package_install_stops_before_runtime_changes(self):
        self.command('omarchy', 'exit 42')
        result = self.run_installer()
        self.assertEqual(result.returncode, 42)
        self.assertFalse(self.configured.exists())


if __name__ == '__main__':
    unittest.main()
