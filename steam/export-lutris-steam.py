#!/usr/bin/env python3
"""Opt-in Lutris -> Steam library and desktop launcher migration. Default: preview."""
import argparse
import binascii
import copy
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import sqlite3
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

import yaml
from lutris import settings
from lutris.util.steam import vdf
from lutris.util.steam.config import get_active_steamid64

ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home()
STATE = Path(os.environ.get('XDG_STATE_HOME', HOME / '.local/state')) / 'arch-setups/steam-library'
PREFERENCE = Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config')) / 'omarchy/steam-library.json'
NAMES = {'ts4_x64exe': 'The Sims 4', 'hs2': 'Honey Select 2 DX', 'ks': 'Koikatsu Sunshine'}
POLICY = json.loads((ROOT / 'steam/metadata-policy.json').read_text())
LAUNCHER_POLICY = json.loads((ROOT / 'steam/launcher-policy.json').read_text())


def excluded(game):
    return game['slug'] in POLICY['excludedSlugs']


def display_name(game):
    return game['name'] if excluded(game) else NAMES.get(game['slug'], game['name'])


def signed(value):
    value &= 0xffffffff
    return value if value < 0x80000000 else value - 0x100000000


def steam_uri(appid, native=False):
    value = int(appid) if native else ((int(appid) & 0xffffffff) << 32) | 0x02000000
    return f'steam://rungameid/{value}'


def process_running(name):
    for p in Path('/proc').glob('[0-9]*/comm'):
        try:
            if p.read_text().strip() == name:
                return True
            if name == 'lutris':
                args = p.with_name('cmdline').read_bytes().split(b'\0')[:2]
                if any(Path(a.decode(errors='replace')).name == 'lutris' for a in args):
                    return True
        except OSError:
            pass
    return False


def field(shortcut, key, default=''):
    return next((v for k, v in shortcut.items() if k.lower() == key.lower()), default)


def put(shortcut, key, value):
    for k in list(shortcut):
        if k.lower() == key.lower():
            shortcut[k] = value
            return
    shortcut[key] = value


def match_shortcut(game, shortcuts):
    legacy = re.search(r'^steam-shortcut-(\d+)(?:-|$)', game['configpath'] or '')
    matches = []
    for key, shortcut in shortcuts.items():
        aid = int(field(shortcut, 'appid', 0)) & 0xffffffff
        uri = f"lutris:rungameid/{game['id']}"
        target = field(shortcut, 'Exe').strip("'\"")
        same_exe = bool(game.get('_exe') and target and target != '/usr/bin/lutris' and
                        Path(target).expanduser().resolve() == Path(game['_exe']).expanduser().resolve())
        if ((legacy and aid == int(legacy[1])) or same_exe or
                field(shortcut, 'LaunchOptions').strip("'\"") == uri):
            matches.append(key)
    if len(matches) > 1:
        raise ValueError('Ambiguous duplicate shortcuts for ' + game['name'])
    return matches[0] if matches else None


def merge_game(game, shortcuts, icon):
    key = match_shortcut(game, shortcuts)
    name = display_name(game)
    if key is None:
        # Lutris's native export convention; existing IDs are NEVER recomputed.
        aid = (binascii.crc32(('"/usr/bin/lutris"' + name).encode()) | 0x80000000)
        if any((int(field(s, 'appid', 0)) & 0xffffffff) == aid for s in shortcuts.values()):
            raise ValueError('New shortcut ID collision for ' + name)
        key = str(max([int(k) for k in shortcuts] + [-1]) + 1)
        shortcuts[key] = dict(appid=signed(aid), IsHidden=0, AllowDesktopConfig=1,
                              AllowOverlay=1, OpenVR=0, Devkit=0,
                              DevkitGameID='', DevkitOverrideAppID=0, LastPlayTime=0, tags={})
    shortcut = shortcuts[key]
    put(shortcut, 'AppName', name)
    put(shortcut, 'Exe', '"/usr/bin/lutris"')
    put(shortcut, 'StartDir', '"' + str(HOME) + '"')
    put(shortcut, 'LaunchOptions', f"lutris:rungameid/{game['id']}")
    put(shortcut, 'IsHidden', 0)
    if excluded(game):
        put(shortcut, 'icon', '')
    elif icon:
        put(shortcut, 'icon', str(icon))
    tags = shortcut.setdefault('tags', {})
    if excluded(game):
        for tag in list(tags):
            if tags[tag] == 'Lutris backend':
                del tags[tag]
    elif 'Lutris backend' not in tags.values():
        tags[str(max([int(k) for k in tags] + [-1]) + 1)] = 'Lutris backend'
    return int(field(shortcut, 'appid')) & 0xffffffff


