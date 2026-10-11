#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

if desktop_file_exists hermes-desktop.desktop ||
  is_command_available hermes-desktop ||
  pacman -Q hermes-desktop >/dev/null 2>&1; then
  log "Hermes Desktop is already installed."
  exit 0
fi

require_omarchy
log "Installing Hermes Desktop with Omarchy..."
omarchy pkg add hermes-desktop
