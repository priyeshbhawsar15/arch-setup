#!/usr/bin/env python3
# Managed by arch-setups/install-sunshine.sh
"""Landscape side monitors only while the main Sunshine host streams.

Portrait monitors reach the stream sideways, because KMS capture sends the
panel's unrotated scanout. Sunshine runs `prepare` before an app starts and
`finish` when it ends. A plain disconnect runs neither, so `watch` follows the
host's log and restores portrait once the client stays away for the grace
period. Sunshine measures the desktop for the stream mouse when a client
connects, so a resumed app would keep the portrait layout: when the grace period
ends with an app still running, `watch` restarts the host to end that app.

The rotation is a Hyprland toggle file, because toggles load after
hyprmoncfg's rules and survive its reloads. It applies only to the Hyprland
instance that wrote it, so a new login never starts in landscape.
"""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import struct
import subprocess
import sys
import time
import urllib.request

MARKER = '-- Managed by arch-setups sunshine-stream-display'
UNIT = 'app-dev.lizardbyte.app.Sunshine.service'
GRACE_SECONDS = 120
IDLE_CHECK_SECONDS = 30


def log(message):
    print(f'sunshine-stream-display: {message}', file=sys.stderr, flush=True)


def lib_dir():
    return Path(__file__).resolve().parent


def config_path():
    return Path(os.environ.get('ARCH_SETUPS_STREAM_DISPLAY_CONFIG', lib_dir()/'sunshine-stream-display.json'))


def runtime_dir():
    return Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))


def toggle_path():
    state = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))
    return state/'omarchy/toggles/hypr/sunshine-stream-landscape.lua'


def recorded_output_path():
    return runtime_dir()/'arch-sunshine-stream-output'


def load_config():
    path = config_path()
    return json.loads(path.read_text()) if path.is_file() else None


# -- Policy rendering (install time)

def render_config(policy):
    """Resolve the `sunshineStream` roles of a monitor policy into helper settings."""
    stream = policy.get('sunshineStream')
    if not stream:
        return None
    roles = policy['monitors']
    displays = sorted((roles[role] for role in stream['landscape']), key=lambda entry: position(entry)[0])
    landscape = []
    x, y = position(displays[0])
    for entry in displays:
        width, _ = mode_size(entry)
        landscape.append({'description': entry['description'], 'mode': entry['mode'],
                          'scale': entry.get('scale', 1), 'x': x, 'y': y})
        x += round(width / entry.get('scale', 1))
    return {'capture': roles[stream['capture']]['description'], 'landscape': landscape}


def position(entry):
    x, y = entry['position'].split('x')
    return int(x), int(y)


def mode_size(entry):
    match = re.match(r'^(\d+)x(\d+)', entry['mode'])
    if not match:
        raise ValueError('landscape displays need an explicit WIDTHxHEIGHT mode')
    return int(match[1]), int(match[2])


def toggle_lua(config, signature):
    """Hyprland rules for the landscape layout, bound to one compositor session.

    Sunshine measures the desktop from 0,0 for the stream mouse, while Hyprland
    maps it across the monitors that exist. When no other monitor is on, the
    layout would start at the first one's usual position and the cursor would
    drift, so the landscape monitors then start at 0,0 instead.
    """
    first = config['landscape'][0]
    names = '{ ' + ', '.join(f'[{json.dumps(d["description"])}] = true' for d in config['landscape']) + ' }'
    rules = []
    for display in config['landscape']:
        rules.append('  hl.monitor({ output = %s, mode = %s, position = string.format("%%dx%%d", %d - dx, %d - dy), '
                     'scale = %s, transform = 0 })' % (json.dumps('desc:' + display['description']), json.dumps(display['mode']),
                                                       display['x'], display['y'], json.dumps(display['scale'])))
    return (f'{MARKER}: landscape while streaming, removed when the stream ends.\n'
            f'if os.getenv("HYPRLAND_INSTANCE_SIGNATURE") == {json.dumps(signature)} then\n'
            f'  local landscape, others = {names}, false\n'
            '  for _, m in ipairs(hl.get_monitors()) do\n'
            '    if not landscape[m.description] and m.name ~= "SUNSHINE-VIRTUAL-1080P" and not m.disabled then others = true end\n'
            '  end\n'
            f'  local dx, dy = 0, 0\n'
            f'  if not others then dx, dy = {first["x"]}, {first["y"]} end\n'
            + '\n'.join(rules) + '\nend\n')


