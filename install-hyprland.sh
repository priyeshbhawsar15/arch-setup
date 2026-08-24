#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

require_omarchy

if [[ ! -f /usr/share/omarchy/config/hypr/hyprland.lua ]]; then
  log "Omarchy Quattro Hyprland Lua configuration is not available."
  exit 1
fi

config_dir="$HOME/.config/hypr"
state_toggle_dir="$HOME/.local/state/omarchy/toggles/hypr"
legacy_backup_dir=""

managed_files=(
  .luarc.json
  monitors.lua
  input.lua
  bindings.lua
  looknfeel.lua
  autostart.lua
  scripts/bar-visibility-mode-toggle.sh
  scripts/monitor-mode-toggle.sh
  scripts/window-span-dp6-dp4-toggle.sh
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
    cmp -s "$SCRIPT_DIR/hypr/$relative_path" "$config_dir/$relative_path" || return 1
  done

  for legacy_file in "${legacy_files[@]}"; do
    [[ ! -e "$legacy_file" ]] || return 1
  done

  cmp -s "$SCRIPT_DIR/sddm/10-wayland.conf" /etc/sddm.conf.d/10-wayland.conf || return 1
  [[ ! -e /etc/sddm.conf.d/10-wayland.conf.pacnew ]]
}

backup_legacy_file() {
  local legacy_file="$1"
  local backup_name

  [[ -e "$legacy_file" ]] || return 0

  if [[ -z "$legacy_backup_dir" ]]; then
    legacy_backup_dir="$config_dir/omarchy-v3-migration-backup-$(date +%Y%m%d%H%M%S)"
    mkdir -p -- "$legacy_backup_dir"
  fi

  backup_name="${legacy_file#$config_dir/}"
  backup_name="${backup_name//\//__}"
  mv -- "$legacy_file" "$legacy_backup_dir/$backup_name"
}

if configuration_is_current; then
  log "Hyprland Quattro configuration is already installed."
  exit 0
fi

for legacy_file in "${legacy_files[@]}"; do
  backup_legacy_file "$legacy_file"
done

for relative_path in "${managed_files[@]}"; do
  source_file="$SCRIPT_DIR/hypr/$relative_path"
  destination_file="$config_dir/$relative_path"
  destination_dir="$(dirname -- "$destination_file")"

  mkdir -p -- "$destination_dir"
  if ! cmp -s "$source_file" "$destination_file"; then
    install -Dm644 "$source_file" "$destination_file"
    [[ "$relative_path" == scripts/* ]] && chmod +x "$destination_file"
  fi
done

if ! cmp -s "$SCRIPT_DIR/sddm/10-wayland.conf" /etc/sddm.conf.d/10-wayland.conf; then
  log "Updating the SDDM Hyprland Lua entrypoint..."
  as_root install -Dm644 "$SCRIPT_DIR/sddm/10-wayland.conf" /etc/sddm.conf.d/10-wayland.conf
fi

if [[ -e /etc/sddm.conf.d/10-wayland.conf.pacnew ]]; then
  log "Removing consumed SDDM pacnew file..."
  as_root rm -f -- /etc/sddm.conf.d/10-wayland.conf.pacnew
fi

if [[ -n "$legacy_backup_dir" ]]; then
  log "Archived legacy Hyprland configuration to: $legacy_backup_dir"
fi

if [[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]] && hyprctl reload; then
  hyprctl configerrors
else
  log "Hyprland is not available for live validation; it will load on the next session."
fi
