#!/usr/bin/env python3
"""Remove the retired 80% Steam UI override; never install a scaling override."""
import argparse
from pathlib import Path
import re
import shutil
import tempfile
import time


def restore(text):
    # Strip only known scaling assignments at the front of a Steam Exec command.
    return re.sub(
        r'^Exec=(?:env (?:GDK_SCALE=1 )?STEAM_FORCE_DESKTOPUI_SCALING=[0-9.]+ )?'
        r'((?:/usr/bin/)?steam)(?: -forcedesktopscaling [0-9.]+)?(?=\s|$)',
        r'Exec=\1', text, flags=re.MULTILINE)


def remove_persisted(text):
    """Surgically remove only the old 0.8 values at known desktop UI VDF paths."""
    targets = {
        ('InstallConfigStore', 'Accessibility', 'DesktopUIScale'),
        ('InstallConfigStore', 'UI', 'display', 'Current', 'ScaleFactor'),
    }
    tokens = list(re.finditer(r'"((?:\\.|[^"\\])*)"|([{}])', text))
    stack, spans = [], []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.group(2) == '}':
            if not stack:
                raise ValueError('Unbalanced Steam VDF')
            stack.pop()
            i += 1
        elif token.group(1) is not None and i + 1 < len(tokens):
            following = tokens[i + 1]
            if following.group(2) == '{':
                stack.append(token.group(1))
                i += 2
            elif following.group(1) is not None:
                if tuple(stack + [token.group(1)]) in targets:
                    try:
                        old_override = abs(float(following.group(1)) - .8) < .00001
                    except ValueError:
                        old_override = False
                    if old_override:
                        start, end = token.start(), following.end()
                        line = text.rfind('\n', 0, start) + 1
                        if not text[line:start].strip():
                            start = line
                        while end < len(text) and text[end] in ' \t\r':
                            end += 1
                        if end < len(text) and text[end] == '\n':
                            end += 1
                        spans.append((start, end))
                i += 2
            else:
                raise ValueError('Unexpected Steam VDF value')
        else:
            raise ValueError('Unexpected Steam VDF token')
    if stack:
        raise ValueError('Unclosed Steam VDF')
    for start, end in reversed(spans):
        text = text[:start] + text[end:]
    return text


def steam_running():
    for p in Path('/proc').glob('[0-9]*/comm'):
        try:
            if p.read_text().strip() == 'steam':
                return True
        except OSError:
            pass
    return False


def write_changed(target, original, updated):
    if original == updated:
        return False
    if target.is_symlink():
        raise ValueError('Refusing symlink: ' + str(target))
    if target.read_text() != original:
        raise ValueError('Steam file changed during reset: ' + str(target))
    backup = target.with_name(target.name + '.bak-ui-reset-' + str(time.time_ns()))
    shutil.copy2(target, backup)
    backup.chmod(0o600)
    with tempfile.NamedTemporaryFile(mode='w', dir=target.parent, delete=False) as stream:
        stream.write(updated)
        temp = Path(stream.name)
    try:
        temp.chmod(target.stat().st_mode & 0o777)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore', action='store_true', help='Compatibility alias; reset is now the only behavior')
    parser.parse_args()
    home = Path.home()
    config = home / '.local/share/Steam/config/config.vdf'
    changed = False
    # Check before modifying any files. A running client can overwrite saved settings.
    original = config.read_text() if config.exists() else None
    updated = remove_persisted(original) if original is not None else None
    if original != updated and steam_running():
        raise SystemExit('Close Steam before removing its saved 80% UI scaling settings.')
    if original is not None:
        changed |= write_changed(config, original, updated)
    import os
    config_home = Path(os.environ.get('XDG_CONFIG_HOME', home / '.config'))
    data_home = Path(os.environ.get('XDG_DATA_HOME', home / '.local/share'))
    for target in (data_home / 'applications/steam.desktop', config_home / 'autostart/steam.desktop'):
        if target.exists():
            text = target.read_text()
            changed |= write_changed(target, text, restore(text))
    print('Retired Steam 80% scaling override removed.' if changed else 'No retired Steam scaling override present.')


if __name__ == '__main__':
    main()
