#!/bin/bash

set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

# Do not replace an explicitly selected nightly installation.
if ! is_command_available t3code && ! is_command_available t3code-nightly; then
  require_omarchy
  omarchy pkg add t3code-bin
fi

# Keep both integrations on the same mise-backed commands used by the terminal.
"$SCRIPT_DIR/install-codex.sh"
"$SCRIPT_DIR/install-github-cli.sh"
python3 "$SCRIPT_DIR/t3/configure-codex.py" "${T3CODE_HOME:-$HOME/.t3}/userdata/settings.json"
