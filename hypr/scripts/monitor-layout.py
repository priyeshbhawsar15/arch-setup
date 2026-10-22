#!/usr/bin/env python3
"""Resolve personal display roles without depending on connector numbering."""
import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


def load_config(path):
    config = json.loads(Path(path).read_text())
    if not isinstance(config, dict):
        raise ValueError('monitor policy must be an object')
    roles = config['monitors']
    allowed = {'monitors', 'toolkitScale', 'windowSpan', 'singleMonitorKeep', 'singleMonitorDisable', 'wallpaperSpan', 'lockMain', 'lockSides', 'barMain', 'widgetTargets'}
    if set(config) - allowed or not isinstance(roles, dict) or not roles:
        raise ValueError('monitor policy must have roles and no unknown fields')
    identities = []
    for entry in roles.values():
        if not isinstance(entry, dict) or set(entry) - {'description', 'connector', 'selector', 'mode', 'position', 'scale', 'transform', 'bitdepth', 'cm', 'sdrbrightness', 'sdrsaturation', 'workspaces'}:
            raise ValueError('unknown monitor setting')
        selectors = [key for key in ('description', 'connector', 'selector') if key in entry]
        if len(selectors) != 1 or not isinstance(entry[selectors[0]], str) or not entry[selectors[0]].strip() or any(ord(c) < 32 for c in entry[selectors[0]]):
            raise ValueError('each monitor needs one nonempty description, connector or primary selector')
        if 'selector' in entry and entry['selector'] != 'primary':
            raise ValueError('only primary is supported as a dynamic selector')
        if any(not isinstance(entry.get(key, ''), str) for key in ('mode', 'position', 'cm')):
            raise ValueError('mode/position/cm must be strings')
        scale = entry.get('scale', 'auto')
        if scale != 'auto' and (type(scale) not in (int, float) or not math.isfinite(scale) or scale <= 0):
            raise ValueError('scale must be auto or a positive finite number')
        if type(entry.get('transform', 0)) is not int or not 0 <= entry.get('transform', 0) <= 7:
            raise ValueError('invalid monitor transform')
        if entry.get('bitdepth', 8) not in (8, 10):
            raise ValueError('bitdepth must be 8 or 10')
        for key in ('sdrbrightness', 'sdrsaturation'):
            if key in entry and (type(entry[key]) not in (int, float) or not math.isfinite(entry[key]) or entry[key] < 0):
                raise ValueError('invalid HDR numeric setting')
        workspaces = entry.get('workspaces', [])
        if not isinstance(workspaces, list) or any(type(n) is not int or n < 1 for n in workspaces):
            raise ValueError('workspaces must be positive integers')
        identities.append((selectors[0], entry[selectors[0]]))
    if len(set(identities)) != len(identities):
        raise ValueError('monitor identities must be unique; include serials for identical models')
    for key in ('windowSpan', 'singleMonitorDisable', 'wallpaperSpan', 'lockSides'):
        if not isinstance(config[key], list) or len(set(config[key])) != len(config[key]):
            raise ValueError(f'{key} must contain distinct monitor roles')
        for role in config[key]:
            if role not in roles:
                raise ValueError(f'unknown role {role} in {key}')
    if not isinstance(config['widgetTargets'], dict):
        raise ValueError('widgetTargets must be an object')
    known_widgets = {'.config/omarchy/' + name + '.json' for name in ('obsidian-tasks', 'omniroute-quota', 'system-metrics', 'weather-widget', 'immich-photo-frame', 'home-assistant')}
    if set(config['widgetTargets']) - known_widgets:
        raise ValueError('widgetTargets may only manage supported widget configuration files')
    for role in [config['singleMonitorKeep'], config['lockMain'], config['barMain'],
                 *config['widgetTargets'].values()]:
        if role not in roles:
            raise ValueError(f'unknown monitor role: {role}')
    if config['singleMonitorKeep'] in config['singleMonitorDisable']:
        raise ValueError('single-monitor mode must keep its main display enabled')
    if len(config['windowSpan']) not in (0, 2):
        raise ValueError('windowSpan must select zero or two displays')
    for path in config['widgetTargets']:
        if Path(path).is_absolute() or '..' in Path(path).parts:
            raise ValueError('widget configuration paths must be relative to HOME')
    if any(roles[role].get('selector') == 'primary' for role in config['singleMonitorDisable']):
        raise ValueError('cannot disable the wildcard primary selector')
    if 'toolkitScale' in config and (type(config['toolkitScale']) is not int or not 1 <= config['toolkitScale'] <= 4):
        raise ValueError('toolkitScale must be an integer from 1 to 4')
    return config


