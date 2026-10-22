#!/usr/bin/env python3
"""Read-only prerequisites, integrity and readiness checks. Never print credentials."""
import argparse
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True  # Read-only diagnostics must not create helper caches.
ROOT = Path(__file__).resolve().parents[1]
REGISTRY = json.loads((ROOT / 'config/features.json').read_text())
SOURCES = json.loads((ROOT / 'config/plugin-sources.json').read_text())
APPLICATIONS = {
    'install-chrome.sh': ['google-chrome-stable', 'google-chrome'],
    'install-brave-origin.sh': ['brave-origin', 'brave-origin-beta'],
    'install-zen.sh': ['zen', 'zen-browser'], 'install-stow.sh': ['stow'],
    'install-hermes-desktop.sh': ['hermes-desktop'], 'install-codex.sh': ['codex'],
    'install-github-cli.sh': ['gh'], 'install-t3code.sh': ['t3code', 't3code-nightly'],
    'install-steam.sh': ['steam'], 'install-lutris.sh': ['lutris'],
    'install-linuwux.sh': ['linuwux'], 'install-sunshine.sh': ['sunshine'],
    'install-tailscale.sh': ['tailscale'], 'install-keyd.sh': ['keyd'], 'install-zsh.sh': ['zsh'],
    'install-t3-planner-executor.sh': ['t3-planner-executor'],
}


def command(args, timeout=8, env=None):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env)
        return result.returncode, result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 1, ''


def available(name):
    if shutil.which(name) or os.access(Path.home() / '.local/bin' / name, os.X_OK):
        return True
    if shutil.which('mise'):
        code, path = command(['mise', 'which', name])
        return code == 0 and os.access(path.strip(), os.X_OK)
    return False


def unlocked(response):
    try:
        state = json.loads(response)
        return isinstance(state, dict) and all(state.get(key) is False for key in ('locked', 'requested', 'sessionLocked'))
    except (ValueError, TypeError):
        return False