def remove_compat(config, ids):
    # Only the chosen shortcuts now targeting a native Linux executable.
    try:
        mapping = config['InstallConfigStore']['Software']['Valve']['Steam']['CompatToolMapping']
    except KeyError:
        return
    for key in list(mapping):
        if key.isdigit() and int(key) in ids:
            del mapping[key]


def desktop(name, uri, icon):
    if any('\n' in str(v) or '\r' in str(v) for v in (name, uri, icon)):
        raise ValueError('Invalid desktop field')
    return ('[Desktop Entry]\nType=Application\nName=' + name.replace('\\', '\\\\') +
            '\nExec=/usr/bin/steam ' + uri + '\nIcon=' + str(icon).replace('\\', '\\\\') +
            '\nTerminal=false\nCategories=Game;\nX-ArchSetups-SteamLibrary=true\n')


def hide_desktop(text, hidden=True):
    sections = re.split(r'(?m)(?=^\[)', text)
    for i, s in enumerate(sections):
        if s.startswith('[Desktop Entry]\n'):
            if re.search(r'(?m)^Hidden=', s):
                s = re.sub(r'(?m)^Hidden=.*$', 'Hidden=' + str(hidden).lower(), s)
            elif hidden:
                s = s.rstrip() + '\nHidden=true\n\n'
            sections[i] = s
    return ''.join(sections)


def desktop_args(text):
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(text)
        return shlex.split(parser.get('Desktop Entry', 'Exec', fallback=''))
    except (ValueError, configparser.Error):
        return []


def desktop_native_id(text):
    args = desktop_args(text)
    if len(args) == 2 and Path(args[0]).name == 'steam':
        match = re.fullmatch(r'steam://rungameid/(\d+)', args[1])
        if match:
            return int(match[1])
    return None


def reconcile_launcher_policy(writer, applications):
    show = LAUNCHER_POLICY['showLutris']
    for name in ('net.lutris.Lutris.desktop', 'net.lutris.Lutris1.desktop'):
        target = applications / name
        source = target if target.exists() else Path('/usr/share/applications') / name
        if not source.exists():
            continue
        text = hide_desktop(source.read_text(), hidden=not show)
        if show and name == 'net.lutris.Lutris.desktop':
            text = re.sub(r'(?m)^NoDisplay=true$', 'NoDisplay=false', text)
        # Preserve the file-handler desktop's NoDisplay=true: only one Lutris app.
        writer.write(target, text.encode())
    for aid in LAUNCHER_POLICY['deduplicateNativeSteamIds']:
        canonical = applications / f'steam-library-{aid}.desktop'
        if not canonical.exists() or canonical.is_symlink():
            continue  # Never hide the only working launcher.
        text = canonical.read_text()
        if 'X-ArchSetups-SteamLibrary=true' not in text or desktop_native_id(text) != aid:
            continue
        writer.write(canonical, hide_desktop(text, hidden=False).encode())
        for target in applications.glob('*.desktop'):
            if target == canonical or target.is_symlink() or not target.is_file():
                continue
            text = target.read_text()
            if desktop_native_id(text) == aid:
                writer.write(target, hide_desktop(text).encode())
    if LAUNCHER_POLICY['removeAoEAccountLaunchers']:
        standard_exists = any(desktop_native_id(p.read_text()) == 813780
                              for p in applications.glob('*.desktop') if p.is_file() and not p.is_symlink())
        if standard_exists:
            for target in applications.glob('aoe2-*.desktop'):
                if target.is_symlink() or not target.is_file():
                    continue
                args = desktop_args(target.read_text())
                if len(args) == 2 and Path(args[0]).name == 'launch-aoe2-account':
                    writer.remove(target)


