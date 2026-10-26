import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('steam_ui_scale', Path(__file__).with_name('configure-ui-scale.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class UiScaleTests(unittest.TestCase):
    def test_remove_main_action_and_silent_overrides(self):
        for arguments in ('%U', 'steam://open/bigpicture', '-silent'):
            text = 'Exec=env GDK_SCALE=1 STEAM_FORCE_DESKTOPUI_SCALING=0.8 /usr/bin/steam -forcedesktopscaling 0.8 ' + arguments + '\n'
            expected = 'Exec=/usr/bin/steam ' + arguments + '\n'
            self.assertEqual(module.restore(text), expected)
            self.assertEqual(module.restore(expected), expected)

    def test_plain_command_line_override(self):
        self.assertEqual(module.restore('Exec=steam -forcedesktopscaling 0.8 %U\n'), 'Exec=steam %U\n')

    def test_unrelated_launcher_unchanged(self):
        text = 'Exec=/custom/launcher --steam\nExec=env OTHER=1 /usr/bin/steam %U\n'
        self.assertEqual(module.restore(text), text)

    def test_remove_only_known_persisted_80_percent_paths(self):
        text = '''"InstallConfigStore"
{
 "Accessibility" { "DesktopUIScale" "0.800000011920928955" }
 "UI" { "display" { "Current" {
 "ScaleFactor" "0.800000011920928955"
 "AutoScaleFactor" "1.423"
 } } }
 "Other" { "ScaleFactor" "0.8" }
 "Escaped" "a \\"quoted\\" value"
}
'''
        updated = module.remove_persisted(text)
        self.assertNotIn('DesktopUIScale', updated)
        self.assertNotIn('0.800000011920928955', updated)
        self.assertIn('"Other" { "ScaleFactor" "0.8" }', updated)
        self.assertIn('"AutoScaleFactor" "1.423"', updated)
        self.assertIn('"Escaped" "a \\"quoted\\" value"', updated)
        self.assertEqual(module.remove_persisted(updated), updated)

    def test_preserves_other_user_scaling(self):
        text = '"InstallConfigStore" { "Accessibility" { "DesktopUIScale" "1.25" } }'
        self.assertEqual(module.remove_persisted(text), text)

    def test_malformed_persisted_config_refused(self):
        with self.assertRaises(ValueError):
            module.remove_persisted('"InstallConfigStore" {')
