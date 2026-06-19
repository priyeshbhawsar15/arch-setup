#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

if is_command_available sunshine || pacman -Q sunshine >/dev/null 2>&1; then
  log "Sunshine is already installed."
  exit 0
fi

require_omarchy
log "Installing Sunshine with Omarchy..."
omarchy pkg add sunshine
