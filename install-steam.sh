#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

# Apply only the desktop UI fix safely while Steam/games are running.
if [[ "${1:-}" == "--ui-scale-only" ]]; then
  python3 "$SCRIPT_DIR/steam/configure-ui-scale.py"
  exit 0
fi

steam_installed=false
if is_command_available steam || pacman -Q steam >/dev/null 2>&1; then
  steam_installed=true
else
  require_omarchy
  log "Installing Steam with Omarchy..."
  omarchy pkg add steam
fi

selection="$(python3 "$SCRIPT_DIR/config/setup-inputs.py" gaming)"
hdr_selected="$(python3 -c 'import json,sys; p=json.loads(sys.argv[1]); print(p["steamHdr"] or any(g["config"].get("system",{}).get("prefix_command")=="steam-gamescope-hdr" for g in p["games"]))' "$selection")"
if [[ "$hdr_selected" != True ]]; then
  if [[ "$steam_installed" == true ]]; then log "Steam is already installed."; else log "Steam installed."; fi
  log "Game launch options, HDR and client scaling are unmanaged (opt-in)."
  exit 0
fi
if ! is_command_available gamescope || ! pacman -Q gamescope >/dev/null 2>&1; then
  require_omarchy
  log "Installing Gamescope with Omarchy..."
  omarchy pkg add gamescope
fi

# Deploy the Gamescope HDR launcher wrapper
local_bin="${HOME}/.local/bin"
mkdir -p "$local_bin"
target_wrapper="$local_bin/steam-gamescope-hdr"
source_wrapper="$SCRIPT_DIR/steam/gamescope-hdr"

wrapper_changed=false
if [[ -e "$target_wrapper" || -L "$target_wrapper" ]]; then
  [[ ! -L "$target_wrapper" && -f "$target_wrapper" ]] || { log "Preserving custom HDR helper/symlink: $target_wrapper" >&2; exit 1; }
  if ! cmp -s "$source_wrapper" "$target_wrapper" && ! grep -q '^# Managed by arch-setups' "$target_wrapper" && [[ "$(sha256sum "$target_wrapper" | cut -d' ' -f1)" != 47a5b2f661728bcdabece0a5dd8b7b3d050d3ef6dbeb3e77896d6567cb9f8f68 ]]; then
    log "Preserving unknown HDR helper: $target_wrapper" >&2; exit 1
  fi
fi
if [[ ! -f "$target_wrapper" ]] || ! cmp -s "$source_wrapper" "$target_wrapper"; then
  [[ ! -f "$target_wrapper" ]] || backup_feature_paths steam-hdr-wrapper "$target_wrapper" >/dev/null
  cp "$source_wrapper" "$target_wrapper"
  chmod +x "$target_wrapper"
  wrapper_changed=true
fi
if [[ ! -x "$target_wrapper" ]]; then
  chmod +x "$target_wrapper"
  wrapper_changed=true
fi

# Configure Gamescope HDR across all installed Steam games
configured_output=""
if [[ "$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["steamHdr"])' "$selection")" == True && -d "${HOME}/.local/share/Steam/userdata" ]]; then
  configured_output="$(python3 "$SCRIPT_DIR/steam/configure-gamescope-hdr.py")"
fi

if [[ "$steam_installed" == true && "$wrapper_changed" == false && "$configured_output" == *"already have"* ]]; then
  log "Steam and Gamescope HDR game configurations are current."
else
  log "Steam and Gamescope HDR configurations updated."
  if [[ -n "$configured_output" ]]; then
    printf '%s\n' "$configured_output"
  fi
fi
