#!/usr/bin/env python3
"""Restore the personal gaming profile without storing games, sessions or saves."""
import argparse
import copy
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

sys.dont_write_bytecode = True  # The default command is a strictly read-only plan.
import yaml
from gaming_profile import load_selection

PROFILE = Path(__file__).resolve().parent / 'profile'


def expand(value, home):
    if isinstance(value, str):
        return value.replace('${HOME}', str(home))
    if isinstance(value, dict):
        return {k: expand(v, home) for k, v in value.items()}
    if isinstance(value, list):
        return [expand(v, home) for v in value]
    return value


def shortcut_ids(profile):
    return {g['shortcut_id'] for g in profile['games'] if g.get('shortcut_id')} | set(profile['retired_shortcuts'])


def merge_config(current, managed, previous=None):
    result = copy.deepcopy(current)
    def prune(target, desired, owned):
        for key, old in owned.items():
            if key not in desired:
                if key in target and target[key] == old:
                    del target[key]
            elif isinstance(old, dict) and isinstance(desired[key], dict) and isinstance(target.get(key), dict):
                prune(target[key], desired[key], old)
    # Remove only still-owned values omitted by the new selection. Otherwise a
    # previous HDR wrapper/env would survive hdr:false forever through merging.
    prune(result, managed, previous or {})
    for section, values in managed.items():
        target = result.setdefault(section, {})
        for key, value in values.items():
            if isinstance(value, dict):
                target.setdefault(key, {}).update(value)
            else:
                target[key] = value
    for obsolete in ('appid', 'steamless_binary', 'run_without_steam'):
        result.get('game', {}).pop(obsolete, None)
    return result


def configured_ini(source, vulkan=False):
    overrides = {'OverlayMenu': 'true', 'UseHQFont': 'false', 'LogToFile': 'true',
                 'LogLevel': '2', 'Fsr4EnableWatermark': 'true'}
    if vulkan:
        overrides.update(VulkanUpscaler='ffx', UseFsr2VulkanInputs='true')
    else:
        overrides.update(Dx12Upscaler='ffx', Fsr4ForceEnableInt8='true')
    for key, value in overrides.items():
        source, count = re.subn(r'^' + key + r'=.*$', key + '=' + value, source, flags=re.M)
        if count != 1:
            raise ValueError(f'Expected one {key} setting')
    source, count = re.subn(r'^ShortcutKey=auto$', 'ShortcutKey=0x08', source, flags=re.M)
    if count != 1:
        raise ValueError('Expected one overlay key')
    return source


def setup_4k(raw, resolution=(3840, 2160)):
    encoding = 'utf-16' if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig'
    text = raw.decode(encoding)
    ET.fromstring(raw)
    for tag, value in [('Width', str(resolution[0])), ('Height', str(resolution[1])), ('FullScreen', 'true')]:
        text, count = re.subn(fr'<{tag}>.*?</{tag}>', f'<{tag}>{value}</{tag}>', text)
        if count != 1:
            raise ValueError(f'Unexpected setup.xml: {tag}')
    return text.encode(encoding)


def engine_display_settings(raw, values):
    """Edit only Halo's engine section, preserving its encoding and line endings."""
    bom, encoding = b'', 'utf-8'
    for signature, codec in ((b'\xff\xfe', 'utf-16-le'), (b'\xfe\xff', 'utf-16-be'), (b'\xef\xbb\xbf', 'utf-8')):
        if raw.startswith(signature):
            bom, encoding = signature, codec
            break
    text = raw[len(bom):].decode(encoding)
    newline = '\r\n' if '\r\n' in text else '\n'
    section = '[/Script/Meteorite.MeteoriteGameUserSettings]'
    headers = list(re.finditer(r'(?m)^' + re.escape(section) + r'[ \t]*\r?$', text))
    if len(headers) != 1:
        raise ValueError('Expected one Meteorite game-settings section; original INI was not changed.')
    start = headers[0].end()
    following = re.search(r'(?m)^\[', text[start:])
    end = start + following.start() if following else len(text)
    body = text[start:end]
    for key, value in values.items():
        pattern = r'(?m)^' + re.escape(key) + r'=[^\r\n]*'
        if len(re.findall(pattern, body)) > 1:
            raise ValueError('Ambiguous game setting: ' + key)
        if re.search(pattern, body):
            body = re.sub(pattern, lambda _: key + '=' + value, body)
        else:
            if not body.endswith('\n'):
                body += newline
            body += key + '=' + value + newline
    return bom + (text[:start] + body + text[end:]).encode(encoding)


