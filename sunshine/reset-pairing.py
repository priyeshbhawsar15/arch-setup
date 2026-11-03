#!/usr/bin/env python3
"""Offline, explicitly requested reset of Sunshine host and client identities."""
import json
import os
from pathlib import Path
import re
import shutil
import tempfile


def main():
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'sunshine'
    conf = config / 'sunshine.conf'
    # Do not reset defaults when Sunshine uses custom identity/state paths.
    if conf.exists():
        for line in conf.read_text().splitlines():
            match = re.match(r'^\s*(pkey|cert|file_state|credentials_file)\s*=\s*(.*?)\s*$', line)
            if match and match[2]:
                raise SystemExit('Custom Sunshine certificate/state path configured; review before reset.')
    state = config / 'sunshine_state.json'
    paths = [state, config / 'credentials/cacert.pem', config / 'credentials/cakey.pem']
    for path in [config, config / 'credentials', *paths]:
        if path.is_symlink():
            raise SystemExit('Refusing symlinked Sunshine identity paths.')
    original = json.loads(state.read_text()) if state.exists() else {}
    # root contains both current named_devices and legacy devices/certs.
    updated = {key: value for key, value in original.items() if key != 'root'}
    parent = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'arch-setups/backups'
    parent.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='sunshine-reset-', dir=parent))
    existing = [path for path in paths if path.exists()]
    for path in existing:
        target = backup / path.relative_to(config)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copy2(path, target)
        target.chmod(0o600)
    fd, stage = tempfile.mkstemp(prefix='.reset-', dir=config)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(updated, stream, indent=2)
            stream.write('\n')
        os.replace(stage, state)
        for path in paths[1:]:
            path.unlink(missing_ok=True)
    except BaseException:
        for path in existing:
            shutil.copy2(backup / path.relative_to(config), path)
        raise
    finally:
        if os.path.exists(stage):
            os.unlink(stage)
    print(f'Cleared all Sunshine paired clients and host certificate/key. Private backup: {backup}')
    print('Restart Sunshine to generate a fresh host identity. Delete old Moonlight PC entries before pairing once.')


if __name__ == '__main__':
    main()
