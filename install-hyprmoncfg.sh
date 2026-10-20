#!/usr/bin/env bash

# Installs hyprmoncfg: Multi-Monitor Manager for Omarchy at a pinned commit.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

plugin_id="crmne.hyprmoncfg"
plugin_url="https://github.com/crmne/omarchy-hyprmoncfg.git"
plugin_tag="v2.3.5"
plugin_commit="cf05a04a50339510cd1f9d547fb5f80556ae6599"
plugin_dir="$HOME/.config/omarchy/plugins/$plugin_id"
shell_config="$HOME/.config/omarchy/shell.json"

bar_role="brightness"
bar_state_file="${XDG_STATE_HOME:-$HOME/.local/state}/arch-setups/crmne.hyprmoncfg/bar-layout.json"

require_omarchy

fail() {
  log "hyprmoncfg: $*"
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
  checkout_pinned_plugin
}

management_dir="${XDG_STATE_HOME:-$HOME/.local/state}/arch-setups/$plugin_id"
management_marker="$management_dir/managed"
daemon_dropin="$HOME/.config/systemd/user/hyprmoncfgd.service.d/arch-setups.conf"

hyprmon_command() {
  hyprmoncfg --hypr-config "$HOME/.config/hypr/monitors.lua" \
    --monitors-conf "$HOME/.config/hypr/hyprmoncfg-monitors.lua" "$@"
}

ensure_hyprmoncfg() {
  if ! command -v hyprmoncfg >/dev/null 2>&1; then
    local package=hyprmoncfg-bin candidate
    for candidate in hyprmoncfg hyprmoncfg-bin hyprmoncfg-git; do
      if pacman -Q "$candidate" >/dev/null 2>&1; then package="$candidate"; break; fi
    done
    log "Installing required hyprmoncfg through the AUR ($package)..."
    omarchy pkg aur add "$package"
    command -v hyprmoncfg >/dev/null 2>&1 || fail "the AUR package did not provide hyprmoncfg"
  fi
  hyprmoncfg version | python3 -c '
import re, sys
match = re.search(r"(\d+)\.(\d+)\.(\d+)", sys.stdin.read())
raise SystemExit(0 if match and tuple(map(int, match.groups())) >= (1, 18, 3) else 1)
' || fail "hyprmoncfg 1.18.3 or newer is required; update your existing package variant"
}

daemon_settings() {
  cat <<'EOF'
# Managed by arch-setups/install-hyprmoncfg.sh.
[Service]
Environment=HYPRLAND_CONFIG=%h/.config/hypr/monitors.lua
Environment=HYPRMONCFG_MONITORS_CONF=%h/.config/hypr/hyprmoncfg-monitors.lua
EOF
}

runtime_is_current() {
  [[ -f "$management_marker" ]] || return 1
  cmp -s "$daemon_dropin" <(daemon_settings) || return 1
  systemctl --user is-enabled --quiet hyprmoncfgd.service || return 1
  systemctl --user is-active --quiet hyprmoncfgd.service || return 1
  hyprmon_command doctor >/dev/null 2>&1 || return 1
  hyprmon_command status --json | jq -e '.daemon.running == true' >/dev/null
}

start_monitor_management() {
  [[ -f "$HOME/.config/hypr/monitors.lua" ]] || fail "install the managed Hyprland modules first"
  mkdir -p -- "$management_dir" "$(dirname -- "$daemon_dropin")"
  if [[ ! -f "$management_dir/daemon-before.json" ]]; then
    local enabled=false active=false
    systemctl --user is-enabled --quiet hyprmoncfgd.service && enabled=true
    systemctl --user is-active --quiet hyprmoncfgd.service && active=true
    printf '{"enabled":%s,"active":%s}\n' "$enabled" "$active" > "$management_dir/daemon-before.json"
    chmod 600 "$management_dir/daemon-before.json"
  fi
  local settings_changed=false
  if ! cmp -s "$daemon_dropin" <(daemon_settings); then
    if [[ -e "$daemon_dropin" ]]; then
      local backup_dir
      backup_dir="$(mktemp -d "$management_dir/daemon-backup.XXXXXX")"
      cp -a -- "$daemon_dropin" "$backup_dir/arch-setups.conf"
    fi
    daemon_settings > "$daemon_dropin"
    settings_changed=true
    systemctl --user daemon-reload
  fi
  touch "$management_marker"
  systemctl --user enable --now hyprmoncfgd.service
  if [[ "$settings_changed" == true ]]; then systemctl --user restart hyprmoncfgd.service; fi
  local attempt ready=false
  for ((attempt = 0; attempt < 100; attempt++)); do
    if hyprmon_command status --json 2>/dev/null | jq -e '.daemon.running == true' >/dev/null; then
      ready=true
      break
    fi
    sleep 0.05
  done
  [[ "$ready" == true ]] || fail "the hyprmoncfg daemon did not become ready"
  hyprmon_command manage || fail "could not enable monitor management"
  runtime_is_current || fail "the daemon or managed monitor include did not become ready"
}

