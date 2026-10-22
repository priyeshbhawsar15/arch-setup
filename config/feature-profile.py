#!/usr/bin/env python3
"""Validate selections, plan setup, and persist explicit successful lifecycle choices."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = json.loads((ROOT / 'config/features.json').read_text())
DEPENDENCIES = {name: item.get('requires', []) for name, item in REGISTRY.items()}


def validate_names(names):
    if not isinstance(names, list) or any(not isinstance(n, str) or n not in REGISTRY for n in names):
        raise ValueError('installer lists must contain registered installer filenames')
    if len(names) != len(set(names)):
        raise ValueError('duplicate installer selection')
    return set(names)


def read_choices(profile, state):
    declared = json.loads(profile.read_text())
    if not isinstance(declared, dict) or set(declared) - {'schemaVersion', 'disabledInstallers', 'enabledInstallers'}:
        raise ValueError('unknown profile keys; expected schemaVersion/enabledInstallers/disabledInstallers')
    if type(declared.get('schemaVersion', 1)) is not int or declared.get('schemaVersion', 1) != 1:
        raise ValueError('unsupported profile schemaVersion')
    disabled = validate_names(declared.get('disabledInstallers', []))
    if 'enabledInstallers' in declared:
        selected = validate_names(declared['enabledInstallers'])
        if selected & disabled:
            raise ValueError('an installer cannot be both enabled and disabled')
        for name in selected:
            if any(dependency not in selected for dependency in DEPENDENCIES[name]):
                raise ValueError('explicit selection omits a required installer for ' + name)
        disabled |= set(REGISTRY) - selected
    choices = json.loads(state.read_text()) if state.exists() else {}
    if not isinstance(choices, dict) or any(name not in REGISTRY or type(value) is not bool for name, value in choices.items()):
        raise ValueError('local choices must map registered installer filenames to booleans')
    return disabled, choices


def enabled(name, disabled, choices, visiting=()):
    if name not in REGISTRY:
        raise ValueError('unknown installer: ' + name)
    if name in visiting:
        raise ValueError('cyclic installer dependency: ' + name)
    return choices.get(name, name not in disabled) and all(
        enabled(dependency, disabled, choices, (*visiting, name)) for dependency in DEPENDENCIES[name])


def plan(disabled, choices):
    return [dict(installer=name, enabled=enabled(name, disabled, choices),
                 reason='selected' if enabled(name, disabled, choices) else 'disabled or dependency disabled')
            for name in REGISTRY]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, default=Path(os.environ.get('ARCH_SETUPS_PROFILE', str(ROOT / 'features.json'))))
    parser.add_argument('--ignore-local', action='store_true', default=os.environ.get('ARCH_SETUPS_IGNORE_LOCAL') == '1')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('export')
    sub.add_parser('validate')
    command = sub.add_parser('plan')
    command.add_argument('--json', action='store_true')
    sub.add_parser('list')
    command = sub.add_parser('enabled')
    command.add_argument('installer', choices=REGISTRY)
    command = sub.add_parser('remember')
    command.add_argument('installer', choices=REGISTRY)
    command.add_argument('value', choices=('true', 'false'))
    args = parser.parse_args()
    state_home = Path(os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local/state'))
    state = state_home / 'arch-setups/features.json'
    # Queries are strictly read-only. Mutations lock and re-read to avoid lost updates.
    if args.command == 'remember':
        state.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (state.parent / 'features.lock').open('a') as lock:
            os.chmod(lock.name, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            _, choices = read_choices(args.profile, state)
            value = args.value == 'true'
            if choices.get(args.installer) == value:
                state.chmod(0o600)
                return 0
            choices[args.installer] = value
            fd, temporary = tempfile.mkstemp(dir=state.parent)
            try:
                with os.fdopen(fd, 'w') as stream:
                    json.dump(choices, stream, indent=2)
                    stream.write('\n')
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, state)
            finally:
                Path(temporary).unlink(missing_ok=True)
        return 0
    disabled, choices = read_choices(args.profile, state)
    if args.ignore_local:
        choices = {}
    rows = plan(disabled, choices)
    if args.command == 'export':
        print(json.dumps({'disabledInstallers': [row['installer'] for row in rows if not row['enabled']]}, indent=2))
    elif args.command == 'enabled':
        return 0 if enabled(args.installer, disabled, choices) else 1
    elif args.command == 'list':
        print('\n'.join(row['installer'] for row in rows if row['enabled']))
    elif args.command == 'plan':
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            for row in rows:
                print(f'{"RUN " if row["enabled"] else "SKIP"} {row["installer"]}: {row["reason"]}')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f'feature-profile: {error}', file=sys.stderr)
        sys.exit(2)
