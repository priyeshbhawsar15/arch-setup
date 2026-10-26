#!/usr/bin/env python3
"""Enable Steam background login startup without changing its menu launcher."""
import os
from pathlib import Path
import re
import shlex
import shutil
import time


def configure(text):
    sections = re.split(r'(?m)(?=^\[)', text)
    found = False
    for i, section in enumerate(sections):
        if not section.startswith('[Desktop Entry]\n'):
            continue
        if found:
            raise ValueError('Duplicate Desktop Entry section')
        found = True
        commands = re.findall(r'(?m)^Exec=(.*)$', section)
        if len(commands) != 1:
            raise ValueError('Expected exactly one main Steam Exec entry')
        args = shlex.split(commands[0])
        if not args or args[0] not in ('steam', '/usr/bin/steam') or any(
                a not in ('-silent', '%U', '%u') for a in args[1:]):
            raise ValueError('Unrecognized custom Steam autostart command; refusing replacement')
        section = re.sub(r'(?m)^Exec=.*$', 'Exec=/usr/bin/steam -silent', section)
        for key, value in [('Hidden', 'false'), ('X-GNOME-Autostart-enabled', 'true')]:
            if re.search(r'(?m)^' + key + '=', section):
                section = re.sub(r'(?m)^' + key + '=.*$', key + '=' + value, section)
        sections[i] = section
    if not found:
        raise ValueError('Missing Desktop Entry section')
    return ''.join(sections)


def main():
    target = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'autostart/steam.desktop'
    if target.is_symlink():
        raise SystemExit('Refusing autostart symlink: ' + str(target))
    source = target if target.exists() else Path('/usr/share/applications/steam.desktop')
    text = source.read_text()
    updated = configure(text)
    if target.exists() and text == updated:
        print('Steam background autostart already installed.')
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.copy2(target, target.with_name(target.name + '.bak-background-' + str(time.time_ns())))
    temp = target.with_name('.steam.desktop.tmp')
    temp.write_text(updated)
    temp.chmod(0o644)
    temp.replace(target)
    print('Steam will start silently at desktop login; current Steam session unchanged.')


if __name__ == '__main__':
    main()
