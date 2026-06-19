#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

if desktop_file_exists brave-origin-beta.desktop ||
  is_command_available brave-origin-beta; then
  log "Brave Origin is already installed."
  exit 0
fi

require_omarchy
log "Installing Brave Origin with Omarchy..."
omarchy install browser brave-origin

