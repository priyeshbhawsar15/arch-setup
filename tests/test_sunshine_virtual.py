import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module():
    spec = importlib.util.spec_from_file_location('virtual_host', ROOT / 'sunshine/virtual-desktop.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class VirtualProfileTests(unittest.TestCase):
    def test_isolated_profile_preserves_main_and_copies_only_admin_login(self):
        helper = module()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = dict(HOME=tmp, XDG_CONFIG_HOME=str(home/'config'), XDG_STATE_HOME=str(home/'state'))
            main = home/'config/sunshine'
            main.mkdir(parents=True)
            state = {'username':'admin','password':'hash','salt':'salt','root':{'uniqueid':'main-host','named_devices':[{'cert':'main-client'}]}}
            (main/'sunshine_state.json').write_text(json.dumps(state))
            (main/'sunshine.conf').write_text('capture = kms\noutput_name = DP-5\n')
            with patch.dict(os.environ, env):
                self.assertTrue(helper.configure())
                profile = helper.profile_dir()
                content = (profile/'sunshine.conf').read_text()
                self.assertIn('capture = wlr', content)
                self.assertIn('encoder = vaapi', content)
                self.assertIn('port = 48989', content)
                self.assertIn('output_name = SUNSHINE-VIRTUAL-1080P', content)
                apps = json.loads((profile/'apps.json').read_text())
                self.assertEqual(apps['env'], {})
                self.assertEqual(apps['apps'][0]['name'], 'Virtual Desktop 1080p')
                copied = json.loads((profile/'sunshine_state.json').read_text())
                self.assertEqual(copied, {'username':'admin','password':'hash','salt':'salt'})
                self.assertEqual((profile/'sunshine_state.json').stat().st_mode & 0o777, 0o600)
                self.assertEqual((main/'sunshine.conf').read_text(), 'capture = kms\noutput_name = DP-5\n')
                self.assertEqual(json.loads((main/'sunshine_state.json').read_text()), state)
                apps['apps'].append({'name':'User app','image-path':'desktop.png'})
                (profile/'apps.json').write_text(json.dumps(apps, indent=2)+'\n')
                helper.configure()
                self.assertEqual(len(json.loads((profile/'apps.json').read_text())['apps']),2)
                self.assertFalse(helper.configure())

    def test_unclaimed_host_is_refused_before_it_can_be_started(self):
        helper=module()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, HOME=tmp, XDG_CONFIG_HOME=tmp, XDG_STATE_HOME=tmp):
            with self.assertRaisesRegex(ValueError,'admin login'):
                helper.configure()
            main=Path(tmp)/'sunshine'; main.mkdir()
            (main/'sunshine_state.json').write_text(json.dumps({'root':{'uniqueid':'main-host'}}))
            with self.assertRaisesRegex(ValueError,'admin login'):
                helper.configure()

    def test_foreign_profile_is_not_adopted(self):
        helper=module()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, HOME=tmp, XDG_CONFIG_HOME=tmp):
            directory=helper.profile_dir(); directory.mkdir(parents=True)
            path=directory/'sunshine.conf'; path.write_text('personal configuration\n')
            with self.assertRaisesRegex(ValueError,'unowned'):
                helper.configure()
            self.assertEqual(path.read_text(),'personal configuration\n')

    def test_existing_unowned_output_is_never_removed_or_adopted(self):
        helper=module()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, HOME=tmp, XDG_RUNTIME_DIR=tmp, HYPRLAND_INSTANCE_SIGNATURE='session'):
            with patch.object(helper,'monitors',return_value=[{'name':helper.OUTPUT}]):
                with self.assertRaisesRegex(ValueError,'unowned'):
                    helper.ensure_output()
                with patch.object(helper,'hypr') as dispatch:
                    helper.cleanup()
                    dispatch.assert_not_called()


