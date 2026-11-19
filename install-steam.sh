#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

# Both historical flags now REMOVE the retired override; neither can reapply 80%.
if [[ "${1:-}" == "--ui-scale-only" || "${1:-}" == "--ui-scale-reset" ]]; then
  python3 "$SCRIPT_DIR/steam/configure-ui-scale.py"
  exit 0
fi

if [[ "${1:-}" == "--background-startup-only" ]]; then
  python3 "$SCRIPT_DIR/steam/configure-autostart.py"
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

# Remove the retired launcher AND Steam-persisted 80% values before startup setup.
python3 "$SCRIPT_DIR/steam/configure-ui-scale.py"
# Keep login startup silent without altering interactive menu/Big Picture launchers.
python3 "$SCRIPT_DIR/steam/configure-autostart.py"

selection="$(python3 "$SCRIPT_DIR/config/setup-inputs.py" gaming)"
hdr_selected="$(python3 -c 'import json,sys; p=json.loads(sys.argv[1]); print(p["steamHdr"] or p["lutrisHdr"] or any(g["config"].get("system",{}).get("prefix_command")=="steam-gamescope-hdr" for g in p["games"]))' "$selection")"
if [[ "$hdr_selected" != True ]]; then
  if [[ "$steam_installed" == true ]]; then log "Steam is already installed."; else log "Steam installed."; fi
  log "Game launch options and HDR are unmanaged (opt-in); retired UI scaling is removed."
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

# `game-display` switches every wrapped game between 4K HDR and 1080p SDR.
target_switch="$local_bin/game-display"
if [[ -e "$target_switch" || -L "$target_switch" ]] && ! { [[ ! -L "$target_switch" && -f "$target_switch" ]] && grep -q '^# Managed by arch-setups' "$target_switch"; }; then
  log "Preserving unknown game-display helper: $target_switch" >&2; exit 1
fi
if [[ ! -f "$target_switch" ]] || ! cmp -s "$SCRIPT_DIR/steam/game-display" "$target_switch" || [[ ! -x "$target_switch" ]]; then
  [[ ! -f "$target_switch" ]] || backup_feature_paths game-display "$target_switch" >/dev/null
  cp "$SCRIPT_DIR/steam/game-display" "$target_switch"
  chmod +x "$target_switch"
  wrapper_changed=true
fi
# 1080p mode targets the host policy's Sunshine capture monitor; the chosen mode is kept.
stream_monitor="$(python3 -c '
import json, sys
policy = json.load(open(sys.argv[1]))
role = (policy.get("sunshineStream") or {}).get("capture")
entry = policy.get("monitors", {}).get(role) or {}
print("desc:" + entry["description"] if entry.get("description") else entry.get("connector", ""))
' "${ARCH_SETUPS_MONITOR_LAYOUT:-$SCRIPT_DIR/monitor-layout.json}")"
display_settings="${XDG_STATE_HOME:-$HOME/.local/state}/omarchy/game-display/settings.json"
if [[ "$(jq -r '.streamMonitor // ""' "$display_settings" 2>/dev/null || true)" != "$stream_monitor" ]]; then
  "$target_switch" set-stream-monitor "$stream_monitor"
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
