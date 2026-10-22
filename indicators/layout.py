#!/usr/bin/env python3
"""Manage personal indicator placement without claiming unrelated bar settings."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys

PLUGIN = 'priyesh.indicators'
ORIGINAL = 'omarchy.indicators'
REGIONS = ('left', 'center', 'right')


def entry_id(entry):
    return entry.get('id') if isinstance(entry, dict) else entry


def transform(config, state, enable):
    result = copy.deepcopy(config)
    bar = result.get('bar', {})
    layout = bar.get('layout', {})
    if not isinstance(bar, dict) or not isinstance(layout, dict):
        raise ValueError('bar/layout must be objects')
    for region in REGIONS:
        if not isinstance(layout.get(region), list):
            raise ValueError('bar layout must contain left, center and right arrays')
    active_bar = bar.get('id', 'omarchy.bar')
    records = state.get('slots', []) if state.get('bar') == active_bar else []
    if enable:
        custom_exists = any(entry_id(e) == PLUGIN for r in REGIONS for e in layout[r])
        if not custom_exists:
            records = []
            for region in REGIONS:
                for index, entry in enumerate(layout[region]):
                    if entry_id(entry) == ORIGINAL:
                        records.append({'region': region, 'original': copy.deepcopy(entry)})
                        replacement = copy.deepcopy(entry) if isinstance(entry, dict) else {}
                        replacement['id'] = PLUGIN
                        layout[region][index] = replacement
            if not records:
                layout['right'].insert(0, {'id': PLUGIN, 'alwaysShow': False})
        for region in REGIONS:
            for entry in layout[region]:
                if isinstance(entry, dict) and entry.get('id') == PLUGIN:
                    if active_bar == 'hancore.shibumi.bar':
                        entry['shibumiModule'] = True
                    entry.setdefault('alwaysShow', False)
        if isinstance(result.get('disabledPlugins'), list) and PLUGIN in result['disabledPlugins']:
            result['disabledPlugins'].remove(PLUGIN)
        return result, {'bar': active_bar, 'slots': records}

    for region in REGIONS:
        replacements = [r['original'] for r in records if r.get('region') == region]
        kept = []
        for entry in layout[region]:
            if entry_id(entry) != PLUGIN:
                kept.append(entry)
            elif replacements and not any(entry_id(e) == ORIGINAL for e in layout[region]):
                kept.append(replacements.pop(0))
        layout[region] = kept
    return result, None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('enable', 'disable'))
    parser.add_argument('shell', type=Path)
    parser.add_argument('state', type=Path)
    args = parser.parse_args()
    if not args.shell.exists():
        if args.action == 'disable':
            return 0
        raise ValueError('existing Omarchy shell configuration is required')
    original_shell = args.shell.read_bytes()
    original_state = args.state.read_bytes() if args.state.exists() else None
    config = json.loads(original_shell)
    state = json.loads(original_state) if original_state is not None else {}
    changed, next_state = transform(config, state, args.action == 'enable')
    spec = importlib.util.spec_from_file_location('managed_config', Path(__file__).resolve().parents[1] / 'config/managed-config.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    # Capture restoration state before altering the bar; both files are backed
    # up and atomically replaced by the shared configuration writer.
    if next_state is not None and next_state != state:
        helper.replace_atomic(args.state, json.dumps(next_state, indent=2) + '\n', original_state)
    if changed != config:
        helper.replace_atomic(args.shell, json.dumps(changed, indent=2) + '\n', original_shell)
    if next_state is None and args.state.exists():
        if args.state.is_symlink():
            raise ValueError('refusing symlinked indicator restoration state')
        args.state.unlink()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        print('indicators layout: ' + str(error), file=sys.stderr)
        sys.exit(1)
