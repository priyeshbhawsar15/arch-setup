#!/usr/bin/env python3
"""Repair duplicate enabled certificate identities with Sunshine stopped."""
import copy
import json
import os
from pathlib import Path
import shutil
import ssl
import tempfile


def deduplicate(state):
    result = copy.deepcopy(state)
    devices = result['root']['named_devices']
    identities = {}
    for index, device in enumerate(devices):
        identity = ssl.PEM_cert_to_DER_cert(device['cert'])
        identities.setdefault(identity, []).append(index)
    remove = set()
    for indexes in identities.values():
        if len(indexes) < 2:
            continue
        # Never override a deliberate revocation or grant new trust.
        if any(str(devices[i].get('enabled', True)).lower() != 'true' for i in indexes):
            raise ValueError('Duplicate certificate has a disabled record; review it in Sunshine before repair.')
        remove.update(indexes[:-1])
    result['root']['named_devices'] = [d for i, d in enumerate(devices) if i not in remove]
    return result, len(remove)


def main():
    path = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'sunshine/sunshine_state.json'
    if path.is_symlink():
        raise SystemExit('Refusing symlinked Sunshine state.')
    old = path.read_bytes()
    updated, count = deduplicate(json.loads(old))
    if not count:
        print('No duplicate pairing certificates found.')
        return
    backups = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'arch-setups/backups'
    backups.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='sunshine-pairing-', dir=backups))
    shutil.copy2(path, backup / path.name)
    (backup / path.name).chmod(0o600)
    # Detect intervening changes before replacing the stopped service's state.
    if path.read_bytes() != old:
        raise SystemExit('Sunshine state changed during repair; refusing to overwrite.')
    fd, stage = tempfile.mkstemp(prefix='.pairing-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(updated, stream, indent=2)
            stream.write('\n')
        os.replace(stage, path)
    finally:
        if os.path.exists(stage):
            os.unlink(stage)
    print(f'Removed {count} duplicate pairing records. Private backup: {backup}')


if __name__ == '__main__':
    main()
