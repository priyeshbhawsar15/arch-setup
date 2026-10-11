#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

if desktop_file_exists zen.desktop ||
  is_command_available zen ||
  is_command_available zen-browser; then
  log "Zen is already installed."
  exit 0
fi

require_omarchy
log "Installing Zen with Omarchy..."
omarchy install browser zen
