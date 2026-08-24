#!/bin/bash

set -euo pipefail

state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/omarchy/per-monitor-bar"
state_file="$state_dir/visibility-mode"
current="always"

if [[ -r "$state_file" ]]; then
  current="$(<"$state_file")"
fi

case "$current" in
  always) next="auto"; label="Auto-hide" ;;
  auto) next="disabled"; label="Disabled" ;;
  *) next="always"; label="Always show" ;;
esac

mkdir -p -- "$state_dir"
temporary_file="$(mktemp "$state_dir/.visibility-mode.XXXXXX")"
printf '%s\n' "$next" >"$temporary_file"
mv -f -- "$temporary_file" "$state_file"

omarchy-notification-send "Top bar" "$label" -g "󰍹"
