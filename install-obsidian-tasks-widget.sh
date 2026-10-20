#!/usr/bin/env bash

# Installs the Obsidian Tasks desktop widget at a reviewed pinned commit.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

plugin_id="priyesh.obsidian-tasks"
plugin_url="https://github.com/priyeshbhawsar15/omarchy-obsidian-tasks.git"
plugin_commit="c930f029ee43043163de2946b7c780c8f995353f"
plugin_dir="$HOME/.config/omarchy/plugins/$plugin_id"
config_file="$HOME/.config/omarchy/obsidian-tasks.json"

require_omarchy

fail() {
  log "Obsidian Tasks: $*"
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
    return
  fi

  mkdir -p -- "$(dirname -- "$config_file")"
  cat >"$config_file" <<'EOF'
{
  "vaultPath": "/home/priyesh/Documents/Obsidian/pb",
  "vaultName": "pb",
  "dashboardPath": "00 Home/Tasks.md",
  "targetScreen": "DP-5"
}
EOF
}

enable_plugin() {
  omarchy-shell shell rescanPlugins >/dev/null
  wait_for_plugin_discovery
  omarchy plugin enable "$plugin_id"
  reconcile_plugin_helper obsidian-tasks-widget "$plugin_dir/bin/obsidian-tasks-widget"
  plugin_is_enabled || fail "Omarchy did not enable $plugin_id"
}

disable_plugin() {
  if plugin_is_enabled; then
    omarchy plugin disable "$plugin_id"
  fi
  remove_plugin_helper obsidian-tasks-widget "$plugin_dir/bin/obsidian-tasks-widget"
  log "Obsidian Tasks widget is disabled."
}

backup_feature_data() {
  backup_feature_paths obsidian-tasks-remove "$config_file" "$HOME/.local/state/omarchy/obsidian-tasks"
}

remove_plugin() {
  plugin_checkout_is_current || fail "the managed pinned checkout is unavailable or modified"
  local backup_dir
  backup_dir="$(backup_feature_data)"
  disable_plugin
  omarchy plugin remove "$plugin_id" --yes
  log "Removed Obsidian Tasks. Configuration and cached task state were backed up to: $backup_dir"
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
ensure_command obsidian obsidian

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

reconcile_plugin_helper obsidian-tasks-widget "$plugin_dir/bin/obsidian-tasks-widget"

if plugin_is_enabled && [[ "$checkout_changed" == false ]]; then
  log "Obsidian Tasks widget is already installed."
  exit 0
fi

if plugin_is_enabled; then
  omarchy plugin disable "$plugin_id"
fi

enable_plugin
log "Installed and activated Obsidian Tasks widget at $plugin_commit."