def live_monitors():
    return json.loads(subprocess.check_output(['hyprctl', '-j', 'monitors', 'all'], text=True))


def resolve(config, outputs, required=()):
    result = {}
    for role, entry in config['monitors'].items():
        if entry.get('selector') == 'primary':
            active = [m for m in outputs if not m.get('disabled')]
            matches = ([m for m in active if m.get('focused')] or active)[:1]
        elif 'connector' in entry:
            matches = [m for m in outputs if m.get('name') == entry['connector']]
        else:
            matches = [m for m in outputs if m.get('description') == entry['description']]
        if len(matches) > 1:
            raise ValueError(f'{role}: display identity is ambiguous')
        result[role] = matches[0] if matches else None
        if role in required and (not result[role] or result[role].get('disabled')):
            raise ValueError(f'{role}: display is disconnected or disabled')
    return result


def canvas(config, outputs):
    if len(config['windowSpan']) != 2:
        raise ValueError('Window spanning is not configured for this host')
    selected = resolve(config, outputs, config['windowSpan'])
    pair = sorted([selected[role] for role in config['windowSpan']], key=lambda m: m['x'])
    dimensions = []
    for monitor in pair:
        w, h = monitor['width'], monitor['height']
        if monitor.get('transform', 0) % 2:
            w, h = h, w
        dimensions.append((math.floor(w / monitor['scale'] + .5),
                           math.floor(h / monitor['scale'] + .5)))
    left, right = pair
    (lw, lh), (rw, rh) = dimensions
    if left['y'] != right['y'] or lh != rh or left['x'] + lw != right['x']:
        raise ValueError(f'{left["name"]} and {right["name"]} must be adjacent with matching logical heights; '
                         'adjust the monitor layout in hyprmoncfg')
    return dict(x=left['x'], y=left['y'], width=lw + rw, height=lh)


def selector(entry):
    return 'desc:' + entry['description'] if 'description' in entry else entry.get('connector', '')


def lua(value):
    # JSON's ASCII-only \\u escapes are not valid Lua escapes. UTF-8 strings are.
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def render(config, path):
    text = Path(path).read_text()
    rules, workspaces = [], []
    if config.get('toolkitScale') is not None:
        if type(config['toolkitScale']) is not int or not 1 <= config['toolkitScale'] <= 4:
            raise ValueError('toolkitScale must be an integer from 1 to 4')
        rules.append('hl.env("GDK_SCALE", ' + json.dumps(str(config['toolkitScale'])) + ')')
    rules.append('hl.monitor({ output = "", mode = "preferred", position = "auto", scale = "auto" })')
    for role, entry in config['monitors'].items():
        text = text.replace(json.dumps('@monitor:' + role + '@'), lua(selector(entry)))
        fields = dict(output=selector(entry), **{k: v for k, v in entry.items() if k not in ('description', 'connector', 'selector', 'workspaces')})
        rules.append('hl.monitor({ ' + ', '.join(key + ' = ' + lua(value) for key, value in fields.items()) + ' })')
        for number in entry.get('workspaces', []):
            if selector(entry):
                workspaces.append('hl.workspace_rule({ workspace = ' + json.dumps(str(number)) + ', monitor = ' + lua(selector(entry)) + ', default = ' + ('true' if number == entry['workspaces'][0] else 'false') + ', persistent = true })')
    main_description = config['monitors'][config['barMain']].get('description', '')
    return text.replace('-- @monitor-rules@', '\n'.join(rules)).replace('-- @workspace-rules@', '\n'.join(workspaces)).replace(json.dumps('@bar-main-description@'), json.dumps(main_description))


def single_monitor_lua(config, outputs):
    resolve(config, outputs, [config['singleMonitorKeep']])
    return ''.join('hl.monitor({ output = ' + lua(selector(config['monitors'][role]))
                   + ', disabled = true })\n' for role in config['singleMonitorDisable'])


def private_backup_directory(label):
    root = Path(os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local/state')) / 'arch-setups/backups'
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=label + '-', dir=root))


ANY_CONTENT = object()