# -- Connector lookup (Sunshine captures by connector name, which can change)

def edid_identity(edid):
    """Return the model name and possible serials Hyprland shows for this EDID."""
    if len(edid) < 128 or edid[:8] != b'\x00\xff\xff\xff\xff\xff\xff\x00':
        return None
    name, serials = '', [f'0x{struct.unpack("<I", edid[12:16])[0]:08X}']
    for offset in range(54, 126, 18):
        block = edid[offset:offset+18]
        if block[:3] != b'\x00\x00\x00':
            continue
        text = block[5:].split(b'\n')[0].decode('ascii', 'replace').strip()
        if block[3] == 0xFC:
            name = text
        elif block[3] == 0xFF and text:
            serials.insert(0, text)
    return name, serials


def connector_for(description, drm_root=None):
    root = Path(drm_root or os.environ.get('ARCH_SETUPS_DRM_ROOT', '/sys/class/drm'))
    matches = []
    for path in sorted(root.glob('card*-*')):
        try:
            if (path/'status').read_text().strip() != 'connected':
                continue
            identity = edid_identity((path/'edid').read_bytes())
        except OSError:
            continue
        if not identity or not identity[0]:
            continue
        name, serials = identity
        if any(description.lower().endswith(f' {name} {serial}'.lower()) for serial in serials):
            matches.append(path.name.split('-', 1)[1])
    return matches[0] if len(matches) == 1 else None


def output_name(record=False):
    config = load_config()
    name = connector_for(config['capture']) if config else None
    if record and name:
        recorded_output_path().write_text(name + '\n')
    return name


# -- Hyprland

def hypr_signature():
    """The session's signature; services may lack it in their environment."""
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    if signature:
        return signature
    sessions = [p for p in (runtime_dir()/'hypr').glob('*') if (p/'.socket.sock').exists()]
    return max(sessions, key=lambda p: p.stat().st_mtime).name if sessions else None


def hyprctl(signature, *args):
    env = dict(os.environ, HYPRLAND_INSTANCE_SIGNATURE=signature)
    return subprocess.run(['hyprctl', *args], env=env, capture_output=True, text=True, timeout=10, check=True).stdout


def monitors(signature):
    return json.loads(hyprctl(signature, 'monitors', '-j'))


def wait_for(signature, config, landscape):
    wanted = {d['description'] for d in config['landscape']}
    for _ in range(25):
        rotated = {m['description']: m['transform'] for m in monitors(signature) if m['description'] in wanted}
        if rotated and all((t == 0) == landscape for t in rotated.values()):
            return True
        time.sleep(0.2)
    return False


def owned_toggle(path):
    try:
        return path.read_text().startswith(MARKER)
    except OSError:
        return False


