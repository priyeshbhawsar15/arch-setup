#!/usr/bin/env python3
"""Validate external inputs and seed portable widget settings without logging secrets."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from urllib.parse import urlsplit

sys.dont_write_bytecode = True  # Including direct validate/plan invocations.
ROOT = Path(__file__).resolve().parents[1]
FIELDS = {
    'omniroute-quota': {'endpoint', 'tokenFile'},
    'immich-photo-frame': {'serverUrl', 'apiKeyFile'},
    'obsidian-tasks': {'vaultPath', 'vaultName', 'dashboardPath'},
    'home-assistant': {'baseUrl', 'tokenFile', 'climate', 'temperature', 'humidity', 'weather', 'switches', 'scenes', 'lights'},
}
DEFAULTS = {
    'omniroute-quota': {'endpoint': '', 'token': '', 'refreshIntervalSeconds': 60},
    'immich-photo-frame': {'serverUrl': '', 'apiKey': ''},
    'obsidian-tasks': {'vaultPath': '', 'vaultName': '', 'dashboardPath': '00 Home/Tasks.md'},
    'home-assistant': {'baseUrl': '', 'tokenFile': '${HOME}/.config/omarchy/hass/token', 'climate': '', 'temperature': '', 'humidity': '', 'weather': '', 'switches': {}, 'scenes': {}, 'lights': {}},
}


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def gaming():
    return module('gaming_inputs', ROOT / 'steam/gaming_profile.py').load_selection()


def settings():
    source = os.environ.get('ARCH_SETUPS_SETTINGS')
    data = json.loads(Path(source).read_text()) if source else {}
    if not isinstance(data, dict) or set(data) - set(FIELDS):
        raise ValueError('unknown widget setting name')
    for name, values in data.items():
        if not isinstance(values, dict) or set(values) - FIELDS[name]:
            raise ValueError('invalid/unknown settings for ' + name)
        for key, value in values.items():
            if name == 'home-assistant' and key in ('switches', 'scenes', 'lights'):
                if not isinstance(value, dict) or any(not isinstance(v, str) for v in value.values()):
                    raise ValueError('HA entity groups must map labels to entity IDs')
                continue
            if not isinstance(value, str):
                raise ValueError('widget fields must be strings')
            if key.endswith('File') or key == 'vaultPath':
                target = module('gaming_paths', ROOT / 'steam/gaming_profile.py').absolute(value, Path.home())
                if key.endswith('File') and (not target.is_file() or target.stat().st_mode & 0o077):
                    raise ValueError('credential reference must exist and be user-only before setup')
            if key in ('endpoint', 'serverUrl', 'baseUrl') and value:
                parsed = urlsplit(value)
                if parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None or parsed.password is not None:
                    raise ValueError('server URL must be HTTPS without embedded credentials')
    return data


def planner_cli():
    helper = module('planner_inputs', ROOT / 't3/configure-planner-executor.py')
    seed = Path(os.environ.get('T3_PLANNER_EXECUTOR_SEED_CONFIG', str(ROOT / 't3/planner-executor.json')))
    seed_data, _ = helper.load_json(seed, fail_closed=True)
    if not isinstance(seed_data, dict):
        raise ValueError('workflow seed must be an existing JSON object')
    config_home = Path(os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config'))
    runtime = Path(os.environ.get('T3_PLANNER_EXECUTOR_RUNTIME_DIR', str(config_home / 't3code/planner-executor')))
    provider = helper.get_executor_cli(runtime / 'config.json', seed)
    if provider not in ('pi', 'codex', 'claudeAgent', 'claude', 'antigravity'):
        raise ValueError('unsupported workflow executor provider')
    if provider == 'antigravity':
        settings_path = Path(os.environ.get('T3_PLANNER_EXECUTOR_SETTINGS', str(Path(os.environ.get('T3CODE_HOME', str(Path.home() / '.t3'))) / 'userdata/settings.json')))
        if helper.detect_providers(settings_path, runtime).get('antigravityStatus') != 'available':
            raise ValueError('native executor binaries must be configured before setup')
    return {'claudeAgent': 'claude', 'antigravity': None}.get(provider, provider)


def seed_widget(name):
    values = settings().get(name, {})
    path = Path.home() / '.config/omarchy' / (name + '.json')
    parent = Path(os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local/state')) / 'arch-setups'
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (parent / 'configuration.lock').open('a') as lock:
        os.chmod(lock.name, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.is_symlink():
            raise ValueError('refusing symlinked widget configuration')
        original = path.read_bytes() if path.exists() else None
        data = json.loads(original) if original is not None else {key: value.replace('${HOME}', str(Path.home())) if isinstance(value, str) else value for key, value in DEFAULTS[name].items()}
        if not isinstance(data, dict):
            raise ValueError('widget configuration must be an object')
        for key, value in values.items():
            if key.endswith('File'):
                source = module('secret_paths', ROOT / 'steam/gaming_profile.py').absolute(value, Path.home())
                if source.stat().st_mode & 0o077 or not source.is_file():
                    raise ValueError('credential source must be a private user-only file')
                if name == 'home-assistant':
                    data[key] = str(source)  # HA consumes a file reference, not an inline token.
                else:
                    data[key[:-4]] = source.read_text().strip()
            else:
                data[key] = value.replace('${HOME}', str(Path.home())) if isinstance(value, str) else value
        if original is not None and data == json.loads(original):
            path.chmod(0o600)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        if original is not None:
            backup = Path(tempfile.mkdtemp(prefix='widget-settings-', dir=parent))
            shutil.copy2(path, backup / path.name)
        fd, tmp = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(data, stream, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            if (path.read_bytes() if path.exists() else None) != original:
                raise ValueError('widget configuration changed concurrently; retry')
            os.replace(tmp, path)
        finally:
            Path(tmp).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('validate')
    sub.add_parser('plan')
    sub.add_parser('gaming')
    sub.add_parser('widget').add_argument('name', choices=FIELDS)
    args = parser.parse_args()
    settings()
    if os.environ.get('T3_PLANNER_EXECUTOR_SEED_CONFIG'):
        planner_cli()
    if args.command == 'widget':
        seed_widget(args.name)
    elif args.command == 'gaming':
        print(json.dumps(gaming()))
    else:
        selected = gaming()
        source = os.environ.get('ARCH_SETUPS_MONITOR_LAYOUT')
        if source:
            module('monitor_inputs', ROOT / 'hypr/scripts/monitor-layout.py').load_config(source)
        if args.command == 'plan':
            print('Gaming: ' + str(len(selected['games'])) + ' selected; Steam import=' + str(selected['importSteam']) + '; blanket Steam HDR=' + str(selected['steamHdr']))
            for game in selected['games']:
                print('  ' + game['slug'] + ': ' + game['config']['game']['exe'] + '; upscaler=' + game.get('upscaler', 'none'))
            if source:
                print('Host policy: ' + source)
            if os.environ.get('ARCH_SETUPS_SETTINGS'):
                print('Local widget settings supplied; credential values are never shown.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError, KeyError) as error:
        # Do not interpolate data/JSON exceptions: a malformed private config
        # can include credential material. Only file/feature names are public.
        print('Setup inputs invalid or unavailable; check the selected profile, settings, host and gaming files.', file=sys.stderr)
        sys.exit(2)
