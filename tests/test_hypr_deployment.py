"""Hyprland deployment and generated-rule integration, without a desktop."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('deployment_monitor_layout',REPO/'hypr/scripts/monitor-layout.py')
layout=importlib.util.module_from_spec(spec);spec.loader.exec_module(layout)
PACKAGE=b'-- isolated package-entrypoint fixture, never deployed to the real host\n'
CUSTOM_BLOCK=b'''\ndo
  local path = os.getenv("HOME") .. "/.config/hypr/hyprmoncfg-monitors.lua"
  local file = io.open(path, "r")
  if file then file:close(); dofile(path) end
  local sm_path = os.getenv("HOME") .. "/.local/state/omarchy/toggles/hypr/desktop-single-monitor.lua"
  local sm_file = io.open(sm_path, "r")
  if sm_file then sm_file:close(); dofile(sm_path) end
end
'''
UPSTREAM_BLOCK=b'''\n-- Added by hyprmoncfg: its generated monitor rules load last, so nothing before this can override the applied layout.
do local path = os.getenv("HOME") .. "/.config/hypr/hyprmoncfg-monitors.lua"; local file = io.open(path, "r"); if file then file:close(); dofile(path) end end
'''

class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='hypr-deployment-');self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.home=self.base/'home';self.home.mkdir();self.repo=self.base/'repo';self.repo.mkdir()
        self.config=self.home/'.config/hypr';self.config.mkdir(parents=True)
        self.system=self.base/'system';self.sddm=self.system/'etc/sddm.conf.d';self.sddm.mkdir(parents=True)
        self.package=self.system/'usr/share/omarchy/config/hypr/hyprland.lua';self.package.parent.mkdir(parents=True);self.package.write_bytes(PACKAGE)
        for relative in ('hypr','sddm'):
            shutil.copytree(REPO/relative,self.repo/relative)
        shutil.copy2(REPO/'lib.sh',self.repo/'lib.sh');shutil.copy2(REPO/'monitor-layout.json',self.repo/'monitor-layout.json')
        text=(REPO/'install-hyprland.sh').read_text().replace('/usr/share/omarchy',str(self.system/'usr/share/omarchy')).replace('/etc/sddm.conf.d',str(self.sddm))
        self.installer=self.repo/'install-hyprland.sh';self.installer.write_text(text)
        self.bin=self.base/'bin';self.bin.mkdir()
        for command,content in {'omarchy':'exit 0','pkexec':'exec "$@"','sudo':'exec "$@"'}.items():
            path=self.bin/command;path.write_text('#!/bin/bash\n'+content+'\n');path.chmod(0o755)
        self.env=dict(os.environ,HOME=str(self.home),PATH=str(self.bin)+':'+os.environ['PATH'],XDG_STATE_HOME=str(self.home/'.local/state'))
        self.env.pop('HYPRLAND_INSTANCE_SIGNATURE',None)
        self.state_patch=patch.dict(os.environ, {'XDG_STATE_HOME': str(self.home/'.local/state')})
        self.state_patch.start(); self.addCleanup(self.state_patch.stop)
        (self.config/'hyprland.lua').write_bytes(PACKAGE)
        (self.sddm/'10-wayland.conf').write_bytes((REPO/'sddm/10-wayland.conf').read_bytes())

    def run_install(self):
        return subprocess.run(['bash',str(self.installer)],env=self.env,capture_output=True,text=True)

    def backups(self):return list((self.home/'.local/state/arch-setups/backups').glob('*'))

    def test_changed_lua_helpers_and_sddm_are_backed_up_privately(self):
        originals={self.config/'bindings.lua':b'-- keep custom bindings\n',self.config/'scripts/shell-recover.sh':b'#!/bin/bash\necho custom\n',self.sddm/'10-wayland.conf':b'custom login config\n',self.sddm/'10-wayland.conf.pacnew':b'package update candidate\n'}
        for path,content in originals.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
        result=self.run_install();self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        backed_files=[p for b in self.backups() for p in b.rglob('*') if p.is_file()]
        for content in originals.values():self.assertTrue(any(p.read_bytes()==content for p in backed_files),repr(content))
        for backup in self.backups():self.assertEqual(backup.stat().st_mode & 0o777,0o700)

    def test_known_legacy_includes_restore_exact_package_entrypoint(self):
        original=PACKAGE+CUSTOM_BLOCK+UPSTREAM_BLOCK;entry=self.config/'hyprland.lua';entry.write_bytes(original);entry.chmod(0o600)
        result=self.run_install();self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(entry.read_bytes(),PACKAGE);self.assertEqual(entry.stat().st_mode & 0o777,0o600)
        self.assertTrue(any(p.read_bytes()==original for b in self.backups() for p in b.rglob('hyprland.lua')))

    def test_unknown_entrypoint_edits_refuse_before_replacing_modules(self):
        original=PACKAGE+CUSTOM_BLOCK+b'-- private extra config\n';entry=self.config/'hyprland.lua';entry.write_bytes(original)
        bindings=self.config/'bindings.lua';bindings.write_text('-- retain me')
        result=self.run_install();self.assertNotEqual(result.returncode,0)
        self.assertEqual(entry.read_bytes(),original);self.assertEqual(bindings.read_text(),'-- retain me')

    def test_matching_helper_content_repairs_executable_permission(self):
        first=self.run_install();self.assertEqual(first.returncode,0,first.stderr)
        helper=self.config/'scripts/shell-recover.sh';helper.chmod(0o600)
        second=self.run_install();self.assertEqual(second.returncode,0,second.stderr)
        self.assertTrue(os.access(helper,os.X_OK))

    def test_final_monitor_install_keeps_include_and_plugin_source_intact(self):
        config=layout.load_config(REPO/'monitor-layout.json');omarchy=self.home/'.config/omarchy';core=omarchy/'plugins/hancore.shibumi.bar/core';core.mkdir(parents=True)
        originals={name:('unmodified fork '+name).encode() for name in ('GroupSlot.qml','BarSection.qml')}
        for name,content in originals.items():(core/name).write_bytes(content)
        shell=omarchy/'shell.json';shell.write_text(json.dumps({'plugins':[{'id':'hancore.shibumi.state','shibumi':{'presentation':{'other':'keep'}}},{'id':'unrelated','secret':'local-only'}]}));shell.chmod(0o600)
        with patch.object(Path,'home',return_value=self.home),patch.object(layout,'live_monitors',return_value=[]):
            layout.install(config,REPO/'monitor-layout.json',REPO,True)
            before=(self.config/'monitors.lua').read_bytes()
            layout.install(config,REPO/'monitor-layout.json',REPO)
            self.assertEqual((self.config/'monitors.lua').read_bytes(),before)
        for name,content in originals.items():self.assertEqual((core/name).read_bytes(),content)
        plugins=json.loads(shell.read_text())['plugins'];self.assertEqual(plugins[0]['shibumi']['presentation'],{'other':'keep','mainMonitorDescription':'Microstep MAG321UP OLED'});self.assertEqual(plugins[1],{'id':'unrelated','secret':'local-only'})
        self.assertEqual(shell.stat().st_mode & 0o777,0o600)
        self.assertIn(b'hyprmoncfg-monitors.lua',before)
        for backup in self.backups():self.assertEqual(backup.stat().st_mode & 0o777,0o700)

    def test_widget_backup_preserves_credentials_and_is_private(self):
        config=layout.load_config(REPO/'monitor-layout.json');path=self.home/'.config/omarchy/obsidian-tasks.json';path.parent.mkdir(parents=True);path.write_text('{"targetScreen":"old","token":"local-only"}');path.chmod(0o600)
        outputs=[{'name':'DP-99','description':config['monitors']['side_left']['description']}]
        with patch.object(Path,'home',return_value=self.home),patch.object(layout,'live_monitors',return_value=outputs):layout.configure_widget(config,'.config/omarchy/obsidian-tasks.json')
        self.assertEqual(json.loads(path.read_text())['token'],'local-only');self.assertEqual(path.stat().st_mode & 0o777,0o600)
        for backup in self.backups():self.assertEqual(backup.stat().st_mode & 0o777,0o700)

    @unittest.skipUnless(shutil.which('lua'),'Lua interpreter required')
    def test_generated_workspaces_are_gated_and_global_api_is_unchanged(self):
        generated=self.config/'hyprmoncfg-monitors.lua';generated.write_text('hl.monitor({output="generated",mode="preferred"})\nhl.workspace_rule({workspace="99"})\n')
        rendered=self.config/'monitors.lua';rendered.write_text(layout.render(layout.load_config(REPO/'monitor-layout.json'),REPO/'hypr/monitors.lua'))
        marker=self.home/'.local/state/arch-setups/crmne.hyprmoncfg/managed';marker.parent.mkdir(parents=True)
        toggle=self.home/'.local/state/omarchy/toggles/hypr/per-monitor-workspaces.lua';toggle.parent.mkdir(parents=True)
        harness='''local rules,generated=0,0
local workspace=function() rules=rules+1 end
hl={env=function() end,monitor=function(m) if m.output=='generated' then generated=generated+1 end end,workspace_rule=workspace}
dofile(os.getenv('HOME')..'/.config/hypr/monitors.lua')
assert(hl.workspace_rule==workspace)
print(rules,generated)
'''
        def run():
            out=subprocess.run(['lua','-'],input=harness,env=self.env,capture_output=True,text=True);self.assertEqual(out.returncode,0,out.stderr);return out.stdout.strip()
        self.assertEqual(run(),'6\t0');marker.touch();self.assertEqual(run(),'7\t1');toggle.touch();self.assertEqual(run(),'0\t1')

if __name__=='__main__':unittest.main()