def write_atomic(path, content, mode=None, expected=ANY_CONTENT):
    if path.is_symlink():
        raise ValueError('refusing symlinked managed configuration: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(mode if mode is not None else (path.stat().st_mode & 0o777 if path.exists() else 0o644))
        if expected is not ANY_CONTENT and (path.read_bytes() if path.exists() else None) != expected:
            raise ValueError('configuration changed concurrently; retry: ' + str(path))
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


# Only these exact historical appendices are safe to remove from the otherwise
# unchanged package template. Any other root-config edit must be reviewed first.
LEGACY_ENTRYPOINT_BLOCKS = (
    b'\ndo\n'
    b'  local path = os.getenv("HOME") .. "/.config/hypr/hyprmoncfg-monitors.lua"\n'
    b'  local file = io.open(path, "r")\n'
    b'  if file then file:close(); dofile(path) end\n'
    b'  local sm_path = os.getenv("HOME") .. "/.local/state/omarchy/toggles/hypr/desktop-single-monitor.lua"\n'
    b'  local sm_file = io.open(sm_path, "r")\n'
    b'  if sm_file then sm_file:close(); dofile(sm_path) end\n'
    b'end\n',
    b'\n-- Added by hyprmoncfg: its generated monitor rules load last, so nothing before this can override the applied layout.\n'
    b'do local path = os.getenv("HOME") .. "/.config/hypr/hyprmoncfg-monitors.lua"; local file = io.open(path, "r"); if file then file:close(); dofile(path) end end\n',
)


def migrate_entrypoint(package_path):
    package = Path(package_path).read_bytes()
    path = Path.home() / '.config/hypr/hyprland.lua'
    if not path.exists():
        write_atomic(path, package)
        return True
    original = path.read_bytes()
    if original == package:
        return False
    if not original.startswith(package):
        raise ValueError('hyprland.lua contains unknown edits; preserving it. Review against the packaged template before installing.')
    tail = original[len(package):]
    while tail:
        block = next((block for block in LEGACY_ENTRYPOINT_BLOCKS if tail.startswith(block)), None)
        if block is None:
            raise ValueError('hyprland.lua contains an unrecognized appendix; preserving it and all managed modules.')
        tail = tail[len(block):]
    backup = private_backup_directory('hyprland-entrypoint')
    shutil.copy2(path, backup / 'hyprland.lua')
    if path.read_bytes() != original:
        raise ValueError('hyprland.lua changed during migration; preserving the intervening edit.')
    write_atomic(path, package)
    print('Backups: ' + str(backup), file=sys.stderr)
    return True


def configure_widget(config, relative):
    role = config['widgetTargets'][relative]
    outputs = live_monitors()
    monitor = resolve(config, outputs)[role]
    if not monitor or monitor.get('disabled'):
        monitor = next((m for m in outputs if m.get('focused') and not m.get('disabled')), None) or next((m for m in outputs if not m.get('disabled')), None)
    if not monitor:
        raise ValueError('connect an active display before installing the widget')
    home = Path.home()
    path = home / relative
    data = json.loads(path.read_text()) if path.exists() else {}
    if data.get('targetScreen') == monitor['name']:
        return False
    if path.exists():
        backup = private_backup_directory('monitor-widget') / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        print('Backups: ' + str(backup), file=sys.stderr)
    data['targetScreen'] = monitor['name']
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, (json.dumps(data, indent=2) + '\n').encode(), path.stat().st_mode & 0o777 if path.exists() else 0o600)
    return True


