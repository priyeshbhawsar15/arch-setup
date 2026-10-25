#!/usr/bin/env python3
"""Reconcile supported personal Shibumi settings, leaving payload/layout intact."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys


def main(shell, policy=None, media_backend_only=False):
    path = Path(shell)
    if not path.is_file():
        raise ValueError('Shibumi requires an existing shell configuration')
    if path.is_symlink():
        raise ValueError('refusing a symlinked shell configuration')
    original_bytes = path.read_bytes()
    data = json.loads(original_bytes)
    original = json.loads(json.dumps(data))
    plugins = data.get('plugins', [])
    entry = next((p for p in plugins if p.get('id') == 'hancore.shibumi.state'), None)
    if entry is None:
        raise ValueError('the suite State plugin must be installed before configuring it')
    if 'hancore.shibumi.media' in data.get('disabledPlugins', []):
        raise ValueError('the required media backend is explicitly disabled; review suite configuration first')
    if not media_backend_only:
        if policy is None:
            raise ValueError('a monitor policy is required unless --media-backend-only is used')
        monitor_policy = json.loads(Path(policy).read_text())
        description = monitor_policy['monitors'][monitor_policy['barMain']].get('description', '')
        settings = entry.setdefault('shibumi', {})
        settings.setdefault('presentation', {})['mainMonitorDescription'] = description
        settings.setdefault('widgets', {}).setdefault('G15', {}).setdefault('enabled', True)
        settings['widgets'].setdefault('G9', {}).setdefault('enabled', False)
    # Hiding G9's widget removes its implicit service demand. The center notch
    # still needs the suite media adapter: load its service without a bar slot.
    if not any(p.get('id') == 'hancore.shibumi.media' for p in plugins):
        plugins.append({'id': 'hancore.shibumi.media'})
    if data != original:
        spec = importlib.util.spec_from_file_location('managed_config', Path(__file__).with_name('managed-config.py'))
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        helper.replace_atomic(path, json.dumps(data, indent=2) + '\n', original_bytes)


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('shell')
        parser.add_argument('policy', nargs='?')
        parser.add_argument('--media-backend-only', action='store_true')
        args = parser.parse_args()
        main(args.shell, args.policy, args.media_backend_only)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('Shibumi settings: ' + str(error), file=sys.stderr)
        sys.exit(1)
