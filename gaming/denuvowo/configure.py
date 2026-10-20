#!/usr/bin/env python3
"""Install pinned shared LinUwUx/GE-Proton assets without touching game settings."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tarfile
import tempfile
import urllib.request

HERE = Path(__file__).resolve().parent


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(url, target):
    if not url.startswith('https://'):
        raise ValueError('Only HTTPS asset URLs are accepted')
    with urllib.request.urlopen(url, timeout=120) as source, target.open('wb') as dest:
        shutil.copyfileobj(source, dest)


def verified_download(asset, path, fetch):
    fetch(asset['url'], path)
    if digest(path) != asset['sha256']:
        raise ValueError(f"SHA256 mismatch for {asset['url']}")


def validate_library(path):
    with path.open('rb') as stream:
        header = stream.read(20)
    if (len(header) < 20 or header[:6] != b'\x7fELF\x02\x01'
            or header[16:20] != b'\x03\x00\x3e\x00'):
        raise ValueError('LinUwUx must be an x86-64 ELF shared library')


def validate_proton(path):
    for filename in ('proton', 'version', 'compatibilitytool.vdf'):
        if not (path / filename).is_file():
            raise ValueError(f'Incomplete Proton runner: missing {filename}')
    if not os.access(path / 'proton', os.X_OK):
        raise ValueError('Proton launcher is not executable')


def canonical_json(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


class Installer:
    def __init__(self, home):
        self.home = home
        self.backup = home / '.local/state/arch-setups/backups' / (
            'linuwux-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        self.changed = 0

    def save(self, path, payload, mode=0o644):
        if path.is_symlink():
            raise ValueError(f'Refusing to replace a symlink: {path}')
        if path.exists() and path.read_bytes() == payload and path.stat().st_mode & 0o777 == mode:
            return
        if path.exists():
            backup = self.backup / path.relative_to(self.home)
            backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copy2(path, backup)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.linuwux-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(payload)
            os.chmod(name, mode)
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)
        self.changed += 1


def install(home, assets=None, fetch=download):
    assets = assets or json.loads((HERE / 'assets.json').read_text())
    if platform.machine() not in ('x86_64', 'AMD64'):
        raise ValueError('This pinned runtime supports x86-64 Linux only')
    if any(c.isspace() or c == ':' for c in str(home)):
        raise ValueError('HOME cannot contain whitespace or colons for LD_PRELOAD')
    root = home / '.local/share/arch-setups/denuvowo'
    library = home / '.local/share/linuwux/LinUwUx.so'
    proton = root / assets['proton']['version']
    paths = [root, proton, library, home / '.local/bin/linuwux',
             home / '.local/bin/launch-denuvowo', root / 'runtime.json']
    for path in paths:
        if path.resolve() != path:
            raise ValueError(f'Refusing symlinked managed path: {path}')
    # Preflight all existing targets before downloading or modifying any of them.
    for path in (library, *paths[3:]):
        if path.exists() and not path.is_file():
            raise ValueError(f'Managed file path is not a regular file: {path}')
    marker = canonical_json(assets['proton'])
    proton_marker = proton / '.arch-setups-asset.json'
    if proton.exists():
        if not proton_marker.is_file() or proton_marker.read_bytes() != marker:
            raise ValueError(f'Refusing unmanaged or mismatched Proton directory: {proton}')
        validate_proton(proton)
    library_current = library.is_file() and digest(library) == assets['linuwux']['sha256']
    if library_current:
        validate_library(library)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / '.install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        installer = Installer(home)
        with tempfile.TemporaryDirectory(prefix='.stage-', dir=root) as temp:
            stage = Path(temp)
            new_library = stage / 'LinUwUx.so'
            if not library_current:
                verified_download(assets['linuwux'], new_library, fetch)
                validate_library(new_library)
            staged_proton = None
            if not proton.exists():
                archive = stage / 'proton.tar.gz'
                verified_download(assets['proton'], archive, fetch)
                unpacked = stage / 'unpacked'
                unpacked.mkdir()
                with tarfile.open(archive, 'r:gz') as tar:
                    # data_filter rejects escaping paths/links and special device nodes.
                    tar.extractall(unpacked, filter='data')
                staged_proton = unpacked / assets['proton']['version']
                if staged_proton.is_symlink() or sorted(p.name for p in unpacked.iterdir()) != [proton.name]:
                    raise ValueError('Unexpected Proton archive layout')
                validate_proton(staged_proton)
                (staged_proton / '.arch-setups-asset.json').write_bytes(marker)
            # All downloaded assets are validated before changing launch files.
            if staged_proton is not None:
                os.rename(staged_proton, proton)
                installer.changed += 1
            if not library_current:
                installer.save(library, new_library.read_bytes())
            installer.save(home / '.local/bin/linuwux', (HERE / 'linuwux').read_bytes(), 0o755)
            installer.save(home / '.local/bin/launch-denuvowo', (HERE / 'launch-denuvowo').read_bytes(), 0o755)
            installer.save(root / 'runtime.json', canonical_json({
                'assets': assets, 'proton_path': str(proton), 'library_path': str(library)}))
        return installer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Download verified assets and install wrappers')
    args = parser.parse_args()
    if not args.apply:
        print('Shared LinUwUx + GE-Proton support; run install-linuwux.sh to install.')
        return 0
    try:
        result = install(Path.home())
    except (OSError, ValueError, tarfile.TarError) as error:
        print(f'LinUwUx setup: {error}', file=sys.stderr)
        return 1
    if result.changed:
        print(f'LinUwUx support updated ({result.changed} changes). Backups, if needed: {result.backup}')
    else:
        print('LinUwUx support is already installed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
