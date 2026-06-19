#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

if is_command_available zsh; then
  log "zsh is already installed."
else
  require_omarchy
  log "Installing zsh with Omarchy..."
  omarchy pkg add zsh
fi

zsh_path="$(command -v zsh)"
current_shell="$(getent passwd "$USER" | cut -d: -f7)"

if [[ "$current_shell" == "$zsh_path" ]]; then
  log "zsh is already the default shell."
  exit 0
fi

log "Setting zsh as the default shell..."
chsh -s "$zsh_path" "$USER"
