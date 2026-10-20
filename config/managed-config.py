#!/usr/bin/env python3
"""Edit owned top-level menu keys without discarding JSONC comments or siblings."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
import time

LEXEME = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|[{}\[\]:,]|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null', re.S)


def parse_menu(text):
    """Validate JSONC and retain token spans used for surgical edits."""
    tokens = []
    clean = list(text)
    for match in LEXEME.finditer(text):
        value = match.group()
        if value.startswith(('//', '/*')):
            clean[match.start():match.end()] = ['\n' if c == '\n' else ' ' for c in value]
        else:
            tokens.append((value, match.start(), match.end()))
    for index, token in enumerate(tokens[:-1]):
        if token[0] == ',' and tokens[index + 1][0] in ('}', ']'):
            clean[token[1]] = ' '
    data = json.loads(''.join(clean))
    if not isinstance(data, dict):
        raise ValueError('menu must be a JSONC object')
    entries = {}
    index = 1
    previous_comma = None
    while index < len(tokens) - 1:
        key = json.loads(tokens[index][0])
        key_start = tokens[index][1]
        index += 2  # key and colon
        value_start = tokens[index][1]
        depth = 0
        while True:
            token = tokens[index]
            if token[0] in ('{', '['):
                depth += 1
            elif token[0] in ('}', ']'):
                depth -= 1
            index += 1
            if depth == 0:
                break
        value_end = tokens[index - 1][2]
        comma = tokens[index][1] if tokens[index][0] == ',' else None
        if key in entries:
            raise ValueError(f'duplicate menu key: {key}')
        entries[key] = (key_start, value_start, value_end, comma, previous_comma)
        if comma is not None:
            previous_comma = comma
            index += 1
    return data, entries, tokens[-1][1]


def merge_key(text, key, value):
    data, entries, closing = parse_menu(text)
    if key in data and data[key] == value:
        return text
    encoded = json.dumps(value, ensure_ascii=False, separators=(', ', ': '))
    if key in entries:
        _, start, end, _, _ = entries[key]
        return text[:start] + encoded + text[end:]
    if entries:
        last = next(reversed(entries.values()))
        if last[3] is None:
            text = text[:last[2]] + ',' + text[last[2]:]
            closing += 1
    addition = '\n  ' + json.dumps(key, ensure_ascii=False) + ': ' + encoded + '\n'
    return text[:closing] + addition + text[closing:]


def remove_key(text, key):
    _, entries, _ = parse_menu(text)
    if key not in entries:
        return text
    start, _, end, following_comma, previous_comma = entries[key]
    if following_comma is not None:
        return text[:start] + text[following_comma + 1:]
    text = text[:start] + text[end:]
    if previous_comma is not None:
        text = text[:previous_comma] + text[previous_comma + 1:]
    return text


def replace_atomic(path, text):
    if path.is_symlink():
        raise ValueError(f'refusing to replace symlinked menu: {path}')
    parse_menu(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    if path.exists():
        state = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state')))
        parent = state / 'arch-setups/backups'
        parent.mkdir(parents=True, exist_ok=True)
        backup = Path(tempfile.mkdtemp(prefix=f'menu-{time.time_ns()}-', dir=parent))
        shutil.copy2(path, backup / path.name)
        print(f'Menu backup: {backup}', file=sys.stderr)
    fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('merge-menu', 'check-menu'):
        command = sub.add_parser(name)
        command.add_argument('path', type=Path)
        command.add_argument('entries', type=json.loads)
        command.add_argument('--keep-existing', action='append', default=[])
    command = sub.add_parser('remove-menu')
    command.add_argument('path', type=Path)
    command.add_argument('keys', nargs='+')
    command.add_argument('--empty-parent')
    args = parser.parse_args()
    original = args.path.read_text() if args.path.exists() else '{\n}\n'
    data, _, _ = parse_menu(original)
    if args.command == 'check-menu':
        return 0 if args.path.exists() and all(data.get(k) == v for k, v in args.entries.items()) else 1
    text = original
    if args.command == 'merge-menu':
        if not isinstance(args.entries, dict):
            raise ValueError('entries must be an object')
        for key, value in args.entries.items():
            if key in args.keep_existing and key in data:
                continue
            text = merge_key(text, key, value)
    else:
        for key in args.keys:
            text = remove_key(text, key)
        if args.empty_parent:
            remaining, _, _ = parse_menu(text)
            if not any(k.startswith(args.empty_parent + '.') for k in remaining):
                text = remove_key(text, args.empty_parent)
    if text != original or not args.path.exists():
        replace_atomic(args.path, text)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        print(f'managed-config: {error}', file=sys.stderr)
        sys.exit(2)
