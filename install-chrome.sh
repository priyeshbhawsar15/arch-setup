#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

if desktop_file_exists google-chrome.desktop ||
  is_command_available google-chrome-stable ||
  is_command_available google-chrome; then
  log "Chrome is already installed."
  exit 0
fi

require_omarchy
log "Installing Chrome with Omarchy..."
omarchy install browser chrome