def install(config, config_path, repo, hypr_only=False):
    home = Path.home()
    backup = None
    changed = False
    wallpaper_changed = False

    def save(path, content, executable=False):
        nonlocal changed, backup
        original = path.read_bytes() if path.exists() else None
        if original == content:
            if executable and not os.access(path, os.X_OK):
                path.chmod((path.stat().st_mode & 0o777) | 0o100)
                changed = True
            return
        if path.exists():
            if backup is None: backup = private_backup_directory('monitor-layout')
            dest = backup / path.relative_to(home)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = path.stat().st_mode & 0o777 if path.exists() else (0o755 if executable else 0o644)
        if executable: mode |= 0o100
        write_atomic(path, content, mode, original)
        changed = True

    save(home / '.config/omarchy/monitor-layout.json', Path(config_path).read_bytes())
    for name in ('monitor-layout.py', 'monitor-mode-toggle.sh', 'window-span-dp6-dp4-toggle.sh'):
        save(home / '.config/hypr/scripts' / name, (repo / 'hypr/scripts' / name).read_bytes(), True)
    save(home / '.config/hypr/monitors.lua', render(config, repo / 'hypr/monitors.lua').encode())
    # Replace a stale connector-based toggle while preserving single-monitor mode.
    toggle = home / '.local/state/omarchy/toggles/hypr/desktop-single-monitor.lua'
    if toggle.exists():
        text = ''.join('hl.monitor({ output = ' + lua(selector(config['monitors'][r]))
                       + ', disabled = true })\n' for r in config['singleMonitorDisable'])
        save(toggle, text.encode())

    if not hypr_only:
        try:
            selected = resolve(config, live_monitors())
        except (subprocess.CalledProcessError, FileNotFoundError):
            selected = dict.fromkeys(config['monitors'])
            print('No Hyprland session: rerun install-monitor-layout.sh with displays connected to map plugin targets.', file=sys.stderr)

        def names(roles):
            if any(not selected[r] for r in roles):
                print('Skipping disconnected monitor roles: ' + ', '.join(roles), file=sys.stderr)
                return None
            return [selected[r]['name'] for r in roles]

        for relative, role in config['widgetTargets'].items():
            path = home / relative
            plugin = 'priyesh.' + Path(relative).stem
            if not selected[role] or (not path.exists() and not
                    (home / '.config/omarchy/plugins' / plugin).exists()):
                continue
            data = json.loads(path.read_text()) if path.exists() else {}
            if data.get('targetScreen') != selected[role]['name']:
                data['targetScreen'] = selected[role]['name']
                save(path, (json.dumps(data, indent=2) + '\n').encode())
        span = names(config['wallpaperSpan'])
        path = home / '.config/omarchy/wallpaper-controller.json'
        if span is not None and path.exists():
            data = json.loads(path.read_text())
            groups = [span] if span else []
            if data.get('spanGroups') != groups:
                data['spanGroups'] = groups
                save(path, (json.dumps(data, indent=2) + '\n').encode())
                wallpaper_changed = True
        path = home / '.config/omarchy/shell.json'
        main = names([config['lockMain']])
        sides = names(config['lockSides'])
        if path.exists():
            data = json.loads(path.read_text())
            original = json.dumps(data)
            for plugin in data.get('plugins', []):
                if plugin.get('id') == 'hancore.shibumi.state':
                    presentation = plugin.setdefault('shibumi', {}).setdefault('presentation', {})
                    presentation['mainMonitorDescription'] = config['monitors'][config['barMain']].get('description', '')
                if plugin.get('id') == 'io.github.sirjul1337.lock-explorer' and main and sides is not None and span is not None:
                    power = plugin.get('phasedPower')
                    if power:
                        power.update(main=main[0], sides=sides, ddcPowerOffMonitors=sides)
                    plugin['wallpaperSpanGroups'] = [span] if span else []
            if json.dumps(data) != original:
                save(path, (json.dumps(data, indent=2) + '\n').encode())
    if backup is not None:
        print('Backups: ' + str(backup), file=sys.stderr)
    return dict(changed=changed, wallpaperChanged=wallpaper_changed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(Path.home() / '.config/omarchy/monitor-layout.json'))
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('resolve')
    sub.add_parser('canvas')
    sub.add_parser('single-monitor-lua')
    sub.add_parser('render').add_argument('path')
    sub.add_parser('configure-widget').add_argument('path')
    sub.add_parser('migrate-entrypoint').add_argument('--package', required=True)
    apply = sub.add_parser('install')
    apply.add_argument('--repo', required=True, type=Path)
    apply.add_argument('--hypr-only', action='store_true')
    args = parser.parse_args()
    try:
        if args.command in ('install', 'configure-widget', 'migrate-entrypoint'):
            lock_root = Path(os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local/state')) / 'arch-setups'
            lock_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            configuration_lock = (lock_root / 'configuration.lock').open('a')
            os.chmod(configuration_lock.name, 0o600)
            fcntl.flock(configuration_lock, fcntl.LOCK_EX)
        config = load_config(args.config)
        if args.command == 'migrate-entrypoint':
            print(json.dumps({'changed': migrate_entrypoint(args.package)}))
        elif args.command == 'render':
            print(render(config, args.path), end='')
        elif args.command == 'configure-widget':
            print('Configured widget display.' if configure_widget(config, args.path) else 'Widget display is already installed.')
        elif args.command == 'canvas':
            print(json.dumps(canvas(config, live_monitors())))
        elif args.command == 'single-monitor-lua':
            print(single_monitor_lua(config, live_monitors()), end='')
        elif args.command == 'resolve':
            selected = resolve(config, live_monitors())
            print(json.dumps({r: m['name'] if m else None for r, m in selected.items()}))
        else:
            print(json.dumps(install(config, args.config, args.repo, args.hypr_only)))
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        print(f'Monitor layout: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
