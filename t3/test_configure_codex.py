import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("configure_codex", Path(__file__).with_name("configure-codex.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ConfigureCodexTests(unittest.TestCase):
    def test_default_path_and_unrelated_settings(self):
        data = {"defaultTheme": "omarchy", "providerInstances": {
            "codex": {"driver": "codex", "enabled": False, "config": {
                "binaryPath": "/usr/bin/codex", "homePath": "/custom/home", "launchArgs": "--config x=y"}},
            "claude": {"driver": "claudeAgent", "config": {"binaryPath": "claude"}},
        }}
        expected = json.loads(json.dumps(data))
        expected["providerInstances"]["codex"]["config"]["binaryPath"] = "codex"
        self.assertEqual(module.configure(data, Path("/home/test")), expected)
        self.assertEqual(data["providerInstances"]["codex"]["config"]["binaryPath"], "/usr/bin/codex")

    def test_preserve_custom_and_managed_instances(self):
        for config in [{"binaryPath": "/opt/custom/codex"}, {"binaryPath": "codex", "setupMode": "managed"}]:
            data = {"providerInstances": {"my-codex": {"driver": "codex", "config": config}}}
            self.assertEqual(module.configure(data, Path("/home/test")), data)

    def test_legacy_and_wrapper(self):
        data = {"providers": {"codex": {"binaryPath": "codex", "enabled": False}},
                "providerInstances": {"codex": {"driver": "codex", "config": {"binaryPath": "/home/test/.local/bin/codex"}}}}
        result = module.configure(data, Path("/home/test"))
        self.assertEqual(result["providers"]["codex"]["binaryPath"], "codex")
        self.assertFalse(result["providers"]["codex"]["enabled"])
        self.assertEqual(result["providerInstances"]["codex"]["config"]["binaryPath"], "codex")

    def test_fresh_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "userdata/settings.json"
            self.assertTrue(module.update(path, Path(directory)))
            original = path.read_bytes()
            self.assertFalse(module.update(path, Path(directory)))
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse(list(path.parent.glob("*.bak-*")))

    def test_backup_and_invalid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            original = '{"defaultTheme":"omarchy"}'
            path.write_text(original)
            self.assertTrue(module.update(path, Path(directory)))
            backups = list(path.parent.glob("*.bak-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), original)
            path.write_text("invalid JSON")
            with self.assertRaises(json.JSONDecodeError):
                module.update(path, Path(directory))
            self.assertEqual(path.read_text(), "invalid JSON")


if __name__ == "__main__":
    unittest.main()
