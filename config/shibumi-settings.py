#!/usr/bin/env python3
"""Reconcile supported personal Shibumi settings, leaving payload/layout intact."""
import importlib.util
import json
from pathlib import Path
import sys


def main(shell, policy):
    path = Path(shell)
    if not path.is_file():
        raise ValueError('Shibumi requires an existing shell configuration')
    if path.is_symlink():
        raise ValueError('refusing a symlinked shell configuration')
    original_bytes = path.read_bytes()
    data = json.loads(original_bytes)
    original = json.loads(json.dumps(data))
    monitor_policy = json.loads(Path(policy).read_text())
    description = monitor_policy['monitors'][monitor_policy['barMain']].get('description', '')
    entry = next((p for p in data.get('plugins', []) if p.get('id') == 'hancore.shibumi.state'), None)
    if entry is None:
        raise ValueError('the suite State plugin must be installed before configuring it')
    settings = entry.setdefault('shibumi', {})
    settings.setdefault('presentation', {})['mainMonitorDescription'] = description
    settings.setdefault('widgets', {}).setdefault('G15', {}).setdefault('enabled', True)
    # The center notch owns the media presentation; retain the suite service.
    settings['widgets'].setdefault('G9', {}).setdefault('enabled', False)
    if data != original:
        spec = importlib.util.spec_from_file_location('managed_config', Path(__file__).with_name('managed-config.py'))
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        helper.replace_atomic(path, json.dumps(data, indent=2) + '\n', original_bytes)


if __name__ == '__main__':
    try:
        main(*sys.argv[1:])
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('Shibumi settings: ' + str(error), file=sys.stderr)
        sys.exit(1)
