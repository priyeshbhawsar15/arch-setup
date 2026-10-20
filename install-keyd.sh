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

config_changed=false
if ! cmp -s "$SCRIPT_DIR/keyd/default.conf" /etc/keyd/default.conf; then
  if sudo test -e /etc/keyd/default.conf || sudo test -L /etc/keyd/default.conf; then
    backup_dir="${XDG_STATE_HOME:-$HOME/.local/state}/arch-setups/backups/keyd-$(date +%Y%m%dT%H%M%S)-$$"
    mkdir -p "$backup_dir"
    chmod 700 "$backup_dir"
    sudo cp -a /etc/keyd/default.conf "$backup_dir/default.conf"
    log "Backed up keyd configuration to $backup_dir/default.conf"
  fi
  log "Installing keyd config..."
  sudo install -Dm644 "$SCRIPT_DIR/keyd/default.conf" /etc/keyd/default.conf
  config_changed=true
fi

if ! systemctl is-enabled --quiet keyd || ! systemctl is-active --quiet keyd; then
  log "Enabling keyd..."
  sudo systemctl enable --now keyd
fi
if [[ "$config_changed" == true ]]; then
  log "Reloading keyd configuration..."
  sudo keyd reload
fi
