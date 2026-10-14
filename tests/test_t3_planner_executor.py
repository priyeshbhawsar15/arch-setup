#!/usr/bin/env python3
"""Isolated fixture tests for T3 Planner-Executor adapter installation and lifecycle."""

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class T3PlannerExecutorTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base = Path(self.temp_dir.name)

        self.fake_home = self.base / "home"
        self.fake_home.mkdir()

        self.fake_bin = self.base / "bin"
        self.fake_bin.mkdir()

        self.omarchy_log = self.base / "omarchy.log"

        # Create dummy binaries for fake_bin
        omarchy_bin = self.fake_bin / "omarchy"
        omarchy_bin.write_text(
            '#!/bin/sh\n'
            'if [ -n "$OMARCHY_LOG" ]; then\n'
            '  printf "%s\\n" "$*" >> "$OMARCHY_LOG"\n'
            'fi\n'
            'exit 0\n'
        )
        omarchy_bin.chmod(0o755)

        for cmd in ("pi", "codex", "claude"):
            cmd_path = self.fake_bin / cmd
            cmd_path.write_text("#!/bin/sh\nexit 0\n")
            cmd_path.chmod(0o755)

        # Isolated system bin containing only standard utilities (no host mise, pi, or codex shims)
        self.sys_bin = self.base / "sys_bin"
        self.sys_bin.mkdir()
        for tool in (
            "bash", "sh", "node", "git", "python3", "cat", "rm", "rmdir",
            "mkdir", "cp", "mv", "chmod", "readlink", "ln", "date", "mktemp",
            "basename", "dirname", "head", "tail", "grep", "sed", "awk",
            "cut", "tr", "sort", "uniq", "find", "uname", "which", "env",
            "flock"
        ):
            p = shutil.which(tool)
            if p:
                (self.sys_bin / tool).symlink_to(p)

        # Build local upstream git repo using portable package files
        self.upstream = self.base / "upstream"
        self.upstream.mkdir()
        self.git("init", "-q", cwd=self.upstream)

        # Stage portable package into fake upstream from adjacent portable repo or override
        portable_src = Path(os.environ.get("T3_PLANNER_EXECUTOR_TEST_SOURCE", str(ROOT.parent / "t3-planner-executor")))
        if not portable_src.is_dir():
            raise unittest.SkipTest(f"Portable package source not found at {portable_src}")

        for sub_dir in ("bin", "config", "lib", "pi", "codex", "claude", "antigravity"):
            shutil.copytree(portable_src / sub_dir, self.upstream / sub_dir)
        shutil.copy2(portable_src / "install.mjs", self.upstream / "install.mjs")
        shutil.copy2(portable_src / "README.md", self.upstream / "README.md")

        # Make sure wrappers/binaries in upstream have execute permissions
        for exec_path in (
            self.upstream / "bin/t3-planner-executor",
            self.upstream / "install.mjs",
            self.upstream / "codex/wrapper.mjs",
            self.upstream / "codex/hooks.mjs",
            self.upstream / "claude/wrapper.mjs",
            self.upstream / "claude/hooks.mjs",
            self.upstream / "antigravity/wrapper.mjs",
        ):
            if exec_path.exists():
                exec_path.chmod(0o755)

        self.git("add", ".", cwd=self.upstream)
        self.git("-c", "user.name=Tests", "-c", "user.email=tests@example.invalid", "commit", "-qm", "initial", cwd=self.upstream)
        self.commit_1 = self.git("rev-parse", "HEAD", cwd=self.upstream).strip()

        # Paths for managed installation
        self.source_dir = self.fake_home / ".local/share/t3-planner-executor/source"
        self.runtime_dir = self.fake_home / ".config/t3code/planner-executor"
        self.settings_path = self.fake_home / ".t3/userdata/settings.json"
        self.settings_path.parent.mkdir(parents=True)
        self.helper_link = self.fake_home / ".local/bin/t3-planner-executor"
        (self.fake_home / ".local/bin").mkdir(parents=True)

        # Initial T3 settings
        self.initial_settings = {
            "providerInstances": {
                "pi": {
                    "driver": "pi",
                    "displayName": "Pi",
                    "enabled": True,
                    "config": {
                        "launchArgs": "--system 'custom jev param' --extension '/path/to/jev.mjs'",
                        "binaryPath": str(self.fake_bin / "pi"),
                    },
                },
                "codex": {
                    "driver": "codex",
                    "displayName": "Codex",
                    "enabled": True,
                    "config": {
                        "binaryPath": str(self.fake_bin / "codex"),
                    },
                },
                "claudeAgent": {
                    "driver": "claudeAgent",
                    "displayName": "Claude",
                    "enabled": True,
                    "config": {
                        "binaryPath": str(self.fake_bin / "claude"),
                    },
                },
                "antigravity": {
                    "driver": "antigravity",
                    "displayName": "Antigravity",
                    "enabled": True,
                    "config": {
                        "binaryPath": "",
                    },
                },
            }
        }
        self.settings_path.write_text(json.dumps(self.initial_settings, indent=2))

        self.env = {
            **os.environ,
            "HOME": str(self.fake_home),
            "XDG_CONFIG_HOME": str(self.fake_home / ".config"),
            "XDG_DATA_HOME": str(self.fake_home / ".local/share"),
            "XDG_STATE_HOME": str(self.fake_home / ".local/state"),
            "T3CODE_HOME": str(self.fake_home / ".t3"),
            "PATH": f"{self.fake_bin}:{self.sys_bin}",
            "OMARCHY_LOG": str(self.omarchy_log),
        }

    def git(self, *args, cwd=None):
        return subprocess.check_output(["git", *args], cwd=cwd, text=True, stderr=subprocess.PIPE)

    def run_installer(self, *args, env_override=None):
        cmd = [
            str(ROOT / "install-t3-planner-executor.sh"),
            "--source-url", str(self.upstream),
            "--source-dir", str(self.source_dir),
            "--runtime-dir", str(self.runtime_dir),
            "--settings", str(self.settings_path),
            "--helper", str(self.helper_link),
            *args,
        ]
        test_env = {**self.env, **(env_override or {})}
        return subprocess.run(cmd, capture_output=True, text=True, env=test_env)

    def test_pending_publication_refusal(self):
        """PENDING_PUBLICATION pin must be refused and not pretend to be installable."""
        res = self.run_installer("--pin", "PENDING_PUBLICATION")
        self.assertEqual(res.returncode, 1)
        self.assertIn("PENDING_PUBLICATION", res.stdout)
        self.assertIn("awaiting final reviewed commit publication", res.stdout)
        self.assertFalse(self.runtime_dir.exists())

    def test_invalid_pin_no_effects(self):
        """Invalid pin fails early with exit 1 and makes no modifications."""
        res = self.run_installer("--pin", "not-a-valid-40-char-hex-pin")
        self.assertEqual(res.returncode, 1)
        self.assertIn("Invalid repository commit pin", res.stdout)
        self.assertFalse(self.runtime_dir.exists())
        self.assertFalse(self.source_dir.exists())

    def test_first_install(self):
        """First installation seeds config, updates managed settings, and creates helper symlink."""
        res = self.run_installer("--pin", self.commit_1)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn(f"Installed and configured T3 Planner-Executor at {self.commit_1}", res.stdout)

        # Check runtime files
        self.assertTrue((self.runtime_dir / "bin/t3-planner-executor").is_file())
        self.assertTrue(os.access(self.runtime_dir / "bin/t3-planner-executor", os.X_OK))
        self.assertTrue((self.runtime_dir / "config.json").is_file())
        self.assertTrue((self.runtime_dir / "codex/wrapper.mjs").is_file())
        self.assertTrue((self.runtime_dir / "pi/planner-executor.mjs").is_file())

        # Check nested config symlink
        nested_cfg = self.runtime_dir / "config/config.json"
        self.assertTrue(nested_cfg.is_symlink())
        self.assertEqual(nested_cfg.resolve(), (self.runtime_dir / "config.json").resolve())

        # Check helper symlink
        self.assertTrue(self.helper_link.is_symlink())
        self.assertEqual(self.helper_link.resolve(), (self.runtime_dir / "bin/t3-planner-executor").resolve())

        # Check seeded config
        cfg = json.loads((self.runtime_dir / "config.json").read_text())
        self.assertTrue(cfg.get("enabled"))
        self.assertEqual(cfg.get("executor", {}).get("provider"), "pi")
        self.assertEqual(cfg.get("executor", {}).get("model"), "antigravity/gemini-3.8-flash")
        self.assertEqual(cfg.get("executor", {}).get("thinking"), "high")
        self.assertEqual(cfg.get("maxFixRounds"), 2)
        self.assertTrue(cfg.get("planner", {}).get("allowEdits"))
        self.assertEqual(cfg.get("shellPolicy"), "planner-workspace")

        # Check settings.json updates
        settings = json.loads(self.settings_path.read_text())
        instances = settings["providerInstances"]

        # Codex binaryPath pointing to wrapper
        self.assertEqual(instances["codex"]["config"]["binaryPath"], str(self.runtime_dir / "codex/wrapper.mjs"))
        self.assertTrue(instances["codex"]["enabled"])

        # Pi launchArgs containing extension while preserving custom jev args
        pi_args = instances["pi"]["config"]["launchArgs"]
        self.assertIn("--system 'custom jev param'", pi_args)
        self.assertIn("--extension '/path/to/jev.mjs'", pi_args)
        self.assertIn(f"--extension '{self.runtime_dir}/pi/planner-executor.mjs'", pi_args)

    def test_second_run_already_installed(self):
        """Second run detects matching state, prints already installed, and exits 0 without writes."""
        res1 = self.run_installer("--pin", self.commit_1)
        self.assertEqual(res1.returncode, 0, res1.stderr)

        backups_dir = self.runtime_dir / "backups"
        initial_backups = list(backups_dir.iterdir()) if backups_dir.exists() else []

        res2 = self.run_installer("--pin", self.commit_1)
        self.assertEqual(res2.returncode, 0, res2.stderr)
        self.assertIn("already installed", res2.stdout)

        current_backups = list(backups_dir.iterdir()) if backups_dir.exists() else []
        self.assertEqual(len(initial_backups), len(current_backups))

    def test_changed_pin_update(self):
        """Changed pin updates the managed checkout and runtime files cleanly."""
        res1 = self.run_installer("--pin", self.commit_1)
        self.assertEqual(res1.returncode, 0, res1.stderr)

        # Make new commit upstream
        (self.upstream / "README.md").write_text("# Updated T3 Planner Executor\n")
        self.git("add", "README.md", cwd=self.upstream)
        self.git("-c", "user.name=Tests", "-c", "user.email=tests@example.invalid", "commit", "-qm", "update pin", cwd=self.upstream)
        commit_2 = self.git("rev-parse", "HEAD", cwd=self.upstream).strip()

        res2 = self.run_installer("--pin", commit_2)
        self.assertEqual(res2.returncode, 0, res2.stderr)
        self.assertIn(f"Installed and configured T3 Planner-Executor at {commit_2}", res2.stdout)

        source_head = self.git("rev-parse", "HEAD", cwd=self.source_dir).strip()
        self.assertEqual(source_head, commit_2)

    def test_preserved_custom_config(self):
        """Custom config fields are preserved when re-running or updating."""
        res1 = self.run_installer("--pin", self.commit_1)
        self.assertEqual(res1.returncode, 0, res1.stderr)

        # Apply operator customization
        cfg_path = self.runtime_dir / "config.json"
        cfg = json.loads(cfg_path.read_text())
        cfg["executor"]["model"] = "custom-fine-tuned-model"
        cfg["executor"]["thinking"] = "medium"
        cfg["maxFixRounds"] = 5
        cfg["customOperatorKey"] = "my_val"
        cfg_path.write_text(json.dumps(cfg, indent=2))

        # Re-run installer (force update check)
        self.helper_link.unlink()
        res2 = self.run_installer("--pin", self.commit_1)
        self.assertEqual(res2.returncode, 0, res2.stderr)

        new_cfg = json.loads(cfg_path.read_text())
        self.assertEqual(new_cfg["executor"]["model"], "custom-fine-tuned-model")
        self.assertEqual(new_cfg["executor"]["thinking"], "medium")
        self.assertEqual(new_cfg["maxFixRounds"], 5)
        self.assertEqual(new_cfg["customOperatorKey"], "my_val")

    def test_pi_launchargs_no_duplicates(self):
        """Repeated configuration does not duplicate the Pi extension in launchArgs."""
        self.run_installer("--pin", self.commit_1)
        self.helper_link.unlink()
        self.run_installer("--pin", self.commit_1)

        settings = json.loads(self.settings_path.read_text())
        pi_args = settings["providerInstances"]["pi"]["config"]["launchArgs"]
        ext_target = f"{self.runtime_dir}/pi/planner-executor.mjs"
        count = pi_args.count(ext_target)
        self.assertEqual(count, 1)

    def test_missing_ag_not_silently_enabled(self):
        """When native Antigravity binary pair is missing, AG is reported pending and not activated."""
        res = self.run_installer("--pin", self.commit_1)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("status: pending", res.stdout)
        self.assertIn("Antigravity provider is pending native setup", res.stdout)

        settings = json.loads(self.settings_path.read_text())
        ag_bin = settings["providerInstances"]["antigravity"]["config"].get("binaryPath", "")
        self.assertNotEqual(ag_bin, str(self.runtime_dir / "antigravity/wrapper.mjs"))

    def test_native_ag_configured_when_pair_present(self):
        """When native Antigravity binary pair is present, AG is properly configured."""
        platform_arch = f"{os.uname().sysname.lower()}-{'x64' if os.uname().machine in ('x86_64', 'amd64') else os.uname().machine}"
        ag_managed = self.fake_home / ".t3/tools/antigravity-acp" / platform_arch
        version_dir = ag_managed / "versions/test-release-123"
        version_dir.mkdir(parents=True)

        fake_server = version_dir / "agy_acp_server.par"
        fake_server.write_text("#!/bin/sh\nexit 0\n")
        fake_server.chmod(0o755)

        fake_harness = version_dir / "localharness_external"
        fake_harness.write_text("#!/bin/sh\nexit 0\n")
        fake_harness.chmod(0o755)

        (ag_managed / "active.json").write_text(json.dumps({"releaseId": "test-release-123"}))

        res = self.run_installer("--pin", self.commit_1)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotIn("status: pending", res.stdout)

        settings = json.loads(self.settings_path.read_text())
        ag_bin = settings["providerInstances"]["antigravity"]["config"].get("binaryPath", "")
        self.assertEqual(ag_bin, str(self.runtime_dir / "antigravity/wrapper.mjs"))

        # Verify descriptor.json
        desc = json.loads((self.runtime_dir / "antigravity/descriptor.json").read_text())
        self.assertEqual(desc["realBinary"], str(fake_server))
        self.assertEqual(desc["realHarness"], str(fake_harness))

    def test_dirty_checkout_refusal(self):
        """Dirty managed source checkout refuses to overwrite."""
        self.run_installer("--pin", self.commit_1)

        (self.source_dir / "local_mod.txt").write_text("uncommitted")

        (self.upstream / "new_file").write_text("upstream new")
        self.git("add", ".", cwd=self.upstream)
        self.git("-c", "user.name=Tests", "-c", "user.email=tests@example.invalid", "commit", "-qm", "new", cwd=self.upstream)
        new_commit = self.git("rev-parse", "HEAD", cwd=self.upstream).strip()

        res = self.run_installer("--pin", new_commit)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("local changes; refusing to overwrite", res.stderr)

    def test_configuration_drift_repaired(self):
        """Drift in managed settings.json is detected and repaired."""
        self.run_installer("--pin", self.commit_1)

        # Reset codex binaryPath
        settings = json.loads(self.settings_path.read_text())
        settings["providerInstances"]["codex"]["config"]["binaryPath"] = str(self.fake_bin / "codex")
        self.settings_path.write_text(json.dumps(settings, indent=2))

        # Installer detects drift and repairs
        res = self.run_installer("--pin", self.commit_1)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn(f"Installed and configured T3 Planner-Executor at {self.commit_1}", res.stdout)

        repaired_settings = json.loads(self.settings_path.read_text())
        self.assertEqual(
            repaired_settings["providerInstances"]["codex"]["config"]["binaryPath"],
            str(self.runtime_dir / "codex/wrapper.mjs")
        )

    def test_disable_enable_persistent_choice(self):
        """--disable sets enabled:false and persists across default no-arg runs."""
        self.run_installer("--pin", self.commit_1)

        res_dis = self.run_installer("--disable")
        self.assertEqual(res_dis.returncode, 0)
        self.assertIn("disabled", res_dis.stdout)

        cfg = json.loads((self.runtime_dir / "config.json").read_text())
        self.assertFalse(cfg.get("enabled"))

        # No-arg run must respect remembered disable choice
        res_noarg = self.run_installer()
        self.assertEqual(res_noarg.returncode, 0)
        self.assertIn("disabled in feature profile", res_noarg.stdout)

        # Re-enable
        res_en = self.run_installer("--enable", "--pin", self.commit_1)
        self.assertEqual(res_en.returncode, 0)
        cfg_re = json.loads((self.runtime_dir / "config.json").read_text())
        self.assertTrue(cfg_re.get("enabled"))

    def test_safe_removal_and_preservation(self):
        """--remove restores T3 settings cleanly, removes wrappers, and creates state backup."""
        self.run_installer("--pin", self.commit_1)

        res_rem = self.run_installer("--remove")
        self.assertEqual(res_rem.returncode, 0, res_rem.stderr)
        self.assertIn("Removed T3 Planner-Executor", res_rem.stdout)

        # Check settings restored to verified backend
        settings = json.loads(self.settings_path.read_text())
        instances = settings["providerInstances"]

        # Codex restored to verified real backend
        self.assertEqual(instances["codex"]["config"]["binaryPath"], str(self.fake_bin / "codex"))

        # Pi extension removed while preserving other launchArgs
        pi_args = instances["pi"]["config"]["launchArgs"]
        self.assertIn("--system 'custom jev param'", pi_args)
        self.assertIn("--extension '/path/to/jev.mjs'", pi_args)
        self.assertNotIn("planner-executor.mjs", pi_args)

        # Helper symlink removed
        self.assertFalse(self.helper_link.exists())

        # Owned wrappers unlinked
        self.assertFalse((self.runtime_dir / "codex/wrapper.mjs").exists())
        self.assertFalse((self.runtime_dir / "pi/planner-executor.mjs").exists())

    def test_failed_malformed_disable_leaves_state_unchanged(self):
        """Malformed config on --disable fails closed without changing feature profile or file bytes."""
        self.run_installer("--pin", self.commit_1)

        cfg_path = self.runtime_dir / "config.json"
        corrupt_bytes = b"{\n  \"enabled\": malformed JSON\n"
        cfg_path.write_bytes(corrupt_bytes)

        res = self.run_installer("--disable")
        self.assertNotEqual(res.returncode, 0)
        # Original bytes preserved
        self.assertEqual(cfg_path.read_bytes(), corrupt_bytes)

    def test_failed_malformed_enable_leaves_state_unchanged(self):
        """Malformed config on --enable fails closed without marking feature enabled."""
        self.run_installer("--pin", self.commit_1)
        self.run_installer("--disable")

        cfg_path = self.runtime_dir / "config.json"
        corrupt_bytes = b"{\n  \"invalid\": true, malformed syntax\n"
        cfg_path.write_bytes(corrupt_bytes)

        res = self.run_installer("--enable", "--pin", self.commit_1)
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(cfg_path.read_bytes(), corrupt_bytes)

    def test_failed_malformed_remove_leaves_state_unchanged(self):
        """Malformed settings or malformed config on --remove fails closed without deleting files or mutating state."""
        self.run_installer("--pin", self.commit_1)

        # 1. Test malformed settings.json
        settings_before = self.settings_path.read_bytes()
        corrupt_settings = b"{\n  \"providerInstances\": { malformed JSON\n"
        self.settings_path.write_bytes(corrupt_settings)

        res1 = self.run_installer("--remove")
        self.assertNotEqual(res1.returncode, 0)
        # Settings preserved
        self.assertEqual(self.settings_path.read_bytes(), corrupt_settings)
        # Runtime files not deleted
        self.assertTrue((self.runtime_dir / "codex/wrapper.mjs").exists())
        self.assertTrue((self.runtime_dir / "pi/planner-executor.mjs").exists())

        # Restore valid settings
        self.settings_path.write_bytes(settings_before)

        # 2. Test malformed config.json: unconfigure must NOT write settings before failing
        cfg_path = self.runtime_dir / "config.json"
        cfg_before = cfg_path.read_bytes()
        corrupt_cfg = b"{\n  \"enabled\": malformed JSON\n"
        cfg_path.write_bytes(corrupt_cfg)

        res2 = self.run_installer("--remove")
        self.assertNotEqual(res2.returncode, 0)
        # Config and settings preserved without partial changes
        self.assertEqual(cfg_path.read_bytes(), corrupt_cfg)
        self.assertEqual(self.settings_path.read_bytes(), settings_before)
        # Runtime files not deleted
        self.assertTrue((self.runtime_dir / "codex/wrapper.mjs").exists())
        self.assertTrue((self.runtime_dir / "pi/planner-executor.mjs").exists())
        self.assertTrue(self.helper_link.exists())

        # Feature choice must remain unchanged
        cfg_path.write_bytes(cfg_before)
        res_check = self.run_installer("--pin", self.commit_1)
        self.assertEqual(res_check.returncode, 0)
        self.assertIn("already installed", res_check.stdout)

    def test_missing_backend_removal_refuses_deletion(self):
        """When a real backend cannot be verified, --remove refuses deletion to avoid breaking T3."""
        self.run_installer("--pin", self.commit_1)

        # Remove codex from fake_bin and simulate missing backend
        (self.fake_bin / "codex").unlink()

        res = self.run_installer("--remove")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("verified backend for Codex not found", res.stderr + res.stdout)
        # Files remain intact
        self.assertTrue((self.runtime_dir / "codex/wrapper.mjs").exists())
        self.assertTrue((self.runtime_dir / "pi/planner-executor.mjs").exists())

    def test_aliased_wrapper_refs_restored(self):
        """Provider aliases with wrapper paths are restored on unconfigure."""
        self.run_installer("--pin", self.commit_1)

        # Add an alias pointing to codex wrapper
        settings = json.loads(self.settings_path.read_text())
        settings["providerInstances"]["codex_validation"] = {
            "driver": "codex",
            "displayName": "Codex Validation",
            "enabled": True,
            "config": {
                "binaryPath": str(self.runtime_dir / "codex/wrapper.mjs"),
            },
        }
        self.settings_path.write_text(json.dumps(settings, indent=2))

        res = self.run_installer("--remove")
        self.assertEqual(res.returncode, 0, res.stderr)

        settings_after = json.loads(self.settings_path.read_text())
        # Both codex and codex_validation restored to real backend
        self.assertEqual(
            settings_after["providerInstances"]["codex_validation"]["config"]["binaryPath"],
            str(self.fake_bin / "codex")
        )
        self.assertEqual(
            settings_after["providerInstances"]["codex"]["config"]["binaryPath"],
            str(self.fake_bin / "codex")
        )

    def test_unknown_adapter_file_retained_or_archived(self):
        """Unknown or preexisting files in adapter directories are retained, not deleted wholesale."""
        self.run_installer("--pin", self.commit_1)

        custom_note = self.runtime_dir / "codex/custom_user_note.txt"
        custom_note.write_text("user note")

        state_file = self.runtime_dir / "state.json"
        state_file.write_text(json.dumps({"activeRun": "abc"}))

        res = self.run_installer("--remove")
        self.assertEqual(res.returncode, 0, res.stderr)

        # Owned wrappers unlinked
        self.assertFalse((self.runtime_dir / "codex/wrapper.mjs").exists())
        # Custom file and state file preserved
        self.assertTrue(custom_note.exists())
        self.assertEqual(custom_note.read_text(), "user note")
        self.assertTrue(state_file.exists())

    def test_fresh_missing_settings_bootstrap(self):
        """When settings.json is initially absent, installer bootstraps minimal settings without error."""
        self.settings_path.unlink()

        res = self.run_installer("--pin", self.commit_1)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(self.settings_path.exists())

        settings = json.loads(self.settings_path.read_text())
        self.assertIn("providerInstances", settings)
        self.assertIn("pi", settings["providerInstances"])
        self.assertIn("codex", settings["providerInstances"])

    def test_missing_executor_without_path_with_fake_mise(self):
        """When pi is not in PATH, read-only mise resolution finds it; if absent from mise, fails cleanly."""
        (self.fake_bin / "pi").unlink()

        # Without mise or pi: fails with clear message
        res_fail = self.run_installer("--pin", self.commit_1)
        self.assertEqual(res_fail.returncode, 1)
        self.assertIn("Configured executor 'pi' is not available", res_fail.stdout)

        # With fake mise returning pi path
        mise_script = self.fake_bin / "mise"
        pi_real_dest = self.base / "mise-pi-bin"
        pi_real_dest.write_text("#!/bin/sh\nexit 0\n")
        pi_real_dest.chmod(0o755)

        mise_script.write_text(f"#!/bin/sh\nif [ \"$1\" = 'which' ] && [ \"$2\" = 'pi' ]; then echo '{pi_real_dest}'; exit 0; fi\nexit 1\n")
        mise_script.chmod(0o755)

        res_ok = self.run_installer("--pin", self.commit_1)
        self.assertEqual(res_ok.returncode, 0, res_ok.stderr)

    def test_drift_all_critical_file_categories_nested_config_helper(self):
        """check_current detects drift in state, hooks, bridges, nested config link, helper, and provider status."""
        self.run_installer("--pin", self.commit_1)

        config_helper = ROOT / "t3/configure-planner-executor.py"
        def run_check():
            return subprocess.run(
                ["python3", str(config_helper), "check-current",
                 "--source-dir", str(self.source_dir),
                 "--source-url", str(self.upstream),
                 "--source-commit", self.commit_1,
                 "--runtime-dir", str(self.runtime_dir),
                 "--settings", str(self.settings_path),
                 "--helper", str(self.helper_link),
                 "--providers", "pi,codex,claudeAgent"],
                capture_output=True, text=True
            )

        # Initial check passes
        self.assertEqual(run_check().returncode, 0)

        # 1. Drift in lib/state.mjs
        state_mjs = self.runtime_dir / "lib/state.mjs"
        orig_state = state_mjs.read_bytes()
        state_mjs.write_bytes(b"// modified state\n")
        self.assertEqual(run_check().returncode, 1)
        state_mjs.write_bytes(orig_state)
        self.assertEqual(run_check().returncode, 0)

        # 2. Drift in codex/hooks.mjs
        hooks_mjs = self.runtime_dir / "codex/hooks.mjs"
        orig_hooks = hooks_mjs.read_bytes()
        hooks_mjs.write_bytes(b"// modified hooks\n")
        self.assertEqual(run_check().returncode, 1)
        hooks_mjs.write_bytes(orig_hooks)
        self.assertEqual(run_check().returncode, 0)

        # 3. Drift in claude/bridge.mjs
        bridge_mjs = self.runtime_dir / "claude/bridge.mjs"
        orig_bridge = bridge_mjs.read_bytes()
        bridge_mjs.write_bytes(b"// modified bridge\n")
        self.assertEqual(run_check().returncode, 1)
        bridge_mjs.write_bytes(orig_bridge)
        self.assertEqual(run_check().returncode, 0)

        # 4. Drift in antigravity/bridge.mjs
        ag_bridge = self.runtime_dir / "antigravity/bridge.mjs"
        orig_ag_bridge = ag_bridge.read_bytes()
        ag_bridge.write_bytes(b"// modified ag bridge\n")
        self.assertEqual(run_check().returncode, 1)
        ag_bridge.write_bytes(orig_ag_bridge)
        self.assertEqual(run_check().returncode, 0)

        # 5. Missing / non-symlink nested config
        nested_cfg = self.runtime_dir / "config/config.json"
        nested_cfg.unlink()
        nested_cfg.write_text("{}")
        self.assertEqual(run_check().returncode, 1)
        nested_cfg.unlink()
        nested_cfg.symlink_to("../config.json")
        self.assertEqual(run_check().returncode, 0)

        # 6. Helper symlink pointing elsewhere
        self.helper_link.unlink()
        self.helper_link.symlink_to("/bin/sh")
        self.assertEqual(run_check().returncode, 1)
        self.helper_link.unlink()
        self.helper_link.symlink_to(self.runtime_dir / "bin/t3-planner-executor")
        self.assertEqual(run_check().returncode, 0)

        # 7. Provider instance enabled: false
        settings = json.loads(self.settings_path.read_text())
        settings["providerInstances"]["codex"]["enabled"] = False
        self.settings_path.write_text(json.dumps(settings, indent=2))
        self.assertEqual(run_check().returncode, 1)
        settings["providerInstances"]["codex"]["enabled"] = True
        self.settings_path.write_text(json.dumps(settings, indent=2))
        self.assertEqual(run_check().returncode, 0)

    def test_optimistic_concurrency(self):
        """atomic_write_json detects concurrent modification and raises RuntimeError."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("cfg_mod", ROOT / "t3/configure-planner-executor.py")
        cfg_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cfg_mod)

        test_file = self.base / "concurrency_test.json"
        test_file.write_text(json.dumps({"a": 1}))

        # Load bytes
        data, expected_bytes = cfg_mod.load_json(test_file, fail_closed=True)

        # Simulate concurrent edit
        test_file.write_text(json.dumps({"a": 2}))

        with self.assertRaises(RuntimeError):
            cfg_mod.atomic_write_json(test_file, {"a": 3}, expected_bytes=expected_bytes)

        # Verify disk bytes not overwritten with {"a": 3}
        self.assertEqual(json.loads(test_file.read_text()), {"a": 2})

    def test_existing_config_disabled_preserved_on_noarg_install(self):
        """Existing operator config with enabled:false remains disabled on normal no-arg run."""
        res = self.run_installer("--pin", self.commit_1)
        self.assertEqual(res.returncode, 0)

        # Operator customizes config.json to disabled without feature profile entry
        cfg_path = self.runtime_dir / "config.json"
        cfg = json.loads(cfg_path.read_text())
        cfg["enabled"] = False
        cfg_path.write_text(json.dumps(cfg, indent=2))

        # Normal no-arg run detects matching state with enabled:false and does not rewrite or fail
        res_noarg = self.run_installer("--pin", self.commit_1)
        self.assertEqual(res_noarg.returncode, 0, res_noarg.stderr)
        self.assertIn("already installed", res_noarg.stdout)

        # Verify config.json remains disabled
        cfg_after = json.loads(cfg_path.read_text())
        self.assertFalse(cfg_after.get("enabled"))

        # Explicit --enable forces it back to true
        res_en = self.run_installer("--enable", "--pin", self.commit_1)
        self.assertEqual(res_en.returncode, 0)
        cfg_final = json.loads(cfg_path.read_text())
        self.assertTrue(cfg_final.get("enabled"))

    def test_missing_flock_routed_through_omarchy(self):
        """When flock is missing, installer routes installation through require_omarchy and omarchy pkg add util-linux."""
        flock_sys = self.sys_bin / "flock"
        if flock_sys.exists() or flock_sys.is_symlink():
            flock_sys.unlink()
        flock_fake = self.fake_bin / "flock"
        if flock_fake.exists() or flock_fake.is_symlink():
            flock_fake.unlink()

        res = self.run_installer("--pin", self.commit_1)
        self.assertEqual(res.returncode, 0, res.stderr)

        self.assertTrue(self.omarchy_log.exists(), "Expected Omarchy to be invoked when flock is missing")
        calls = [line.strip() for line in self.omarchy_log.read_text().splitlines() if line.strip()]
        self.assertIn("pkg add util-linux", calls)

    def test_missing_flock_without_omarchy_fails(self):
        """When flock is missing and omarchy is unavailable, require_omarchy fails closed."""
        flock_sys = self.sys_bin / "flock"
        if flock_sys.exists() or flock_sys.is_symlink():
            flock_sys.unlink()
        flock_fake = self.fake_bin / "flock"
        if flock_fake.exists() or flock_fake.is_symlink():
            flock_fake.unlink()

        # Remove omarchy
        (self.fake_bin / "omarchy").unlink()

        res = self.run_installer("--pin", self.commit_1)
        self.assertEqual(res.returncode, 1)
        self.assertIn("omarchy is not available on PATH", res.stdout + res.stderr)

    def test_flock_present_install_idempotency(self):
        """When flock is present, installer does not invoke omarchy pkg add, and subsequent run is idempotent."""
        # Ensure flock is available in sys_bin
        flock_p = shutil.which("flock")
        if not flock_p:
            mock_flock = self.fake_bin / "flock"
            mock_flock.write_text("#!/bin/sh\nexit 0\n")
            mock_flock.chmod(0o755)
        elif not (self.sys_bin / "flock").exists():
            (self.sys_bin / "flock").symlink_to(flock_p)

        # Clear omarchy log if it exists
        if self.omarchy_log.exists():
            self.omarchy_log.unlink()

        # First install
        res1 = self.run_installer("--pin", self.commit_1)
        self.assertEqual(res1.returncode, 0, res1.stderr)
        self.assertIn(f"Installed and configured T3 Planner-Executor at {self.commit_1}", res1.stdout)

        # Confirm omarchy pkg add util-linux was NOT called
        calls1 = []
        if self.omarchy_log.exists():
            calls1 = [line.strip() for line in self.omarchy_log.read_text().splitlines() if line.strip()]
        self.assertNotIn("pkg add util-linux", calls1)

        # Second install (idempotency check)
        res2 = self.run_installer("--pin", self.commit_1)
        self.assertEqual(res2.returncode, 0, res2.stderr)
        self.assertIn("already installed", res2.stdout)

        # Confirm still not called
        calls2 = []
        if self.omarchy_log.exists():
            calls2 = [line.strip() for line in self.omarchy_log.read_text().splitlines() if line.strip()]
        self.assertNotIn("pkg add util-linux", calls2)


if __name__ == "__main__":
    unittest.main()
