#!/usr/bin/env python3
"""Deploy the pinned Fluentbird userChrome theme into the active Thunderbird profile.

Ownership is recorded in a private manifest inside the profile's chrome/ folder.
Only manifest-listed files are ever replaced or removed. Foreign files, symlinks
and unrelated user.js lines are preserved, and anything this helper changes is
backed up privately first. Running Thunderbird is never touched: userChrome.css
and user.js are read at startup, so a restart applies the change.

Exit codes: 0 changed, 10 already current / nothing to do, 11 no profile yet,
1 error (message on stderr; nothing was changed when a conflict is reported).
"""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
MANIFEST = '.arch-setups-fluentbird.json'
BEGIN = '// >>> arch-setups fluentbird (managed; do not edit) >>>'
END = '// <<< arch-setups fluentbird <<<'
PREF = 'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);'
BLOCK = BEGIN + '\n' + PREF + '\n' + END + '\n'
BLOCK_PATTERN = re.compile(re.escape(BEGIN) + r'.*?' + re.escape(END) + r'\n?', re.S)
# Upstream entries deployed as-is. custom.css is repo-owned personal CSS (the
# upstream stub is deliberately not used) and LICENSE travels as the MIT notice.
UPSTREAM = ('userChrome.css', 'Icons', 'Titlebar_Icons')
LICENSE_NAME = 'LICENSE.fluentbird'
DEFAULT_THEME = 'default-theme@mozilla.org'
CHANGED, UNCHANGED, NO_PROFILE = 0, 10, 11


class Problem(Exception):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def roots():
    override = os.environ.get('ARCH_SETUPS_THUNDERBIRD_DIR')
    if override:
        return [Path(override)]
    config = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    return [Path.home() / '.thunderbird', config / 'thunderbird']


def find_profile(explicit=None):
    """Return the profile Thunderbird starts with, or None before its first run."""
    explicit = explicit or os.environ.get('ARCH_SETUPS_THUNDERBIRD_PROFILE')
    if explicit:
        path = Path(explicit)
        return path if path.is_dir() else None
    for root in roots():
        ini = root / 'profiles.ini'
        if not ini.is_file():
            continue
        parser = configparser.RawConfigParser(strict=False)
        parser.optionxform = str
        try:
            parser.read(ini, encoding='utf-8')
        except (configparser.Error, UnicodeDecodeError, OSError):
            continue

        def locate(value, relative=True):
            path = Path(value)
            return path if path.is_absolute() or not relative else root / path

        # The per-installation default is what this Thunderbird actually opens;
        # a profile flagged Default=1 may belong to an older/other installation.
        defaults = {locate(parser[name]['Default']) for name in parser.sections()
                    if name.startswith('Install') and parser[name].get('Default')}
        defaults = sorted(path for path in defaults if path.is_dir())
        if len(defaults) > 1:
            raise Problem('Several Thunderbird installations declare different default profiles; choose one with --profile.')
        if defaults:
            return defaults[0]
        for name in parser.sections():
            section = parser[name]
            if name.startswith('Profile') and section.get('Default') == '1' and section.get('Path'):
                path = locate(section['Path'], section.get('IsRelative', '1') != '0')
                if path.is_dir():
                    return path
    return None


def collect(source, custom):
    """Desired relative path -> bytes, from the pinned checkout and the repo custom CSS."""
    source = Path(source)
    wanted = {}
    for entry in UPSTREAM:
        base = source / entry
        if base.is_symlink():
            raise Problem(f'Refusing symlink in theme source: {base}')
        if base.is_file():
            wanted[entry] = base.read_bytes()
        elif base.is_dir():
            for path in sorted(base.rglob('*')):
                if path.is_symlink():
                    raise Problem(f'Refusing symlink in theme source: {path}')
                if path.is_file():
                    wanted[path.relative_to(source).as_posix()] = path.read_bytes()
        else:
            raise Problem(f'Theme source lacks {entry}: {source}')
    licence = source / 'LICENSE'
    if licence.is_file() and not licence.is_symlink():
        wanted[LICENSE_NAME] = licence.read_bytes()
    wanted['custom.css'] = Path(custom).read_bytes()
    return wanted


def read_manifest(chrome):
    try:
        data = json.loads((chrome / MANIFEST).read_text())
        files = data['files']
        if isinstance(files, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in files.items()):
            return {'revision': str(data.get('revision', '')), 'files': files}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return {'revision': '', 'files': {}}


