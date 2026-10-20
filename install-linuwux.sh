#!/bin/bash
# Shared DenuvOwO launch support, independent of any game/display profile.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

if ! is_command_available umu-run; then
  require_omarchy
  log "Installing UMU launcher with Omarchy..."
  omarchy pkg add umu-launcher
fi

/usr/bin/python3 "$SCRIPT_DIR/gaming/denuvowo/configure.py" --apply
