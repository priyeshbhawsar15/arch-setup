#!/usr/bin/env python3
"""Keep Steam desktop UI at 80%, without changing monitor or game scaling."""
from pathlib import Path
import re
import shutil
import time


def configure(text):
    return re.sub(
        r'^Exec=(?:env (?:GDK_SCALE=1 )?STEAM_FORCE_DESKTOPUI_SCALING=[0-9.]+ )?'
        r'(?:/usr/bin/)?steam(?: -forcedesktopscaling [0-9.]+)?(?=\s|$)',
        'Exec=env GDK_SCALE=1 STEAM_FORCE_DESKTOPUI_SCALING=0.8 /usr/bin/steam -forcedesktopscaling 0.8',
        text, flags=re.MULTILINE)


def main():
    target = Path.home() / '.local/share/applications/steam.desktop'
    source = target if target.exists() else Path('/usr/share/applications/steam.desktop')
    text = source.read_text()
    updated = configure(text)
    if 'Exec=env GDK_SCALE=1 STEAM_FORCE_DESKTOPUI_SCALING=0.8 /usr/bin/steam -forcedesktopscaling 0.8' not in updated:
        raise SystemExit('Unrecognized custom Steam launcher; refusing to overwrite it')
    if target.exists() and updated == text:
        print('Steam UI scaling already configured at 80%.')
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.copy2(target, target.with_name(target.name + '.bak-ui-scale-' + str(time.time_ns())))
    target.write_text(updated)
    print('Steam launcher UI scaling set to 80%; fully exit Steam and relaunch from the application menu.')


if __name__ == '__main__':
    main()
