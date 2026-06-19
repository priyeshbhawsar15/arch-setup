#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

if is_command_available tailscale || pacman -Q tailscale >/dev/null 2>&1; then
  log "Tailscale is already installed."
  exit 0
fi

require_omarchy
log "Installing Tailscale with Omarchy..."
omarchy pkg add tailscale

log "Enabling tailscaled..."
sudo systemctl enable --now tailscaled
