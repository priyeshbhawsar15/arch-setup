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
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

import yaml

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


def merge_config(current, managed):
    result = copy.deepcopy(current)
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


def setup_4k(raw):
    encoding = 'utf-16' if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig'
    text = raw.decode(encoding)
    ET.fromstring(raw)
    for tag, value in [('Width', '3840'), ('Height', '2160'), ('FullScreen', 'true')]:
        text, count = re.subn(fr'<{tag}>.*?</{tag}>', f'<{tag}>{value}</{tag}>', text)
        if count != 1:
            raise ValueError(f'Unexpected setup.xml: {tag}')
    return text.encode(encoding)


def desktop(name, command, icon):
    if any('\n' in v or '\r' in v for v in (name, command, icon)):
        raise ValueError('Desktop fields must be single-line')
    return (f'[Desktop Entry]\nName={name}\nExec={command}\nIcon={icon}\n'
            'Terminal=false\nType=Application\nCategories=Game;\nKeywords=Lutris;\n')


class Installer:
    def __init__(self, home):
        self.home = home
        self.backup = home / '.local/state/arch-setups/backups' / ('gaming-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        self.changed = 0

    def save(self, path, payload, mode=None):
        path = Path(path)
        if path.is_symlink():
            path = path.resolve()
        if path.exists() and path.read_bytes() == payload:
            if mode is not None and path.stat().st_mode & 0o777 != mode:
                path.chmod(mode)
                self.changed += 1
            return False
        if path.exists():
            # Relative path preserves names across multiple game directories.
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
        with tempfile.TemporaryDirectory(prefix='arch-upscaler-') as tmp:
            stage = Path(tmp)
            base = assets[2] if kind == 'fsr4vk-043' else assets[0]
            subprocess.run(['7z', 'x', '-y', '-o' + tmp, str(self.asset(base))], check=True, stdout=subprocess.DEVNULL)
            if kind == 'fsr4vk-043':
                for source in (stage / 'OptiScaler').rglob('*'):
                    if source.is_file() and source.suffix.lower() in ('.dll', '.ini'):
                        self.save(target / 'OptiScaler' / source.relative_to(stage / 'OptiScaler'), source.read_bytes())
                with zipfile.ZipFile(self.asset(assets[1])) as archive:
                    self.save(target / 'dxgi.dll', archive.read('OptiScaler.dll'))
                    self.save(target / 'OptiScaler/amd_fidelityfx_upscaler_vk.dll', archive.read('OptiScaler/amd_fidelityfx_upscaler_vk.dll'))
                ini = PROFILE / 'OptiScaler-fsr4vk-0.4.3.ini'
            else:
                for source in stage.iterdir():
                    if source.is_file() and source.suffix.lower() in ('.dll', '.ini') and source.name != 'OptiScaler.ini':
                        self.save(target / ('dxgi.dll' if source.name == 'OptiScaler.dll' else source.name), source.read_bytes())
                ini = PROFILE / 'OptiScaler-0.9.4.ini'
            # In-game Save Settings owns tuning after first installation.
            if not (target / 'OptiScaler.ini').exists():
                self.save(target / 'OptiScaler.ini', configured_ini(ini.read_text(), kind == 'fsr4vk-043').encode())

    def artwork(self, game):
        from PIL import Image
        destinations = {'banner': ('banners', 'JPEG', (920, 430)), 'cover': ('coverart', 'JPEG', (600, 900)), 'icon': (None, 'PNG', (128, 128))}
        complete = True
        for kind, url in game.get('artwork', {}).items():
            folder, fmt, size = destinations[kind]
            path = (self.home / '.local/share/lutris' / folder / (game['slug'] + '.jpg') if folder else self.home / '.local/share/icons/hicolor/128x128/apps' / ('lutris_' + game['slug'] + '.png'))
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
    root = home / '.local/share/lutris'
    db = root / 'pga.db'
    if not db.exists():
        raise RuntimeError('Initialize Lutris first (install-lutris.sh does this).')
    with closing(sqlite3.connect(db)) as con:
        con.row_factory = sqlite3.Row
        def backup_db():
            dest = installer.backup / 'pga.db'
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                with closing(sqlite3.connect(dest)) as saved:
                    con.backup(saved)
        for game in games:
            exe = Path(game['config']['game']['exe'])
            if not exe.is_file():
                print(f'Skipped {game["name"]}: mount/install game first: {exe}')
                continue
            # Halo owns resolution/HDR directly, without a nested Gamescope display.
            if game.get('display_settings'):
                settings = Path(game['config']['game']['prefix']) / 'drive_c/users/steamuser/AppData/Local/Meteorite/Saved/Config/Windows/GameUserSettings.ini'
                if settings.exists():
                    text = settings.read_text()
                    section = '[/Script/Meteorite.MeteoriteGameUserSettings]'
                    start = text.index(section) + len(section)
                    end = text.find('\n[', start)
                    if end == -1:
                        end = len(text)
                    body = text[start:end]
                    for key, value in game['display_settings'].items():
                        pattern = r'(?m)^' + re.escape(key) + r'=.*$'
                        if re.search(pattern, body):
                            body = re.sub(pattern, key + '=' + value, body)
                        else:
                            body += '\n' + key + '=' + value + '\n'
                    updated = text[:start] + body + text[end:]
                    if updated != text:
                        installer.save(settings, updated.encode())
                else:
                    print('Launch Halo once, then rerun to apply its 4K/HDR settings.')
            rows = con.execute('SELECT * FROM games WHERE installer_slug=? OR slug=?', (game['key'], game['slug'])).fetchall()
            if len(rows) > 1:
                raise RuntimeError('Ambiguous Lutris entries for ' + game['name'])
            row = rows[0] if rows else None
            configpath = row['configpath'] if row else 'arch-profile-' + game['key']
            path = root / 'games' / (configpath + '.yml')
            current = yaml.safe_load(path.read_bytes()) if path.exists() else {}
            merged = merge_config(current or {}, game['config'])
            if merged != current:
                installer.save(path, yaml.safe_dump(merged, sort_keys=False).encode())
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
                installer.save(p, setup_4k(p.read_bytes()))
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
                installer.save(home / '.local/share/applications' / ('lutris-' + game['slug'] + '.desktop'), text.encode())
            if upscalers and game.get('upscaler'):
                installer.upscaler(game, profile['assets'])
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
    for filename in ('fc26-linuwux.desktop', 'lutris-ea-sports-fc-27.desktop', 'lutris-ea-sports-fc-26-4k120-linuwux.desktop'):
        installer.remove(home / '.local/share/applications' / filename)
    installer.save(home / '.local/bin/launch-aoe2-account', (PROFILE / 'launch-aoe2-account').read_bytes(), 0o755)
    for account, label, filename in [('pbtroopers', 'pbtrooper15', 'aoe2-pbtroopers.desktop'), ('the_gremlin15', 'The_Gremlin15', 'aoe2-the-gremlin15.desktop')]:
        text = desktop(label + ' — Age of Empires II', f'"{home}/.local/bin/launch-aoe2-account" {account}', 'steam_icon_813780')
        installer.save(home / '.local/share/applications' / filename, text.encode())
    qbit = home / '.local/share/applications/qBittorrent.desktop'
    text = qbit.read_text() if qbit.exists() else expand((PROFILE / 'qBittorrent.desktop').read_text(), home)
    text = re.sub(r'^Name=.*$', 'Name=qBittorrent Web', text, flags=re.M)
    if not qbit.exists() and not (home / '.local/share/applications/icons/qBittorrent.png').exists():
        text = re.sub(r'^Icon=.*$', 'Icon=web-browser', text, flags=re.M)
    installer.save(qbit, text.encode())
    if installer.changed:
        subprocess.run(['update-desktop-database', str(home / '.local/share/applications')], check=True)
        print(f'Gaming profile: {installer.changed} changes. Backups: {installer.backup}')
    else:
        print('Gaming profile already installed and current.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Apply; default is a read-only plan')
    parser.add_argument('--upscalers', action='store_true', help='Fetch SHA256-pinned third-party DLLs and install them; offline/single-player only')
    args = parser.parse_args()
    profile = json.loads((PROFILE / 'games.json').read_text())
    if args.apply:
        apply(profile, Path.home(), args.upscalers)
    else:
        for game in expand(profile['games'], Path.home()):
            print(game['name'], 'available' if Path(game['config']['game']['exe']).is_file() else 'missing; will skip', game.get('upscaler', ''))
        print('Read-only. Use --apply; add --upscalers to install pinned experimental DLLs.')


if __name__ == '__main__':
    main()
