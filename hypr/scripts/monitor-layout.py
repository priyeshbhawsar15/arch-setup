#!/usr/bin/env python3
"""Resolve personal display roles without depending on connector numbering."""
import argparse
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
    roles = config['monitors']
    if not {'main', 'side_left', 'side_right'}.issubset(roles):
        raise ValueError('keep the main/side_left/side_right role names; edit their descriptions to replace displays')
    descriptions = [entry['description'] for entry in roles.values()]
    if not descriptions or any(not isinstance(d, str) or not d.strip() for d in descriptions):
        raise ValueError('monitor descriptions must be nonempty strings')
    if len(set(descriptions)) != len(descriptions):
        raise ValueError('monitor descriptions must be unique; include serials for identical models')
    for key in ('windowSpan', 'singleMonitorDisable', 'wallpaperSpan', 'lockSides'):
        if not config[key] or len(set(config[key])) != len(config[key]):
            raise ValueError(f'{key} must contain distinct monitor roles')
        for role in config[key]:
            if role not in roles:
                raise ValueError(f'unknown role {role} in {key}')
    for role in [config['singleMonitorKeep'], config['lockMain'], config['barMain'],
                 *config['widgetTargets'].values()]:
        if role not in roles:
            raise ValueError(f'unknown monitor role: {role}')
    if config['singleMonitorKeep'] in config['singleMonitorDisable']:
        raise ValueError('single-monitor mode must keep its main display enabled')
    if len(config['windowSpan']) != 2:
        raise ValueError('windowSpan must select exactly two displays')
    for path in config['widgetTargets']:
        if Path(path).is_absolute() or '..' in Path(path).parts:
            raise ValueError('widget configuration paths must be relative to HOME')
    return config


def live_monitors():
    return json.loads(subprocess.check_output(['hyprctl', '-j', 'monitors', 'all'], text=True))


def resolve(config, outputs, required=()):
    result = {}
    for role, entry in config['monitors'].items():
        matches = [m for m in outputs if m.get('description') == entry['description']]
        if len(matches) > 1:
            raise ValueError(f'{role}: display identity is ambiguous ({entry["description"]})')
        result[role] = matches[0] if matches else None
        if role in required and (not result[role] or result[role].get('disabled')):
            raise ValueError(f'{role}: display is disconnected or disabled ({entry["description"]})')
    return result


def canvas(config, outputs):
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


def render(config, path):
    text = Path(path).read_text()
    for role, entry in config['monitors'].items():
        text = text.replace(json.dumps('@monitor:' + role + '@'), json.dumps('desc:' + entry['description']))
    main_description = config['monitors'][config['barMain']]['description']
    return text.replace(json.dumps('@bar-main-description@'), json.dumps(main_description))


def single_monitor_lua(config, outputs):
    resolve(config, outputs, [config['singleMonitorKeep']])
    return ''.join('hl.monitor({ output = ' + json.dumps('desc:' + config['monitors'][role]['description'])
                   + ', disabled = true })\n' for role in config['singleMonitorDisable'])


def private_backup_directory(label):
    root = Path(os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local/state')) / 'arch-setups/backups'
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=label + '-', dir=root))


def write_atomic(path, content, mode=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(mode if mode is not None else (path.stat().st_mode & 0o777 if path.exists() else 0o644))
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
    monitor = resolve(config, live_monitors())[role]
    if not monitor:
        raise ValueError(f'{role}: connect the configured widget display before installing')
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
        if path.exists() and path.read_bytes() == content:
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
        write_atomic(path, content, mode)
        changed = True

    save(home / '.config/omarchy/monitor-layout.json', Path(config_path).read_bytes())
    for name in ('monitor-layout.py', 'monitor-mode-toggle.sh', 'window-span-dp6-dp4-toggle.sh'):
        save(home / '.config/hypr/scripts' / name, (repo / 'hypr/scripts' / name).read_bytes(), True)
    save(home / '.config/hypr/monitors.lua', render(config, repo / 'hypr/monitors.lua').encode())
    # Replace a stale connector-based toggle while preserving single-monitor mode.
    toggle = home / '.local/state/omarchy/toggles/hypr/desktop-single-monitor.lua'
    if toggle.exists():
        text = ''.join('hl.monitor({ output = ' + json.dumps('desc:' + config['monitors'][r]['description'])
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
            metrics_config = relative == '.config/omarchy/system-metrics.json'
            if not selected[role] or (not path.exists() and not (metrics_config and
                    (home / '.config/omarchy/plugins/priyesh.system-metrics').exists())):
                continue
            data = json.loads(path.read_text()) if path.exists() else {}
            if data.get('targetScreen') != selected[role]['name']:
                data['targetScreen'] = selected[role]['name']
                save(path, (json.dumps(data, indent=2) + '\n').encode())
        span = names(config['wallpaperSpan'])
        path = home / '.config/omarchy/wallpaper-controller.json'
        if span and path.exists():
            data = json.loads(path.read_text())
            if data.get('spanGroups') != [span]:
                data['spanGroups'] = [span]
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
                    presentation['mainMonitorDescription'] = config['monitors'][config['barMain']]['description']
                if plugin.get('id') == 'io.github.sirjul1337.lock-explorer' and main and sides and span:
                    power = plugin.get('phasedPower')
                    if power:
                        power.update(main=main[0], sides=sides, ddcPowerOffMonitors=sides)
                    plugin['wallpaperSpanGroups'] = [span]
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
