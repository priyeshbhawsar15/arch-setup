#!/usr/bin/env python3
"""Managed by arch-setups: reversible desktop gaming mode; no root/input grabs."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HOME = Path.home()
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config')) / 'omarchy/gaming-mode.json'
STATE = Path(os.environ.get('XDG_STATE_HOME', HOME / '.local/state')) / 'omarchy/gaming-mode'
WALLPAPER = HOME / '.config/omarchy/wallpaper-controller.json'
STOP = False
# Shared Wine services can outlive the game. They must not hold Gaming Mode on.
BACKGROUND_PROCESSES = {
    'steam', 'steamwebhelper', 'lutris', 'wineserver', 'wineserver64', 'services.exe',
    'winedevice.exe', 'explorer.exe', 'rpcss.exe', 'svchost.exe', 'plugplay.exe',
    'conhost.exe', 'wineboot.exe', 'winedbg', 'winedbg.exe', 'crashpad_handler',
}
GAME_ENV_KEYS = {'SteamAppId', 'SteamGameId', 'GAME_NAME', 'HYPRLAND_INSTANCE_SIGNATURE'}
NON_GAME_APP_IDS = {'431960'}  # Wallpaper Engine is a desktop background, not a game.
# Only reviewed, independent desktop overlays. Never accept core/bar/lock IDs here.
DEFAULT_PAUSE_PLUGINS = (
    'priyesh.system-metrics', 'priyesh.weather-widget', 'priyesh.immich-photo-frame',
)



def run(*args, timeout=30):
    p = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f'{args[0]}: {p.stderr.strip() or p.stdout.strip()}')
    return p.stdout


def read(path, default=None):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    tmp.chmod(0o600)
    tmp.replace(path)


def connect():
    instances = json.loads(run('hyprctl', 'instances', '-j'))
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    matches = [i for i in instances if i['instance'] == signature]
    if not matches:
        matches = [i for i in instances if i['wl_socket'] == os.environ.get('WAYLAND_DISPLAY')]
    if not matches and len(instances) == 1:
        matches = instances
    if len(matches) != 1:
        raise RuntimeError('Cannot select a unique active Hyprland session')
    os.environ['HYPRLAND_INSTANCE_SIGNATURE'] = matches[0]['instance']
    os.environ.setdefault('WAYLAND_DISPLAY', matches[0]['wl_socket'])
    os.environ.setdefault('OMARCHY_PATH', '/usr/share/omarchy')


def hypr(command):
    return json.loads(run('hyprctl', '-j', command))


def monitor(config):
    monitors = hypr('monitors')
    selector = config['monitor']
    matches = [m for m in monitors if m['name'] == selector or 'desc:' + m['description'] == selector]
    if len(matches) != 1:
        raise RuntimeError(f'Gaming monitor unavailable or ambiguous: {selector}')
    return matches[0]


def monitor_spec(m, vrr):
    # hl.monitor REPLACES a rule. Never submit a partial {output, vrr} table.
    return dict(output=m['name'], mode=f"{m['width']}x{m['height']}@{m['refreshRate']:.5f}",
                position=f"{m['x']}x{m['y']}", scale=m['scale'], transform=m['transform'],
                bitdepth=10 if '2101010' in m['currentFormat'] else 8,
                cm=m['colorManagementPreset'], sdrbrightness=m['sdrBrightness'],
                sdrsaturation=m['sdrSaturation'], sdr_min_luminance=m['sdrMinLuminance'],
                sdr_max_luminance=m['sdrMaxLuminance'], vrr=vrr)


def set_vrr(m, value):
    spec = monitor_spec(m, value)
    # JSON keys are not Lua table keys. Values are JSON scalars compatible with Lua here.
    fields = ','.join(k + '=' + json.dumps(v) for k, v in spec.items())
    result = run('hyprctl', 'eval', 'hl.monitor({' + fields + '})')
    if result.strip() != 'ok':
        raise RuntimeError('Hyprland rejected monitor update: ' + result)


def valid_steam_id(value):
    return 0 < len(value) <= 20 and value.isdigit() and int(value) > 0 and value not in NON_GAME_APP_IDS


def game_windows(clients):
    # Fallback for games that sanitize their environment. Steam/Big Picture and
    # generic Gamescope windows alone are intentionally NOT activation signals.
    prefix = 'steam_app_'
    return any(c.get('class', '').startswith(prefix) and
               valid_steam_id(c['class'][len(prefix):]) for c in clients)


def process_game_source(comm, environment):
    name = comm.lower()
    if name in BACKGROUND_PROCESSES or name.startswith(('linux-wallpaper', 'steamwebhelper', 'fossilize')):
        return None
    steam_ids = [environment.get(key, '') for key in ('SteamAppId', 'SteamGameId')]
    if any(value in NON_GAME_APP_IDS for value in steam_ids):
        return None
    if any(valid_steam_id(value) for value in steam_ids):
        return 'Steam'
    # Lutris configure_game() assigns GAME_NAME for all of its runners, not only
    # Wine. No per-game config edits or user-script hook replacement are needed.
    game_name = environment.get('GAME_NAME', '').strip()
    if game_name and game_name.casefold().replace(' ', '') != 'wallpaperengine':
        return 'Lutris'
    return None


def running_games(proc_root=Path('/proc'), uid=None):
    uid = os.getuid() if uid is None else uid
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    for process in proc_root.glob('[0-9]*'):
        try:
            if process.stat().st_uid != uid:
                continue
            comm = (process / 'comm').read_text().strip()
            if comm.lower() in BACKGROUND_PROCESSES or comm.lower().startswith(('linux-wallpaper', 'fossilize')):
                continue
            # Read only our own processes, bound each read, retain only game
            # marker keys. Never log/store complete environments or credentials.
            with (process / 'environ').open('rb') as stream:
                raw = stream.read(256 * 1024)
            environment = {}
            for item in raw.split(b'\0'):
                key, sep, value = item.partition(b'=')
                key = key.decode(errors='replace')
                if sep and key in GAME_ENV_KEYS:
                    environment[key] = value.decode(errors='replace')
            other_session = environment.get('HYPRLAND_INSTANCE_SIGNATURE')
            if signature and other_session and signature != other_session:
                continue
            if process_game_source(comm, environment):
                return True
        except (OSError, ValueError):
            # Processes exiting mid-scan or unreadable /proc entries are normal.
            continue
    return False


def gaming_requested(clients):
    return leases() or game_windows(clients) or running_games()


def plugin_states():
    plugins = json.loads(run('omarchy', 'plugin', 'list', '--json', timeout=3))
    if not isinstance(plugins, list):
        raise RuntimeError('Invalid Omarchy plugin catalog response')
    return {p['id']: p for p in plugins}


def pause_candidates(config, states):
    ids = config.get('pausePlugins', list(DEFAULT_PAUSE_PLUGINS))
    if not isinstance(ids, list) or any(not isinstance(p, str) or p not in DEFAULT_PAUSE_PLUGINS for p in ids):
        raise RuntimeError('pausePlugins must be a list of reviewed nonessential widget IDs')
    if len(ids) != len(set(ids)):
        raise RuntimeError('Duplicate pausePlugins IDs')
    return [p for p in ids if states.get(p, {}).get('enabled') and states[p].get('canDisable', True)]


def set_plugin_enabled(plugin, enabled):
    if plugin not in DEFAULT_PAUSE_PLUGINS:
        raise RuntimeError('Refusing to toggle an essential/unreviewed plugin: ' + plugin)
    run('omarchy', 'plugin', 'enable' if enabled else 'disable', plugin, timeout=5)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = plugin_states().get(plugin, {})
        # Catalog `active` describes the selected BAR, not service/overlay load.
        # The shell's _syncServices destroys disabled service instances.
        if state.get('enabled') == enabled:
            return
        time.sleep(.1)
    raise RuntimeError('Plugin did not reach requested enabled state: ' + plugin)


def restore_plugins(session):
    ids = session.get('pausedPlugins', [])
    if not ids:
        return
    if any(p not in DEFAULT_PAUSE_PLUGINS for p in ids):
        raise RuntimeError('Unreviewed plugin in recovery journal')
    states = plugin_states()
    errors = []
    for plugin in ids:
        # Removed plugins stay removed; manually resumed ones need no mutation.
        if plugin in states and not states[plugin].get('enabled'):
            try:
                set_plugin_enabled(plugin, True)
            except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
                errors.append(str(error))
    if errors:
        raise RuntimeError('; '.join(errors))


def wallpaper_owned(session, config):
    return (session.get('wallpaper') and config and not config.get('wallpaperEnabled', True)
            and config.get('active') == session['wallpaper'])


def enter(config):
    if type(config.get('pauseDecorations', True)) is not bool:
        raise RuntimeError('pauseDecorations must be a boolean')
    m = monitor(config)
    w = read(WALLPAPER, {})
    # Validate even when no widget is installed. An empty list opts out of pausing.
    pause_candidates(config, {})
    candidates = pause_candidates(config, plugin_states()) if config.get('pausePlugins', DEFAULT_PAUSE_PLUGINS) else []
    session = {'schemaVersion': 1,
               'signature': os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'),
               'pauseDecorations': config.get('pauseDecorations', True),
               'monitor': config['monitor'], 'previousVrr': config.get('restoreVrr', int(m['vrr'])),
               'wallpaper': w.get('active') if w.get('wallpaperEnabled', True) else None,
               'pausedPlugins': candidates}
    # Journal BEFORE side effects, allowing recovery after a crash.
    save(STATE / 'session.json', session)
    try:
        if session['wallpaper']:
            run(str(HOME / '.local/bin/wallpaper-controller'), 'stop')
        set_vrr(m, 1)
        for plugin in candidates:
            set_plugin_enabled(plugin, False)
    except Exception:
        leave(session)
        raise
    print('Gaming Mode active', flush=True)
    return session


def leave(session):
    errors = []
    try:
        if session['signature'] == os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
            # Preserve current layout/HDR changes made during play; restore only VRR.
            set_vrr(monitor(session), session['previousVrr'])
    except Exception as error:
        errors.append(str(error))
    try:
        if wallpaper_owned(session, read(WALLPAPER, {})):
            run(str(HOME / '.local/bin/wallpaper-controller'), 'apply', session['wallpaper'])
    except Exception as error:
        errors.append(str(error))
    try:
        restore_plugins(session)
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        errors.append(str(error))
    if errors:
        raise RuntimeError('Restoration incomplete (journal retained): ' + '; '.join(errors))
    (STATE / 'session.json').unlink(missing_ok=True)
    print('Desktop restored', flush=True)


def birth(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def leases():
    active = False
    for p in STATE.glob('lease-*.json'):
        data = read(p, {})
        if data.get('birth') and birth(data.get('pid')) == data['birth']:
            active = True
        else:
            p.unlink(missing_ok=True)
    return active


def watch():
    global STOP
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (STATE / 'watch.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: globals().__setitem__('STOP', True))
    config = read(CONFIG)
    if not config or not config.get('monitor'):
        raise RuntimeError('Configure ' + str(CONFIG))
    session = read(STATE / 'session.json')
    if session:
        leave(session)
        session = None
    misses = 0
    try:
        while not STOP:
            try:
                if session is None:
                    pending = read(STATE / 'session.json')
                    if pending:
                        leave(pending)
                clients = hypr('clients')
                requested = gaming_requested(clients)
                misses = 0 if requested else misses + 1
                if requested and session is None:
                    session = enter(config)
                elif session and misses >= 3:
                    leave(session)
                    session = None
                elif session:
                    m = monitor(config)
                    if not m['vrr']:
                        set_vrr(m, 1)  # Reconcile after a desktop config reload.
            except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
                # A failed query is NOT an exit signal. Keep the recovery journal.
                print(str(error), file=sys.stderr, flush=True)
                time.sleep(5)  # Avoid repeated wallpaper/theme churn on failed transitions.
            time.sleep(1)
    finally:
        if session:
            leave(session)


def launch(command, hdr=False):
    if not command:
        raise RuntimeError('Usage: gaming-mode run [--hdr] -- GAME [ARGS...]')
    # Avoid accidental nested Gamescope for existing HDR/profile wrappers.
    if any(Path(c).name in ('gamescope', 'steam-gamescope-hdr', 'gaming-mode') for c in command):
        raise RuntimeError('Already wrapped: use either this launcher OR the existing Gamescope wrapper.')
    run('systemctl', '--user', 'is-active', '--quiet', 'arch-gaming-mode.service')
    config = read(CONFIG)
    m = monitor(config)
    pid = os.getpid()
    lease = STATE / f'lease-{pid}.json'
    save(lease, {'pid': pid, 'birth': birth(pid)})
    try:
        result = run('hyprctl', 'eval', 'hl.dispatch(hl.dsp.focus({monitor=' + json.dumps(m['name']) + '}))')
        if result.strip() != 'ok':
            raise RuntimeError('Could not focus the gaming monitor: ' + result)
        width, height = m['width'], m['height']
        if m['transform'] % 2:
            width, height = height, width
        args = ['gamescope', '--backend', 'wayland', '--fullscreen', '--force-windows-fullscreen',
                '-w', str(width), '-h', str(height), '-W', str(width), '-H', str(height),
                '-r', str(round(m['refreshRate']))]
        env = os.environ.copy()
        if hdr:
            args += ['--hdr-enabled', '--hdr-sdr-content-nits', '203']
            env.update(ENABLE_HDR_WSI='1', DXVK_HDR='1')
        # Overlay injection into Gamescope itself is unsupported; MangoApp is separate.
        preload = env.get('LD_PRELOAD', '')
        kept = [p for p in preload.replace(':', ' ').split() if 'gameoverlayrenderer.so' not in p]
        if kept:
            env['LD_PRELOAD'] = ':'.join(kept)
        else:
            env.pop('LD_PRELOAD', None)
        return subprocess.call(args + ['--'] + command, env=env)
    finally:
        lease.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for name in ('watch', 'status', 'big-picture'):
        sub.add_parser(name)
    launch_parser = sub.add_parser('run')
    launch_parser.add_argument('--hdr', action='store_true')
    launch_parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = getattr(args, 'command', [])
    if command[:1] == ['--']:
        command.pop(0)
    if args.action != 'status':
        connect()
    if args.action == 'watch':
        watch()
    elif args.action == 'status':
        print(json.dumps(read(STATE / 'session.json', {'active': False}), indent=2))
    elif args.action == 'big-picture':
        run('systemctl', '--user', 'start', 'arch-gaming-mode.service')
        run('steam', 'steam://open/bigpicture')
    else:
        return launch(command, args.hdr)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print('gaming-mode: ' + str(error), file=sys.stderr)
        sys.exit(1)
