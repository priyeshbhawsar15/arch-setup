#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

lutris_installed=false
if is_command_available lutris || pacman -Q lutris >/dev/null 2>&1; then
  lutris_installed=true
  log "Lutris is already installed."
else
  require_omarchy
  log "Installing Lutris with Omarchy..."
  omarchy pkg add lutris
fi

# Sync Steam library and non-Steam games into Lutris with full launch options
# Lutris and PyGObject are Arch's Python modules, not a mise Python environment.
/usr/bin/python3 "$SCRIPT_DIR/steam/sync-lutris-steam.py"

# Personal direct-Proton profiles run after generic Steam imports. Third-party
# upscalers are pinned/verified; no game files, saves or Steam tokens are stored.
if ! is_command_available 7z; then
  require_omarchy
  omarchy pkg add 7zip
fi
/usr/bin/python3 "$SCRIPT_DIR/steam/configure-gaming-profile.py" --apply --upscalers

if [[ "$lutris_installed" == false ]]; then
  log "Lutris installed and game library synchronized."
fi
