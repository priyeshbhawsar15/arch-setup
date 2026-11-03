#!/usr/bin/env python3
"""Manage one SDDM drop-in, preserving and checking surrounding configuration."""
import argparse
import configparser
import os
from pathlib import Path
import pwd
import re
import shutil
import sys
import tempfile

MARKER = '# Managed by arch-setups/install-sddm-autologin.sh\n'
NAME = '90-arch-setups-autologin.conf'
SESSION = 'hyprland-uwsm.desktop'


def autologin(path):
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read(path)
    return dict(parser['Autologin']) if parser.has_section('Autologin') else {}


def configure(enabled, user, root=Path('/'), check_only=False):
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*[$]?', user):
        raise ValueError('Invalid login user name.')
    path = root / 'etc/sddm.conf.d' / NAME
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('Refusing symlinked SDDM configuration.')
    old = path.read_text() if path.exists() else None
    if old is not None and not old.startswith(MARKER):
        raise ValueError('Refusing foreign SDDM autologin file.')
    if not enabled and old is None:
        # Nothing of ours to turn off. Writing blank values here would override
        # autologin configured by an earlier drop-in this feature does not own.
        return False
    if enabled and not (root / 'usr/share/wayland-sessions' / SESSION).is_file():
        raise ValueError('The Hyprland UWSM session must be installed first.')
    desired = {'User': user if enabled else '', 'Session': SESSION if enabled else '', 'Relogin': 'false'}
    # /etc/sddm.conf takes precedence over every drop-in. Later drop-ins can
    # also override us: refuse conflicts instead of silently promising a toggle.
    later = sorted(p for p in path.parent.glob('*.conf') if p.name > NAME)
    later.append(root / 'etc/sddm.conf')
    for override in later:
        if not override.exists():
            continue
        for key, value in autologin(override).items():
            if key in desired and value != desired[key]:
                raise ValueError(f'Conflicting autologin override: {override} ({key}).')
    content = MARKER + '[Autologin]\n' + ''.join(f'{k}={v}\n' for k, v in desired.items())
    if old == content:
        return False
    if check_only:
        return True
    if old is not None:
        parent = root / 'var/lib/arch-setups/backups'
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup = Path(tempfile.mkdtemp(prefix='sddm-autologin-', dir=parent))
        shutil.copy2(path, backup / path.name)
        print(f'SDDM configuration backup: {backup}')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, stage = tempfile.mkstemp(prefix='.autologin-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
        os.chmod(stage, 0o644)
        os.replace(stage, path)
    finally:
        if os.path.exists(stage):
            os.unlink(stage)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['enable', 'disable', 'status'])
    parser.add_argument('--user')
    parser.add_argument('--check', action='store_true', help='Read-only: exit 0 if current, 1 if a change is needed.')
    args = parser.parse_args()
    if args.mode == 'status':
        values = {}
        for directory in ['/usr/lib/sddm/sddm.conf.d', '/etc/sddm.conf.d']:
            for path in sorted(Path(directory).glob('*.conf')):
                values.update(autologin(path))
        if Path('/etc/sddm.conf').exists():
            values.update(autologin(Path('/etc/sddm.conf')))
        print('SDDM autologin: ' + ('enabled for ' + values['User'] if values.get('User') else 'disabled'))
        print('Session: ' + values.get('Session', ''))
        print('Relogin: ' + values.get('Relogin', 'false'))
        return
    if not args.check and os.geteuid() != 0:
        raise SystemExit('Writing SDDM configuration requires system authentication.')
    account = pwd.getpwnam(args.user or '')
    if account.pw_uid == 0:
        raise SystemExit('Automatic root login is not supported.')
    changed = configure(args.mode == 'enable', account.pw_name, check_only=args.check)
    if args.check:
        raise SystemExit(1 if changed else 0)
    print('SDDM autologin configured.' if changed else 'SDDM autologin configuration is already installed.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, configparser.Error) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
