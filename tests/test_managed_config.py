import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "config/managed-config.py"


class MenuEditsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.menu = self.home / "menu.jsonc"
        self.env = {**os.environ, "HOME": str(self.home), "XDG_STATE_HOME": str(self.home / "state")}

    def run_edit(self, command, *args):
        return subprocess.run(["python3", str(SCRIPT), command, str(self.menu), *args],
                              env=self.env, text=True, capture_output=True)

    def test_merge_preserves_comments_and_independent_entries(self):
        self.menu.write_text('{\n // keep this note\n "style.custom": {"action": "printf \\\"hello\\\""},\n}\n')
        self.menu.chmod(0o640)
        payload = json.dumps({"style.hyprland.omaland": {"label": "Editor", "action": "edit \"a\""}})
        result = self.run_edit("merge-menu", payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('// keep this note', self.menu.read_text())
        self.assertIn('"style.custom": {"action": "printf \\\"hello\\\""}', self.menu.read_text())
        self.assertEqual(stat.S_IMODE(self.menu.stat().st_mode), 0o640)
        self.assertEqual(self.run_edit("check-menu", payload).returncode, 0)
        before = self.menu.stat().st_mtime_ns
        self.assertEqual(self.run_edit("merge-menu", payload).returncode, 0)
        self.assertEqual(self.menu.stat().st_mtime_ns, before)
        backups = list((self.home / "state/arch-setups/backups").glob("menu-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(stat.S_IMODE(backups[0].stat().st_mode), 0o700)

    def test_remove_exact_key_preserves_shared_parent_and_sibling(self):
        self.menu.write_text('{\n "style.hyprland": {"label":"My own parent"},\n "style.hyprland.omaland": {"label":"Editor"},\n "style.hyprland.custom": {"label":"Mine"}\n}\n')
        result = self.run_edit("remove-menu", "style.hyprland.omaland", "--empty-parent", "style.hyprland")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.menu.read_text()), {
            "style.hyprland": {"label": "My own parent"},
            "style.hyprland.custom": {"label": "Mine"}})

    def test_remove_multiple_keys_and_empty_parent_leaves_valid_menu(self):
        self.menu.write_text('{"style.custom":{},"style.hyprland":{},"style.hyprland.omaland":{},"style.hyprland.edit":{}}')
        result = self.run_edit("remove-menu", "style.hyprland.omaland", "style.hyprland.edit", "--empty-parent", "style.hyprland")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.menu.read_text()), {"style.custom": {}})

    def test_invalid_input_never_overwrites_original(self):
        original = '{"custom": {broken}\n}'
        self.menu.write_text(original)
        result = self.run_edit("merge-menu", '{"owned":{}}')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.menu.read_text(), original)

    def test_keep_existing_parent_does_not_replace_user_configuration(self):
        self.menu.write_text('{"style.hyprland":{"label":"My label"}}')
        result = self.run_edit("merge-menu", '{"style.hyprland":{"label":"Default"},"style.hyprland.omaland":{}}',
                               "--keep-existing", "style.hyprland")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.menu.read_text())["style.hyprland"], {"label":"My label"})


if __name__ == "__main__":
    unittest.main()
