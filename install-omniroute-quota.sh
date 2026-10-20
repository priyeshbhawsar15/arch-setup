#!/usr/bin/env bash

# Installs OmniRoute Quota Monitor for Omarchy at a pinned commit.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

plugin_id="priyesh.omniroute-quota"
plugin_url="https://github.com/priyeshbhawsar15/omarchy-omniroute-quota.git"
plugin_commit="b2e3be74e29d9d94e97be9db3d0242641d5b2348"
plugin_dir="$HOME/.config/omarchy/plugins/$plugin_id"
config_file="$HOME/.config/omarchy/omniroute-quota.json"

require_omarchy

fail() {
  log "OmniRoute Quota: $*"
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
  if [[ -f "$config_file" ]]; then
    chmod 600 "$config_file"
    return
  fi
  mkdir -p -- "$(dirname -- "$config_file")"
  cat >"$config_file" <<'EOF'
{
  "endpoint": "https://omniroute.home.priyeshbhawsar.com",
  "token": "",
  "refreshIntervalSeconds": 60,
  "targetScreen": "DP-4",
  "position": "top-right",
  "width": 320,
  "topMargin": 40,
  "rightMargin": 16
}
EOF
  chmod 600 "$config_file"
}

enable_plugin() {
  omarchy-shell shell rescanPlugins >/dev/null
  wait_for_plugin_discovery
  omarchy plugin enable "$plugin_id"
  reconcile_plugin_helper omniroute-quota "$plugin_dir/bin/omniroute-quota"
  plugin_is_enabled || fail "Omarchy did not enable $plugin_id"
}

disable_plugin() {
  if plugin_is_enabled; then
    omarchy plugin disable "$plugin_id"
  fi
  remove_plugin_helper omniroute-quota "$plugin_dir/bin/omniroute-quota"
  log "OmniRoute Quota is disabled."
}

backup_feature_data() {
  backup_feature_paths omniroute-quota-remove "$config_file" "$HOME/.local/state/omarchy/omniroute-quota"
}

remove_plugin() {
  plugin_checkout_is_current || fail "the managed pinned checkout is unavailable or modified"
  local backup_dir
  backup_dir="$(backup_feature_data)"
  disable_plugin
  omarchy plugin remove "$plugin_id" --yes
  log "Removed OmniRoute Quota. Configuration and state were backed up to: $backup_dir"
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

reconcile_plugin_helper omniroute-quota "$plugin_dir/bin/omniroute-quota"

if plugin_is_enabled && [[ "$checkout_changed" == false ]]; then
  log "OmniRoute Quota is already installed."
  exit 0
fi

if plugin_is_enabled; then
  omarchy plugin disable "$plugin_id"
fi

enable_plugin
log "Installed and activated OmniRoute Quota at $plugin_commit."
