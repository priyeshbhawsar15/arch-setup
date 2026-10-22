"""Portable, opt-in gaming selection. This module does not write or download."""
import copy
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CATALOG = Path(__file__).parent / 'profile/games.json'
DEFAULT = ROOT / 'gaming/selection.json'


def absolute(value, home):
    if not isinstance(value, str) or not value or '\n' in value or '\x00' in value:
        raise ValueError('expected a nonempty single-line path')
    path = Path(value.replace('${HOME}', str(home))).expanduser()
    if not path.is_absolute() or '${' in str(path):
        raise ValueError('paths must be absolute (or start with ${HOME})')
    return path


def load_selection(path=None, home=None):
    home = home or Path.home()
    path = Path(path or os.environ.get('ARCH_SETUPS_GAMING_PROFILE') or DEFAULT)
    data = json.loads(path.read_text())
    allowed = {'schemaVersion', 'libraries', 'games', 'steamHdr', 'importSteam'}
    if not isinstance(data, dict) or set(data) - allowed or type(data.get('schemaVersion')) is not int or data['schemaVersion'] != 1:
        raise ValueError('invalid gaming selection schema or unknown keys')
    for key in ('steamHdr', 'importSteam'):
        if type(data.get(key, False)) is not bool:
            raise ValueError(key + ' must be a boolean')
    libraries, selected = data.get('libraries', {}), data.get('games', {})
    if not isinstance(libraries, dict) or not isinstance(selected, dict):
        raise ValueError('libraries and games must be objects')
    for name, value in libraries.items():
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', name):
            raise ValueError('invalid library name')
        absolute(value, home)
    catalog = json.loads(CATALOG.read_text())
    by_id = {game['slug']: game for game in catalog['games']}
    games = []
    for identity, options in selected.items():
        if identity not in by_id or not isinstance(options, dict):
            raise ValueError('unknown game or invalid game options: ' + identity)
        allowed_options = {'enabled', 'library', 'path', 'prefix', 'wineVersion', 'desktop', 'hdr', 'resolution', 'upscaler', 'required', 'allowModReplacement', 'artwork'}
        if set(options) - allowed_options:
            raise ValueError('unknown game option: ' + identity)
        for key in ('enabled', 'desktop', 'hdr', 'required', 'allowModReplacement', 'artwork'):
            if key in options and type(options[key]) is not bool:
                raise ValueError(key + ' must be a boolean')
        if not options.get('enabled', True):
            continue
        if options.get('library') not in libraries:
            raise ValueError('game needs a configured library: ' + identity)
        relative = options.get('path')
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or '..' in Path(relative).parts or '${' in relative:
            raise ValueError('game path must be relative to its library: ' + identity)
        directory = absolute(libraries[options['library']], home) / relative
        size = options.get('resolution')
        if size is not None and (not isinstance(size, list) or len(size) != 2 or any(type(v) is not int or not 320 <= v <= 16384 for v in size)):
            raise ValueError('resolution must be [width, height], 320..16384')
        if options.get('hdr') and size is None:
            raise ValueError('HDR Gamescope requires an explicit resolution: ' + identity)
        kind = options.get('upscaler', 'none')
        template = by_id[identity]
        if kind not in ('none', template.get('upscaler', 'none')):
            raise ValueError('unsupported upscaler for ' + identity)
        if options.get('wineVersion') is not None and (not isinstance(options['wineVersion'], str) or not options['wineVersion'].strip()):
            raise ValueError('wineVersion must be a nonempty string')
        # Symlinked game directories are supported; paths never resolve from a
        # username-specific automount name or a historical Steam shortcut ID.
        def expand(value):
            if isinstance(value, str):
                return value.replace('${GAME}', str(directory)).replace('${HOME}', str(home))
            if isinstance(value, dict):
                return {key: expand(v) for key, v in value.items()}
            if isinstance(value, list):
                return [expand(v) for v in value]
            return value
        game = expand(copy.deepcopy(template))
        game.update(required=options.get('required', False), allowModReplacement=options.get('allowModReplacement', False))
        if not options.get('artwork', False):
            game.pop('artwork', None)
        config = game['config']
        config['game']['prefix'] = str(absolute(options.get('prefix', '${HOME}/.local/share/wineprefixes/arch-setups/' + identity), home))
        if options.get('wineVersion'):
            config.setdefault('wine', {})['version'] = options['wineVersion']
        if 'desktop' in options:
            game['desktop'] = options['desktop']
        system = config.setdefault('system', {})
        system.pop('prefix_command', None)
        environment = system.setdefault('env', {})
        hdr_environment = {key: environment.pop(key) for key in ('ENABLE_HDR_WSI', 'DXVK_HDR', 'PROTON_ENABLE_HDR') if key in environment}
        environment.pop('FSR4_VK_LOG', None)
        if kind == 'none':
            game.pop('upscaler', None)
            # These catalog overrides exist only to load the selected upscaler.
            if 'dxgi' in environment.get('WINEDLLOVERRIDES', ''):
                environment.pop('WINEDLLOVERRIDES', None)
        args = config['game'].get('args', '')
        args = re.sub(r'-screen-(?:width|height|fullscreen)\s+\d+\s*', '', args).strip()
        config['game']['args'] = args
        if size:
            game['resolution'] = size
            if 'setup_xml' in game:
                config['game']['args'] = (args + f' -screen-width {size[0]} -screen-height {size[1]} -screen-fullscreen 1').strip()
        else:
            game.pop('setup_xml', None)
        if 'display_settings' in game:
            if size:
                for key in ('ResolutionSizeX', 'LastUserConfirmedResolutionSizeX', 'DesiredScreenWidth', 'LastUserConfirmedDesiredScreenWidth'):
                    game['display_settings'][key] = str(size[0])
                for key in ('ResolutionSizeY', 'LastUserConfirmedResolutionSizeY', 'DesiredScreenHeight', 'LastUserConfirmedDesiredScreenHeight'):
                    game['display_settings'][key] = str(size[1])
                if not options.get('hdr'):
                    game['display_settings'].pop('bUseHDRDisplayOutput', None)
            else:
                game.pop('display_settings')
        if options.get('hdr'):
            system['prefix_command'] = 'steam-gamescope-hdr'
            environment.update(hdr_environment)
            environment.update(ARCH_SETUPS_GAME_WIDTH=str(size[0]), ARCH_SETUPS_GAME_HEIGHT=str(size[1]))
        games.append(game)
    return dict(games=games, retired_shortcuts=[], assets=catalog['assets'], steamHdr=data.get('steamHdr', False), importSteam=data.get('importSteam', False))


def owned_shortcuts(profile):
    """Only successfully resolved selected games displace generic imports."""
    return {game['shortcut_id'] for game in profile['games']
            if game.get('shortcut_id') and Path(game['config']['game']['exe']).is_file()}
