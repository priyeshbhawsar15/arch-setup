#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

if is_command_available thunderbird || desktop_file_exists org.mozilla.Thunderbird.desktop; then
  log "Thunderbird is already installed."
  exit 0
fi

require_omarchy
log "Installing Thunderbird with Omarchy..."
omarchy pkg add thunderbird