stop_monitor_management() {
  # Unmanage is also necessary for legacy installations lacking our marker:
  # stopping the daemon alone leaves generated monitor rules loading on reload.
  if command -v hyprmoncfg >/dev/null 2>&1; then
    hyprmon_command unmanage || fail "could not hand monitor management back; the plugin remains enabled"
  elif [[ -f "$management_marker" ]]; then
    fail "hyprmoncfg is missing; restore its binary before disabling management"
  fi
  rm -f -- "$management_marker"
  if [[ -f "$management_dir/daemon-before.json" ]]; then
    if ! jq -e '.active' "$management_dir/daemon-before.json" >/dev/null; then
      systemctl --user stop hyprmoncfgd.service
    fi
    if ! jq -e '.enabled' "$management_dir/daemon-before.json" >/dev/null; then
      systemctl --user disable hyprmoncfgd.service
    fi
  fi
}

# Keep the reversible layout change separate from Omarchy's plugin registry.
# Restore before disabling a cloned widget so the registry cannot replace an
# unrelated stock workspace entry with a manufactured fallback.
manage_bar_layout() {
  python3 "$SCRIPT_DIR/config/bar-layout.py" "$shell_config" "$bar_state_file" \
    "$plugin_id" "$bar_role" "$1"
}

enable_plugin() {
  omarchy-shell shell rescanPlugins >/dev/null
  wait_for_plugin_discovery
  start_monitor_management
  manage_bar_layout enable
  omarchy plugin enable "$plugin_id"
  plugin_is_enabled || fail "Omarchy did not enable $plugin_id"
}

disable_plugin() {
  local was_enabled=false
  if plugin_is_enabled; then was_enabled=true; fi
  stop_monitor_management
  manage_bar_layout disable
  if [[ "$was_enabled" == true ]]; then
    omarchy plugin disable "$plugin_id"
  fi
  log "hyprmoncfg is disabled."
}

backup_feature_data() {
  backup_feature_paths hyprmoncfg-remove "$HOME/.config/hyprmoncfg" "$HOME/.local/state/hyprmoncfg" \
    "$management_dir" "$daemon_dropin" "$shell_config" \
    "$HOME/.config/hypr/hyprmoncfg-monitors.lua" "$HOME/.config/hypr/monitors.lua"
}

remove_plugin() {
  plugin_checkout_is_current || fail "the managed pinned checkout is unavailable or modified"
  local backup_dir
  backup_dir="$(backup_feature_data)"
  disable_plugin
  omarchy plugin remove "$plugin_id" --yes
  rm -f -- "$daemon_dropin" "$management_dir/daemon-before.json"
  systemctl --user daemon-reload
  log "Removed hyprmoncfg. Configuration and state were backed up to: $backup_dir"
}

case "${1:-}" in
  --disable) disable_plugin; exit 0 ;;
  --remove) remove_plugin; exit 0 ;;
  "") ;;
  *) fail "usage: $0 [--disable|--remove]" ;;
esac

ensure_command git git
ensure_command jq jq
ensure_hyprmoncfg

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

if plugin_is_enabled && manage_bar_layout check && runtime_is_current && [[ "$checkout_changed" == false ]]; then
  log "hyprmoncfg is already installed."
  exit 0
fi

enable_plugin
log "Installed and activated hyprmoncfg at $plugin_tag ($plugin_commit)."
