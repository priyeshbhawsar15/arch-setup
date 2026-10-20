"""Run installers against temporary files and external-command session fixtures."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
PINS = {
    'crmne.hyprmoncfg': ('https://github.com/crmne/omarchy-hyprmoncfg.git', 'cf05a04a50339510cd1f9d547fb5f80556ae6599'),
    'mmsbrggr.per-monitor-workspaces': ('https://github.com/priyeshbhawsar15/omarchy-per-monitor-workspaces.git', '0292ebec608cd7d3907b8f9f9427c252b242edf2'),
    'tmn73.calendar': ('https://github.com/tmn73/omarchy-calendar.git', '08f5c01fb3b40322787ebfa9805429baa19beb5f'),
}

FIXTURE = r'''#!/usr/bin/python3
import json, os, pathlib, sys
home=pathlib.Path(os.environ['HOME']); sf=home/'fixture-state.json'
s=json.loads(sf.read_text()); name=pathlib.Path(sys.argv[0]).name; args=sys.argv[1:]
s['calls'].append([name,*args])
def finish(code=0, output=None):
    sf.write_text(json.dumps(s))
    if output is not None: print(output)
    raise SystemExit(code)
shell=home/'.config/omarchy/shell.json'
if name=='git':
    pid=pathlib.Path(args[1]).name
    pin=s['pins'].get(pid, ['', ''])
    if 'get-url' in args: finish(output=pin[0])
    if 'rev-parse' in args: finish(output=pin[1])
    finish()
if name=='omarchy':
    if args[:2]==['plugin','list']:
        d=json.loads(shell.read_text()); enabled={e.get('id') if isinstance(e,dict) else e for sec in d.get('bar',{}).get('layout',{}).values() for e in sec}
        enabled|={e['id'] for e in d.get('plugins',[]) if isinstance(e,dict)}
        finish(output=json.dumps([{'id':p,'enabled':p in enabled} for p in s['pins']]))
    if args[:2]==['plugin','enable']:
        d=json.loads(shell.read_text()); pid=args[2]
        layout=d['bar']['layout']
        if not any((e.get('id') if isinstance(e,dict) else e)==pid for sec in layout.values() for e in sec):
            layout['left' if pid.startswith('mmsbrggr.') else 'right'].append({'id':pid})
        shell.write_text(json.dumps(d)); finish()
    if args[:2]==['plugin','disable']:
        d=json.loads(shell.read_text()); pid=args[2]
        for sec,entries in d['bar']['layout'].items():
            changed=[]
            for e in entries:
                ident=e.get('id') if isinstance(e,dict) else e
                if ident!=pid: changed.append(e)
                elif pid.startswith('mmsbrggr.'):
                    changed.append({**e,'id':'omarchy.workspaces'} if isinstance(e,dict) else 'omarchy.workspaces')
            d['bar']['layout'][sec]=changed
        d['plugins']=[p for p in d.get('plugins',[]) if not isinstance(p,dict) or p.get('id')!=pid]
        shell.write_text(json.dumps(d)); finish()
    if args[:2]==['plugin','remove']:
        shutil=None
        import shutil
        shutil.rmtree(home/'.config/omarchy/plugins'/args[2]); finish()
    if args[:2]==['bar','set']:
        d=json.loads(shell.read_text())
        for entries in d['bar']['layout'].values():
            for e in entries:
                if isinstance(e,dict) and e.get('id')==args[2]: e[args[3]]=json.loads(args[4])
        shell.write_text(json.dumps(d)); finish()
    if args[:2]==['bar','move']:
        d=json.loads(shell.read_text());pid=args[2];found=None
        for entries in d['bar']['layout'].values():
            for e in entries[:]:
                if (e.get('id') if isinstance(e,dict) else e)==pid: entries.remove(e);found=e
        if found: d['bar']['layout']['left'].insert(1,found)
        shell.write_text(json.dumps(d));finish()
    if args[:2]==['pkg','add'] and args[2]=='hyprmoncfg': finish(1)
    if args[:3]==['pkg','aur','add']:
        source=pathlib.Path(os.environ['FIXTURE_SOURCE'])
        (pathlib.Path(os.environ['FIXTURE_BIN'])/'hyprmoncfg').symlink_to(source)
        finish()
    finish()
if name=='hyprmoncfg':
    if 'unmanage' in args:
        if s.get('unmanageFails'): finish(1)
        s['managed']=False;finish()
    if 'manage' in args: s['managed']=True;finish()
    if 'doctor' in args: finish(0 if s.get('managed') else 1)
    if 'status' in args:
        pending=s.get('statusPending',0)
        s['statusPending']=max(0,pending-1)
        finish(output=json.dumps({'daemon':{'running':not pending and s.get('active',{}).get('hyprmoncfgd.service',False)}}))
    if 'version' in args: finish(output='hyprmoncfg version 1.22.1')
    finish()
if name=='systemctl':
    operation=next((x for x in args if not x.startswith('-')), '')
    units=[x for x in args if x.endswith(('.service','.timer'))]
    if operation=='is-enabled': finish(0 if s.get('enabled',{}).get(units[-1]) else 1)
    if operation=='is-active': finish(0 if s.get('active',{}).get(units[-1]) else 1)
    if operation in ('enable','start','restart'):
        for unit in units:
            if operation=='enable': s.setdefault('enabled',{})[unit]=True
            if operation!='enable' or '--now' in args: s.setdefault('active',{})[unit]=True
    if operation in ('disable','stop'):
        for unit in units:
            if operation=='disable': s.setdefault('enabled',{})[unit]=False
            if operation=='stop' or '--now' in args: s.setdefault('active',{})[unit]=False
    finish()
if name=='gws':
    if args==['auth','status']: finish(output=json.dumps({'scopes':['https://www.googleapis.com/auth/calendar.readonly'] if s.get('auth') else []}))
    if args==['--version']: finish(output='gws 0.13.2')
    finish(99)
finish()
'''


class PluginLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='plugin-lifecycle-')
        self.base = Path(self.temp.name); self.home = self.base/'home'; self.bin=self.base/'bin'
        self.home.mkdir(); self.bin.mkdir()
        self.fixture=self.base/'fixture'; self.fixture.write_text(FIXTURE);self.fixture.chmod(0o755)
        for command in ('omarchy','omarchy-shell','git','systemctl','hyprmoncfg','gws','hyprctl'):
            (self.bin/command).symlink_to(self.fixture)
        for command in ('dirname','python3','jq','mkdir','mktemp','mv','cp','chmod','install','rm','date','sleep','cmp','cat','touch','readlink'):
            target=shutil.which(command)
            if target: (self.bin/command).symlink_to(target)
        self.state={'pins':PINS,'calls':[], 'managed':False,'active':{},'enabled':{}}
        self.write_state()
        self.shell=self.home/'.config/omarchy/shell.json';self.shell.parent.mkdir(parents=True)
        self.original={'bar':{'id':'hancore.shibumi.bar','layout':{
            'left':[{'id':'hancore.shibumi.control-center'}, {'id':'hancore.shibumi.workspaces','color':'custom'}, {'id':'hancore.shibumi.status'}],
            'center':[{'id':'hancore.shibumi.center','custom':'clock'}, {'id':'custom.middle'}],
            'right':[{'id':'custom.first'}, {'id':'hancore.shibumi.brightness','custom':True}, {'id':'custom.last'}]},'centerAnchor':'custom.middle'},
            'plugins':[{'id':'hancore.shibumi.state','shibumi':{'widgets':{'G13':{'enabled':True,'other':4}},'order':{'left':['G1','G2','G3']},'v1SlotRoles':{'left':['base','accent','extra']}}}], 'unrelated':{'keep':True}}
        self.write_shell(self.original)
        for pid in PINS:
            plugin=self.home/'.config/omarchy/plugins'/pid;(plugin/'.git').mkdir(parents=True)
        (self.home/'.config/omarchy/plugins/hancore.shibumi.state/lib/presentation').mkdir(parents=True)
        units=self.home/'.config/omarchy/plugins/tmn73.calendar/sync/systemd'; units.mkdir(parents=True)
        (units/'omarchy-calendar-sync.service').write_text('[Unit]\nDescription=Sync calendar\n[Service]\nType=oneshot\nExecStart=%h/.config/omarchy/plugins/tmn73.calendar/sync/omarchy-calendar-sync\n')
        (units/'omarchy-calendar-sync.timer').write_text('[Unit]\nDescription=Calendar timer\n[Timer]\nOnCalendar=*:0/5\nPersistent=true\n[Install]\nWantedBy=timers.target\n')
        sync=units.parent/'omarchy-calendar-sync';sync.write_text('#!/bin/bash\nexit 0\n');sync.chmod(0o755)
        (self.home/'.config/hypr').mkdir();(self.home/'.config/hypr/monitors.lua').write_text('-- personal monitors\n')
        self.env=dict(os.environ,HOME=str(self.home),PATH=str(self.bin),FIXTURE_SOURCE=str(self.fixture),FIXTURE_BIN=str(self.bin),XDG_STATE_HOME=str(self.home/'.local/state'),XDG_RUNTIME_DIR=str(self.base/'runtime'),DBUS_SESSION_BUS_ADDRESS='fixture')
        self.env.pop('HYPRLAND_INSTANCE_SIGNATURE',None)

    def tearDown(self): self.temp.cleanup()
    def write_state(self): (self.home/'fixture-state.json').write_text(json.dumps(self.state))
    def read_state(self): return json.loads((self.home/'fixture-state.json').read_text())
    def write_shell(self,data):self.shell.write_text(json.dumps(data))
    def read_shell(self):return json.loads(self.shell.read_text())
    def run_installer(self,name,*args,success=True):
        result=subprocess.run(['/usr/bin/bash',str(REPO/name),*args],env=self.env,capture_output=True,text=True)
        if success:self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        return result

    def test_missing_hyprmoncfg_uses_aur_then_reconciles_daemon(self):
        (self.bin/'hyprmoncfg').unlink()
        self.run_installer('install-hyprmoncfg.sh')
        state=self.read_state(); self.assertTrue(state['managed']);self.assertTrue(state['active'].get('hyprmoncfgd.service'));self.assertTrue(state['enabled'].get('hyprmoncfgd.service'))

    def test_hyprmoncfg_waits_for_daemon_ipc_before_manage(self):
        self.state['statusPending']=2;self.write_state()
        self.run_installer('install-hyprmoncfg.sh');self.assertTrue(self.read_state()['managed'])

    def test_hyprmoncfg_disable_unmanages_before_unloading_ui(self):
        self.run_installer('install-hyprmoncfg.sh');self.run_installer('install-hyprmoncfg.sh','--disable')
        state=self.read_state();self.assertFalse(state['managed']);self.assertEqual(self.read_shell(),self.original)
        calls=state['calls'];unmanage=next(i for i,c in enumerate(calls) if c[0]=='hyprmoncfg' and 'unmanage' in c)
        disabled=next(i for i,c in enumerate(calls) if c[:3]==['omarchy','plugin','disable'])
        self.assertLess(unmanage,disabled)
        self.assertNotIn(str(self.home/'.config/hypr/hyprland.lua'),str(calls))

    def test_failed_unmanage_keeps_plugin_enabled(self):
        self.run_installer('install-hyprmoncfg.sh');s=self.read_state();s['unmanageFails']=True;self.state=s;self.write_state()
        before=self.read_shell();self.run_installer('install-hyprmoncfg.sh','--disable',success=False)
        self.assertEqual(self.read_shell(),before)

    def test_hyprmoncfg_repeat_enable_preserves_settings_and_repairs_daemon(self):
        self.run_installer('install-hyprmoncfg.sh');s=self.read_state();s['active']['hyprmoncfgd.service']=False;self.state=s;self.write_state()
        self.run_installer('install-hyprmoncfg.sh');self.assertTrue(self.read_state()['active']['hyprmoncfgd.service'])
        self.run_installer('install-hyprmoncfg.sh','--disable');self.run_installer('install-hyprmoncfg.sh','--disable');self.assertEqual(self.read_shell(),self.original)

    def test_stock_bar_disable_does_not_add_shibumi_widgets(self):
        stock={'bar':{'layout':{'left':['omarchy.workspaces'],'center':['omarchy.clock'],'right':['omarchy.tray']}},'plugins':[]}
        for name in ('install-per-monitor-workspaces.sh','install-hyprmoncfg.sh','install-calendar.sh'):
            with self.subTest(name=name):
                self.write_shell(stock);self.run_installer(name,'--disable');self.assertEqual(self.read_shell(),stock)

    def test_bar_change_backups_are_private(self):
        self.run_installer('install-calendar.sh')
        backup_root=self.home/'.local/state/arch-setups/backups'
        backups=list(backup_root.glob('*-bar-*'))
        self.assertTrue(backups)
        for backup in backups: self.assertEqual(backup.stat().st_mode & 0o777,0o700)

    def test_pmw_roundtrip_restores_positions_settings_and_roles(self):
        self.run_installer('install-per-monitor-workspaces.sh');self.run_installer('install-per-monitor-workspaces.sh')
        self.run_installer('install-per-monitor-workspaces.sh','--disable');self.run_installer('install-per-monitor-workspaces.sh','--disable')
        self.assertEqual(self.read_shell(),self.original)

    def test_pmw_disable_after_switch_to_stock_preserves_stock_workspace(self):
        self.run_installer('install-per-monitor-workspaces.sh')
        stock={'bar':{'layout':{'left':['omarchy.workspaces'],'center':['omarchy.clock'],'right':[]}},'plugins':[]}
        self.write_shell(stock);self.run_installer('install-per-monitor-workspaces.sh','--disable');self.assertEqual(self.read_shell(),stock)

    def test_calendar_roundtrip_restores_full_center_and_anchor(self):
        self.run_installer('install-calendar.sh');self.run_installer('install-calendar.sh')
        self.run_installer('install-calendar.sh','--disable');self.run_installer('install-calendar.sh','--disable')
        self.assertEqual(self.read_shell(),self.original)

    def test_calendar_disable_preserves_user_center_edits(self):
        self.run_installer('install-calendar.sh');edited=self.read_shell();edited['bar']['layout']['center']=[{'id':'custom.replacement'}];edited['bar']['centerAnchor']='custom.replacement';self.write_shell(edited)
        self.run_installer('install-calendar.sh','--disable');self.assertEqual(self.read_shell(),edited)

    def test_calendar_authenticated_timer_lifecycle(self):
        self.state['auth']=True;self.write_state();config=self.home/'.config/omarchy/calendar-sync.json';config.write_text(json.dumps({'profile':str(self.home/'auth'),'gwsPath':str(self.bin/'gws')}))
        self.run_installer('install-calendar.sh');state=self.read_state();self.assertTrue(state['active'].get('omarchy-calendar-sync.timer'));self.assertTrue(state['enabled'].get('omarchy-calendar-sync.timer'))
        self.run_installer('install-calendar.sh','--disable');state=self.read_state();self.assertFalse(state['active'].get('omarchy-calendar-sync.timer'));self.assertFalse(state['enabled'].get('omarchy-calendar-sync.timer'))
        self.run_installer('install-calendar.sh','--remove');self.assertFalse((self.home/'.config/systemd/user/omarchy-calendar-sync.timer').exists())

    def test_hyprmoncfg_reconcile_preserves_existing_widget_settings(self):
        self.run_installer('install-hyprmoncfg.sh')
        d=self.read_shell()
        for entry in d['bar']['layout']['right']:
            if entry.get('id')=='crmne.hyprmoncfg': entry['customPanelPreference']='keep'
        self.write_shell(d);s=self.read_state();s['active']['hyprmoncfgd.service']=False;self.state=s;self.write_state()
        self.run_installer('install-hyprmoncfg.sh')
        self.assertTrue(any(e.get('customPanelPreference')=='keep' for e in self.read_shell()['bar']['layout']['right']))

    def test_calendar_disable_adopts_and_stops_legacy_upstream_timer(self):
        source=self.home/'.config/omarchy/plugins/tmn73.calendar/sync/systemd'
        units=self.home/'.config/systemd/user';units.mkdir(parents=True)
        for name in ('omarchy-calendar-sync.service','omarchy-calendar-sync.timer'): shutil.copy2(source/name,units/name)
        self.state['active']['omarchy-calendar-sync.timer']=True;self.state['enabled']['omarchy-calendar-sync.timer']=True;self.write_state()
        self.run_installer('install-calendar.sh','--disable')
        self.assertFalse(self.read_state()['active']['omarchy-calendar-sync.timer'])
        self.assertFalse(self.read_state()['enabled']['omarchy-calendar-sync.timer'])

    def test_calendar_custom_unit_is_preserved_before_any_write(self):
        units=self.home/'.config/systemd/user';units.mkdir(parents=True)
        custom=units/'omarchy-calendar-sync.timer';custom.write_text('custom timer contents')
        before=self.read_shell();result=self.run_installer('install-calendar.sh',success=False)
        self.assertNotEqual(result.returncode,0);self.assertEqual(custom.read_text(),'custom timer contents')
        self.assertFalse((units/'omarchy-calendar-sync.service').exists());self.assertEqual(self.read_shell(),before)

    def test_calendar_disable_does_not_stop_user_replaced_timer(self):
        self.state['auth']=True;self.write_state()
        (self.home/'.config/omarchy/calendar-sync.json').write_text(json.dumps({'gwsPath':str(self.bin/'gws')}))
        self.run_installer('install-calendar.sh')
        timer=self.home/'.config/systemd/user/omarchy-calendar-sync.timer';timer.write_text('replacement user timer')
        self.run_installer('install-calendar.sh','--disable')
        self.assertTrue(self.read_state()['active']['omarchy-calendar-sync.timer'])
        self.assertEqual(timer.read_text(),'replacement user timer')

    def test_calendar_absent_anchor_and_stock_center_roundtrip(self):
        stock={'bar':{'layout':{'left':[],'center':['omarchy.clock',{'id':'custom.more','setting':7}],'right':[]}},'plugins':[]}
        self.write_shell(stock);self.run_installer('install-calendar.sh');self.run_installer('install-calendar.sh','--disable')
        self.assertEqual(self.read_shell(),stock)

    def test_calendar_unauthenticated_does_not_start_sync(self):
        result=self.run_installer('install-calendar.sh');self.assertIn('OAuth',result.stdout)
        self.assertFalse(self.read_state()['active'].get('omarchy-calendar-sync.timer',False))
        self.assertTrue((self.home/'.config/systemd/user/omarchy-calendar-sync.timer').exists())

    def test_calendar_remove_backs_up_actual_files_and_bar(self):
        config=self.home/'.config/omarchy/calendar-sync.json';config.write_text('{"calendars":{"exclude":["personal"]}}')
        events=self.home/'.local/state/omarchy/calendar-events.json';events.parent.mkdir(parents=True);events.write_text('{"events":[]}')
        self.run_installer('install-calendar.sh');self.run_installer('install-calendar.sh','--remove')
        backups=self.home/'.local/state/arch-setups/backups'
        self.assertTrue(list(backups.rglob('calendar-events.json')));self.assertTrue(list(backups.rglob('calendar-sync.json')));self.assertTrue(list(backups.rglob('shell.json')))

if __name__=='__main__': unittest.main()
