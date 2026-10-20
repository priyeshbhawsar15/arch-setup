#!/usr/bin/env python3
"""Persist explicit feature choices and export them for a fresh-machine rebuild."""

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile

DEPENDENCIES = {'install-per-monitor-workspaces.sh': ['install-shibumi-shell.sh']}


def read_choices(profile, state):
    declared = json.loads(profile.read_text()) if profile.exists() else {'disabledInstallers': []}
    disabled = declared.get('disabledInstallers')
    if not isinstance(disabled, list) or any(not isinstance(name, str) for name in disabled):
        raise ValueError('disabledInstallers must be an array of installer filenames')
    choices = json.loads(state.read_text()) if state.exists() else {}
    if not isinstance(choices, dict) or any(type(value) is not bool for value in choices.values()):
        raise ValueError('local feature choices must map installer filenames to booleans')
    return set(disabled), choices


def enabled(name, disabled, choices):
    selected = choices.get(name, name not in disabled)
    return selected and all(enabled(dependency, disabled, choices) for dependency in DEPENDENCIES.get(name, []))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, default=Path(__file__).resolve().parents[1] / 'features.json')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('export')
    command = sub.add_parser('enabled')
    command.add_argument('installer')
    command = sub.add_parser('remember')
    command.add_argument('installer')
    command.add_argument('value', choices=('true', 'false'))
    args = parser.parse_args()
    state_home = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state')))
    state = state_home / 'arch-setups/features.json'
    disabled, choices = read_choices(args.profile, state)
    if args.command == 'export':
        names = disabled | set(choices)
        print(json.dumps({'disabledInstallers': sorted(name for name in names if not enabled(name, disabled, choices))}, indent=2))
        return 0
    if not re.fullmatch(r'install-[a-z0-9-]+\.sh', args.installer):
        raise ValueError('expected an installer filename')
    if args.command == 'enabled':
        return 0 if enabled(args.installer, disabled, choices) else 1
    value = args.value == 'true'
    if choices.get(args.installer) == value:
        state.chmod(0o600)
        return 0
    choices[args.installer] = value
    state.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=state.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(choices, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, state)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError) as error:
        print(f'feature-profile: {error}', file=sys.stderr)
        sys.exit(2)
