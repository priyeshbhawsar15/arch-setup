"""Host portability, private settings and successful-only lifecycle preferences."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HostPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = load('portable_monitor_policy', 'hypr/scripts/monitor-layout.py')

    def test_laptop_needs_no_side_displays_or_hdr(self):
        config = self.policy.load_config(ROOT / 'profiles/laptop.json')
        outputs = [{'name': 'eDP-1', 'description': 'Any laptop', 'focused': True}]
        self.assertEqual(self.policy.resolve(config, outputs)['main']['name'], 'eDP-1')
        text = self.policy.render(config, ROOT / 'hypr/monitors.lua')
        self.assertNotIn('3840', text)
        self.assertNotIn('hdr', text)
        self.assertNotIn('@monitor:', text)
        self.assertEqual(self.policy.single_monitor_lua(config, outputs), '')
        with self.assertRaisesRegex(ValueError, 'not configured'):
            self.policy.canvas(config, outputs)

    def test_unicode_display_names_render_as_valid_lua_not_json_unicode_escapes(self):
        config = self.policy.load_config(ROOT / 'profiles/laptop.json')
        config['monitors']['main'] = {'description': 'Écran principal', 'mode': 'preferred'}
        text = self.policy.render(config, ROOT / 'hypr/monitors.lua')
        self.assertIn('Écran principal', text)
        self.assertNotIn('\\u00', text)

    def test_arbitrary_home_paths_are_not_widget_destinations(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = json.loads((ROOT / 'profiles/laptop.json').read_text())
            config['widgetTargets'] = {'.ssh/authorized_keys': 'main'}
            path = Path(tmp) / 'bad.json'
            path.write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError, 'supported widget'):
                self.policy.load_config(path)


class PrivateSettingsTests(unittest.TestCase):
    def test_workflow_seed_selects_executor_without_assuming_pi(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            seed = home / 'workflow.json'
            seed.write_text('{"enabled":true,"executor":{"provider":"codex","model":"chosen-by-user"}}')
            with patch.dict(os.environ, {'HOME': str(home), 'XDG_CONFIG_HOME': str(home / 'config'), 'T3_PLANNER_EXECUTOR_SEED_CONFIG': str(seed), 'T3_PLANNER_EXECUTOR_RUNTIME_DIR': str(home / 'runtime')}):
                inputs = load('external_planner_inputs', 'config/setup-inputs.py')
                self.assertEqual(inputs.planner_cli(), 'codex')
            self.assertEqual(list(home.iterdir()), [seed])

    def test_secret_file_is_materialized_privately_without_disclosing_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            secret = home / 'token'
            secret.write_text('PRIVATE_TEST_TOKEN')
            secret.chmod(0o600)
            settings = home / 'settings.json'
            settings.write_text(json.dumps({'omniroute-quota': {'endpoint': 'https://quota.example.net', 'tokenFile': str(secret)}}))
            result = subprocess.run(['/usr/bin/python3', str(ROOT / 'config/setup-inputs.py'), 'widget', 'omniroute-quota'],
                env=dict(os.environ, HOME=str(home), XDG_STATE_HOME=str(home / 'state'), ARCH_SETUPS_SETTINGS=str(settings)), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('PRIVATE_TEST_TOKEN', result.stdout + result.stderr)
            path = home / '.config/omarchy/omniroute-quota.json'
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text())['token'], 'PRIVATE_TEST_TOKEN')

    def test_home_assistant_starts_with_no_personal_url_or_entity_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = dict(os.environ, HOME=str(home), XDG_STATE_HOME=str(home / 'state'))
            env.pop('ARCH_SETUPS_SETTINGS', None)
            result = subprocess.run(['/usr/bin/python3', str(ROOT / 'config/setup-inputs.py'), 'widget', 'home-assistant'], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads((home / '.config/omarchy/home-assistant.json').read_text())
            self.assertEqual(data['baseUrl'], '')
            self.assertEqual(data['climate'], '')
            self.assertEqual(data['switches'], {})
            self.assertEqual(data['tokenFile'], str(home / '.config/omarchy/hass/token'))

    def test_home_assistant_retains_a_token_reference_not_inline_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            token = home / 'token'
            token.write_text('NEVER_INLINE_HA_TOKEN')
            token.chmod(0o600)
            settings = home / 'settings.json'
            settings.write_text(json.dumps({'home-assistant': {'baseUrl': 'https://ha.example.net', 'tokenFile': str(token), 'switches': {'Desk': 'switch.desk'}}}))
            result = subprocess.run(['/usr/bin/python3', str(ROOT / 'config/setup-inputs.py'), 'widget', 'home-assistant'],
                env=dict(os.environ, HOME=str(home), XDG_STATE_HOME=str(home / 'state'), ARCH_SETUPS_SETTINGS=str(settings)), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            text = (home / '.config/omarchy/home-assistant.json').read_text()
            self.assertNotIn('NEVER_INLINE_HA_TOKEN', text + result.stdout + result.stderr)
            self.assertEqual(json.loads(text)['tokenFile'], str(token))
            self.assertEqual(json.loads(text)['switches'], {'Desk': 'switch.desk'})

    def test_foreign_permissions_are_rejected_without_creating_widget_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            token = home / 'token'
            token.write_text('NEVER_PRINT_ME')
            token.chmod(0o644)
            settings = home / 'settings.json'
            settings.write_text(json.dumps({'immich-photo-frame': {'apiKeyFile': str(token)}}))
            result = subprocess.run(['/usr/bin/python3', str(ROOT / 'config/setup-inputs.py'), 'widget', 'immich-photo-frame'],
                env=dict(os.environ, HOME=str(home), XDG_STATE_HOME=str(home / 'state'), ARCH_SETUPS_SETTINGS=str(settings)), capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('NEVER_PRINT_ME', result.stdout + result.stderr)
            self.assertFalse((home / '.config/omarchy/immich-photo-frame.json').exists())


class LifecycleChoiceTests(unittest.TestCase):
    def test_rollback_traps_do_not_suppress_successful_disable_preference(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            script = home / 'install-weather-widget.sh'
            script.write_text('#!/bin/bash\nset -euo pipefail\nSCRIPT_DIR=' + str(ROOT) + '\nsource "$SCRIPT_DIR/lib.sh"\nfeature_lifecycle "$0" "$@"\ntrap \'printf cleanup > "$HOME/cleaned"\' EXIT\nexit "${BODY_STATUS:-0}"\n')
            env = dict(os.environ, HOME=str(home), XDG_STATE_HOME=str(home / 'state'), ARCH_SETUPS_PROFILE=str(ROOT / 'features.json'))
            env.pop('ARCH_SETUPS_AUTOMATED', None)
            env.pop('ARCH_SETUPS_LIFECYCLE_RUNNING', None)
            result = subprocess.run(['bash', str(script), '--disable'], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            state = home / 'state/arch-setups/features.json'
            self.assertIs(json.loads(state.read_text())['install-weather-widget.sh'], False)
            before = state.read_bytes()
            result = subprocess.run(['bash', str(script)], env=dict(env, BODY_STATUS='3'), capture_output=True, text=True)
            self.assertEqual(result.returncode, 3)
            self.assertEqual(state.read_bytes(), before)
            self.assertTrue((home / 'cleaned').exists())


if __name__ == '__main__':
    unittest.main()
