#!/bin/bash
# Apply connector-specific preferences after feature installers, preserving secrets/state.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
command -v python3 >/dev/null || { printf 'Python 3 is required.\n' >&2; exit 1; }
changed="$(python3 - "$SCRIPT_DIR" <<'PY'
import json, pathlib, shutil, sys, time
home = pathlib.Path.home()
repo = pathlib.Path(sys.argv[1])
backup = home / '.local/state/arch-setups/backups' / ('monitor-layout-' + str(time.time_ns()))
changed = False

def save(path, content):
    global changed
    if path.read_bytes() == content:
        return
    dest = backup / path.relative_to(home)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
    path.write_bytes(content)
    changed = True

for name in ('wallpaper-controller', 'obsidian-tasks', 'shell'):
    path = home / '.config/omarchy' / (name + '.json')
    if not path.exists():
        continue
    data = json.loads(path.read_text())
    if name == 'wallpaper-controller':
        data['spanGroups'] = [['DP-5', 'DP-4']]
    elif name == 'obsidian-tasks':
        data['targetScreen'] = 'DP-5'
    else:
        for plugin in data.get('plugins', []):
            if plugin.get('id') == 'io.github.sirjul1337.lock-explorer':
                power = plugin.get('phasedPower')
                if power:
                    power.update(main='DP-6', sides=['DP-5', 'DP-4'])
    # Do not rewrite files merely for formatting.
    if data != json.loads(path.read_text()):
        save(path, (json.dumps(data, indent=2) + '\n').encode())

for name in ('GroupSlot.qml', 'BarSection.qml'):
    path = home / '.config/omarchy/plugins/hancore.shibumi.bar/core' / name
    if path.exists():
        save(path, (repo / 'shibumi' / name).read_bytes())
path = home / '.config/hypr/scripts/monitor-mode-toggle.sh'
if path.exists():
    save(path, (repo / 'hypr/scripts/monitor-mode-toggle.sh').read_bytes())
print('changed' if changed else 'current')
if changed:
    print('Backups: ' + str(backup), file=sys.stderr)
PY
)"
if [[ "$changed" == current ]]; then
  printf 'Monitor layout is already installed.\n'
  exit 0
fi
if command -v wallpaper-controller >/dev/null; then
  # Restore intentionally keeps an existing process; explicitly reapply only
  # when enabled so connector changes replace its old command line.
  active="$(python3 -c 'import json,pathlib; c=json.loads((pathlib.Path.home()/".config/omarchy/wallpaper-controller.json").read_text()); print(c.get("active", "") if c.get("wallpaperEnabled", True) else "")')"
  if [[ -n "$active" ]]; then
    wallpaper-controller apply "$active"
  else
    wallpaper-controller restore
  fi
fi
printf 'Configured DP-6 main, DP-5/DP-4 side widgets and wallpaper span.\n'
