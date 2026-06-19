#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

if is_command_available stow; then
  log "stow is already installed."
  exit 0
fi

require_omarchy
log "Installing stow with Omarchy..."
omarchy pkg add stow

