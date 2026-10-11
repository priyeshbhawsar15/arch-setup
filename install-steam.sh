#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

steam_installed=false
if is_command_available steam || pacman -Q steam >/dev/null 2>&1; then
  steam_installed=true
else
  require_omarchy
  log "Installing Steam with Omarchy..."
  omarchy pkg add steam
fi

if ! is_command_available gamescope || ! pacman -Q gamescope >/dev/null 2>&1; then
  require_omarchy
  log "Installing Gamescope with Omarchy..."
  omarchy pkg add gamescope
fi

# Deploy the Gamescope HDR launcher wrapper
local_bin="${HOME}/.local/bin"
mkdir -p "$local_bin"
target_wrapper="$local_bin/steam-gamescope-hdr"
source_wrapper="$SCRIPT_DIR/steam/gamescope-hdr"

wrapper_changed=false
if [[ ! -f "$target_wrapper" ]] || ! cmp -s "$source_wrapper" "$target_wrapper"; then
  cp "$source_wrapper" "$target_wrapper"
  chmod +x "$target_wrapper"
  wrapper_changed=true
fi

# Configure Gamescope HDR across all installed Steam games
configured_output=""
if [[ -d "${HOME}/.local/share/Steam/userdata" ]]; then
  configured_output="$(python3 "$SCRIPT_DIR/steam/configure-gamescope-hdr.py")"
fi

if [[ "$steam_installed" == true && "$wrapper_changed" == false && "$configured_output" == *"already have"* ]]; then
  log "Steam and Gamescope HDR game configurations are current."
else
  log "Steam and Gamescope HDR configurations updated."
  if [[ -n "$configured_output" ]]; then
    printf '%s\n' "$configured_output"
  fi
fi
