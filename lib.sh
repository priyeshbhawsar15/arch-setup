#!/bin/bash

set -euo pipefail

log() {
  printf '%s\n' "$*"
}

is_command_available() {
  command -v "$1" >/dev/null 2>&1
}

desktop_file_exists() {
  local desktop_file="$1"

  [[ -f "$HOME/.local/share/applications/$desktop_file" ]] ||
    [[ -f "/usr/share/applications/$desktop_file" ]] ||
    [[ -f "$HOME/.nix-profile/share/applications/$desktop_file" ]]
}

require_omarchy() {
  if ! is_command_available omarchy; then
    log "omarchy is not available on PATH."
    exit 1
  fi
}

