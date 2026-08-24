#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

require_omarchy

plugin_id="per-monitor-bar"
plugin_url="https://github.com/priyeshbhawsar15/omarchy-per-monitor-bar.git"

if omarchy plugin list --json | jq -e --arg id "$plugin_id" 'any(.[]; .id == $id)' >/dev/null; then
  log "Per-monitor Omarchy bar plugin is already installed."
  exit 0
fi

omarchy plugin add "$plugin_url" --enable --yes
log "Installed the per-monitor Omarchy bar plugin. Drag each bar independently to an edge."