def desktop(name, command, icon):
    if any('\n' in v or '\r' in v for v in (name, command, icon)):
        raise ValueError('Desktop fields must be single-line')
    return (f'[Desktop Entry]\nName={name}\nExec={command}\nIcon={icon}\n'
            'Terminal=false\nType=Application\nCategories=Game;\nKeywords=Lutris;\n')


class Installer:
    def __init__(self, home):
        self.home = home
        self.state_home = Path(os.environ.get('XDG_STATE_HOME', str(home / '.local/state'))) if home == Path.home() else home / '.local/state'
        self.data_home = Path(os.environ.get('XDG_DATA_HOME', str(home / '.local/share'))) if home == Path.home() else home / '.local/share'
        self.backup = self.state_home / 'arch-setups/backups' / ('gaming-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        self.changed = 0

    def prepare_backup(self):
        self.backup.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.backup.chmod(0o700)

    def save(self, path, payload, mode=None):
        path = Path(path)
        if path.is_symlink():
            raise ValueError('Refusing symlinked managed file: ' + str(path))
        if path.exists() and path.read_bytes() == payload:
            if mode is not None and path.stat().st_mode & 0o777 != mode:
                path.chmod(mode)
                self.changed += 1
            return False
        if path.exists():
            # Relative path preserves names across multiple game directories.
            self.prepare_backup()
            dest = self.backup / 'files' / str(path).lstrip('/')
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copy2(path, dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix='.arch-gaming-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(payload)
            os.chmod(tmp, mode if mode is not None else (path.stat().st_mode & 0o777 if path.exists() else 0o644))
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        self.changed += 1
        return True

    def link(self, path, target):
        path, target = Path(path), Path(target)
        if path.is_symlink() and path.readlink() == target:
            return
        if path.exists() or path.is_symlink():
            print(f'Preserved conflicting local path: {path}; expected link to {target}')
            return
        if not target.exists():
            print(f'Skipped unavailable symlink target: {target}')
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target)
        self.changed += 1

    def remove(self, path):
        """Archive an explicitly retired desktop entry, not user game data."""
        path = Path(path)
        if path.exists() or path.is_symlink():
            self.prepare_backup()
            dest = self.backup / 'removed' / path.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), dest)
            self.changed += 1

    def asset(self, asset):
        path = self.home / '.cache/arch-setups/gaming' / asset['name']
        def valid():
            return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == asset['sha256']
        if not valid():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp = tempfile.mkstemp(dir=path.parent)
            os.close(fd)
            try:
                urllib.request.urlretrieve(asset['url'], temp)
                if hashlib.sha256(Path(temp).read_bytes()).hexdigest() != asset['sha256']:
                    raise ValueError('SHA256 mismatch: ' + asset['name'])
                os.replace(temp, path)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
        return path

    def upscaler(self, game, assets):
        kind = game['upscaler']
        target = Path(game['config']['game']['exe']).parent.resolve()
        record = self.state_home / 'arch-setups/mods' / (game['slug'] + '.json')
        owned = json.loads(record.read_text()) if record.exists() else {}
        payloads = {}
        with tempfile.TemporaryDirectory(prefix='arch-upscaler-') as tmp:
            stage = Path(tmp)
            base = assets[2] if kind == 'fsr4vk-043' else assets[0]
            subprocess.run(['7z', 'x', '-y', '-o' + tmp, str(self.asset(base))], check=True, stdout=subprocess.DEVNULL)
            if kind == 'fsr4vk-043':
                for source in (stage / 'OptiScaler').rglob('*'):
                    if source.is_file() and source.suffix.lower() in ('.dll', '.ini'):
                        payloads['OptiScaler/' + str(source.relative_to(stage / 'OptiScaler'))] = source.read_bytes()
                with zipfile.ZipFile(self.asset(assets[1])) as archive:
                    payloads['dxgi.dll'] = archive.read('OptiScaler.dll')
                    payloads['OptiScaler/amd_fidelityfx_upscaler_vk.dll'] = archive.read('OptiScaler/amd_fidelityfx_upscaler_vk.dll')
                ini = PROFILE / 'OptiScaler-fsr4vk-0.4.3.ini'
            else:
                for source in stage.iterdir():
                    if source.is_file() and source.suffix.lower() in ('.dll', '.ini') and source.name != 'OptiScaler.ini':
                        payloads['dxgi.dll' if source.name == 'OptiScaler.dll' else source.name] = source.read_bytes()
                ini = PROFILE / 'OptiScaler-0.9.4.ini'
            # Validate every destination before modifying any mod file. Existing
            # foreign mods need explicit per-game adoption, not just a backup.
            for name, payload in payloads.items():
                path = target / name
                if path.is_symlink() or not path.resolve().is_relative_to(target):
                    raise ValueError('Refusing symlinked mod destination: ' + str(path))
                if path.exists() and path.read_bytes() != payload:
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    if owned.get(str(path)) != digest and not game.get('allowModReplacement', False):
                        raise ValueError('Foreign/modified mod file; explicitly set allowModReplacement to adopt: ' + str(path))
            for name, payload in payloads.items():
                path = target / name
                self.save(path, payload)
                owned[str(path)] = hashlib.sha256(payload).hexdigest()
            # In-game Save Settings owns tuning after first installation.
            if not (target / 'OptiScaler.ini').exists():
                self.save(target / 'OptiScaler.ini', configured_ini(ini.read_text(), kind == 'fsr4vk-043').encode())
            self.save(record, (json.dumps(owned, indent=2) + '\n').encode(), 0o600)

    def artwork(self, game):
        from PIL import Image
        destinations = {'banner': ('banners', 'JPEG', (920, 430)), 'cover': ('coverart', 'JPEG', (600, 900)), 'icon': (None, 'PNG', (128, 128))}
        complete = True
        for kind, url in game.get('artwork', {}).items():
            folder, fmt, size = destinations[kind]
            path = (self.data_home / 'lutris' / folder / (game['slug'] + '.jpg') if folder else self.data_home / 'icons/hicolor/128x128/apps' / ('lutris_' + game['slug'] + '.png'))
            if path.exists():
                continue
            try:
                with urllib.request.urlopen(url, timeout=45) as response:
                    image = Image.open(io.BytesIO(response.read())).convert('RGB')
                image.thumbnail(size, Image.Resampling.LANCZOS)
                output = io.BytesIO()
                image.save(output, format=fmt)
                self.save(path, output.getvalue())
            except Exception as exc:
                complete = False
                print(f'Artwork unavailable for {game["name"]}: {exc}')
        return complete


