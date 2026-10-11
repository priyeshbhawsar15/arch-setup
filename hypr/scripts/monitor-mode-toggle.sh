#!/bin/bash

set -euo pipefail

toggle_dir="$HOME/.local/state/omarchy/toggles/hypr"
toggle_file="$toggle_dir/desktop-single-monitor.lua"
legacy_toggle_file="$toggle_dir/desktop-single-monitor.conf"

mkdir -p "$toggle_dir"

if [[ -f "$toggle_file" ]]; then
  rm -f -- "$toggle_file" "$legacy_toggle_file"
  notify-send -u low "󰍹    Multi-monitor mode enabled"
  hyprctl reload
  if command -v wallpaper-controller >/dev/null 2>&1; then
    (sleep 1.8 && wallpaper-controller restore >/dev/null 2>&1) &
  fi
else
  pkill -f 'linux-wallpaperengine' 2>/dev/null || true
  cat >"$toggle_file" <<'EOF'
hl.monitor({ output = "desc:Lenovo Group Limited LEN S22e-19 0x01010101", disabled = true })
hl.monitor({ output = "desc:Lenovo Group Limited LEN S22e-19 0x59333830", disabled = true })
hl.monitor({ output = "DP-5", disabled = true })
hl.monitor({ output = "DP-4", disabled = true })
EOF
  notify-send -u low "󰍹    Single monitor mode enabled"
  hyprctl eval 'hl.monitor({ output = "desc:Lenovo Group Limited LEN S22e-19 0x01010101", disabled = true }); hl.monitor({ output = "desc:Lenovo Group Limited LEN S22e-19 0x59333830", disabled = true }); hl.monitor({ output = "DP-5", disabled = true }); hl.monitor({ output = "DP-4", disabled = true })'
  if command -v wallpaper-controller >/dev/null 2>&1; then
    (sleep 0.4 && wallpaper-controller restore >/dev/null 2>&1) &
  fi
fi
