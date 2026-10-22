#!/usr/bin/env python3
"""Check the exact public source APIs used by customized plugin installers.

Downloads source as data only: never executes remote code, changes pins, or
fetches private plugins. This is a network contract check, not live acceptance.
"""
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def fetch(source, pin, path):
    match = re.fullmatch(r'https://github.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\.git', source)
    if not match or not re.fullmatch(r'[a-f0-9]{40}', pin):
        raise ValueError('invalid pinned GitHub source')
    url = f'https://raw.githubusercontent.com/{match[1]}/{pin}/{path}'
    with urllib.request.urlopen(url, timeout=25) as response:
        return response.read(2_000_000).decode()


def check(sources, getter=fetch):
    shibumi = sources['install-shibumi-shell.sh']
    cli = getter(shibumi['source'], shibumi['pin'], 'scripts/shibumi_suite/cli.py')
    for flag in ('--user-layout', '--keep-layout'):
        if not re.search(r'add_argument\(\s*[\'"]' + re.escape(flag) + r'[\'"]', cli):
            raise ValueError('Pinned Shibumi CLI lacks ' + flag)
    omaland = sources['install-omaland.sh']
    manifest = json.loads(getter(omaland['source'], omaland['pin'], 'manifest.json'))
    if manifest.get('id') != 'bobbynicholas.omaland' or manifest.get('archSetups', {}).get('personalModule') != 'hypr/looknfeel.lua':
        raise ValueError('Pinned Omaland manifest does not implement the personal-module contract')


if __name__ == '__main__':
    try:
        check(json.loads((ROOT / 'config/plugin-sources.json').read_text()))
        print('Exact public Shibumi/Omaland source contracts passed.')
    except (OSError, ValueError, KeyError, urllib.error.URLError) as error:
        print('Source contract check failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
