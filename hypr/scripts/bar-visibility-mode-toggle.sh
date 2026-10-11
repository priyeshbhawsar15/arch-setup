#!/usr/bin/env bash

# Cycles top bar visibility between Always show, Auto-hide, and Disabled.
# Communicates with Shibumi Shell / Omarchy bar through state toggles.

set -euo pipefail

toggles_dir="${XDG_STATE_HOME:-$HOME/.local/state}/omarchy/toggles"
mkdir -p -- "$toggles_dir"

if [[ -f "$toggles_dir/bar-off" ]]; then
  # Currently Disabled -> switch to Always show
  rm -f -- "$toggles_dir/bar-off" "$toggles_dir/bar-autohide"
  label="Always show"
  icon="󰍹"
elif [[ -f "$toggles_dir/bar-autohide" ]]; then
  # Currently Auto-hide -> switch to Disabled
  rm -f -- "$toggles_dir/bar-autohide"
  touch "$toggles_dir/bar-off"
  label="Disabled"
  icon="󰍺"
else
  # Currently Always show -> switch to Auto-hide
  rm -f -- "$toggles_dir/bar-off"
  touch "$toggles_dir/bar-autohide"
  label="Auto-hide"
  icon="󰍺"
fi

if command -v omarchy-notification-send >/dev/null 2>&1; then
  omarchy-notification-send "Top bar" "$label" -g "$icon"
elif command -v notify-send >/dev/null 2>&1; then
  notify-send "Top bar" "$label"
fi
