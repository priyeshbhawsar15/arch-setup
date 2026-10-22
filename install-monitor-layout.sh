#!/bin/bash
# Apply the central display-role policy after feature installers.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
command -v python3 >/dev/null || { log 'Python 3 is required.'; exit 1; }
result="$(python3 "$SCRIPT_DIR/hypr/scripts/monitor-layout.py" \
  --config "${ARCH_SETUPS_MONITOR_LAYOUT:-$SCRIPT_DIR/monitor-layout.json}" install --repo "$SCRIPT_DIR")"
if [[ "$result" == *'"changed": false'* ]]; then
  log 'Monitor layout is already installed.'
  exit 0
fi
if [[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]]; then
  hyprctl reload
  errors="$(hyprctl configerrors)"
  [[ -z "$errors" ]] || { printf '%s\n' "$errors" >&2; exit 1; }
fi
if [[ "$result" == *'"wallpaperChanged": true'* ]] && command -v wallpaper-controller >/dev/null; then
  active="$(python3 -c 'import json,pathlib; c=json.loads((pathlib.Path.home()/".config/omarchy/wallpaper-controller.json").read_text()); print(c.get("active", "") if c.get("wallpaperEnabled", True) else "")')"
  if [[ -n "$active" ]]; then
    wallpaper-controller apply "$active"
  else
    wallpaper-controller restore
  fi
fi
log 'Configured monitor roles from monitor-layout.json.'
