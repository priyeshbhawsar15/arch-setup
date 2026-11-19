#!/usr/bin/env python3
"""Route every Lutris Windows game through the managed main-monitor HDR Gamescope wrapper.

`lutrisHdr: true` in the gaming selection applies this; `false` restores the
prefix commands this script set (still unchanged ones only). Ownership lives in
the state home so opting out never removes a wrapper the user chose.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
import yaml

WRAPPER = 'steam-gamescope-hdr'
# Store clients are launchers, not games: fullscreen Gamescope would trap their UI.
LAUNCHERS = {'epicgameslauncher.exe', 'upc.exe', 'ubisoftconnect.exe', 'galaxyclient.exe',
             'eadesktop.exe', 'battle.net.exe', 'steam.exe'}
# Repository-owned legacy catalog command (RDR2): an exact match is ours to migrate.
LEGACY = {'gamescope -w 3840 -h 2160 -W 3840 -H 2160 -r 120 -f --hdr-enabled --hdr-sdr-content-nits 203 --'}


def games_dir(override: Path | None) -> Path:
    if override:
        return override
    try:
        from lutris import settings  # honours lutris.conf and both directory layouts
        return Path(settings.GAME_CONFIG_DIR)
    except (Exception, SystemExit):  # headless or unavailable GI: use the XDG layout
        config = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'lutris/games'
        return config if config.is_dir() else Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share') / 'lutris/games'


def state_file() -> Path:
    # An empty XDG variable means unset; never resolve state relative to the cwd.
    return Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') / 'arch-setups/games/lutris-hdr.json'


def wine_game(config: dict) -> bool:
    game = config.get('game')
    if not isinstance(game, dict) or game.get('appid'):  # Steam runner: Steam launch options own it
        return False
    exe = str(game.get('exe') or '')
    return exe.lower().endswith('.exe') and Path(exe).name.lower() not in LAUNCHERS


def lutris_running() -> bool:
    return subprocess.run(['pgrep', '-u', str(os.getuid()), '-f', r'(^|/)(python[0-9.]* )?(/usr/bin/)?lutris( |$)'],
                          stdout=subprocess.DEVNULL).returncode == 0


def save(path: Path, config: dict) -> None:
    shutil.copy2(path, path.with_name(f'{path.name}.bak-hdr-{datetime.now():%Y%m%d%H%M%S%f}'))
    fd, temporary = tempfile.mkstemp(prefix='.lutris-hdr-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            yaml.safe_dump(config, stream, sort_keys=False)
            stream.flush()
            os.fsync(stream.fileno())
        shutil.copymode(path, temporary)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def plan(directory: Path, owned: dict, enable: bool):
    """Yield (path, config, new_prefix_or_None, previous) for pending edits."""
    for path in sorted(directory.glob('*.yml')):
        if path.is_symlink() or not path.is_file():
            continue
        config = yaml.safe_load(path.read_text()) or {}
        if not isinstance(config, dict):
            continue
        system = config.get('system') if isinstance(config.get('system'), dict) else {}
        current = str(system.get('prefix_command') or '').strip()
        if enable:
            if not wine_game(config) or WRAPPER in current:
                continue
            if current and current not in LEGACY:
                print(f'Kept user-owned prefix command for {config.get("name") or path.stem}: {current}')
                continue
            yield path, config, WRAPPER, current or None
        elif path.name in owned and current == WRAPPER:
            yield path, config, owned[path.name].get('previous'), None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--games-dir', type=Path)
    parser.add_argument('--remove', action='store_true', help='restore prefix commands this script set')
    args = parser.parse_args()
    ledger = state_file()
    owned = json.loads(ledger.read_text()) if ledger.is_file() else {}
    if args.remove and not owned:
        return 0
    directory = games_dir(args.games_dir)
    if not directory.is_dir():
        print('No Lutris game configurations yet; HDR wrapping applies on a later run.')
        return 0
    pending = list(plan(directory, owned, not args.remove))
    if pending and lutris_running():
        raise SystemExit(f'{len(pending)} Lutris game(s) need HDR changes: close Lutris and rerun.')
    for path, config, prefix, previous in pending:
        system = config.setdefault('system', {})
        if prefix:
            system['prefix_command'] = prefix
        else:
            system.pop('prefix_command', None)
        save(path, config)
        name = config.get('name') or Path(str(config['game'].get('exe', path.stem))).stem
        if args.remove:
            owned.pop(path.name, None)
            print(f'Restored launch command for {name}.')
        else:
            owned[path.name] = {'previous': previous}
            print(f'{name} -> main-monitor Gamescope HDR')
    # Ownership ends once the user changes or deletes a wrapped configuration.
    owned = {key: value for key, value in owned.items() if (directory / key).is_file()
             and str(((yaml.safe_load((directory / key).read_text()) or {}).get('system') or {}).get('prefix_command') or '') == WRAPPER}
    if owned:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(json.dumps(owned, indent=2, sort_keys=True) + '\n')
    else:
        ledger.unlink(missing_ok=True)
    if not pending:
        print('Lutris games already match the HDR selection.' if not args.remove else 'No owned Lutris HDR wrappers remain.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
