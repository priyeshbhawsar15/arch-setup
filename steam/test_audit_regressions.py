import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("hdr_audit", Path(__file__).with_name("configure-gamescope-hdr.py"))
hdr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hdr)


class SteamAuditTests(unittest.TestCase):
    def test_argument_only_options_follow_the_game_command(self):
        self.assertEqual(hdr.wrap_launch_options("-novid -dx11"),
                         "steam-gamescope-hdr %command% -novid -dx11")

    def test_escaped_quotes_preserve_a_single_launch_options_value(self):
        fixture = ('"UserLocalConfigStore"\n{\n"Software"\n{\n"Valve"\n{\n"Steam"\n{\n'
                   '"apps"\n{\n"123"\n{\n'
                   '"LaunchOptions" "PROTON_LOG=1 %command% \\"argument with spaces\\""\n'
                   '}\n}\n}\n}\n}\n}\n')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "localconfig.vdf"
            path.write_text(fixture)
            self.assertTrue(hdr.process_vdf(path, {"123": "Example"})[0])
            updated = path.read_text()
            self.assertEqual(updated.count('"LaunchOptions"'), 1)
            self.assertIn('PROTON_LOG=1 steam-gamescope-hdr %command% \\"argument with spaces\\"', updated)
            self.assertFalse(hdr.process_vdf(path, {"123": "Example"})[0])

    def test_installed_games_include_secondary_libraries_with_escaped_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "Steam"
            (root / "steamapps").mkdir(parents=True)
            secondary = base / 'Games "Library"'
            (secondary / "steamapps").mkdir(parents=True)
            (secondary / "steamapps/appmanifest_456.acf").write_text(
                '"AppState"\n{\n"appid" "456"\n"name" "External Game"\n}\n')
            escaped = str(secondary).replace('"', '\\"')
            (root / "steamapps/libraryfolders.vdf").write_text(
                '"libraryfolders"\n{\n"1"\n{\n"path" "' + escaped + '"\n}\n}\n')
            self.assertEqual(hdr.get_installed_games(root), {"456": "External Game"})

