#!/usr/bin/env python3
"""Reconcile only the managed Sunshine network policy; preserve personal settings."""
import os
from pathlib import Path
import re
import shutil
import tempfile


def main():
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'sunshine'
    config.mkdir(parents=True, exist_ok=True)
    path = config / 'sunshine.conf'
    if path.is_symlink():
        raise SystemExit('Refusing symlinked sunshine.conf; reconcile its source explicitly.')
    old = path.read_text() if path.exists() else ''
    managed = {
        'upnp': 'disabled', 'address_family': 'ipv4', 'bind_address': '127.0.0.1',
        'port': '47989', 'origin_web_ui_allowed': 'lan',
        'capture': 'kms', 'csrf_allowed_origins': '', 'lan_encryption_mode': '2', 'wan_encryption_mode': '2',
    }
    lines = []
    for line in old.splitlines():
        match = re.match(r'^\s*([a-zA-Z_]+)\s*=', line)
        if match and match[1] in managed:
            continue
        lines.append(line)
    content = '\n'.join(lines).rstrip() + '\n' if lines else ''
    content += '\n'.join(f'{key} = {value}' for key, value in managed.items()) + '\n'
    if content == old:
        print('Sunshine network configuration already installed.')
        return
    if path.exists():
        backups = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'arch-setups/backups'
        backups.mkdir(parents=True, exist_ok=True)
        backup = Path(tempfile.mkdtemp(prefix='sunshine-', dir=backups))
        shutil.copy2(path, backup / path.name)
        print(f'Backed up configuration to {backup}')
    fd, stage = tempfile.mkstemp(prefix='.sunshine-', dir=config)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
        os.replace(stage, path)
    finally:
        if os.path.exists(stage):
            os.unlink(stage)


if __name__ == '__main__':
    main()
