#!/usr/bin/env python3
"""Own reversible plugin bar edits without overwriting later user changes.

Arguments: SHELL_CONFIG STATE_FILE PLUGIN_ID ROLE ACTION.
Roles: calendar, brightness, workspaces. Actions: enable, disable, check.
"""
import copy, fcntl, json, os, pathlib, shutil, sys, tempfile, time
path, state_path = map(pathlib.Path, sys.argv[1:3])
plugin_id, role, action = sys.argv[3:]
if not path.exists():
    raise SystemExit(1 if action in ('enable', 'check') else 0)
# Serializes cooperating setup helpers; the final byte comparison also detects
# intervening shell/GUI edits which do not participate in this lock.
lock_root = pathlib.Path(os.environ.get('XDG_STATE_HOME') or str(pathlib.Path.home() / '.local/state')) / 'arch-setups'
if action != 'check':
    lock_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    configuration_lock = (lock_root / 'configuration.lock').open('a')
    os.chmod(configuration_lock.name, 0o600)
    fcntl.flock(configuration_lock, fcntl.LOCK_EX)
original_bytes = path.read_bytes()
data = json.loads(original_bytes)
bar = data.get('bar', {})
layout = bar.get('layout', {})
bar_id = bar.get('id', 'omarchy.bar')
state = json.loads(state_path.read_text()) if state_path.exists() else None
missing = {'absent': True}

def entry_id(entry):
    return entry.get('id') if isinstance(entry, dict) else entry

def state_entry():
    return next((p for p in data.get('plugins', []) if isinstance(p, dict) and p.get('id') == 'hancore.shibumi.state'), None)

def property_value(key):
    value = state_entry()
    for part in key.split('.'):
        if not isinstance(value, dict) or part not in value: return missing
        value = value[part]
    return copy.deepcopy(value)

def set_property(key, value):
    target = state_entry()
    if target is None: return
    parts = key.split('.')
    for part in parts[:-1]: target = target.setdefault(part, {})
    if value == missing: target.pop(parts[-1], None)
    else: target[parts[-1]] = copy.deepcopy(value)

def save_json(target, value):
    if target.exists() and json.loads(target.read_text()) == value: return
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=target.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.chmod(name, target.stat().st_mode & 0o777 if target.exists() else 0o600)
        os.replace(name, target)
    finally:
        pathlib.Path(name).unlink(missing_ok=True)

if action == 'check':
    if not state or state['barId'] != bar_id: raise SystemExit(1)
    entries = [e for values in layout.values() for e in values if entry_id(e) == plugin_id]
    if len(entries) != 1: raise SystemExit(1)
    if role == 'calendar':
        good = layout.get('center') == state['appliedCenter'] and bar.get('centerAnchor') == plugin_id
    else:
        native = 'hancore.shibumi.workspaces' if role == 'workspaces' else 'hancore.shibumi.brightness'
        good = not any(entry_id(e) == native for values in layout.values() for e in values)
        if role == 'workspaces': good = good and entries[0].get('shibumiModule') is True and entries[0].get('count') == 5
        good = good and all(property_value(key) == value for key, value in state.get('appliedProperties', {}).items())
    raise SystemExit(0 if good else 1)

if action == 'enable':
    if role == 'workspaces' and bar_id != 'hancore.shibumi.bar':
        raise SystemExit('Per-monitor Workspaces requires the active Shibumi bar.')
    if state and state['barId'] != bar_id:
        raise SystemExit('The active bar changed; disable this feature before managing its new layout.')
    if state is None:
        state = {'barId': bar_id, 'nativeEntries': [], 'beforeProperties': {}, 'appliedProperties': {}}
        state['beforeCenter'] = copy.deepcopy(layout.get('center', []))
        state['beforeAnchor'] = copy.deepcopy(bar.get('centerAnchor', missing))
        if role != 'calendar' and bar_id == 'hancore.shibumi.bar':
            native = 'hancore.shibumi.workspaces' if role == 'workspaces' else 'hancore.shibumi.brightness'
            state['nativeEntries'] = [{'section': section, 'index': index, 'entry': copy.deepcopy(entry)}
                for section, values in layout.items() for index, entry in enumerate(values) if entry_id(entry) == native]
        if role == 'brightness' and bar_id == 'hancore.shibumi.bar':
            key = 'shibumi.widgets.G13.enabled'
            state['beforeProperties'][key] = property_value(key)
            state['appliedProperties'][key] = False
        save_json(state_path, state)
    found = next((copy.deepcopy(e) for values in layout.values() for e in values if entry_id(e) == plugin_id), {'id': plugin_id})
    if not isinstance(found, dict): found = {'id': plugin_id}
    for section, values in layout.items():
        layout[section] = [e for e in values if entry_id(e) != plugin_id]
    if role == 'calendar':
        layout['center'] = [found]; bar['centerAnchor'] = plugin_id
        state['appliedCenter'] = copy.deepcopy(layout['center'])
    else:
        native = 'hancore.shibumi.workspaces' if role == 'workspaces' else 'hancore.shibumi.brightness'
        if bar_id == 'hancore.shibumi.bar':
            for section, values in layout.items(): layout[section] = [e for e in values if entry_id(e) != native]
        if role == 'workspaces': found.update(shibumiModule=True, count=5)
        section = state['nativeEntries'][0]['section'] if state['nativeEntries'] else ('left' if role == 'workspaces' else 'right')
        index = state['nativeEntries'][0]['index'] if state['nativeEntries'] else len(layout.get(section, []))
        layout.setdefault(section, []).insert(min(index, len(layout.get(section, []))), found)
        for key, value in state['appliedProperties'].items(): set_property(key, value)
    save_json(state_path, state)
elif action == 'disable':
    owned = any(entry_id(e) == plugin_id for values in layout.values() for e in values)
    same_bar = state is not None and state['barId'] == bar_id
    center_owned = same_bar and layout.get('center') == state.get('appliedCenter')
    for section, values in layout.items(): layout[section] = [e for e in values if entry_id(e) != plugin_id]
    if same_bar:
        if role == 'calendar':
            if center_owned: layout['center'] = state['beforeCenter']
            if bar.get('centerAnchor') == plugin_id:
                if center_owned and state['beforeAnchor'] != missing: bar['centerAnchor'] = state['beforeAnchor']
                else: bar.pop('centerAnchor', None)
        elif owned:
            for item in state['nativeEntries']:
                section, entry = item['section'], item['entry']
                if not any(entry_id(e) == entry_id(entry) for values in layout.values() for e in values):
                    layout.setdefault(section, []).insert(min(item['index'], len(layout.get(section, []))), entry)
        for key, value in state.get('appliedProperties', {}).items():
            if property_value(key) == value: set_property(key, state['beforeProperties'][key])
else:
    raise SystemExit('Unknown layout operation')

if json.loads(original_bytes) != data:
    backup = state_path.parent.parent / 'backups' / (plugin_id + '-bar-' + str(time.time_ns()))
    backup.mkdir(mode=0o700, parents=True, exist_ok=True)
    shutil.copy2(path, backup / 'shell.json')
    if path.read_bytes() != original_bytes: raise SystemExit('Shell configuration changed during layout update; retry.')
    save_json(path, data)
if action == 'disable': state_path.unlink(missing_ok=True)