class VirtualCleanupTests(unittest.TestCase):
    def test_different_compositor_session_does_not_touch_outputs(self):
        helper=module()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, XDG_RUNTIME_DIR=tmp, HYPRLAND_INSTANCE_SIGNATURE='new-session'):
            helper.write_runtime({'session':'old-session','output_id':7})
            with patch.object(helper,'monitors') as inspect:
                helper.cleanup()
                inspect.assert_not_called()

    def test_disabled_owned_output_is_removed(self):
        helper=module()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, XDG_RUNTIME_DIR=tmp, HYPRLAND_INSTANCE_SIGNATURE='session'):
            helper.write_runtime({'session':'session','output_id':7})
            outputs=[{'name':helper.OUTPUT,'id':7,'disabled':True}]
            def monitors(include_inactive=False):
                return list(outputs) if include_inactive else []
            def dispatch(*args):
                if args==('output','remove',helper.OUTPUT): outputs.clear()
                else: raise AssertionError(args)
            with patch.object(helper,'monitors',side_effect=monitors), patch.object(helper,'hypr',side_effect=dispatch):
                helper.cleanup()
            self.assertEqual(outputs,[])
            self.assertFalse(helper.runtime_file().exists())

    def test_failed_removal_keeps_ownership_for_retry(self):
        import subprocess
        helper=module()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, XDG_RUNTIME_DIR=tmp, HYPRLAND_INSTANCE_SIGNATURE='session'):
            helper.write_runtime({'session':'session','output_id':7})
            with patch.object(helper,'session_alive',return_value=True), patch.object(helper,'monitors',return_value=[{'name':helper.OUTPUT,'id':7}]), patch.object(helper,'hypr',side_effect=subprocess.CalledProcessError(1,['hyprctl'])):
                with self.assertRaises(subprocess.CalledProcessError): helper.cleanup()
            self.assertTrue(helper.runtime_file().exists())

    def test_owned_output_creation_focus_restore_and_removal(self):
        helper=module()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, XDG_RUNTIME_DIR=tmp, HYPRLAND_INSTANCE_SIGNATURE='session'):
            outputs=[{'name':'PHYSICAL','id':0,'focused':True}]
            def dispatch(*args):
                if args==('output','create','headless',helper.OUTPUT):
                    outputs.append({'name':helper.OUTPUT,'id':7,'focused':False})
                elif args==('output','remove',helper.OUTPUT): outputs.pop()
                elif args[0]=='eval' and args[1].startswith('hl.monitor('):
                    outputs[-1].update(width=1920,height=1080,scale=1)
                elif args[0]=='eval' and 'hl.dsp.focus' in args[1]:
                    for output in outputs: output['focused']=json.dumps(output['name']) in args[1]
                else: raise AssertionError(args)
                return 'ok'
            with patch.object(helper,'monitors',side_effect=lambda **_: outputs), patch.object(helper,'hypr',side_effect=dispatch):
                helper.prepare()
                self.assertTrue(outputs[-1]['focused'])
                self.assertEqual(helper.runtime_state()['previous_focus'],'PHYSICAL')
                helper.finish()
                self.assertTrue(outputs[0]['focused'])
                helper.cleanup()
                self.assertEqual([output['name'] for output in outputs],['PHYSICAL'])
                self.assertFalse(helper.runtime_file().exists())

    def test_cleanup_cli_reports_live_failure(self):
        helper=module()
        with patch.object(helper,'cleanup',side_effect=ValueError('Removal failed')):
            self.assertEqual(helper.main(['cleanup']),1)

    def test_ended_compositor_cleanup_discards_only_stale_state(self):
        import subprocess
        helper=module()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, XDG_RUNTIME_DIR=tmp, HYPRLAND_INSTANCE_SIGNATURE='session'):
            helper.write_runtime({'session':'session','output_id':7})
            with patch.object(helper,'session_alive',return_value=False), patch.object(helper,'monitors',side_effect=subprocess.CalledProcessError(1,['hyprctl'])):
                helper.cleanup()
            self.assertFalse(helper.runtime_file().exists())

    def test_output_id_mismatch_preserves_state_and_output(self):
        helper=module()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, XDG_RUNTIME_DIR=tmp, HYPRLAND_INSTANCE_SIGNATURE='session'):
            helper.write_runtime({'session':'session','output_id':7})
            with patch.object(helper,'monitors',return_value=[{'name':helper.OUTPUT,'id':8}]), patch.object(helper,'hypr') as dispatch:
                with self.assertRaisesRegex(ValueError,'ownership'): helper.cleanup()
                dispatch.assert_not_called()
            self.assertTrue(helper.runtime_file().exists())


class VirtualInstallerTests(unittest.TestCase):
    def test_unchanged_enable_does_not_restart_active_host(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp); binaries=home/'bin'; binaries.mkdir()
            log=home/'systemctl.log'
            commands={'sunshine':'exit 0','hyprctl':'exit 0','pkexec':'exit 0',
                      'systemctl':'printf "%s\\n" "$*" >> "$VIRTUAL_TEST_LOG"'}
            for name,body in commands.items():
                path=binaries/name; path.write_text('#!/bin/bash\n'+body+'\n'); path.chmod(0o755)
            env=dict(os.environ,HOME=tmp,XDG_CONFIG_HOME=str(home/'config'),XDG_STATE_HOME=str(home/'state'),
                     XDG_RUNTIME_DIR=tmp,HYPRLAND_INSTANCE_SIGNATURE='session',ARCH_SETUPS_AUTOMATED='1',
                     VIRTUAL_TEST_LOG=str(log),PATH=str(binaries)+':'+os.environ['PATH'])
            main=home/'config/sunshine'; main.mkdir(parents=True)
            (main/'sunshine_state.json').write_text(json.dumps({'username':'admin','password':'hash','salt':'salt'}))
            for invocation in range(2):
                log.write_text('')
                result=subprocess.run(['bash',str(ROOT/'install-virtual-desktop.sh'),'--enable'],env=env,text=True,capture_output=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                calls=log.read_text()
                if invocation==0: self.assertIn('--user restart arch-sunshine-virtual.service',calls)
                else:
                    self.assertNotIn('restart',calls)
                    self.assertIn('--user start arch-sunshine-virtual.service',calls)
                    self.assertIn('already installed',result.stdout)

    def test_disable_without_installed_unit_still_cleans_up(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp); binaries=home/'bin'; binaries.mkdir(); log=home/'calls.log'
            commands={'pkexec':'printf "pkexec %s\\n" "$*" >> "$VIRTUAL_TEST_LOG"',
                      'systemctl':'printf "%s\\n" "$*" >> "$VIRTUAL_TEST_LOG"; [[ "$*" != *" cat "* ]] || exit 1; [[ "$*" != *"--now"* ]] || exit 1'}
            for name,body in commands.items():
                path=binaries/name; path.write_text('#!/bin/bash\n'+body+'\n'); path.chmod(0o755)
            env=dict(os.environ,HOME=tmp,XDG_CONFIG_HOME=str(home/'config'),XDG_STATE_HOME=str(home/'state'),
                     XDG_RUNTIME_DIR=tmp,HYPRLAND_INSTANCE_SIGNATURE='session',ARCH_SETUPS_AUTOMATED='1',
                     VIRTUAL_TEST_LOG=str(log),PATH=str(binaries)+':'+os.environ['PATH'])
            result=subprocess.run(['bash',str(ROOT/'install-virtual-desktop.sh'),'--disable'],env=env,text=True,capture_output=True,stdin=subprocess.DEVNULL)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('virtual-firewall.sh disable',log.read_text())
            self.assertNotIn('--now',log.read_text())
