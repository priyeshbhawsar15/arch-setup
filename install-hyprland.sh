#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

require_omarchy
command -v python3 >/dev/null || { log "Python 3 is required for monitor configuration."; exit 1; }

if [[ ! -f /usr/share/omarchy/config/hypr/hyprland.lua ]]; then
  log "Omarchy Quattro Hyprland Lua configuration is not available."
  exit 1
fi

config_dir="$HOME/.config/hypr"
state_toggle_dir="$HOME/.local/state/omarchy/toggles/hypr"
legacy_backup_dir=""
configuration_backup_dir=""

managed_files=(
  .luarc.json
  monitors.lua
  input.lua
  bindings.lua
  looknfeel.lua
  autostart.lua
  scripts/monitor-mode-toggle.sh
  scripts/window-span-dp6-dp4-toggle.sh
  scripts/bar-visibility-mode-toggle.sh
  scripts/shell-recover.sh
)

legacy_files=(
  "$config_dir/hyprland.conf"
  "$config_dir/monitors.conf"
  "$config_dir/input.conf"
  "$config_dir/bindings.conf"
  "$config_dir/looknfeel.conf"
  "$config_dir/autostart.conf"
  "$state_toggle_dir/desktop-single-monitor.conf"
  "$state_toggle_dir/flags.conf"
)

as_root() {
  if (( EUID == 0 )); then
    "$@"
  elif [[ -t 0 ]]; then
    sudo "$@"
  else
    pkexec "$@"
  fi
}

configuration_is_current() {
  local relative_path

  for relative_path in "${managed_files[@]}"; do
    if [[ "$relative_path" == monitors.lua || "$relative_path" == scripts/monitor-mode-toggle.sh || "$relative_path" == scripts/window-span-dp6-dp4-toggle.sh ]]; then
      continue # Deployed and checked by the shared monitor installer below.
    fi
    cmp -s "$SCRIPT_DIR/hypr/$relative_path" "$config_dir/$relative_path" || return 1
    if [[ "$relative_path" == scripts/* && ! -x "$config_dir/$relative_path" ]]; then return 1; fi
  done

  for legacy_file in "${legacy_files[@]}"; do
    [[ ! -e "$legacy_file" ]] || return 1
  done

  cmp -s "$SCRIPT_DIR/sddm/10-wayland.conf" /etc/sddm.conf.d/10-wayland.conf || return 1
  [[ ! -e /etc/sddm.conf.d/10-wayland.conf.pacnew ]]
}

# Reject unknown entrypoint edits before replacing any personal modules.
entrypoint_result="$(python3 "$SCRIPT_DIR/hypr/scripts/monitor-layout.py" \
  --config "$SCRIPT_DIR/monitor-layout.json" migrate-entrypoint \
  --package /usr/share/omarchy/config/hypr/hyprland.lua)"

monitor_result="$(python3 "$SCRIPT_DIR/hypr/scripts/monitor-layout.py" \
  --config "$SCRIPT_DIR/monitor-layout.json" install --repo "$SCRIPT_DIR" --hypr-only)"
if configuration_is_current && [[ "$monitor_result" == *'"changed": false'* && "$entrypoint_result" == *'"changed": false'* ]]; then
  log "Hyprland Quattro configuration is already installed."
  exit 0
fi

existing_legacy=()
for legacy_file in "${legacy_files[@]}"; do
  [[ -e "$legacy_file" || -L "$legacy_file" ]] && existing_legacy+=("$legacy_file")
done
if ((${#existing_legacy[@]})); then
  legacy_backup_dir="$(backup_feature_paths hyprland-legacy "${existing_legacy[@]}")"
  rm -f -- "${existing_legacy[@]}"
fi

changed_destinations=()
for relative_path in "${managed_files[@]}"; do
  [[ "$relative_path" == monitors.lua || "$relative_path" == scripts/monitor-mode-toggle.sh || "$relative_path" == scripts/window-span-dp6-dp4-toggle.sh ]] && continue
  destination_file="$config_dir/$relative_path"
  if [[ -e "$destination_file" || -L "$destination_file" ]] && ! cmp -s "$SCRIPT_DIR/hypr/$relative_path" "$destination_file"; then
    changed_destinations+=("$destination_file")
  elif [[ "$relative_path" == scripts/* && -e "$destination_file" && ! -x "$destination_file" ]]; then
    changed_destinations+=("$destination_file")
  fi
done
if [[ -e /etc/sddm.conf.d/10-wayland.conf ]] && ! cmp -s "$SCRIPT_DIR/sddm/10-wayland.conf" /etc/sddm.conf.d/10-wayland.conf; then
  changed_destinations+=(/etc/sddm.conf.d/10-wayland.conf)
fi
if [[ -e /etc/sddm.conf.d/10-wayland.conf.pacnew ]]; then
  changed_destinations+=(/etc/sddm.conf.d/10-wayland.conf.pacnew)
fi
if ((${#changed_destinations[@]})); then
  configuration_backup_dir="$(backup_feature_paths hyprland-config "${changed_destinations[@]}")"
  log "Backed up changed Hyprland/SDDM files to: $configuration_backup_dir"
fi

for relative_path in "${managed_files[@]}"; do
  [[ "$relative_path" == monitors.lua || "$relative_path" == scripts/monitor-mode-toggle.sh || "$relative_path" == scripts/window-span-dp6-dp4-toggle.sh ]] && continue
  source_file="$SCRIPT_DIR/hypr/$relative_path"
  destination_file="$config_dir/$relative_path"
  destination_dir="$(dirname -- "$destination_file")"

  mkdir -p -- "$destination_dir"
  if ! cmp -s "$source_file" "$destination_file"; then
    mode=644
    [[ ! -e "$destination_file" ]] || mode="$(stat -c %a -- "$destination_file")"
    install -Dm "$mode" "$source_file" "$destination_file"
  fi
  if [[ "$relative_path" == scripts/* && ! -x "$destination_file" ]]; then
    chmod u+x -- "$destination_file"
  fi
done

if ! cmp -s "$SCRIPT_DIR/sddm/10-wayland.conf" /etc/sddm.conf.d/10-wayland.conf; then
  log "Updating the SDDM Hyprland Lua entrypoint..."
  sddm_mode=644
  [[ ! -e /etc/sddm.conf.d/10-wayland.conf ]] || sddm_mode="$(stat -c %a -- /etc/sddm.conf.d/10-wayland.conf)"
  as_root install -Dm "$sddm_mode" "$SCRIPT_DIR/sddm/10-wayland.conf" /etc/sddm.conf.d/10-wayland.conf
fi

if [[ -e /etc/sddm.conf.d/10-wayland.conf.pacnew ]]; then
  log "Removing consumed SDDM pacnew file..."
  as_root rm -f -- /etc/sddm.conf.d/10-wayland.conf.pacnew
fi

if [[ -n "$legacy_backup_dir" ]]; then
  log "Archived legacy Hyprland configuration to: $legacy_backup_dir"
fi

if [[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]]; then
  hyprctl reload
  config_errors="$(hyprctl configerrors)"
  [[ -z "$config_errors" ]] || { printf '%s\n' "$config_errors" >&2; exit 1; }
else
  log "Hyprland is not available for live validation; it will load on the next session."
fi
