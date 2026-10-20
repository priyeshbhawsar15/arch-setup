#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

if is_command_available tailscale || pacman -Q tailscale >/dev/null 2>&1; then
  log "Tailscale is already installed."
else
  require_omarchy
  log "Installing Tailscale with Omarchy..."
  omarchy pkg add tailscale
fi

if ! systemctl is-enabled --quiet tailscaled || ! systemctl is-active --quiet tailscaled; then
  log "Enabling tailscaled..."
  sudo systemctl enable --now tailscaled
else
  log "tailscaled is already enabled and running."
fi
