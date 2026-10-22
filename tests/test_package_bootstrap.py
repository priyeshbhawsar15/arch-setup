"""Cold-ISO preparation policy; no real package/update commands are executed."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('package_bootstrap', ROOT / 'config/package-bootstrap.py')
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)
CHECK_DATABASES = bootstrap.check_databases


class PackageBootstrapTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='cold-iso-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.marker = self.root / 'state/arch-setups/initial-system-update.json'
        self.data = {'ready': False, 'missing': ['core', 'extra']}
        for target, replacement in (
            ('marker_path', lambda: self.marker),
            ('boot_id', lambda: 'first-boot'),
            ('check_databases', lambda: dict(self.data)),
            ('restart_reasons', lambda **_: []),
        ):
            context = patch.object(bootstrap, target, replacement)
            context.start(); self.addCleanup(context.stop)
        context = patch.object(bootstrap.shutil, 'which', return_value=None)
        context.start(); self.addCleanup(context.stop)
        context = contextlib.redirect_stdout(io.StringIO())
        context.__enter__(); self.addCleanup(context.__exit__, None, None, None)
        context = contextlib.redirect_stderr(io.StringIO())
        context.__enter__(); self.addCleanup(context.__exit__, None, None, None)

    def finish(self):
        self.data.update(ready=True, missing=[])
        return 0

    def test_warm_system_does_not_update_or_write(self):
        self.data.update(ready=True, missing=[])
        with patch.object(bootstrap, 'perform_update') as update:
            self.assertEqual(bootstrap.prepare(), 0)
            update.assert_not_called()
        self.assertFalse(self.marker.parent.exists())

    def test_noninteractive_cold_system_requires_explicit_approval(self):
        with patch.object(bootstrap.sys.stdin, 'isatty', return_value=False), patch.object(bootstrap, 'perform_update') as update:
            self.assertEqual(bootstrap.prepare(), 2)
            update.assert_not_called()
        self.assertFalse(self.marker.parent.exists())

    def test_interactive_decline_does_not_update_or_write(self):
        with patch.object(bootstrap.sys.stdin, 'isatty', return_value=True), patch('builtins.input', return_value='no'), patch.object(bootstrap, 'perform_update') as update:
            self.assertEqual(bootstrap.prepare(), 2)
            update.assert_not_called()
        self.assertFalse(self.marker.parent.exists())

    def test_approved_update_completes_once_and_keeps_marker_private(self):
        def update():
            self.assertEqual(self.marker.stat().st_mode & 0o777, 0o600)
            return self.finish()
        with patch.object(bootstrap, 'perform_update', side_effect=update) as action:
            self.assertEqual(bootstrap.prepare(True), 0)
            self.assertEqual(bootstrap.prepare(True), 0)
            self.assertEqual(action.call_count, 1)
        self.assertFalse(self.marker.exists())

    def test_failed_update_requires_recovery_even_if_indexes_now_exist(self):
        def fail_after_sync():
            self.data.update(ready=True, missing=[])
            return 1
        with patch.object(bootstrap, 'perform_update', side_effect=fail_after_sync):
            self.assertEqual(bootstrap.prepare(True), 1)
        self.assertEqual(json.loads(self.marker.read_text())['status'], 'failed')
        with patch.object(bootstrap, 'perform_update', side_effect=self.finish) as update:
            self.assertEqual(bootstrap.prepare(True), 0)
            update.assert_called_once()

    def test_restart_stops_setup_and_new_boot_resumes_without_reupdating(self):
        with patch.object(bootstrap, 'perform_update', side_effect=self.finish), patch.object(bootstrap, 'restart_reasons', return_value=['new kernel requires reboot']):
            self.assertEqual(bootstrap.prepare(True), 3)
            self.assertEqual(bootstrap.prepare(True), 3)
        self.assertEqual(json.loads(self.marker.read_text())['status'], 'awaiting-restart')
        with patch.object(bootstrap, 'boot_id', return_value='second-boot'), patch.object(bootstrap, 'perform_update') as update:
            self.assertEqual(bootstrap.prepare(), 0)
            update.assert_not_called()
        self.assertFalse(self.marker.exists())

    def test_invalid_existing_marker_fails_closed_without_updating_or_overwriting(self):
        self.data.update(ready=True, missing=[])
        self.marker.parent.mkdir(parents=True)
        for value in (None, [], False, {}, {'status': 'unknown', 'bootId': 'x'}, {'status': 'running', 'bootId': ''}):
            original = json.dumps(value)
            self.marker.write_text(original)
            with self.subTest(value=value), patch.object(bootstrap, 'perform_update') as update:
                with self.assertRaises(ValueError):
                    bootstrap.prepare(True)
                update.assert_not_called()
                self.assertEqual(self.marker.read_text(), original)

    def test_update_stages_use_omarchy_and_do_not_run_restart_or_orphan_removal(self):
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            self.assertEqual(kwargs['env']['OMARCHY_UPDATE_UNATTENDED'], '1')
            return SimpleNamespace(returncode=0)
        with patch.object(bootstrap.subprocess, 'run', side_effect=run):
            self.assertEqual(bootstrap.perform_update(), 0)
        self.assertEqual(calls, [
            ['omarchy', 'snapshot', 'create'], ['omarchy', 'update', 'keyring'],
            ['omarchy', 'update', 'system', 'pkgs'], ['omarchy', 'migrate'],
            ['omarchy', 'hook', 'post-update'],
        ])

    def test_missing_or_empty_indexes_are_detected_while_offline_db_is_ignored(self):
        database = self.root / 'pacman'
        (database / 'sync').mkdir(parents=True)
        (database / 'sync/offline.db').write_text('ISO')
        (database / 'sync/core.db').write_text('core metadata')
        (database / 'sync/extra.db').touch()
        with patch.object(bootstrap.subprocess, 'check_output', side_effect=[str(database), 'core\nextra\nmultilib\n']):
            result = CHECK_DATABASES()
        self.assertEqual(result, {'ready': False, 'missing': ['extra', 'multilib']})


if __name__ == '__main__':
    unittest.main()
