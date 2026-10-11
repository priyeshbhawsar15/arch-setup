#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

lutris_installed=false
if is_command_available lutris || pacman -Q lutris >/dev/null 2>&1; then
  lutris_installed=true
else
  require_omarchy
  log "Installing Lutris with Omarchy..."
  omarchy pkg add lutris
fi

# Sync Steam library and non-Steam games into Lutris with full launch options
if [[ -f "$SCRIPT_DIR/steam/sync-lutris-steam.py" ]]; then
  python3 "$SCRIPT_DIR/steam/sync-lutris-steam.py"
fi

if [[ "$lutris_installed" == true ]]; then
  log "Lutris and game library configurations are current."
else
  log "Lutris installed and game library synchronized."
fi
