#!/usr/bin/env python3
"""Read-only setup checks; never display credential values or modify configuration."""

import argparse
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def command(args, timeout=6):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 1, ''


def inspect(preflight=False, dotfiles=None):
    checks = []

    def add(name, status, message):
        checks.append(dict(name=name, status=status, message=message))

    dotfiles = dotfiles or ROOT.parent / 'dotfiles'
    absent = [name for name in ('nvim', 'starship', 'tmux', 'zsh') if not (dotfiles / name).is_dir()]
    add('dotfiles', 'error' if absent else 'ok',
        'Missing sibling dotfiles packages: ' + ', '.join(absent) if absent else 'All four sibling Stow packages are present.')
    if shutil.which('omarchy'):
        code, version = command(['omarchy', 'version'])
        match = re.search(r'(\d+)\.(\d+)\.(\d+)', version)
        valid = code == 0 and match and tuple(map(int, match.groups())) >= (4, 0, 4)
        add('omarchy', 'ok' if valid else 'error', 'Quattro 4.0.4 or newer available.' if valid else 'Omarchy 4.0.4+ is required.')
    else:
        add('omarchy', 'error', 'Install Omarchy before running setup.')
    state_home = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state')))
    profile = runpy.run_path(str(ROOT / 'config/feature-profile.py'))
    try:
        disabled, choices = profile['read_choices'](ROOT / 'features.json', state_home / 'arch-setups/features.json')
        add('feature-profile', 'ok', 'Declared and local feature choices are valid.')
    except (OSError, ValueError, TypeError, AttributeError):
        disabled, choices = set(), {}
        add('feature-profile', 'error', 'Repair features.json or the local feature-choice file before setup.')
    if preflight:
        code, plugins = command(['omarchy-shell', 'shell', 'listPlugins'])
        try:
            ready = code == 0 and isinstance(json.loads(plugins), list)
        except ValueError:
            ready = False
        add('desktop-session', 'ok' if ready else 'error',
            'Omarchy shell IPC is available.' if ready else 'Run setup in an active, unlocked Omarchy desktop session.')
        lock_code, lock_state = command(['omarchy-shell', '-q', 'omarchy.lock', 'status'])
        if lock_code == 0 and lock_state.strip().lower() in ('locked', 'true'):
            add('screen-lock', 'error', 'Unlock the desktop before setup restarts shell components.')
        private_features = ('install-immich-photo-frame.sh', 'install-obsidian-tasks-widget.sh', 'install-home-assistant.sh', 'install-indicators.sh')
        if any(profile['enabled'](name, disabled, choices) for name in private_features):
            gh = '/usr/bin/gh' if Path('/usr/bin/gh').exists() else None
            if not gh and shutil.which('mise'):
                code, resolved = command(['mise', 'which', 'gh'])
                if code == 0 and Path(resolved.strip()).is_file():
                    gh = resolved.strip()
            code, _ = command([gh, 'auth', 'status']) if gh else (1, '')
            add('private-git-auth', 'ok' if code == 0 else 'error',
                'GitHub CLI authentication is available.' if code == 0 else 'Authenticate GitHub for enabled private plugins (install-github-cli.sh, then gh auth login).')
        return checks

    shell_config = Path.home() / '.config/omarchy/shell.json'
    try:
        shell = json.loads(shell_config.read_text()) if shell_config.exists() else {}
    except (OSError, ValueError):
        shell = {}
        add('shell-config', 'error', 'shell.json is invalid or unreadable; restore its backup before deploying.')
    active_ids = {p['id'] if isinstance(p, dict) else p for p in shell.get('plugins', [])}
    bar = shell.get('bar', {})
    active_ids.add(bar.get('id', 'omarchy.bar'))
    for section in bar.get('layout', {}).values():
        active_ids.update(p['id'] if isinstance(p, dict) else p for p in section)
    for installer in sorted(ROOT.glob('install-*.sh')):
        source = installer.read_text()
        identity = re.search(r'^plugin_id="([^"]+)"', source, re.M)
        pin = re.search(r'^plugin_commit="([a-f0-9]{40})"', source, re.M)
        if not identity or not pin:
            continue
        plugin_id = identity.group(1)
        target = Path.home() / '.config/omarchy/plugins' / plugin_id
        wanted = profile['enabled'](installer.name, disabled, choices)
        if not target.exists():
            add('plugin:' + plugin_id, 'warn' if wanted else 'ok',
                'Enabled feature not installed yet.' if wanted else 'Disabled feature is absent.')
            continue
        code, revision = command(['git', '--no-optional-locks', '-C', str(target), 'rev-parse', 'HEAD'])
        _, dirty = command(['git', '--no-optional-locks', '-C', str(target), 'status', '--porcelain', '--untracked-files=all'])
        source_url = re.search(r'^plugin_url="([^"]+)"', source, re.M)
        origin_code, origin = command(['git', '-C', str(target), 'remote', 'get-url', 'origin'])
        matches = code == 0 and revision.strip() == pin.group(1) and not dirty.strip()
        if source_url:
            matches = matches and origin_code == 0 and origin.strip() == source_url.group(1)
        add('plugin:' + plugin_id, 'ok' if matches else 'error',
            'Clean checkout matches source and pin.' if matches else 'Checkout/source/pin differs or local modifications exist; preserve them before updating.')
        add('enabled:' + plugin_id, 'ok' if (plugin_id in active_ids) == wanted else 'warn',
            'Enabled state matches feature preference.' if (plugin_id in active_ids) == wanted else 'Enabled state differs from the declared/local preference.')
    for feature in ('omniroute-quota', 'immich-photo-frame', 'home-assistant'):
        path = Path.home() / '.config/omarchy' / (feature + '.json')
        if path.exists():
            add('credentials:' + feature, 'ok' if path.stat().st_mode & 0o077 == 0 else 'error',
                'User-only configuration permissions.' if path.stat().st_mode & 0o077 == 0 else 'Credential-bearing config must have mode 0600; rerun its installer.')
    token = Path.home() / '.config/omarchy/hass/token'
    if token.exists() and token.stat().st_mode & 0o077:
        add('credentials:hass-token', 'error', 'Home Assistant token must be user-only (0600).')
    entry = Path.home() / '.config/hypr/hyprland.lua'
    packaged = Path('/usr/share/omarchy/config/hypr/hyprland.lua')
    if entry.exists() and packaged.exists():
        same = entry.read_bytes() == packaged.read_bytes()
        add('hypr-entrypoint', 'ok' if same else 'error',
            'Entrypoint matches packaged template.' if same else 'Entrypoint contains local edits; the Hyprland installer migrates only known legacy monitor blocks.')
    marker = state_home / 'arch-setups/crmne.hyprmoncfg/managed'
    if marker.exists():
        unmanaged = Path.home() / '.config/hyprmoncfg/unmanaged'
        code, output = command(['hyprmoncfg', '--hypr-config', str(Path.home() / '.config/hypr/monitors.lua'),
                                '--monitors-conf', str(Path.home() / '.config/hypr/hyprmoncfg-monitors.lua'), 'doctor'])
        good = code == 0 and output.startswith('OK  ') and not unmanaged.exists()
        add('monitor-management', 'ok' if good else 'error',
            'Generated monitor include is managed and loads last.' if good else 'Monitor management/include disagrees; rerun its managed installer in an unlocked session.')
    for helper in ('omniroute-quota', 'system-metrics-collector', 'weather-widget', 'immich-photo-frame', 'obsidian-tasks-widget'):
        path = Path.home() / '.local/bin' / helper
        if path.is_symlink() and not path.exists():
            add('helper:' + helper, 'error', 'Dangling managed helper link; rerun its installer or remove the owned link.')
    add('external-assets', 'warn', 'Workshop downloads, Obsidian vault, HA/Immich credentials, and Calendar OAuth remain local prerequisites; setup does not invent or publish them.')
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--dotfiles', type=Path)
    parser.add_argument('--export-profile', action='store_true')
    args = parser.parse_args()
    if args.export_profile:
        return subprocess.run([sys.executable, str(ROOT / 'config/feature-profile.py'), 'export']).returncode
    checks = inspect(args.preflight, args.dotfiles)
    good = not any(check['status'] == 'error' for check in checks)
    if args.json:
        print(json.dumps(dict(ok=good, checks=checks), indent=2))
    else:
        for row in checks:
            print(f'{row["status"].upper():5} {row["name"]}: {row["message"]}')
    return 0 if good else 1


if __name__ == '__main__':
    sys.exit(main())
