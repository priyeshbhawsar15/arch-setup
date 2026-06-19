#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

if is_command_available keyd || pacman -Q keyd >/dev/null 2>&1; then
  log "keyd is already installed."
else
  require_omarchy
  log "Installing keyd with Omarchy..."
  omarchy pkg add keyd
fi

log "Installing keyd config..."
sudo install -Dm644 "$SCRIPT_DIR/keyd/default.conf" /etc/keyd/default.conf

log "Enabling keyd..."
sudo systemctl enable --now keyd