def atomic_write(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name + '.')
    try:
        with os.fdopen(handle, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


class Backup:
    """Private, lazily created archive of files before this helper changes them."""

    def __init__(self, profile):
        self.profile = profile
        self.directory = None

    def save(self, path):
        if not (path.exists() or path.is_symlink()):
            return
        if self.directory is None:
            state = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state')
            parent = state / 'arch-setups/backups'
            parent.mkdir(parents=True, exist_ok=True)
            self.directory = Path(tempfile.mkdtemp(prefix='fluentbird-' + time.strftime('%Y%m%dT%H%M%S') + '-', dir=parent))
        target = self.directory / path.relative_to(self.profile)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target, follow_symlinks=False)


def check_layout(profile):
    chrome = profile / 'chrome'
    if chrome.is_symlink():
        raise Problem(f'{chrome} is a symlink; refusing to manage a chrome folder owned elsewhere.')
    if chrome.exists() and not chrome.is_dir():
        raise Problem(f'{chrome} is not a directory.')
    return chrome


def inside_symlink(chrome, relative):
    current = chrome
    for part in Path(relative).parts[:-1]:
        current = current / part
        if current.is_symlink() or (current.exists() and not current.is_dir()):
            return True
    return False


def user_js_text(profile):
    path = profile / 'user.js'
    if path.is_symlink():
        raise Problem(f'{path} is a symlink; refusing to edit a user.js owned elsewhere.')
    if not path.exists():
        return path, None
    try:
        return path, path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as error:
        raise Problem(f'Cannot safely read {path}: {error}') from error


def with_block(text):
    if text is not None and BLOCK.rstrip('\n') in text:
        return text
    base = BLOCK_PATTERN.sub('', text or '')
    separator = '' if not base or base.endswith('\n') else '\n'
    return base + separator + BLOCK


def apply(profile, source, revision, custom):
    wanted = collect(source, custom)
    if 'userChrome.css' not in wanted:
        raise Problem('Theme source does not provide userChrome.css.')
    chrome = check_layout(profile)
    manifest = read_manifest(chrome)
    owned = manifest['files']
    hashes = {rel: digest(data) for rel, data in wanted.items()}

    conflicts, drifted, missing = [], [], []
    for rel, want in hashes.items():
        path = chrome / rel
        if inside_symlink(chrome, rel):
            conflicts.append(rel)
        elif not (path.exists() or path.is_symlink()):
            missing.append(rel)
        elif path.is_symlink() or not path.is_file():
            conflicts.append(rel)
        elif digest(path.read_bytes()) != want:
            (drifted if rel in owned else conflicts).append(rel)
    if conflicts:
        raise Problem('Refusing to overwrite files this setup does not own in ' + str(chrome) + ': '
                      + ', '.join(sorted(conflicts)) + '. Move them aside (or remove them) and rerun.')
    stale = [rel for rel in owned if rel not in wanted and (chrome / rel).is_file() and not (chrome / rel).is_symlink()
             and not inside_symlink(chrome, rel)]

    user_path, user_text = user_js_text(profile)
    new_user_text = with_block(user_text)
    manifest_current = manifest['revision'] == revision and set(owned) == set(wanted) and owned == hashes
    if not (missing or drifted or stale) and new_user_text == user_text and manifest_current:
        return UNCHANGED

    backup = Backup(profile)
    for rel in drifted + stale:
        backup.save(chrome / rel)
    for rel in missing + drifted:
        atomic_write(chrome / rel, wanted[rel], 0o644)
    for rel in stale:
        (chrome / rel).unlink()
    prune(chrome, stale)
    if new_user_text != user_text:
        backup.save(user_path)
        atomic_write(user_path, new_user_text.encode(), 0o600 if user_text is None else user_path.stat().st_mode & 0o777)
    atomic_write(chrome / MANIFEST, (json.dumps({'schema': 1, 'revision': revision, 'files': hashes}, indent=2, sort_keys=True) + '\n').encode(), 0o600)
    if backup.directory:
        print(f'Backed up replaced files to {backup.directory}')
    return CHANGED


