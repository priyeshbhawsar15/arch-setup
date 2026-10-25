import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('steam_autostart', Path(__file__).with_name('configure-autostart.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AutostartTests(unittest.TestCase):
    def test_only_main_command_changed(self):
        text = '[Desktop Entry]\nName=Steam\nExec=/usr/bin/steam %U\n\n[Desktop Action BigPicture]\nExec=/usr/bin/steam steam://open/bigpicture\n'
        updated = module.configure(text)
        self.assertIn('Exec=/usr/bin/steam -silent\n', updated)
        self.assertIn('Exec=/usr/bin/steam steam://open/bigpicture\n', updated)
        self.assertIn('Name=Steam\n', updated)
        self.assertEqual(module.configure(updated), updated)

    def test_reenables_disabled_entry(self):
        text = '[Desktop Entry]\nExec=steam\nHidden=true\nX-GNOME-Autostart-enabled=false\n'
        updated = module.configure(text)
        self.assertIn('Hidden=false', updated)
        self.assertIn('X-GNOME-Autostart-enabled=true', updated)

    def test_rejects_custom_commands(self):
        for command in ['/custom/steam', 'env SPECIAL=1 steam', 'steam -bigpicture']:
            with self.assertRaises(ValueError):
                module.configure('[Desktop Entry]\nExec=' + command + '\n')

    def test_missing_or_duplicate_main_entry_rejected(self):
        for text in ['[Other]\nExec=steam\n', '[Desktop Entry]\nExec=steam\nExec=steam\n']:
            with self.assertRaises(ValueError):
                module.configure(text)
