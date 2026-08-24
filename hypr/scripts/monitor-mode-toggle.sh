#!/bin/bash

set -euo pipefail

toggle_dir="$HOME/.local/state/omarchy/toggles/hypr"
toggle_file="$toggle_dir/desktop-single-monitor.lua"
legacy_toggle_file="$toggle_dir/desktop-single-monitor.conf"

mkdir -p "$toggle_dir"

if [[ -f "$toggle_file" ]]; then
  rm -f -- "$toggle_file" "$legacy_toggle_file"
  notify-send -u low "󰍹    Multi-monitor mode enabled"
else
  cat >"$toggle_file" <<'EOF'
hl.monitor({ output = "DP-6", disabled = true })
hl.monitor({ output = "DP-4", disabled = true })
EOF
  notify-send -u low "󰍹    Single monitor mode enabled"
fi

hyprctl reload