def prune(chrome, removed):
    for directory in sorted({str(Path(rel).parent) for rel in removed if Path(rel).parent != Path('.')}, key=len, reverse=True):
        try:
            (chrome / directory).rmdir()
        except OSError:
            pass


def remove(profile):
    chrome = check_layout(profile)
    manifest = read_manifest(chrome)
    owned = manifest['files']
    user_path, user_text = user_js_text(profile)
    has_block = user_text is not None and BEGIN in user_text
    present = [rel for rel in owned if (chrome / rel).is_file() and not (chrome / rel).is_symlink() and not inside_symlink(chrome, rel)]
    if not present and not has_block and not (chrome / MANIFEST).exists():
        return UNCHANGED
    backup = Backup(profile)
    for rel in present:
        path = chrome / rel
        if digest(path.read_bytes()) != owned[rel]:
            backup.save(path)  # Preserve anything edited locally before deleting it.
        path.unlink()
    prune(chrome, present)
    (chrome / MANIFEST).unlink(missing_ok=True)
    try:
        chrome.rmdir()  # Only if the theme was all it held.
    except OSError:
        pass
    if has_block:
        backup.save(user_path)
        remaining = BLOCK_PATTERN.sub('', user_text)
        if remaining.strip():
            atomic_write(user_path, remaining.encode(), user_path.stat().st_mode & 0o777)
        else:
            user_path.unlink()
    if backup.directory:
        print(f'Backed up locally changed files to {backup.directory}')
    return CHANGED


def active_theme(profile):
    try:
        match = re.search(r'user_pref\("extensions\.activeThemeID",\s*"([^"]*)"\);', (profile / 'prefs.js').read_text(errors='replace'))
    except OSError:
        return None
    return match.group(1) if match else None


def status(profile, revision, custom):
    if profile is None:
        return dict(state='no-profile', profile=None, warnings=[],
                    message='Thunderbird has no profile yet: start it once, then rerun ./install-fluentbird.sh.')
    report = dict(profile=str(profile), warnings=[])
    chrome = profile / 'chrome'
    manifest = read_manifest(chrome)
    owned = manifest['files']
    theme = active_theme(profile)
    if theme not in (None, DEFAULT_THEME):
        report['warnings'].append(f'Thunderbird theme is {theme}; Fluentbird needs the System theme (Settings > General > Appearance).')
    if not owned:
        return dict(report, state='not-applied', message='Fluentbird is not deployed; run ./install-fluentbird.sh.')
    drift = [rel for rel, want in owned.items() if not (chrome / rel).is_file() or digest((chrome / rel).read_bytes()) != want]
    if drift:
        return dict(report, state='modified', message='Deployed theme files changed or are missing (' + ', '.join(sorted(drift)[:3]) + '); rerun ./install-fluentbird.sh.')
    try:
        _, text = user_js_text(profile)
    except Problem:
        text = None
    if not text or BLOCK.rstrip('\n') not in text:
        return dict(report, state='inactive', message='user.js lacks the stylesheet preference; rerun ./install-fluentbird.sh.')
    try:
        custom_current = owned.get('custom.css') == digest(Path(custom).read_bytes())
    except OSError:
        custom_current = False
    if manifest['revision'] != revision or not custom_current:
        return dict(report, state='stale', message='Deployed theme does not match the pinned revision/custom CSS; rerun ./install-fluentbird.sh.')
    return dict(report, state='current', message='Fluentbird deployed at the pinned revision; restart Thunderbird after changes.')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('apply', 'remove', 'status'):
        command = commands.add_parser(name)
        command.add_argument('--profile', help='Thunderbird profile directory (default: the installation default).')
        if name != 'remove':
            command.add_argument('--revision', required=True)
            command.add_argument('--custom', type=Path, default=HERE / 'fluentbird-custom.css')
        if name == 'apply':
            command.add_argument('--source', type=Path, required=True)
        if name == 'status':
            command.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        profile = find_profile(args.profile)
        if args.command == 'status':
            report = status(profile, args.revision, args.custom)
            if args.json:
                print(json.dumps(report))
            else:
                print(report['message'])
                for warning in report['warnings']:
                    print('Warning: ' + warning)
            return 0
        if profile is None:
            return NO_PROFILE
        if args.command == 'apply':
            return apply(profile, args.source, args.revision, args.custom)
        return remove(profile)
    except (Problem, OSError) as error:
        print('Fluentbird: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
