#!/usr/bin/env bash

# Installs Omaland (Hyprland Visual Look & Feel Editor) for Omarchy at a pinned commit.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
feature_lifecycle "$0" "$@"

plugin_id="bobbynicholas.omaland"
plugin_url="https://github.com/priyeshbhawsar15/omaland.git"
upstream_url="https://github.com/bobby-nicholas/omaland.git"
plugin_commit="796f134b98f97363290f13a5708eaf1045e11325"
plugin_dir="$HOME/.config/omarchy/plugins/$plugin_id"

menu_file="$HOME/.config/omarchy/extensions/omarchy-menu.jsonc"
desktop_file="$HOME/.local/share/applications/omaland.desktop"

require_omarchy

fail() {
  log "Omaland: $*"
  exit 1
}

ensure_command() {
  local command="$1" package="$2"
  if command -v "$command" >/dev/null 2>&1; then
    return
  fi
  log "Installing required command '$command'..."
  omarchy pkg add "$package"
}

plugin_checkout_is_current() {
  managed_plugin_checkout_current "$plugin_dir" "$plugin_url" "$plugin_commit"
}

plugin_is_enabled() {
  omarchy plugin list --json | jq -e --arg id "$plugin_id" \
    'any(.[]; .id == $id and .enabled)' >/dev/null
}

wait_for_plugin_discovery() {
  local attempt
  for (( attempt = 0; attempt < 40; attempt++ )); do
    if omarchy plugin list --json | jq -e --arg id "$plugin_id" \
      'any(.[]; .id == $id)' >/dev/null; then
      return
    fi
    sleep 0.05
  done
  fail "Omarchy did not discover $plugin_id after a plugin rescan"
}

checkout_pinned_plugin() {
  install_pinned_plugin "$plugin_dir" "$plugin_url" "$plugin_commit" "$plugin_id" "$upstream_url"
}

update_pinned_plugin() {
  checkout_pinned_plugin
}

enable_plugin() {
  omarchy-shell shell rescanPlugins >/dev/null
  wait_for_plugin_discovery
  omarchy plugin enable "$plugin_id"
  install_desktop_entry
  install_menu_entry
  plugin_is_enabled || fail "Omarchy did not enable $plugin_id"
}

install_desktop_entry() {
  if [[ -e "$desktop_file" || -L "$desktop_file" ]]; then
    if [[ -L "$desktop_file" ]] || ! grep -q '^X-Omaland-Managed=true$' "$desktop_file"; then
      log "Preserving custom Omaland desktop entry: $desktop_file"
      return 0
    fi
  fi
  local stage
  mkdir -p -- "$(dirname -- "$desktop_file")"
  stage="$(mktemp "${desktop_file}.XXXXXX")"
  sed "s|@ICON@|$plugin_dir/icon.png|" "$plugin_dir/omaland.desktop" > "$stage"
  chmod 755 "$stage"
  if [[ -f "$desktop_file" ]] && cmp -s "$stage" "$desktop_file" && [[ -x "$desktop_file" ]]; then
    rm -- "$stage"
    return 0
  fi
  if [[ -f "$desktop_file" ]]; then backup_feature_paths omaland-desktop "$desktop_file" >/dev/null; fi
  mv -- "$stage" "$desktop_file"
  update-desktop-database "$(dirname -- "$desktop_file")" >/dev/null 2>&1 || true
}

remove_desktop_entry() {
  if [[ -f "$desktop_file" && ! -L "$desktop_file" ]] && grep -q '^X-Omaland-Managed=true$' "$desktop_file"; then
    rm -f -- "$desktop_file"
    update-desktop-database "$(dirname -- "$desktop_file")" >/dev/null 2>&1 || true
  fi
}

menu_entries() {
  jq -cn \
    --arg edit 'omarchy-launch-config-editor "$HOME/.config/hypr/looknfeel.lua"' \
    '{"style.hyprland": {icon:"󰸌", label:"Hyprland", aliases:["hyprland","looknfeel"]},
      "style.hyprland.omaland": {icon:"󰸌", label:"Omaland Visual Editor", aliases:["omaland"], action:"omarchy-shell shell toggle bobbynicholas.omaland"},
      "style.hyprland.edit": {icon:"󰏫", label:"Edit Config", action:$edit}}'
}

install_menu_entry() {
  python3 "$SCRIPT_DIR/config/managed-config.py" merge-menu "$menu_file" "$(menu_entries)" \
    --keep-existing style.hyprland
}

remove_menu_entry() {
  [[ -f "$menu_file" ]] || return 0
  python3 "$SCRIPT_DIR/config/managed-config.py" remove-menu "$menu_file" \
    style.hyprland.omaland style.hyprland.edit --empty-parent style.hyprland
}

disable_plugin() {
  if plugin_is_enabled; then
    omarchy plugin disable "$plugin_id"
  fi
  remove_desktop_entry
  remove_menu_entry
  log "Omaland is disabled."
}

backup_feature_data() {
  local backup_dir path relative_path
  backup_dir="$HOME/.local/state/arch-setups/backups/omaland-remove-$(date +%Y%m%d%H%M%S)"
  install -d -m700 -- "$backup_dir"
  for path in "$HOME/.config/hypr/looknfeel.lua" "$HOME/.config/hypr/hyprland.lua" "$menu_file" "$desktop_file"; do
    [[ -e "$path" || -L "$path" ]] || continue
    relative_path="${path#$HOME/}"
    mkdir -p -- "$backup_dir/$(dirname -- "$relative_path")"
    cp -a -- "$path" "$backup_dir/$relative_path"
  done
  printf '%s\n' "$backup_dir"
}

remove_plugin() {
  plugin_checkout_is_current || fail "the managed pinned checkout is unavailable or modified"
  local backup_dir
  backup_dir="$(backup_feature_data)"
  disable_plugin
  omarchy plugin remove "$plugin_id" --yes
  log "Removed Omaland. Configuration and state were backed up to: $backup_dir"
}

case "${1:-}" in
  --disable) disable_plugin; exit 0 ;;
  --remove) remove_plugin; exit 0 ;;
  "") ;;
  *) fail "usage: $0 [--disable|--remove]" ;;
esac

ensure_command git git
ensure_command jq jq
ensure_command python3 python
ensure_command lua lua

checkout_changed=false
if [[ -e "$plugin_dir" || -L "$plugin_dir" ]]; then
  if ! plugin_checkout_is_current; then
    update_pinned_plugin
    checkout_changed=true
  fi
else
  checkout_pinned_plugin
  checkout_changed=true
fi

jq -e '.archSetups.personalModule == "hypr/looknfeel.lua"' "$plugin_dir/manifest.json" >/dev/null \
  || fail "the reviewed personal-module fork must be published and pinned before activation"

if plugin_is_enabled && [[ "$checkout_changed" == false ]]; then
  install_desktop_entry
  install_menu_entry
  log "Omaland is already installed."
  exit 0
fi

if plugin_is_enabled; then
  omarchy plugin disable "$plugin_id"
fi

enable_plugin
log "Installed and activated Omaland at $plugin_commit."