class Writer:
    def __init__(self):
        self.backup = None
        self.changes = 0

    def write(self, path, content):
        path = Path(path)
        if path.is_symlink():
            raise ValueError('Refusing symlink destination: ' + str(path))
        old = path.read_bytes() if path.exists() else None
        if old == content:
            return
        if self.backup is None:
            STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.backup = Path(tempfile.mkdtemp(prefix='backup-', dir=STATE))
        record = self.backup / str(path).lstrip('/')
        record.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if old is not None:
            shutil.copy2(path, record)
            record.chmod(0o600)
        with (self.backup / 'changes.jsonl').open('a') as stream:
            stream.write(json.dumps({'path': str(path), 'existed': old is not None}) + '\n')
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix='.steam-library-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content)
            if (path.read_bytes() if path.exists() else None) != old:
                raise RuntimeError('File changed during migration: ' + str(path))
            os.chmod(tmp, path.stat().st_mode & 0o777 if path.exists() else 0o600)
            os.replace(tmp, path)
        finally:
            Path(tmp).unlink(missing_ok=True)
        self.changes += 1

    def remove(self, path):
        path = Path(path)
        if not path.exists():
            return
        if path.is_symlink():
            raise ValueError('Refusing symlink removal: ' + str(path))
        original = path.read_bytes()
        if self.backup is None:
            STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.backup = Path(tempfile.mkdtemp(prefix='backup-', dir=STATE))
        record = self.backup / str(path).lstrip('/')
        record.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copy2(path, record)
        record.chmod(0o600)
        with (self.backup / 'changes.jsonl').open('a') as stream:
            stream.write(json.dumps({'path': str(path), 'existed': True, 'removed': True}) + '\n')
        if path.read_bytes() != original:
            raise RuntimeError('File changed during removal: ' + str(path))
        path.unlink()
        self.changes += 1


def remove_owned_art(writer, aid, grid, owned):
    pattern = re.compile(str(aid) + r'(?:p|_hero|_logo)?\.(?:png|jpg|jpeg)$')
    for raw, digest in list(owned.items()):
        p = Path(raw)
        if p.parent == grid and pattern.fullmatch(p.name):
            if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() != digest:
                print('Preserving user-modified artwork: ' + p.name)
                continue
            writer.remove(p)
            del owned[raw]


def image_bytes(url):
    # Catalog/public Steam artwork only. No API credentials, scripts or arbitrary hosts.
    if not re.match(r'https://(?:shared\.akamai\.steamstatic\.com|cdn\.akamai\.steamstatic\.com|shared\.fastly\.steamstatic\.com)/', url):
        raise ValueError('Unapproved artwork source')
    with urllib.request.urlopen(url, timeout=12) as response:
        data = response.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024 or not (data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith(b'\xff\xd8')):
        raise ValueError('Artwork is not a bounded PNG/JPEG image')
    return data


def artwork(writer, game, aid, grid, catalog, owned):
    meta = catalog.get(game['slug'], {})
    sources = meta.get('artwork', {})
    store = re.search(r'/app/(\d+)', meta.get('store_url', ''))
    storeid = store[1] if store else ('1222670' if game['slug'] == 'ts4_x64exe' else None)
    base = f'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{storeid}'
    candidates = {
        'cover': (str(aid) + 'p', HOME / '.local/share/lutris/coverart' / (game['slug'] + '.jpg'), sources.get('cover') or (base + '/library_600x900_2x.jpg' if storeid else None)),
        'banner': (str(aid), HOME / '.local/share/lutris/banners' / (game['slug'] + '.jpg'), sources.get('banner') or (base + '/header.jpg' if storeid else None)),
        'hero': (str(aid) + '_hero', None, base + '/library_hero.jpg' if storeid else None),
        'logo': (str(aid) + '_logo', None, base + '/logo.png' if storeid else None),
    }
    missing = []
    for kind, (stem, local, url) in candidates.items():
        destinations = [grid / (stem + ext) for ext in ('.png', '.jpg', '.jpeg')]
        existing = [p for p in destinations if p.exists()]
        if existing:
            continue  # Never replace existing custom artwork.
        try:
            data = local.read_bytes() if local and local.is_file() else image_bytes(url) if url else None
            if data is None:
                missing.append(kind)
                continue
            ext = '.png' if data.startswith(b'\x89PNG') else '.jpg'
            target = grid / (stem + ext)
            writer.write(target, data)
            owned[str(target)] = hashlib.sha256(data).hexdigest()
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            missing.append(kind)
    if missing:
        print('Artwork unavailable for ' + NAMES.get(game['slug'], game['name']) + ': ' + ', '.join(missing))


