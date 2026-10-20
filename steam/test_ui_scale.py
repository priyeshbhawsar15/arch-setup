import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('steam_ui_scale', Path(__file__).with_name('configure-ui-scale.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class UiScaleTests(unittest.TestCase):
    def test_main_and_actions_preserve_arguments(self):
        text = 'Exec=/usr/bin/steam %U\nExec=steam steam://open/games\nName=Steam\n'
        result = module.configure(text)
        self.assertIn('GDK_SCALE=1 STEAM_FORCE_DESKTOPUI_SCALING=0.8 /usr/bin/steam -forcedesktopscaling 0.8 %U', result)
        self.assertIn('STEAM_FORCE_DESKTOPUI_SCALING=0.8 /usr/bin/steam -forcedesktopscaling 0.8 steam://open/games', result)
        self.assertIn('Name=Steam', result)

    def test_idempotent(self):
        once = module.configure('Exec=/usr/bin/steam %U\n')
        self.assertEqual(module.configure(once), once)

    def test_migrates_existing_managed_scale(self):
        result = module.configure('Exec=env STEAM_FORCE_DESKTOPUI_SCALING=1 /usr/bin/steam %U\n')
        self.assertEqual(result, 'Exec=env GDK_SCALE=1 STEAM_FORCE_DESKTOPUI_SCALING=0.8 /usr/bin/steam -forcedesktopscaling 0.8 %U\n')

    def test_unrelated_exec_unchanged(self):
        text = 'Exec=/custom/launcher --steam\n'
        self.assertEqual(module.configure(text), text)
