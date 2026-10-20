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
  # Validate the kept display before stopping wallpapers or disabling anything.
  rules="$(python3 "$(dirname -- "${BASH_SOURCE[0]}")/monitor-layout.py" single-monitor-lua 2>&1)" || {
    notify-send -u low "$rules"
    exit 1
  }
  pkill -f 'linux-wallpaperengine' 2>/dev/null || true
  printf '%s\n' "$rules" >"$toggle_file"
  notify-send -u low "󰍹    Single monitor mode enabled"
  hyprctl eval "$rules"
  if command -v wallpaper-controller >/dev/null 2>&1; then
    (sleep 0.4 && wallpaper-controller restore >/dev/null 2>&1) &
  fi
fi