class Lock:
    def __enter__(self):
        self.file = open(runtime_dir()/'arch-sunshine-stream-display.lock', 'w')
        fcntl.flock(self.file, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        self.file.close()


def prepare():
    """Rotate to landscape. Never fails: a failing prep command aborts the stream."""
    try:
        config, signature = load_config(), hypr_signature()
        if not config or not signature:
            log('no stream display policy or Hyprland session; leaving monitors as they are')
            return
        path = toggle_path()
        with Lock():
            if path.exists() and not owned_toggle(path):
                log(f'refusing to replace unowned {path}')
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            text = toggle_lua(config, signature)
            if not path.exists() or path.read_text() != text:
                path.write_text(text)
                hyprctl(signature, 'reload')
            log('landscape applied' if wait_for(signature, config, True) else 'landscape not confirmed')
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        log(f'could not apply landscape: {error}')


def finish():
    """Return to the normal layout if this helper rotated it."""
    path = toggle_path()
    with Lock():
        if not owned_toggle(path):
            return False
        path.unlink()
        signature = hypr_signature()
        try:
            if signature:
                hyprctl(signature, 'reload')
                config = load_config()
                if config and not wait_for(signature, config, False):
                    log('portrait not confirmed')
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            # A session that ended needs no reload; its next start reads no toggle.
            log(f'reload after restore failed: {error}')
        log('normal layout restored')
        return True


# -- Watching the host

def app_running():
    try:
        with urllib.request.urlopen('http://127.0.0.1:47989/serverinfo', timeout=5) as response:
            match = re.search(rb'<currentgame>(\d+)</currentgame>', response.read())
        return bool(match and int(match[1]))
    except OSError:
        return False


def restart_host(reason):
    log(f'restarting Sunshine: {reason}')
    subprocess.run(['systemctl', '--user', 'restart', UNIT], timeout=60, check=False)


class Watcher:
    """Turns host log lines and time into restore decisions."""

    def __init__(self, grace=GRACE_SECONDS, clock=time.monotonic):
        self.grace, self.clock = grace, clock
        self.connected = False
        self.deadline = None

    def line(self, text):
        if 'CLIENT CONNECTED' in text:
            self.connected, self.deadline = True, None
        elif 'CLIENT DISCONNECTED' in text:
            self.connected, self.deadline = False, self.clock() + self.grace

    def expired(self):
        if self.deadline is not None and not self.connected and self.clock() >= self.deadline:
            self.deadline = None
            return True
        return False


def last_client_line():
    out = subprocess.run(['journalctl', '--user', '-u', UNIT, '-o', 'cat', '-n', '2000', '--no-pager'],
                         capture_output=True, text=True, timeout=30).stdout
    lines = [line for line in out.splitlines() if 'CLIENT ' in line]
    return lines[-1] if lines else ''


def on_grace_expired():
    finish()
    # A resumed app keeps the layout Sunshine measured when it started, and only a
    # launch runs `prepare`, so end the app for the next connection.
    if load_config() and app_running():
        restart_host('the client left and its app would resume without landscape')


def check_connector(watcher):
    if watcher.connected or watcher.deadline is not None:
        return
    try:
        started = recorded_output_path().read_text().strip()
    except OSError:
        return
    current = output_name()
    if current and started and current != started:
        restart_host(f'the streamed monitor moved from {started} to {current}')


def watch():
    watcher = Watcher()
    watcher.line(last_client_line())
    if not watcher.connected:
        # The client may have left while this service was not running.
        watcher.deadline = watcher.clock() + watcher.grace
    follow = subprocess.Popen(['journalctl', '--user', '-u', UNIT, '-o', 'cat', '-f', '-n', '0'],
                              stdout=subprocess.PIPE, text=True)
    next_check = time.monotonic() + IDLE_CHECK_SECONDS
    while True:
        ready, _, _ = select.select([follow.stdout], [], [], 5)
        if ready:
            text = follow.stdout.readline()
            if not text:
                raise SystemExit('journal follower ended')
            watcher.line(text)
        if watcher.expired():
            on_grace_expired()
        if time.monotonic() >= next_check:
            next_check = time.monotonic() + IDLE_CHECK_SECONDS
            check_connector(watcher)


def configure(layout_path):
    # Validate with the same rules as every other monitor policy consumer.
    spec = importlib.util.spec_from_file_location(
        'monitor_layout', Path(__file__).resolve().parents[1]/'hypr/scripts/monitor-layout.py')
    layout = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(layout)
    rendered = render_config(layout.load_config(layout_path))
    return json.dumps(rendered, indent=2) + '\n' if rendered else ''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('command', choices=['prepare', 'finish', 'watch', 'output-name', 'configure'])
    parser.add_argument('--record', action='store_true', help='Remember the name for the connector check.')
    parser.add_argument('--layout', type=Path, help='Monitor policy for configure.')
    args = parser.parse_args(argv)
    if args.command == 'prepare':
        prepare()
    elif args.command == 'finish':
        try:
            finish()
        except OSError as error:
            log(f'could not restore: {error}')
    elif args.command == 'output-name':
        name = output_name(record=args.record)
        if not name:
            return 1
        print(name)
    elif args.command == 'configure':
        sys.stdout.write(configure(args.layout))
    else:
        watch()
    return 0


if __name__ == '__main__':
    sys.exit(main())
