#!/usr/bin/env bash

# Installs the Shibumi-specific fork of Per-monitor Workspaces at one reviewed
# commit. The feature replaces Shibumi's workspace presentation, while its Lua
# actions provide named workspaces scoped to each focused monitor.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

plugin_id="mmsbrggr.per-monitor-workspaces"
plugin_url="https://github.com/priyeshbhawsar15/omarchy-per-monitor-workspaces.git"
plugin_commit="0292ebec608cd7d3907b8f9f9427c252b242edf2"
plugin_dir="$HOME/.config/omarchy/plugins/$plugin_id"
shell_config="$HOME/.config/omarchy/shell.json"
toggle_path="$HOME/.local/state/omarchy/toggles/hypr/per-monitor-workspaces.lua"
state_dir="$HOME/.local/state/omarchy"

bar_role="workspaces"
bar_state_file="${XDG_STATE_HOME:-$HOME/.local/state}/arch-setups/mmsbrggr.per-monitor-workspaces/bar-layout.json"

require_omarchy

fail() {
  log "Per-monitor Workspaces: $*"
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

shibumi_is_active() {
  [[ -f "$shell_config" ]] || return 1
  jq -e '.bar.id == "hancore.shibumi.bar"' "$shell_config" >/dev/null
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

plugin_is_configured() {
  [[ -f "$shell_config" && -f "$toggle_path" ]] || return 1
  jq -e --arg id "$plugin_id" '
    .bar.id == "hancore.shibumi.bar"
    and any(.bar.layout.left[], .bar.layout.center[], .bar.layout.right[];
      type == "object" and .id == $id and .shibumiModule == true and .count == 5)
  ' "$shell_config" >/dev/null && manage_bar_layout check
}

checkout_pinned_plugin() {
  install_pinned_plugin "$plugin_dir" "$plugin_url" "$plugin_commit" "$plugin_id"
}

update_pinned_plugin() {
  checkout_pinned_plugin
}

write_enabled_toggle() {
  mkdir -p -- "$(dirname -- "$toggle_path")"
  cat > "$toggle_path" <<'EOF'
-- Presence enables Per-monitor Workspaces through managed Hyprland modules.
-- The plugin's named-workspace bindings are loaded from bindings.lua.
EOF
}

# Keep the reversible layout change separate from Omarchy's plugin registry.
# Restore before disabling a cloned widget so the registry cannot replace an
# unrelated stock workspace entry with a manufactured fallback.
manage_bar_layout() {
  python3 "$SCRIPT_DIR/config/bar-layout.py" "$shell_config" "$bar_state_file" \
    "$plugin_id" "$bar_role" "$1"
}

reload_hyprland() {
  if [[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]]; then
    hyprctl reload
    hyprctl configerrors
  fi
}

enable_plugin() {
  shibumi_is_active || fail "Shibumi must be the active bar before enabling this Shibumi-only widget"
  [[ -d "$HOME/.config/omarchy/plugins/hancore.shibumi.state/lib/presentation" ]] \
    || fail "Shibumi's required presentation library is unavailable"

  omarchy-shell shell rescanPlugins >/dev/null
  wait_for_plugin_discovery
  manage_bar_layout enable
  omarchy plugin enable "$plugin_id"
  write_enabled_toggle
  reload_hyprland

  plugin_is_enabled || fail "Omarchy did not enable $plugin_id"
  plugin_is_configured || fail "Shibumi did not retain the managed workspace widget configuration"
}

disable_plugin() {
  local was_enabled=false
  if plugin_is_enabled; then was_enabled=true; fi
  manage_bar_layout disable
  if [[ "$was_enabled" == true ]]; then
    omarchy plugin disable "$plugin_id"
  fi
  rm -f -- "$toggle_path"
  reload_hyprland
  log "Per-monitor Workspaces is disabled; Shibumi's native workspace widget and Omarchy's numeric workspace rules are restored."
}

backup_feature_data() {
  backup_feature_paths per-monitor-workspaces-remove "$toggle_path" "$state_dir/$plugin_id.lua" \
    "$state_dir/$plugin_id.layouts.lua" "$state_dir/$plugin_id.offer-dismissed" \
    "$shell_config" "$(dirname -- "$bar_state_file")"
}

remove_plugin() {
  plugin_checkout_is_current || fail "the managed pinned checkout is unavailable or modified"
  local backup_dir
  backup_dir="$(backup_feature_data)"
  disable_plugin
  omarchy plugin remove "$plugin_id" --yes
  rm -f -- \
    "$state_dir/$plugin_id.lua" \
    "$state_dir/$plugin_id.layouts.lua" \
    "$state_dir/$plugin_id.offer-dismissed"
  log "Removed Per-monitor Workspaces. Plugin state was backed up to: $backup_dir"
}

case "${1:-}" in
  --disable) disable_plugin; exit 0 ;;
  --remove) remove_plugin; exit 0 ;;
  "") ;;
  *) fail "usage: $0 [--disable|--remove]" ;;
esac

ensure_command git git
ensure_command jq jq

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

if plugin_is_enabled && plugin_is_configured && [[ "$checkout_changed" == false ]]; then
  log "Per-monitor Workspaces is already installed."
  exit 0
fi


enable_plugin
if [[ "$checkout_changed" == true ]]; then
  # Omarchy rescans the plugin catalog, but a running QML Loader may retain a
  # component from the preceding reviewed revision. Restart only on a changed
  # pin so the active Shibumi bar instantiates the new source deterministically.
  omarchy restart shell
fi
log "Installed and activated Per-monitor Workspaces at $plugin_commit."
