#!/usr/bin/env python3
"""Initialize a fresh ISO's missing package indexes without a partial upgrade.

Only explicit confirmation/approval allows mutations. Omarchy owns the update
commands; this helper never invokes a database-only pacman sync or reboots.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True


def check_databases():
    try:
        database = subprocess.check_output(['pacman-conf', 'DBPath'], text=True, stderr=subprocess.PIPE).strip()
        names = subprocess.check_output(['pacman-conf', '--repo-list'], text=True, stderr=subprocess.PIPE).splitlines()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError('Cannot read the configured Arch package databases.') from error
    if not database or not names:
        raise ValueError('No configured Arch repositories/database path.')
    missing = []
    for name in names:
        path = Path(database) / 'sync' / (name + '.db')
        if name and (not path.is_file() or path.stat().st_size == 0):
            missing.append(name)
    return {'ready': not missing, 'missing': missing}


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def restart_reasons(ignore_flag=False):
    reasons = []
    modules = Path('/usr/lib/modules')
    installed = list(modules.glob('*/vmlinuz'))
    if installed and not (modules / os.uname().release / 'vmlinuz').is_file():
        reasons.append('new kernel requires reboot')
    if not ignore_flag and (Path.home() / '.local/state/omarchy/reboot-required').exists():
        reasons.append('Omarchy reports reboot required')
    result = subprocess.run(['pgrep', '-u', str(os.getuid()), '-x', 'Hyprland'], capture_output=True, text=True)
    for pid in result.stdout.split():
        try:
            if '(deleted)' in os.readlink('/proc/' + pid + '/exe'):
                reasons.append('updated Hyprland requires logout/login')
        except OSError:
            pass
    return reasons


def marker_path():
    return Path(os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local/state')) / 'arch-setups/initial-system-update.json'


def save_marker(path, status, identity):
    if path.is_symlink():
        raise ValueError('Refusing a symlinked initial-update marker.')
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump({'status': status, 'bootId': identity}, stream)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def perform_update():
    # These are the system stages used by Omarchy's updater. Deliberately do
    # not invoke its interactive restart picker, unrelated AUR/mise updates,
    # or orphan removal. Migrations/hooks follow the full -Syu package stage.
    commands = [
        ['omarchy', 'snapshot', 'create'],
        ['omarchy', 'update', 'keyring'],
        ['omarchy', 'update', 'system', 'pkgs'],
        ['omarchy', 'migrate'],
        ['omarchy', 'hook', 'post-update'],
    ]
    inherited = ()
    try:
        fd = int(os.environ['OMARCHY_UPDATE_LOCK_FD']); os.fstat(fd)
        inherited = (fd,)
    except (KeyError, ValueError, OSError):
        pass
    for index, command in enumerate(commands):
        print('==> Initial platform preparation: ' + ' '.join(command), flush=True)
        result = subprocess.run(command, env=dict(os.environ, OMARCHY_UPDATE_UNATTENDED='1'), pass_fds=inherited)
        if result.returncode:
            if index == 0 and result.returncode == 127:
                print('WARNING: Snapper unavailable; no platform snapshot created.', file=sys.stderr)
                continue
            return result.returncode
    return 0


def prepare(approved=False):
    state = check_databases()
    marker = marker_path()
    if marker.is_symlink():
        raise ValueError('Refusing a symlinked initial-update marker.')
    previous = json.loads(marker.read_text()) if marker.exists() else None
    identity = boot_id()
    if marker.exists() and (not isinstance(previous, dict) or previous.get('status') not in ('running', 'failed', 'awaiting-restart') or not isinstance(previous.get('bootId'), str) or not previous['bootId']):
        raise ValueError('Invalid initial-update recovery marker; preserve/review it before setup.')
    if previous and previous['status'] == 'awaiting-restart':
        reasons = restart_reasons(ignore_flag=previous['bootId'] != identity)
        if reasons:
            print('Initial platform update completed, but restart is required: ' + '; '.join(reasons) + '. Reboot/login, then rerun setup.', file=sys.stderr)
            return 3
        marker.unlink()
        previous = None
    if state['ready'] and previous is None:
        return 0
    print('Package preparation required: missing indexes ' + ', '.join(state['missing']) + ('.' if state['missing'] else '; an earlier initial update did not finish.'), flush=True)
    print('Setup must run Omarchy snapshot/keyring/full system-package update/migration stages. It will not perform a partial upgrade or reboot automatically.', flush=True)
    if not approved:
        if not sys.stdin.isatty():
            print('Run interactively to confirm, or explicitly pass --approve-system-update.', file=sys.stderr)
            return 2
        if input('Approve this initial platform update? [y/N] ').strip().lower() not in ('y', 'yes'):
            print('Platform update declined; no installers were run.', file=sys.stderr)
            return 2
    save_marker(marker, 'running', identity)
    if shutil.which('omarchy-update-lock'):
        command = ['omarchy-update-lock', 'run', sys.executable, str(Path(__file__).resolve()), 'perform']
        status = subprocess.run(command).returncode
    else:
        status = perform_update()
    if status or not check_databases()['ready']:
        save_marker(marker, 'failed', identity)
        print('Initial platform preparation failed. Resolve Omarchy update errors, then rerun with approval. No application installers were run.', file=sys.stderr)
        return 1
    reasons = restart_reasons()
    if reasons:
        save_marker(marker, 'awaiting-restart', identity)
        print('Platform prepared; reboot/login is required before setup continues: ' + '; '.join(reasons), file=sys.stderr)
        return 3
    marker.unlink()
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status', 'prepare', 'perform'))
    parser.add_argument('--approved', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if args.action == 'status':
        try:
            state = dict(check_databases(), pending=marker_path().exists() or marker_path().is_symlink())
        except ValueError as error:
            state = dict(ready=False, pending=False, missing=[], error=str(error))
        if args.json:
            print(json.dumps(state))
        elif state.get('error'):
            print('Package index availability must be checked on the Omarchy target.')
        elif not state['ready'] or state['pending']:
            print('Initial package preparation/recovery required before apply; confirmation will be requested (or use --approve-system-update).')
        else:
            print('Configured package indexes are available; no initial system update needed.')
        return 0
    if args.action == 'perform':
        path = marker_path()
        if not path.is_file() or json.loads(path.read_text()).get('status') != 'running':
            raise ValueError('Internal update stage requires an approved running preparation marker.')
        return perform_update()
    return prepare(args.approved)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError) as error:
        print('Package bootstrap: ' + str(error), file=sys.stderr)
        sys.exit(2)
