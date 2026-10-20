#!/usr/bin/env bash

# Installs System Metrics HUD for Omarchy at a pinned commit.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

plugin_id="priyesh.system-metrics"
plugin_url="https://github.com/priyeshbhawsar15/omarchy-system-metrics.git"
plugin_commit="aac22520daa5f27b94699dad3479c8d811062995"
plugin_dir="$HOME/.config/omarchy/plugins/$plugin_id"

require_omarchy

fail() {
  log "System Metrics: $*"
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

enable_plugin() {
  omarchy-shell shell rescanPlugins >/dev/null
  wait_for_plugin_discovery
  omarchy plugin enable "$plugin_id"
  reconcile_plugin_helper system-metrics-collector "$plugin_dir/bin/system-metrics-collector"
  plugin_is_enabled || fail "Omarchy did not enable $plugin_id"
}

disable_plugin() {
  if plugin_is_enabled; then
    omarchy plugin disable "$plugin_id"
  fi
  remove_plugin_helper system-metrics-collector "$plugin_dir/bin/system-metrics-collector"
  log "System Metrics HUD is disabled."
}

backup_feature_data() {
  backup_feature_paths system-metrics-remove "$HOME/.config/omarchy/system-metrics.json" "$HOME/.config/system-metrics" "$HOME/.local/state/omarchy/system-metrics"
}

remove_plugin() {
  plugin_checkout_is_current || fail "the managed pinned checkout is unavailable or modified"
  local backup_dir
  backup_dir="$(backup_feature_data)"
  disable_plugin
  omarchy plugin remove "$plugin_id" --yes
  log "Removed System Metrics HUD. Configuration and state were backed up to: $backup_dir"
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

python3 "$SCRIPT_DIR/hypr/scripts/monitor-layout.py" --config "$SCRIPT_DIR/monitor-layout.json" \
  configure-widget .config/omarchy/system-metrics.json || fail "cannot configure the System Metrics display"

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

reconcile_plugin_helper system-metrics-collector "$plugin_dir/bin/system-metrics-collector"

if plugin_is_enabled && [[ "$checkout_changed" == false ]]; then
  log "System Metrics HUD is already installed."
  exit 0
fi

if plugin_is_enabled; then
  omarchy plugin disable "$plugin_id"
fi

enable_plugin
if [[ "$checkout_changed" == true ]]; then
  # An existing QML service can retain its old component after a pin update.
  omarchy restart shell
fi
log "Installed and activated System Metrics HUD at $plugin_commit."
