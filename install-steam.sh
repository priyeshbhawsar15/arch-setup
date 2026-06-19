#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

if is_command_available steam || pacman -Q steam >/dev/null 2>&1; then
  log "Steam is already installed."
  exit 0
fi

require_omarchy
log "Installing Steam with Omarchy..."
omarchy pkg add steam
