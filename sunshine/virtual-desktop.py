#!/usr/bin/env python3
# Managed by arch-setups/install-virtual-desktop.sh
"""Independent Sunshine profile and owned Hyprland 1080p virtual output."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

OUTPUT = 'SUNSHINE-VIRTUAL-1080P'
OWNER = 'arch-setups-sunshine-virtual-v1'


def config_home():
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))


def profile_dir():
    return config_home()/'sunshine-virtual/sunshine'


def save(path, text):
    if path.is_symlink():
        raise ValueError(f'Refusing symlinked file: {path}')
    if path.exists() and path.read_text() == text:
        return False
    if path.exists():
        parent = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'arch-setups/backups'
        parent.mkdir(parents=True, exist_ok=True)
        backup = Path(tempfile.mkdtemp(prefix='sunshine-virtual-', dir=parent))
        shutil.copy2(path, backup/path.name)
        (backup/path.name).chmod(0o600)
    fd, stage = tempfile.mkstemp(prefix='.virtual-', dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            stream.write(text)
        os.replace(stage,path)
    finally:
        if os.path.exists(stage): os.unlink(stage)
    return True


def configure():
    root = profile_dir()
    marker = root/'.arch-setups-managed'
    if root.is_symlink() or root.parent.is_symlink():
        raise ValueError('Refusing symlinked virtual profile.')
    if root.exists() and any(root.iterdir()) and (not marker.is_file() or marker.read_text().strip()!=OWNER):
        raise ValueError('Refusing unowned virtual profile.')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    for private in (root/'sunshine_state.json', root/'credentials'):
        if private.is_symlink(): raise ValueError('Refusing symlinked virtual credentials.')
    changed = save(marker,OWNER+'\n')
    settings = {
        'sunshine_name':socket.gethostname()+' Virtual 1080p', 'capture':'wlr',
        'encoder':'vaapi', 'output_name':OUTPUT, 'port':'48989',
        'bind_address':'0.0.0.0', 'address_family':'ipv4', 'upnp':'disabled',
        'origin_web_ui_allowed':'wan', 'csrf_allowed_origins':'',
        'lan_encryption_mode':'2','wan_encryption_mode':'2','system_tray':'disabled',
        'hevc_mode':'2','av1_mode':'1',
    }
    path=root/'sunshine.conf'
    old=path.read_text() if path.exists() else ''
    lines=[]
    for line in old.splitlines():
        key=re.match(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=',line)
        if not key or key[1] not in settings: lines.append(line)
    content='\n'.join(lines).rstrip()
    content=(content+'\n' if content else '')+''.join(f'{k} = {v}\n' for k,v in settings.items())
    changed=save(path,content) or changed
    apps_path=root/'apps.json'
    apps=json.loads(apps_path.read_text()) if apps_path.exists() else {'env':{},'apps':[]}
    if not isinstance(apps.get('env'),dict) or not isinstance(apps.get('apps'),list):
        raise ValueError('Invalid virtual apps schema; env and apps are required.')
    command='"$(HOME)/.local/lib/arch-setups/sunshine-virtual.py" '
    entry={'name':'Virtual Desktop 1080p','image-path':'desktop.png','_arch_setups_virtual':True,
           'prep-cmd':[{'do':command+'prepare','undo':command+'finish'}]}
    found=False
    for i,app in enumerate(apps['apps']):
        if app.get('_arch_setups_virtual') is True:
            if found: raise ValueError('Duplicate managed virtual app entries.')
            apps['apps'][i]=entry; found=True
        elif app.get('name')==entry['name']:
            raise ValueError('Refusing to replace an unowned virtual app.')
    if not found: apps['apps'].append(entry)
    changed=save(apps_path,json.dumps(apps,indent=2)+'\n') or changed
    state=root/'sunshine_state.json'
    source=config_home()/'sunshine/sunshine_state.json'
    # Seed only the admin login once; never copy host identity or client trust.
    if not state.exists() and source.is_file():
        current=json.loads(source.read_text())
        auth={k:current[k] for k in ('username','password','salt') if k in current}
        if len(auth)==3: changed=save(state,json.dumps(auth,indent=2)+'\n') or changed
    # A host with no login lets anyone who reaches its admin port create one and
    # approve their own pairing PIN, so never open the port or start it unclaimed.
    login=json.loads(state.read_text()) if state.exists() else {}
    if not all(login.get(k) for k in ('username','password','salt')):
        raise ValueError('Create the admin login at https://localhost:47990 first, then rerun this installer.')
    return changed


def hypr(*args):
    return subprocess.check_output(['hyprctl',*args],text=True,timeout=5)


def monitors(include_inactive=False):
    args=['monitors']+(['all'] if include_inactive else [])+['-j']
    return json.loads(hypr(*args))


def runtime_file():
    return Path(os.environ.get('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}'))/'arch-sunshine-virtual.json'


def runtime_state():
    path=runtime_file()
    data=json.loads(path.read_text()) if path.is_file() else {}
    if data.get('session') != os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
        return {}
    return data


def write_runtime(data):
    # Runtime state contains only output ownership/focus; avoid persistent backups.
    path=runtime_file()
    if path.is_symlink(): raise ValueError('Refusing symlinked virtual runtime state.')
    fd,stage=tempfile.mkstemp(prefix='.virtual-runtime-',dir=path.parent)
    with os.fdopen(fd,'w') as stream: json.dump(data,stream)
    os.replace(stage,path)


def focus(name):
    hypr('eval',f'hl.dispatch(hl.dsp.focus({{monitor={json.dumps(name)}}}))')


def ensure_output():
    before=monitors()
    existing=next((m for m in monitors(include_inactive=True) if m['name']==OUTPUT),None)
    state=runtime_state()
    if existing and (not state or state.get('output_id') != existing.get('id')):
        raise ValueError('Refusing to adopt an unowned virtual output.')
    old_focus=next((m['name'] for m in before if m.get('focused')),None)
    if not existing:
        hypr('output','create','headless',OUTPUT)
        existing=next((m for m in monitors() if m['name']==OUTPUT),None)
        if not existing: raise ValueError('Hyprland did not create the named virtual output.')
        write_runtime({'session':os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'), 'output_id':existing['id']})
    hypr('eval',f'hl.monitor({{output={json.dumps(OUTPUT)}, mode="1920x1080@60", position="auto-right", scale=1}})')
    current=monitors()
    if old_focus and old_focus!=OUTPUT and any(m['name']==OUTPUT and m.get('focused') for m in current):
        focus(old_focus)
    for _ in range(10):
        output=next((m for m in monitors() if m['name']==OUTPUT),{})
        if output.get('width')==1920 and output.get('height')==1080 and output.get('scale')==1:
            return
        time.sleep(0.2)
    raise ValueError('Virtual output did not reach unscaled 1920x1080.')


def session_alive():
    signature=os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    # A missing session socket establishes that the owning compositor ended.
    # Missing environment alone cannot establish this; keep failures visible.
    if not signature: return True
    return (runtime_file().parent/'hypr'/signature/'.socket.sock').exists()


def cleanup():
    state=runtime_state()
    if not state: return
    try:
        existing=next((m for m in monitors(include_inactive=True) if m['name']==OUTPUT),None)
        if existing:
            if state.get('output_id')!=existing.get('id'):
                raise ValueError('Virtual output ownership changed; refusing removal.')
            hypr('output','remove',OUTPUT)
            if any(m['name']==OUTPUT for m in monitors(include_inactive=True)):
                raise ValueError('Hyprland did not remove the owned virtual output.')
    except (OSError,subprocess.SubprocessError):
        if session_alive(): raise
    runtime_file().unlink(missing_ok=True)


def prepare():
    ensure_output()
    state=runtime_state()
    state['previous_focus']=next((m['name'] for m in monitors() if m.get('focused')),None)
    write_runtime(state)
    focus(OUTPUT)


def finish():
    state=runtime_state(); previous=state.get('previous_focus'); current=monitors()
    if previous and previous!=OUTPUT and any(m['name']==previous for m in current) and any(m['name']==OUTPUT and m.get('focused') for m in current):
        focus(previous)


def run():
    ensure_output()
    root=profile_dir()
    os.environ['CONFIGURATION_DIRECTORY']=str(root.parent)
    args=['/usr/bin/sunshine',str(root/'sunshine.conf')]
    try:
        interfaces=json.loads(subprocess.check_output(['ip','-j','-4','address','show','up'],text=True,timeout=3))
        origins=[]
        for interface in interfaces:
            for address in interface.get('addr_info',[]):
                value=str(ipaddress.IPv4Address(address['local']))
                origins.append(f'https://{value}:48990')
        if origins: args.append('csrf_allowed_origins='+','.join(origins))
    except (OSError,ValueError,subprocess.SubprocessError): pass
    os.execv(args[0],args)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['configure','run','cleanup','prepare','finish'])
    parser.add_argument('--json',action='store_true',help='Report configuration changes as JSON.')
    args=parser.parse_args(argv)
    try:
        if args.command=='configure':
            changed=configure()
            print(json.dumps({'changed':changed}) if args.json else 'Virtual desktop configured.' if changed else 'Virtual desktop is already installed.')
        else: globals()[args.command]()
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        print(str(error),file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    sys.exit(main())
