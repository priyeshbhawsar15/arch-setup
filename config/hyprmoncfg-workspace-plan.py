#!/usr/bin/env python3
"""Check or stand down the global workspace plan saved in hyprmoncfg profiles.

Per-monitor Workspaces owns named per-output workspaces. A profile whose plan is
enabled makes hyprmoncfg generate numeric rules and rebind Super+number on
Omarchy 4.5, so only the `enabled` flag changes; the rules stay for a later
re-enable and every other profile field is preserved.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile


def planned_profiles(directory):
    found = []
    for path in sorted(Path(directory).glob('*.json')):
        data = json.loads(path.read_text())
        plan = data.get('workspaces') if isinstance(data, dict) else None
        if isinstance(plan, dict) and plan.get('enabled') is True:
            found.append((path, data))
    return found


def replace(path, data):
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f'.{path.name}.')
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(data, stream, indent=2)
            stream.write('\n')
        os.chmod(temporary, path.stat().st_mode & 0o7777)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'disable'))
    parser.add_argument('profiles', type=Path)
    args = parser.parse_args()
    found = planned_profiles(args.profiles)
    if args.action == 'check':
        return 1 if found else 0
    for path, data in found:
        data['workspaces']['enabled'] = False
        replace(path, data)
    return 0


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        print('hyprmoncfg workspace plan: ' + str(error), file=sys.stderr)
        sys.exit(2)
