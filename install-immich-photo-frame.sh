#!/usr/bin/env bash

# Installs Immich Photo Frame for Omarchy at a reviewed pinned commit.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
feature_lifecycle "$0" "$@"

plugin_id="priyesh.immich-photo-frame"
plugin_url="https://github.com/priyeshbhawsar15/omarchy-immich-photo-frame.git"
plugin_commit="6221323be37f96bd17b18f0875bb062f9fbe66d3"
plugin_dir="$HOME/.config/omarchy/plugins/$plugin_id"
config_file="$HOME/.config/omarchy/immich-photo-frame.json"

require_omarchy

fail() {
  log "Immich Photo Frame: $*"
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
  install_pinned_plugin "$plugin_dir" "$plugin_url" "$plugin_commit" "$plugin_id"
}

update_pinned_plugin() {
  install_pinned_plugin "$plugin_dir" "$plugin_url" "$plugin_commit" "$plugin_id"
}

seed_configuration() {
  python3 "$SCRIPT_DIR/config/setup-inputs.py" widget immich-photo-frame
  log "Immich credentials are local prerequisites; readiness is checked by doctor.sh."
}

enable_plugin() {
  omarchy-shell shell rescanPlugins >/dev/null
  wait_for_plugin_discovery
  omarchy plugin enable "$plugin_id"
  reconcile_plugin_helper immich-photo-frame "$plugin_dir/bin/immich-photo-frame"
  plugin_is_enabled || fail "Omarchy did not enable $plugin_id"
}

disable_plugin() {
  if plugin_is_enabled; then
    omarchy plugin disable "$plugin_id"
  fi
  remove_plugin_helper immich-photo-frame "$plugin_dir/bin/immich-photo-frame"
  log "Immich Photo Frame is disabled."
}

backup_feature_data() {
  backup_feature_paths immich-photo-frame-remove "$config_file" "$HOME/.local/state/omarchy/immich-photo-frame"
}

remove_plugin() {
  plugin_checkout_is_current || fail "the managed pinned checkout is unavailable or modified"
  local backup_dir
  backup_dir="$(backup_feature_data)"
  disable_plugin
  omarchy plugin remove "$plugin_id" --yes
  log "Removed Immich Photo Frame. Configuration and cached photo data were backed up to: $backup_dir"
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

seed_configuration

reconcile_plugin_helper immich-photo-frame "$plugin_dir/bin/immich-photo-frame"

if plugin_is_enabled && [[ "$checkout_changed" == false ]]; then
  log "Immich Photo Frame is already installed."
  exit 0
fi

if plugin_is_enabled; then
  omarchy plugin disable "$plugin_id"
fi

enable_plugin
log "Installed and activated Immich Photo Frame at $plugin_commit."
