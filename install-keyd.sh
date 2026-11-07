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
backup_dir=""
# default.conf: physical keyboards. sunshine.conf: Sunshine's virtual keyboard.
for name in default.conf sunshine.conf; do
  cmp -s "$SCRIPT_DIR/keyd/$name" "/etc/keyd/$name" && continue
  if sudo test -e "/etc/keyd/$name" || sudo test -L "/etc/keyd/$name"; then
    if [[ -z "$backup_dir" ]]; then
      backup_dir="${XDG_STATE_HOME:-$HOME/.local/state}/arch-setups/backups/keyd-$(date +%Y%m%dT%H%M%S)-$$"
      mkdir -p "$backup_dir"
      chmod 700 "$backup_dir"
    fi
    sudo cp -a "/etc/keyd/$name" "$backup_dir/$name"
    log "Backed up keyd configuration to $backup_dir/$name"
  fi
  log "Installing keyd config $name..."
  sudo install -Dm644 "$SCRIPT_DIR/keyd/$name" "/etc/keyd/$name"
  config_changed=true
done

if ! systemctl is-enabled --quiet keyd || ! systemctl is-active --quiet keyd; then
  log "Enabling keyd..."
  sudo systemctl enable --now keyd
fi
if [[ "$config_changed" == true ]]; then
  log "Reloading keyd configuration..."
  sudo keyd reload
fi