def load_library(removed_slugs=()):
    db = sqlite3.connect('file:' + settings.DB_PATH + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        query = 'SELECT id,name,slug,runner,configpath FROM games WHERE installed=1'
        if removed_slugs:
            query += ' OR slug IN (' + ','.join('?' for _ in removed_slugs) + ')'
        return [dict(r) for r in db.execute(query + ' ORDER BY id', tuple(removed_slugs))]
    finally:
        db.close()


def select_account(steam, explicit):
    if explicit:
        if not explicit.isdigit():
            raise ValueError('Account must be a numeric Steam userdata ID')
        account = explicit
    else:
        active = get_active_steamid64()
        if not active:
            raise ValueError('Cannot identify active Steam account; pass --account USERDATA_ID')
        account = str(int(active) - 76561197960265728)
    if not (steam / 'userdata' / account / 'config').is_dir():
        raise ValueError('Selected Steam userdata directory does not exist')
    return account


def migrate(args):
    preference = json.loads(PREFERENCE.read_text()) if PREFERENCE.exists() else {}
    from gaming_profile import load_selection
    if args.if_enabled and not (preference.get('enabled') or load_selection().get('exportSteam')):
        return
    if getattr(args, 'launchers_only', False):
        if not args.apply:
            raise ValueError('--launchers-only requires --apply; it never edits Steam library files')
        applications = Path(os.environ.get('XDG_DATA_HOME', HOME / '.local/share')) / 'applications'
        writer = Writer()
        reconcile_launcher_policy(writer, applications)
        if shutil.which('update-desktop-database'):
            subprocess.run(['update-desktop-database', str(applications)], check=True)
        print(f'Launcher policy: {writer.changes} changes. Backups: {writer.backup or "none (already current)"}')
        return
    steam = HOME / '.local/share/Steam'
    account = select_account(steam, args.account or preference.get('account'))
    base = steam / 'userdata' / account / 'config'
    path = base / 'shortcuts.vdf'
    original = path.read_bytes() if path.exists() else None
    data = vdf.binary_loads(original) if original else {'shortcuts': {}}
    shortcuts = data.setdefault('shortcuts', {})
    games = load_library(POLICY['removedSlugs'])
    catalog = {g['slug']: g for g in json.loads((ROOT / 'steam/profile/games.json').read_text())['games']}
    exported = []
    native = []
    removed = []
    for game in games:
        if game['slug'] in POLICY['removedSlugs']:
            key = match_shortcut(game, shortcuts)
            if key is not None:
                aid = int(field(shortcuts[key], 'appid')) & 0xffffffff
                removed.append((game, aid))
                del shortcuts[key]
                print('Remove uninstalled entry: ' + game['name'])
            continue
        cfgpath = Path(settings.GAME_CONFIG_DIR) / (game['configpath'] + '.yml')
        config = yaml.safe_load(cfgpath.read_text()) or {}
        if game['runner'] == 'steam':
            aid = config.get('game', {}).get('appid')
            if not str(aid).isdigit():
                raise ValueError('Invalid native Steam ID for ' + game['name'])
            native.append((game, int(aid)))
            continue
        exe = Path(config.get('game', {}).get('exe', ''))
        if not exe.is_absolute():
            exe = Path(config.get('game', {}).get('prefix', '')) / exe
        game['_exe'] = str(exe)
        icon = HOME / '.local/share/icons/hicolor/128x128/apps' / ('lutris_' + game['slug'] + '.png')
        if excluded(game):
            icon = ''
        elif not icon.exists():
            icon = 'steam'
        aid = merge_game(game, shortcuts, icon)
        exported.append((game, aid, icon))
        print(f"{display_name(game)}: Steam shortcut {aid}, Lutris ID {game['id']}" +
              ('' if exe.exists() else ' [source executable unavailable]'))
    print(f'Account {account}: {len(exported)} non-Steam entries, {len(native)} native Steam entries')
    if not args.apply:
        print('Preview only; close Steam and Lutris, then use --apply --enable to persist this preference.')
        return
    if process_running('steam') or process_running('lutris'):
        raise RuntimeError('Close Steam and Lutris before applying. No files changed.')
    if (path.read_bytes() if path.exists() else None) != original:
        raise RuntimeError('Steam shortcuts changed while planning')
    writer = Writer()
    configpath = steam / 'config/config.vdf'
    config_bytes = configpath.read_bytes()
    config = vdf.loads(config_bytes.decode())
    original_config = copy.deepcopy(config)
    ids = {aid for _, aid, _ in exported} | {aid for _, aid in removed}
    remove_compat(config, ids)
    applications = Path(os.environ.get('XDG_DATA_HOME', HOME / '.local/share')) / 'applications'
    ownership = STATE / 'ownership.json'
    owned = json.loads(ownership.read_text()) if ownership.exists() else {}
    for game, aid in removed:
        remove_owned_art(writer, aid, base / 'grid', owned)
        target = applications / f'steam-library-{aid}.desktop'
        if target.exists():
            if 'X-ArchSetups-SteamLibrary=true' not in target.read_text():
                raise ValueError('Foreign removed-game launcher: ' + str(target))
            writer.remove(target)
    for game, aid, _ in exported:
        if excluded(game):
            remove_owned_art(writer, aid, base / 'grid', owned)
        elif (args.artwork or preference.get('artwork')) and not getattr(args, 'no_artwork_downloads', False):
            artwork(writer, game, aid, base / 'grid', catalog, owned)
    # Reuse downloaded art as an icon where Lutris had none; do not invent branding.
    enriched = []
    for game, aid, icon in exported:
        if icon == 'steam' and not excluded(game):
            choices = [base / 'grid' / (str(aid) + suffix) for suffix in ('.png', '.jpg', 'p.png', 'p.jpg')]
            icon = next((p for p in choices if p.is_file()), icon)
            if icon != 'steam':
                put(shortcuts[match_shortcut(game, shortcuts)], 'icon', str(icon))
        enriched.append((game, aid, icon))
    exported = enriched
    binary = vdf.binary_dumps(data)
    if vdf.binary_loads(binary) != data:
        raise ValueError('Shortcut binary round-trip failed')
    desktops = {}
    for game, aid, icon in exported:
        desktops[f'steam-library-{aid}.desktop'] = desktop(display_name(game), steam_uri(aid), icon or 'steam')
    for game, aid in native:
        icon = HOME / '.local/share/icons/hicolor/128x128/apps' / ('lutris_' + game['slug'] + '.png')
        desktops[f'steam-library-{aid}.desktop'] = desktop(game['name'], steam_uri(aid, native=True), icon if icon.is_file() else 'steam')
    # Preflight all launcher collisions before editing Steam's library.
    for filename in desktops:
        target = applications / filename
        if target.exists() and 'X-ArchSetups-SteamLibrary=true' not in target.read_text():
            raise ValueError('Foreign game launcher: ' + str(target))
        if target.is_symlink():
            raise ValueError('Symlink launcher: ' + str(target))
    if configpath.read_bytes() != config_bytes:
        raise RuntimeError('Steam configuration changed while planning')
    writer.write(path, binary)
    if config != original_config:
        writer.write(configpath, vdf.dumps(config, pretty=True).encode())
    for filename, text in desktops.items():
        target = applications / filename
        writer.write(target, text.encode())
        # Desktop entries must be readable to the session launcher.
        target.chmod(0o644)
    for p in applications.glob('lutris-*.desktop'):
        text = p.read_text()
        if re.search(r'(?m)^Exec=(?:/usr/bin/)?lutris lutris:rungameid/\d+\s*$', text):
            writer.write(p, hide_desktop(text).encode())
    reconcile_launcher_policy(writer, applications)
    # Existing Omarchy wheel entries incorrectly used 32-bit non-Steam IDs.
    wheel = HOME / '.config/omarchy/extensions/gamepad-wheel.json'
    if wheel.exists():
        menu = json.loads(wheel.read_text())
        old = copy.deepcopy(menu)
        for entry in menu.values():
            if not isinstance(entry, dict):
                continue
            match = re.fullmatch(r'steam steam://rungameid/(\d+)', entry.get('action', ''))
            if match and int(match[1]) in ids:
                entry['action'] = 'steam ' + steam_uri(match[1])
        if menu != old:
            writer.write(wheel, (json.dumps(menu, indent=2) + '\n').encode())
    writer.write(ownership, (json.dumps(owned, indent=2, sort_keys=True) + '\n').encode())
    if args.enable:
        writer.write(PREFERENCE, (json.dumps(dict(enabled=True, account=account,
                     artwork=args.artwork or preference.get('artwork', False)), indent=2) + '\n').encode())
    if shutil.which('update-desktop-database'):
        subprocess.run(['update-desktop-database', str(applications)], check=True)
    print(f'Applied {writer.changes} changes. Private backups: {writer.backup or "none (already current)"}')
    print('Lutris remains installed as the launch backend; prefixes, runners, saves and YAML settings were not changed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--enable', action='store_true')
    parser.add_argument('--if-enabled', action='store_true')
    parser.add_argument('--artwork', action='store_true')
    parser.add_argument('--account')
    parser.add_argument('--no-artwork-downloads', action='store_true', help='Apply metadata policy without fetching more artwork')
    parser.add_argument('--launchers-only', action='store_true', help='Reconcile local app visibility/duplicates without editing Steam or requiring it closed')
    args = parser.parse_args()
    migrate(args)


if __name__ == '__main__':
    main()