def inspect(preflight=False, dotfiles=None, profile_path=None):
    checks = []
    def add(name, status, message):
        checks.append(dict(name=name, status=status, message=message))

    state = Path(os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local/state'))
    helper = runpy.run_path(str(ROOT / 'config/feature-profile.py'))
    profile_path = profile_path or Path(os.environ.get('ARCH_SETUPS_PROFILE', str(ROOT / 'features.json')))
    try:
        disabled, choices = helper['read_choices'](profile_path, state / 'arch-setups/features.json')
        if os.environ.get('ARCH_SETUPS_IGNORE_LOCAL') == '1':
            choices = {}
        selected = {name for name in REGISTRY if helper['enabled'](name, disabled, choices)}
        add('feature-profile', 'ok', 'Declared and local feature choices are valid.')
    except (OSError, ValueError, TypeError, KeyError):
        add('feature-profile', 'error', 'Invalid feature profile or remembered choices; no selection was inferred.')
        return checks
    if dotfiles is not None or 'install-dotfiles.sh' in selected:
        dotfiles = dotfiles or Path(os.environ.get('ARCH_SETUPS_DOTFILES_DIR', str(ROOT.parent / 'dotfiles')))
        absent = [name for name in ('nvim', 'starship', 'tmux', 'zsh') if not (dotfiles / name).is_dir()]
        add('dotfiles', 'error' if absent else 'ok',
            'Provide the separate dotfiles repository with --dotfiles-dir (nvim/starship/tmux/zsh).' if absent else 'Selected dotfiles packages are available.')
    code, version = command(['omarchy', 'version'])
    match = re.search(r'(\d+)\.(\d+)\.(\d+)', version)
    valid = code == 0 and match and tuple(map(int, match.groups())) >= (4, 0, 4)
    add('omarchy', 'ok' if valid else 'error', 'Omarchy 4.0.4+ available; plugin API checks are separate.' if valid else 'A supported Omarchy 4.0.4+ installation is required.')

    inputs = runpy.run_path(str(ROOT / 'config/setup-inputs.py'))
    try:
        inputs['settings']()
        games = inputs['gaming']()
        host_path = Path(os.environ.get('ARCH_SETUPS_MONITOR_LAYOUT', str(ROOT / 'monitor-layout.json')))
        host = runpy.run_path(str(ROOT / 'hypr/scripts/monitor-layout.py'))['load_config'](host_path)
        add('inputs', 'ok', 'Gaming, widget settings and host policy are valid.')
    except (OSError, ValueError, TypeError, KeyError):
        add('inputs', 'error', 'Repair the selected gaming, widget settings or host file; values are not logged.')
        return checks
    if games['games'] and 'install-lutris.sh' not in selected:
        add('gaming-feature', 'error', 'Selected direct game profiles require install-lutris.sh in the feature selection.')
    if (games['steamHdr'] or any(game['config'].get('system', {}).get('prefix_command') == 'steam-gamescope-hdr' for game in games['games'])) and 'install-steam.sh' not in selected:
        add('gaming-hdr-feature', 'error', 'Selected HDR behavior requires install-steam.sh to deploy Gamescope and the managed launcher.')
    for game in games['games']:
        present = Path(game['config']['game']['exe']).is_file()
        add('game:' + game['slug'], 'ok' if present else ('error' if game['required'] else 'pending'),
            'Selected game executable is available.' if present else 'Mount/install the selected game or remove it from the selection; it will not be claimed from generic imports.')
        if not preflight and present and game['runner'] == 'wine':
            version = game['config'].get('wine', {}).get('version')
            code, _ = command(['/usr/bin/python3', '-c',
                'import sys; from lutris.runners.wine import wine; sys.exit(0 if wine().is_installed(version=sys.argv[1], fallback=False) else 1)', str(version)])
            add('runner:' + game['slug'], 'ok' if code == 0 else ('error' if game['required'] else 'pending'),
                'Configured Wine/Proton runner is available.' if code == 0 else 'Install the selected Wine/Proton runner in Lutris, or choose an available wineVersion.')
    if preflight:
        if selected:
            try:
                packages = runpy.run_path(str(ROOT / 'config/package-bootstrap.py'))['check_databases']()
                add('package-indexes', 'ok' if packages['ready'] else 'warn',
                    'Configured package indexes are available.' if packages['ready'] else 'Fresh ISO indexes are missing; apply will request approval for an initial full system-package update before installers.')
            except (OSError, ValueError):
                add('package-indexes', 'error', 'Cannot inspect configured package databases; repair pacman configuration before setup.')
        if 'install-t3-planner-executor.sh' in selected:
            try:
                executor = inputs['planner_cli']()
                provisioned = executor == 'codex' and 'install-codex.sh' in selected
                ready = executor is None or provisioned or available(executor)
                add('workflow-executor', 'ok' if ready else 'error', 'Configured executor is available or will be provided by a selected dependency; provider/model authentication remains external.' if ready else 'Install the configured executor CLI before setup, or select another --planner-config.')
            except (OSError, ValueError, TypeError):
                add('workflow-executor', 'error', 'Invalid workflow configuration/seed; no executor was inferred.')
        for name in sorted(selected):
            for tool in REGISTRY[name].get('commands', []):
                add('tool:' + tool, 'ok' if available(tool) else 'error',
                    'Required tool available.' if available(tool) else 'Install the required tool before setup: ' + tool)
        if any(REGISTRY[name].get('session') for name in selected):
            code, plugins = command(['omarchy-shell', 'shell', 'listPlugins'])
            try:
                ready = code == 0 and isinstance(json.loads(plugins), list)
            except ValueError:
                ready = False
            add('desktop-session', 'ok' if ready else 'error', 'Desktop IPC available.' if ready else 'Run desktop features in an active Omarchy session.')
            code, response = command(['omarchy-shell', 'lock', 'status'])
            safe = code == 0 and unlocked(response)
            add('screen-lock', 'ok' if safe else 'error', 'Desktop is unlocked.' if safe else 'Unlock the session; unknown/failed lock responses block desktop mutations.')
        sources = {name: SOURCES.get(name, REGISTRY[name]) for name in selected}
        environment = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_ASKPASS='/bin/false', SSH_ASKPASS='/bin/false', GCM_INTERACTIVE='Never', GIT_SSH_COMMAND='ssh -oBatchMode=yes -oConnectTimeout=5 -oStrictHostKeyChecking=yes')
        for name, source in sorted(sources.items()):
            if name == 'install-t3-planner-executor.sh':
                source = dict(source, source=os.environ.get('T3_PLANNER_EXECUTOR_REPO_URL', source['source']), pin=os.environ.get('T3_PLANNER_EXECUTOR_REPO_PIN', source['pin']))
            if 'source' not in source:
                continue
            pin = source.get('pin', '')
            if not re.fullmatch(r'[a-f0-9]{40}', pin):
                add('source:' + name, 'error', 'Source is unpublished or lacks an exact commit pin.')
                continue
            if REGISTRY[name].get('plugin'):
                checkout = Path.home() / '.config/omarchy/plugins' / REGISTRY[name]['plugin']
            elif REGISTRY[name].get('suite'):
                checkout = Path.home() / '.local/share/shibumi-shell' / pin
            else:
                checkout = Path(os.environ.get('T3_PLANNER_EXECUTOR_SOURCE_DIR', str(Path(os.environ.get('XDG_DATA_HOME') or str(Path.home() / '.local/share')) / 't3-planner-executor/source')))
            rev_code, revision = command(['git', '--no-optional-locks', '-C', str(checkout), 'rev-parse', 'HEAD'])
            origin_code, origin = command(['git', '-C', str(checkout), 'remote', 'get-url', 'origin'])
            dirty_code, dirty = command(['git', '--no-optional-locks', '-C', str(checkout), 'status', '--porcelain', '--untracked-files=all'])
            if not checkout.is_symlink() and rev_code == origin_code == dirty_code == 0 and revision.strip() == pin and origin.strip() in [source['source'], *source.get('aliases', [])] and not dirty.strip():
                add('source:' + name, 'ok', 'Exact clean source is already available locally; no network check needed.')
                continue
            code, _ = command(['git', '-c', 'credential.interactive=false', 'ls-remote', '--exit-code', source['source'], 'HEAD'], timeout=20, env=environment)
            add('source:' + name, 'ok' if code == 0 else 'error',
                'Selected Git transport can access the source; commit admission happens during staging.' if code == 0 else 'Cannot access source using its configured Git transport; authenticate/verify host trust before setup.')
        return checks

    # Permissions are checked even for disabled integrations, without reading
    # credential values into any diagnostic output.
    for name in ('omniroute-quota', 'immich-photo-frame', 'home-assistant'):
        path = Path.home() / '.config/omarchy' / (name + '.json')
        if path.exists():
            private = path.stat().st_mode & 0o077 == 0
            add('credentials:' + name, 'ok' if private else 'error', 'Private configuration permissions.' if private else 'Credential-bearing configuration must be user-only (0600).')
    token = Path.home() / '.config/omarchy/hass/token'
    if token.exists() and token.stat().st_mode & 0o077:
        add('credentials:hass-token', 'error', 'Home Assistant token must be user-only (0600).')

    code, response = command(['omarchy', 'plugin', 'list', '--json']) if any(REGISTRY[name].get('plugin') for name in selected) else (0, '[]')
    try:
        entries = json.loads(response)
        if code != 0 or not isinstance(entries, list):
            raise ValueError()
        active = {item['id'] for item in entries if isinstance(item, dict) and item.get('enabled') is True}
    except (ValueError, KeyError, TypeError):
        active = set()
        add('plugin-registry', 'error', 'Cannot read the live plugin registry.')
    for name in sorted(selected):
        metadata = REGISTRY[name]
        if name in APPLICATIONS:
            good = any(available(tool) for tool in APPLICATIONS[name])
            if name == 'install-t3-planner-executor.sh' and os.environ.get('T3_PLANNER_EXECUTOR_HELPER'):
                good = os.access(os.environ['T3_PLANNER_EXECUTOR_HELPER'], os.X_OK)
            add('application:' + name, 'ok' if good else 'error', 'Executable is available.' if good else 'Selected application executable is missing.')
        if metadata.get('plugin'):
            identity = metadata['plugin']
            target = Path.home() / '.config/omarchy/plugins' / identity
            source = SOURCES[name]
            rev_code, revision = command(['git', '--no-optional-locks', '-C', str(target), 'rev-parse', 'HEAD'])
            dirty_code, dirty = command(['git', '--no-optional-locks', '-C', str(target), 'status', '--porcelain', '--untracked-files=all'])
            origin_code, origin = command(['git', '-C', str(target), 'remote', 'get-url', 'origin'])
            good = not target.is_symlink() and rev_code == dirty_code == origin_code == 0 and revision.strip() == source['pin'] and origin.strip() in [source['source'], *source.get('aliases', [])] and not dirty.strip()
            add('plugin:' + identity, 'ok' if good else 'error', 'Clean source and pin match.' if good else 'Missing, dirty, foreign or unpinned selected plugin checkout.')
            add('enabled:' + identity, 'ok' if identity in active else 'error', 'Plugin enabled.' if identity in active else 'Selected plugin is not enabled.')
        if metadata.get('suite'):
            marker = Path.home() / '.local/state/shibumi/install.json'
            try:
                installed = json.loads(marker.read_text())
                source = SOURCES[name]
                suite_code, _ = command([str(Path(installed['sourceRoot']) / 'scripts/shibumi-suite'), 'status'], timeout=20)
                good = installed.get('sourceRevision') == source['pin'] and suite_code == 0
            except (OSError, ValueError, KeyError):
                good = False
            add('suite:shibumi', 'ok' if good else 'error', 'Suite lifecycle status verified.' if good else 'Selected Shibumi suite is absent or fails its lifecycle check.')
        if metadata.get('config'):
            specification = metadata['config']
            path = Path.home() / specification['path']
            try:
                values = json.loads(path.read_text())
                ready = all(isinstance(values.get(key), str) and values[key].strip() for key in specification['required'])
                if 'vaultPath' in specification['required']:
                    ready = ready and Path(values['vaultPath']).is_dir()
                for field in ('endpoint', 'serverUrl'):
                    if field in specification['required']:
                        ready = ready and values[field].startswith('https://') and 'example.com' not in values[field]
            except (OSError, ValueError, TypeError, KeyError):
                ready = False
            add('readiness:' + name, 'ok' if ready else 'pending', 'Local prerequisites configured; remote service connectivity still needs acceptance.' if ready else 'Supply local settings/data and secure credentials; integration is not ready.')
    if 'install-home-assistant.sh' in selected:
        try:
            ha = json.loads((Path.home() / '.config/omarchy/home-assistant.json').read_text())
            ha_token = Path(ha.get('tokenFile', str(token))).expanduser()
            entities = any(ha.get(key) for key in ('climate', 'temperature', 'humidity', 'weather')) or any(ha.get(key) for key in ('switches', 'scenes', 'lights'))
            ready = ha_token.is_file() and ha_token.stat().st_size > 0 and not ha_token.stat().st_mode & 0o077 and ha.get('baseUrl', '').startswith('https://') and bool(entities)
        except (OSError, ValueError, TypeError):
            ready = False
        add('readiness:home-assistant', 'ok' if ready else 'pending', 'HA local URL/token/entity prerequisites present; verify server connectivity.' if ready else 'Supply the Home Assistant HTTPS URL, private token-file reference and entity mappings locally.')
    if 'install-tailscale.sh' in selected:
        code, response = command(['tailscale', 'status', '--json'])
        try:
            ready = code == 0 and json.loads(response).get('BackendState') == 'Running'
        except ValueError:
            ready = False
        add('readiness:tailscale', 'ok' if ready else 'pending', 'Tailscale enrolled and running.' if ready else 'Enroll this device with tailscale up.')
    if 'install-calendar.sh' in selected:
        code, _ = command(['systemctl', '--user', 'is-active', '--quiet', 'omarchy-calendar-sync.timer'])
        add('readiness:calendar', 'ok' if code == 0 else 'pending', 'Calendar timer active; verify event sync.' if code == 0 else 'Complete Calendar OAuth and rerun its installer.')
    if 'install-sunshine.sh' in selected:
        code, _ = command(['systemctl', '--user', 'is-active', '--quiet', 'sunshine'])
        add('readiness:sunshine', 'ok' if code == 0 else 'pending', 'Sunshine active; verify pairing and capture.' if code == 0 else 'Configure Sunshine credentials, pairing, capture and service startup.')
    if 'install-hyprland.sh' in selected:
        code, errors = command(['hyprctl', 'configerrors'])
        add('hypr-configuration', 'ok' if code == 0 and not errors.strip() else 'error', 'Live Hyprland configuration is valid.' if code == 0 and not errors.strip() else 'Hyprland reports configuration errors or cannot be queried.')
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--acceptance', action='store_true', help='Pending required integration setup exits 2, not success.')
    parser.add_argument('--profile', type=Path)
    parser.add_argument('--dotfiles', type=Path)
    parser.add_argument('--export-profile', action='store_true')
    args = parser.parse_args()
    if args.export_profile:
        return subprocess.run([sys.executable, str(ROOT / 'config/feature-profile.py'), 'export']).returncode
    checks = inspect(args.preflight, args.dotfiles, args.profile)
    errors = any(row['status'] == 'error' for row in checks)
    pending = any(row['status'] == 'pending' for row in checks)
    good = not errors and not (args.acceptance and pending)
    if args.json:
        print(json.dumps(dict(ok=good, checks=checks), indent=2))
    else:
        for row in checks:
            print(f'{row["status"].upper():7} {row["name"]}: {row["message"]}')
    return 1 if errors else (2 if args.acceptance and pending else 0)


if __name__ == '__main__':
    sys.exit(main())