def apply(profile, home, upscalers):
    if not profile['games'] and not profile.get('retired_shortcuts'):
        print('No games selected; no game files, accounts, launchers or database entries changed.')
        return
    if subprocess.run(['pgrep', '-u', str(os.getuid()), '-f', r'(^|/)(python[0-9.]* )?(/usr/bin/)?lutris( |$)'], stdout=subprocess.DEVNULL).returncode == 0:
        raise RuntimeError('Close Lutris before applying the gaming profile.')
    games = expand(profile['games'], home)
    processes = subprocess.check_output(['ps', '-u', str(os.getuid()), '-o', 'args='], text=True)
    commands = subprocess.check_output(['ps', '-u', str(os.getuid()), '-o', 'comm='], text=True).splitlines()
    for game in games:
        exe = game['config']['game']['exe']
        if exe.endswith('.exe') and (exe in processes or exe.replace('/', '\\') in processes or Path(exe).name[:15] in commands):
            raise RuntimeError('Close ' + game['name'] + ' before applying the profile.')
    installer = Installer(home)
    for path, target in expand(profile.get('symlinks', {}), home).items():
        installer.link(path.replace('${HOME}', str(home)), target)
    data_home = Path(os.environ.get('XDG_DATA_HOME', str(home / '.local/share'))) if home == Path.home() else home / '.local/share'
    config_home = Path(os.environ.get('XDG_CONFIG_HOME', str(home / '.config'))) if home == Path.home() else home / '.config'
    root = data_home / 'lutris'
    configs = (config_home / 'lutris' if (config_home / 'lutris').exists() else root) / 'games'
    db = root / 'pga.db'
    applications = data_home / 'applications'
    if home == Path.home():
        # Lutris versions support both legacy config and new data layouts,
        # and may override the database/runner directories in lutris.conf.
        from lutris import settings
        root, configs, db = Path(settings.DATA_DIR), Path(settings.GAME_CONFIG_DIR), Path(settings.DB_PATH)
    if not db.exists():
        raise RuntimeError('Initialize Lutris first (install-lutris.sh does this).')
    with closing(sqlite3.connect(db)) as con:
        con.row_factory = sqlite3.Row
        def backup_db():
            dest = installer.backup / 'pga.db'
            if not dest.exists():
                installer.prepare_backup()
                dest.parent.mkdir(parents=True, exist_ok=True)
                with closing(sqlite3.connect(dest)) as saved:
                    con.backup(saved)
        for game in games:
            exe = Path(game['config']['game']['exe'])
            if not exe.is_file():
                print(f'Skipped {game["name"]}: mount/install game first: {exe}')
                continue
            # Engine preferences exist only when the selection requests dimensions.
            if game.get('display_settings'):
                settings = Path(game['config']['game']['prefix']) / 'drive_c/users/steamuser/AppData/Local/Meteorite/Saved/Config/Windows/GameUserSettings.ini'
                if settings.is_symlink():
                    raise ValueError('Refusing symlinked game-settings INI: ' + str(settings))
                if settings.is_file():
                    installer.save(settings, engine_display_settings(settings.read_bytes(), game['display_settings']))
                else:
                    print('Launch Halo once, then rerun to apply its selected resolution/HDR settings.')
            rows = con.execute('SELECT * FROM games WHERE installer_slug=? OR slug=?', (game['key'], game['slug'])).fetchall()
            if len(rows) > 1:
                raise RuntimeError('Ambiguous Lutris entries for ' + game['name'])
            row = rows[0] if rows else None
            configpath = row['configpath'] if row else 'arch-profile-' + game['key']
            if not configpath or Path(configpath).name != configpath:
                raise ValueError('Unsafe Lutris configpath for ' + game['name'])
            path = configs / (configpath + '.yml')
            legacy = root / 'games' / (configpath + '.yml')
            source = path if path.exists() else legacy
            current = yaml.safe_load(source.read_bytes()) if source.exists() else {}
            if current is not None and not isinstance(current, dict):
                raise ValueError('Lutris YAML must be a mapping: ' + str(source))
            ownership = installer.state_home / 'arch-setups/games' / (game['slug'] + '.json')
            previous = json.loads(ownership.read_text()) if ownership.exists() else {}
            if not isinstance(previous, dict):
                raise ValueError('Invalid managed game ownership record')
            if not previous and configpath.startswith('arch-profile-'):
                catalog = json.loads((PROFILE / 'games.json').read_text())
                previous = next((item['config'] for item in catalog['games'] if item['slug'] == game['slug']), {})
            # The namespaced launcher/environment are positively identified
            # legacy owned values even before an ownership record existed.
            if not previous:
                previous = {'system': {'env': {}}}
                system = (current or {}).get('system', {})
                if system.get('prefix_command') == 'steam-gamescope-hdr':
                    previous['system']['prefix_command'] = system['prefix_command']
                for key, value in system.get('env', {}).items():
                    if key.startswith('ARCH_SETUPS_GAME_'):
                        previous['system']['env'][key] = value
            merged = merge_config(current or {}, game['config'], previous)
            if merged != current or not path.exists():
                installer.save(path, yaml.safe_dump(merged, sort_keys=False).encode())
            # A positively selected database row identifies this historical
            # misplaced file. Keep the original privately for recovery.
            if source == legacy and legacy != path and legacy.exists():
                installer.remove(legacy)
            values = dict(name=game['name'], slug=game['slug'], runner=game['runner'], executable=str(exe), directory=game['config']['game']['working_dir'], installed=1, installer_slug=game['key'], year=game['year'])
            if not row or any(row[k] != v for k, v in values.items()):
                # Backup before starting a write transaction; sqlite backup inside it can block.
                con.commit()
                backup_db()
                if row:
                    con.execute('UPDATE games SET ' + ','.join(k + '=?' for k in values) + ' WHERE id=?', (*values.values(), row['id']))
                    gid = row['id']
                else:
                    values['configpath'] = configpath
                    cur = con.execute('INSERT INTO games (' + ','.join(values) + ') VALUES (' + ','.join('?' for _ in values) + ')', tuple(values.values()))
                    gid = cur.lastrowid
                installer.changed += 1
                con.commit()
            else:
                gid = row['id']
            if game.get('setup_xml') and Path(game['setup_xml']).is_file():
                p = Path(game['setup_xml'])
                installer.save(p, setup_4k(p.read_bytes(), game.get('resolution', (3840, 2160))))
            if game.get('artwork') and installer.artwork(game):
                flags = ['has_custom_banner', 'has_custom_icon', 'has_custom_coverart_big']
                actual = con.execute('SELECT ' + ','.join(flags) + ' FROM games WHERE id=?', (gid,)).fetchone()
                if tuple(actual) != (1, 1, 1):
                    con.commit()
                    backup_db()
                    con.execute('UPDATE games SET ' + ','.join(k + '=1' for k in flags) + ' WHERE id=?', (gid,))
                    con.commit()
                    installer.changed += 1
            if game['desktop']:
                # Numeric database IDs are resolved on this machine, never copied from the old install.
                text = desktop(game['name'], f'lutris lutris:rungameid/{gid}', 'lutris_' + game['slug'])
                installer.save(applications / ('lutris-' + game['slug'] + '.desktop'), text.encode())
            if upscalers and game.get('upscaler'):
                installer.upscaler(game, profile['assets'])
            installer.save(ownership, (json.dumps(game['config'], indent=2) + '\n').encode(), 0o600)
        # Retire launch entries only. Never delete games, prefixes, saves, or Steam files here.
        for aid in profile['retired_shortcuts']:
            retired = con.execute('SELECT id,slug FROM games WHERE installer_slug=? OR configpath LIKE ?', (f'steam-shortcut-{aid}', f'steam-shortcut-{aid}-%')).fetchall()
            if retired:
                con.commit()
                backup_db()
                for row in retired:
                    con.execute('DELETE FROM games WHERE id=?', (row['id'],))
                    installer.changed += 1
                con.commit()
    if installer.changed:
        if applications.is_dir():
            subprocess.run(['update-desktop-database', str(applications)], check=True)
        print(f'Gaming profile: {installer.changed} changes. Backups: {installer.backup}')
    else:
        print('Gaming profile already installed and current.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, help='Gaming selection (default: empty gaming/selection.json)')
    parser.add_argument('--selection-summary', action='store_true')
    parser.add_argument('--apply', action='store_true', help='Apply; default is a read-only plan')
    parser.add_argument('--upscalers', action='store_true', help='Fetch SHA256-pinned third-party DLLs and install them; offline/single-player only')
    args = parser.parse_args()
    profile = load_selection(args.profile)
    if args.selection_summary:
        print(json.dumps(dict(games=len(profile['games']), importSteam=profile['importSteam'], steamHdr=profile['steamHdr'], upscalers=any(game.get('upscaler') for game in profile['games']))))
        return
    if args.apply:
        apply(profile, Path.home(), args.upscalers)
    else:
        for game in expand(profile['games'], Path.home()):
            print(game['name'], 'available' if Path(game['config']['game']['exe']).is_file() else 'missing; will skip', game.get('upscaler', ''))
        print('Read-only. Use --apply; add --upscalers to install pinned experimental DLLs.')


if __name__ == '__main__':
    main()
